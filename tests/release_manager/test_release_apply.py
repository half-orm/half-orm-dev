"""
Tests for ReleaseManager.apply_release() method.

Tests the integration testing workflow that applies ALL patches
(candidates + staged) for complete release validation.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from half_orm_dev.release_manager import ReleaseManager, ReleaseManagerError
from half_orm_dev.release_file import ReleaseFile
from half_orm_dev import modules  # Import for patching


@pytest.fixture
def release_manager_for_apply(tmp_path):
    """Create ReleaseManager configured for apply_release tests."""
    # Create directories
    releases_dir = tmp_path / ".hop" / "releases"
    releases_dir.mkdir(parents=True)
    patches_dir = tmp_path / "Patches"
    patches_dir.mkdir()
    model_dir = tmp_path / ".hop" / "model"
    model_dir.mkdir(parents=True)

    # Create schema file
    schema_file = model_dir / "schema-1.0.0.sql"
    schema_file.write_text("CREATE TABLE test (id SERIAL);")
    schema_symlink = model_dir / "schema.sql"
    schema_symlink.symlink_to("schema-1.0.0.sql")

    # Mock repo
    mock_repo = Mock()
    mock_repo.base_dir = str(tmp_path)
    mock_repo.releases_dir = str(releases_dir)
    mock_repo.model_dir = str(model_dir)

    # Mock hgit (git operations)
    mock_hgit = Mock()
    mock_hgit.branch = "ho-release/1.1.0"
    mock_repo.hgit = mock_hgit

    # Mock patch_manager
    mock_patch_manager = Mock()
    mock_patch_manager.apply_patch_files = Mock(return_value=["01_test.sql"])
    mock_repo.patch_manager = mock_patch_manager

    # Mock model
    mock_model = Mock()
    mock_repo.model = mock_model

    # Mock restore_database_from_schema
    mock_repo.restore_database_from_schema = Mock()

    # Create release manager
    rel_mgr = ReleaseManager(mock_repo)

    return rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir


class TestGetAllReleasePatchesForTesting:
    """Test get_all_release_patches_for_testing helper method."""

    def test_returns_all_patches_including_candidates(self, release_manager_for_apply):
        """Test that both candidates and staged patches are returned."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir = release_manager_for_apply

        # Create TOML file with candidates and staged
        release_file = ReleaseFile("1.1.0", releases_dir)
        release_file.create_empty()
        release_file.add_patch("123-candidate-patch")
        release_file.add_patch("456-staged-patch")
        release_file.move_to_staged("456-staged-patch", "commit456")

        # Get all patches for testing
        patches = rel_mgr.get_all_release_patches_for_testing()

        # Both should be included
        assert "123-candidate-patch" in patches
        assert "456-staged-patch" in patches
        assert len(patches) == 2

    def test_includes_rc_patches(self, release_manager_for_apply):
        """Test that RC patches are included."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir = release_manager_for_apply

        # Create RC file (format: patch_id:merge_commit)
        rc_file = releases_dir / "1.1.0-rc1.txt"
        rc_file.write_text("100-rc-patch:abc123\n101-rc-patch2:def456\n")

        # Create TOML file with candidates
        release_file = ReleaseFile("1.1.0", releases_dir)
        release_file.create_empty()
        release_file.add_patch("200-candidate")

        # Get all patches
        patches = rel_mgr.get_all_release_patches_for_testing()

        # All should be included
        assert patches == ["100-rc-patch", "101-rc-patch2", "200-candidate"]

    def test_empty_when_no_release(self, release_manager_for_apply):
        """Test returns empty list when no development release."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir = release_manager_for_apply

        # No release files created

        patches = rel_mgr.get_all_release_patches_for_testing()

        assert patches == []


class TestApplyRelease:
    """Test apply_release method."""

    def test_apply_release_success_with_tests(self, release_manager_for_apply):
        """Test successful apply_release with passing tests."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir = release_manager_for_apply

        # Create release file
        release_file = ReleaseFile("1.1.0", releases_dir)
        release_file.create_empty()
        release_file.add_patch("123-feature")
        release_file.add_patch("456-bugfix")

        # Mock subprocess for pytest
        with patch('subprocess.run') as mock_subprocess_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "3 passed"
            mock_result.stderr = ""
            mock_subprocess_run.return_value = mock_result

            # Mock modules.generate
            with patch('half_orm_dev.modules.generate'):
                result = rel_mgr.apply_release(run_tests=True)

        assert result['status'] == 'success'
        assert result['version'] == '1.1.0'
        assert result['tests_passed'] is True
        assert len(result['patches_applied']) == 2
        assert "123-feature" in result['patches_applied']
        assert "456-bugfix" in result['patches_applied']

    def test_apply_release_without_tests(self, release_manager_for_apply):
        """Test apply_release with tests skipped."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir = release_manager_for_apply

        # Create release file
        release_file = ReleaseFile("1.1.0", releases_dir)
        release_file.create_empty()
        release_file.add_patch("123-feature")

        # Mock modules.generate
        with patch('half_orm_dev.modules.generate'):
            result = rel_mgr.apply_release(run_tests=False)

        assert result['status'] == 'success'
        assert result['tests_passed'] is None
        assert result['test_output'] is None

    def test_apply_release_tests_fail(self, release_manager_for_apply):
        """Test apply_release when tests fail."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir = release_manager_for_apply

        # Create release file
        release_file = ReleaseFile("1.1.0", releases_dir)
        release_file.create_empty()
        release_file.add_patch("123-feature")

        # Mock subprocess for pytest failure
        with patch('subprocess.run') as mock_subprocess_run:
            mock_result = Mock()
            mock_result.returncode = 1
            mock_result.stdout = "1 failed, 2 passed"
            mock_result.stderr = "AssertionError"
            mock_subprocess_run.return_value = mock_result

            with patch('half_orm_dev.modules.generate'):
                result = rel_mgr.apply_release(run_tests=True)

        assert result['status'] == 'failed'
        assert result['tests_passed'] is False
        assert "1 failed" in result['test_output']

    def test_apply_release_wrong_branch(self, release_manager_for_apply):
        """Test apply_release fails when not on release branch."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir = release_manager_for_apply

        # Create release file
        release_file = ReleaseFile("1.1.0", releases_dir)
        release_file.create_empty()

        # Set wrong branch
        mock_repo.hgit.branch = "main"

        with pytest.raises(ReleaseManagerError, match="Must be on release branch"):
            rel_mgr.apply_release()

    def test_apply_release_no_development_release(self, release_manager_for_apply):
        """Test apply_release fails when no development release."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir = release_manager_for_apply

        # No release file created

        with pytest.raises(ReleaseManagerError, match="No development release found"):
            rel_mgr.apply_release()

    def test_apply_release_applies_all_patches_in_order(self, release_manager_for_apply):
        """Test that patches are applied in correct order."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir = release_manager_for_apply

        # Create RC file first (format: patch_id:merge_commit)
        rc_file = releases_dir / "1.1.0-rc1.txt"
        rc_file.write_text("001-first:abc123\n")

        # Create TOML with candidates and staged
        release_file = ReleaseFile("1.1.0", releases_dir)
        release_file.create_empty()
        release_file.add_patch("002-candidate")
        release_file.add_patch("003-staged")
        release_file.move_to_staged("003-staged", "commit003")

        # Track apply order
        apply_order = []

        def track_apply(patch_id, model):
            apply_order.append(patch_id)
            return [f"{patch_id}.sql"]

        mock_repo.patch_manager.apply_patch_files.side_effect = track_apply

        with patch('half_orm_dev.modules.generate'):
            rel_mgr.apply_release(run_tests=False)

        # Verify order: RC first, then TOML in order
        assert apply_order == ["001-first", "002-candidate", "003-staged"]

    def test_apply_release_restores_db_on_failure(self, release_manager_for_apply):
        """Test that database is restored on failure."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir = release_manager_for_apply

        # Create release file
        release_file = ReleaseFile("1.1.0", releases_dir)
        release_file.create_empty()
        release_file.add_patch("123-feature")

        # Make apply_patch_files fail
        mock_repo.patch_manager.apply_patch_files.side_effect = Exception("SQL error")

        with pytest.raises(ReleaseManagerError, match="Release apply failed"):
            rel_mgr.apply_release(run_tests=False)

        # Verify restore was called twice (initial + cleanup)
        assert mock_repo.restore_database_from_schema.call_count >= 2

    def test_apply_release_pytest_not_found(self, release_manager_for_apply):
        """Test apply_release handles missing pytest gracefully."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir = release_manager_for_apply

        # Create release file
        release_file = ReleaseFile("1.1.0", releases_dir)
        release_file.create_empty()
        release_file.add_patch("123-feature")

        # Mock subprocess to raise FileNotFoundError
        with patch('subprocess.run') as mock_subprocess_run:
            mock_subprocess_run.side_effect = FileNotFoundError("pytest not found")

            with patch('half_orm_dev.modules.generate'):
                result = rel_mgr.apply_release(run_tests=True)

        assert result['status'] == 'success'
        assert result['tests_passed'] is None
        assert "pytest not found" in result['test_output']


class TestApplyReleaseTemporaryBranch:
    """Test temporary branch creation and cleanup."""

    def test_apply_release_creates_temporary_branch(self, release_manager_for_apply):
        """Test that apply_release creates ho-validate/release-X.Y.Z branch."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir = release_manager_for_apply

        # Create release file
        release_file = ReleaseFile("1.1.0", releases_dir)
        release_file.create_empty()
        release_file.add_patch("123-feature")

        with patch('half_orm_dev.modules.generate'):
            rel_mgr.apply_release(run_tests=False)

        # Verify branch creation
        mock_repo.hgit.create_branch.assert_called_once_with("ho-validate/release-1.1.0")
        mock_repo.hgit.checkout.assert_any_call("ho-validate/release-1.1.0")

    def test_apply_release_switches_back_to_original_branch(self, release_manager_for_apply):
        """Test that apply_release switches back to original branch after completion."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir = release_manager_for_apply

        # Create release file
        release_file = ReleaseFile("1.1.0", releases_dir)
        release_file.create_empty()
        release_file.add_patch("123-feature")

        with patch('half_orm_dev.modules.generate'):
            rel_mgr.apply_release(run_tests=False)

        # Verify switch back to original branch (last checkout call)
        checkout_calls = mock_repo.hgit.checkout.call_args_list
        assert checkout_calls[-1][0][0] == "ho-release/1.1.0"

    def test_apply_release_deletes_temporary_branch(self, release_manager_for_apply):
        """Test that apply_release deletes temporary branch after completion."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir = release_manager_for_apply

        # Create release file
        release_file = ReleaseFile("1.1.0", releases_dir)
        release_file.create_empty()
        release_file.add_patch("123-feature")

        with patch('half_orm_dev.modules.generate'):
            rel_mgr.apply_release(run_tests=False)

        # Verify branch deletion (should be called at least once for cleanup)
        delete_calls = [call[0][0] for call in mock_repo.hgit.delete_branch.call_args_list]
        assert "ho-validate/release-1.1.0" in delete_calls

    def test_apply_release_cleans_up_on_error(self, release_manager_for_apply):
        """Test that temporary branch is cleaned up even on error."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir = release_manager_for_apply

        # Create release file
        release_file = ReleaseFile("1.1.0", releases_dir)
        release_file.create_empty()
        release_file.add_patch("123-feature")

        # Make apply_patch_files fail
        mock_repo.patch_manager.apply_patch_files.side_effect = Exception("SQL error")

        with pytest.raises(ReleaseManagerError):
            rel_mgr.apply_release(run_tests=False)

        # Verify cleanup was attempted
        checkout_calls = [call[0][0] for call in mock_repo.hgit.checkout.call_args_list]
        assert "ho-release/1.1.0" in checkout_calls  # Should try to switch back

    def test_apply_release_deletes_existing_validate_branch(self, release_manager_for_apply):
        """Test that existing validate branch is deleted before creating new one."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir = release_manager_for_apply

        # Create release file
        release_file = ReleaseFile("1.1.0", releases_dir)
        release_file.create_empty()
        release_file.add_patch("123-feature")

        with patch('half_orm_dev.modules.generate'):
            rel_mgr.apply_release(run_tests=False)

        # First delete call should be to clean up any existing branch
        first_delete = mock_repo.hgit.delete_branch.call_args_list[0]
        assert first_delete[0][0] == "ho-validate/release-1.1.0"


class TestApplyReleaseCandidateMerge:
    """Test merging of candidate patch branches."""

    def test_apply_release_merges_candidate_branches(self, release_manager_for_apply):
        """Test that candidate patch branches are merged into temp branch."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir = release_manager_for_apply

        # Create release file with candidates and staged
        release_file = ReleaseFile("1.1.0", releases_dir)
        release_file.create_empty()
        release_file.add_patch("123-candidate")
        release_file.add_patch("456-staged")
        release_file.move_to_staged("456-staged", "commit456")

        with patch('half_orm_dev.modules.generate'):
            result = rel_mgr.apply_release(run_tests=False)

        # Verify only candidate branches were merged (staged already on release branch)
        merge_calls = [call[0][0] for call in mock_repo.hgit.merge.call_args_list]
        assert "ho-patch/123-candidate" in merge_calls
        assert "ho-patch/456-staged" not in merge_calls

        # Verify result includes merged candidates
        assert result['candidates_merged'] == ["123-candidate"]

    def test_apply_release_no_merge_for_staged_only(self, release_manager_for_apply):
        """Test that no merge happens when only staged patches exist."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir = release_manager_for_apply

        # Create release file with only staged patches
        release_file = ReleaseFile("1.1.0", releases_dir)
        release_file.create_empty()
        release_file.add_patch("456-staged")
        release_file.move_to_staged("456-staged", "commit456")

        with patch('half_orm_dev.modules.generate'):
            result = rel_mgr.apply_release(run_tests=False)

        # Verify no merge was called
        mock_repo.hgit.merge.assert_not_called()
        assert result['candidates_merged'] == []

    def test_apply_release_merge_failure_raises_error(self, release_manager_for_apply):
        """Test that merge failure raises appropriate error."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir = release_manager_for_apply

        # Create release file with candidate
        release_file = ReleaseFile("1.1.0", releases_dir)
        release_file.create_empty()
        release_file.add_patch("123-conflict")

        # Make merge fail
        mock_repo.hgit.merge.side_effect = Exception("Merge conflict")

        with pytest.raises(ReleaseManagerError, match="Failed to merge candidate branch"):
            rel_mgr.apply_release(run_tests=False)

    def test_apply_release_merges_multiple_candidates_in_order(self, release_manager_for_apply):
        """Test that multiple candidates are merged in TOML order."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir = release_manager_for_apply

        # Create release file with multiple candidates
        release_file = ReleaseFile("1.1.0", releases_dir)
        release_file.create_empty()
        release_file.add_patch("001-first")
        release_file.add_patch("002-second")
        release_file.add_patch("003-third")

        merge_order = []
        def track_merge(branch):
            merge_order.append(branch)

        mock_repo.hgit.merge.side_effect = track_merge

        with patch('half_orm_dev.modules.generate'):
            result = rel_mgr.apply_release(run_tests=False)

        # Verify merge order matches TOML order
        assert merge_order == [
            "ho-patch/001-first",
            "ho-patch/002-second",
            "ho-patch/003-third"
        ]
        assert result['candidates_merged'] == ["001-first", "002-second", "003-third"]


class TestApplyReleaseVsPatchApply:
    """Test the difference between release apply and patch apply context."""

    def test_release_apply_includes_candidates(self, release_manager_for_apply):
        """Verify release apply includes candidates that patch apply excludes."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir = release_manager_for_apply

        # Create TOML with both statuses
        release_file = ReleaseFile("1.1.0", releases_dir)
        release_file.create_empty()
        release_file.add_patch("123-candidate")
        release_file.add_patch("456-staged")
        release_file.move_to_staged("456-staged", "commit456")

        # get_all_release_context_patches (used by patch apply) - only staged
        context_patches = rel_mgr.get_all_release_context_patches()
        assert "123-candidate" not in context_patches
        assert "456-staged" in context_patches

        # get_all_release_patches_for_testing (used by release apply) - all
        testing_patches = rel_mgr.get_all_release_patches_for_testing()
        assert "123-candidate" in testing_patches
        assert "456-staged" in testing_patches
