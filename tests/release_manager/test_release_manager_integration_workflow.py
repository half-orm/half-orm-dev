"""
Tests for the new release integration workflow with release branches.

This module tests the enhanced workflow where:
1. `release new` creates a release branch (ho-release/{version})
2. `patch add` merges patches into the release branch
3. `promote rc` tags the release branch
4. `promote prod` merges the release branch into ho-prod

This solves the problem of patch dependencies by ensuring patches
can see each other's changes during development.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call
from git.exc import GitCommandError

from half_orm_dev.release_manager import ReleaseManager, ReleaseManagerError
from half_orm_dev.repo import Repo


@pytest.fixture
def release_manager(tmp_path):
    """Create ReleaseManager with mocked Repo for testing."""
    # Create releases/ directory
    releases_dir = tmp_path / "releases"
    releases_dir.mkdir(exist_ok=True)

    # Create Patches/ directory
    patches_dir = tmp_path / "Patches"
    patches_dir.mkdir()

    # Mock Repo
    mock_repo = Mock()
    mock_repo.base_dir = str(tmp_path)

    # Mock database
    mock_database = Mock()
    mock_repo.database = mock_database

    # Mock patch_manager for data file generation
    mock_patch_manager = Mock()
    mock_patch_manager._collect_data_files_from_patches = Mock(return_value=[])
    mock_patch_manager._sync_release_files_to_ho_prod = Mock()
    mock_repo.patch_manager = mock_patch_manager

    # Create ReleaseManager
    rel_mgr = ReleaseManager(mock_repo)

    return rel_mgr, mock_repo, tmp_path, releases_dir


class TestReleaseIntegrationWorkflow:
    """Test the new workflow with release branches for patch integration."""

    def test_new_release_creates_branch(self, release_manager, mock_hgit_complete):
        """Test that 'release new' creates a release branch."""
        rel_mgr, repo, temp_dir, releases_dir = release_manager
        repo.hgit = mock_hgit_complete

        # Mock version calculation
        rel_mgr._calculate_next_version = Mock(return_value="0.1.0")

        # Create new release
        result = rel_mgr.new_release("minor")

        # Should create branch ho-release/0.1.0 from ho-prod
        mock_hgit_complete.create_branch.assert_called_once_with(
            "ho-release/0.1.0",
            from_branch="ho-prod"
        )

        # Should push the branch
        assert call("ho-release/0.1.0") in mock_hgit_complete.push_branch.call_args_list

        # Should create empty stage file
        stage_file = releases_dir / "0.1.0-stage.txt"
        assert stage_file.exists()

        # Should return version
        assert result['version'] == "0.1.0"
        assert result['branch'] == "ho-release/0.1.0"

    def test_patch_add_merges_into_release_branch(self, release_manager, mock_hgit_complete):
        """Test that 'patch add' merges the patch into the release branch."""
        rel_mgr, repo, temp_dir, releases_dir = release_manager
        repo.hgit = mock_hgit_complete

        # Setup: create stage file
        stage_file = releases_dir / "0.1.0-stage.txt"
        stage_file.write_text("")

        # Mock: patch branch exists
        mock_hgit_complete.branch_exists.return_value = True

        # Add patch to release
        result = rel_mgr.add_patch_to_release("1-first", "0.1.0")

        # Should rename patch branch to archived name
        mock_hgit_complete.delete_branch.assert_called_once_with(
            "ho-patch/1-first", force=True
        )

        # Should checkout release branch
        checkout_calls = [c for c in mock_hgit_complete.checkout.call_args_list
                         if c == call("ho-release/0.1.0")]
        assert len(checkout_calls) > 0

        # Should merge archived patch into release branch
        mock_hgit_complete.merge.assert_called_once_with(
            "ho-patch/1-first",
            no_ff=True,
            message="[HOP] Merge patch #1-first into release %0.1.0"
        )

        # Should update stage file
        assert "1-first" in stage_file.read_text()

        # Should push release branch
        assert call("ho-release/0.1.0") in mock_hgit_complete.push_branch.call_args_list

    def test_patch_add_handles_merge_conflicts(self, release_manager, mock_hgit_complete):
        """Test that merge conflicts during 'patch add' are handled gracefully."""
        rel_mgr, repo, temp_dir, releases_dir = release_manager
        repo.hgit = mock_hgit_complete

        # Setup: create stage file
        stage_file = releases_dir / "0.1.0-stage.txt"
        stage_file.write_text("")

        # Mock: merge fails with conflict
        mock_hgit_complete.branch_exists.return_value = True
        mock_hgit_complete.merge.side_effect = GitCommandError(
            "git merge", 1, stderr="CONFLICT (content): Merge conflict in file.txt"
        )

        # Should raise error with helpful message
        with pytest.raises(ReleaseManagerError, match="Merge conflict"):
            rel_mgr.add_patch_to_release("002-second", "0.1.0")

        # Should still be on release branch for conflict resolution
        assert call("ho-release/0.1.0") in mock_hgit_complete.checkout.call_args_list

    def test_multiple_patches_integrated_in_order(self, release_manager, mock_hgit_complete):
        """Test that multiple patches are merged in sequence."""
        rel_mgr, repo, temp_dir, releases_dir = release_manager
        repo.hgit = mock_hgit_complete

        # Setup: create stage file
        stage_file = releases_dir / "0.1.0-stage.txt"
        stage_file.write_text("")

        mock_hgit_complete.branch_exists.return_value = True

        # Add first patch
        rel_mgr.add_patch_to_release("1-first", "0.1.0")

        # Add second patch
        rel_mgr.add_patch_to_release("2-second", "0.1.0")

        # Both should be merged
        merge_calls = mock_hgit_complete.merge.call_args_list
        assert len(merge_calls) == 2
        assert merge_calls[0] == call(
            "ho-patch/1-first",
            no_ff=True,
            message="[HOP] Merge patch #1-first into release %0.1.0"
        )
        assert merge_calls[1] == call(
            "ho-patch/2-second",
            no_ff=True,
            message="[HOP] Merge patch #2-second into release %0.1.0"
        )

        # Stage file should contain both
        content = stage_file.read_text()
        assert "1-first" in content
        assert "2-second" in content

    def test_promote_rc_tags_release_branch(self, release_manager, mock_hgit_complete):
        """Test that 'promote rc' creates tag on release branch."""
        rel_mgr, repo, temp_dir, releases_dir = release_manager
        repo.hgit = mock_hgit_complete

        # Setup: create stage file
        stage_file = releases_dir / "0.1.0-stage.txt"
        stage_file.write_text("001-first\n")

        # Promote to RC
        result = rel_mgr.promote_to_rc()

        # Should checkout release branch
        assert call("ho-release/0.1.0") in mock_hgit_complete.checkout.call_args_list

        # Should create tag on release branch
        mock_hgit_complete.create_tag.assert_called_once_with('v0.1.0-rc1', 'Release Candidate %0.1.0')

        # Should push tag
        mock_hgit_complete.push_tag.assert_called_once_with('v0.1.0-rc1')

        # Should rename stage file to rc
        rc_file = releases_dir / "0.1.0-rc1.txt"
        assert rc_file.exists()
        assert stage_file.exists()

    def test_promote_prod_merges_release_into_ho_prod(self, release_manager, mock_hgit_complete):
        """Test that 'promote prod' merges release branch into ho-prod."""
        rel_mgr, repo, temp_dir, releases_dir = release_manager
        repo.hgit = mock_hgit_complete

        # Setup: create rc file (with proper rc number)
        rc_file = releases_dir / "0.1.0-rc1.txt"
        rc_file.write_text("001-first\n002-second\n")

        # Setup: create stage file (automatically created after promote_to_rc)
        stage_file = releases_dir / "0.1.0-stage.txt"
        stage_file.write_text("001-first\n002-second\n")

        # Promote to prod
        result = rel_mgr.promote_to_prod()

        # Should checkout ho-prod
        assert call("ho-prod") in mock_hgit_complete.checkout.call_args_list

        # Should merge release branch into ho-prod (fast-forward)
        mock_hgit_complete.merge.assert_called_once_with(
            "ho-release/0.1.0",
            ff_only=True,
            message="[HOP] Merge release %0.1.0 into production"
        )

        # Should create prod tag on ho-prod
        mock_hgit_complete.create_tag.assert_called_once_with('v0.1.0', 'Production release %0.1.0')

        # Should push ho-prod and tag
        assert call("ho-prod") in mock_hgit_complete.push_branch.call_args_list
        mock_hgit_complete.push_tag.assert_called_once_with("v0.1.0")

        # Should rename rc file to prod
        prod_file = releases_dir / "0.1.0.txt"
        assert prod_file.exists()
        assert not stage_file.exists()

    def test_promote_prod_cleans_up_branches(self, release_manager, mock_hgit_complete):
        """Test that 'promote prod' deletes patch and release branches."""
        rel_mgr, repo, temp_dir, releases_dir = release_manager
        repo.hgit = mock_hgit_complete

        # Setup: create rc file with patches
        stage_file = releases_dir / "0.1.0-stage.txt"
        stage_file.write_text("1-first\n2-second\n")

        # Promote to prod
        rel_mgr.promote_to_prod()

        # Should delete patch branches (local and remote)
        delete_branch_calls = mock_hgit_complete.delete_branch.call_args_list
        delete_remote_calls = mock_hgit_complete.delete_remote_branch.call_args_list

        # Should delete release branch
        assert call("ho-release/0.1.0", force=True) in delete_branch_calls
        assert call("ho-release/0.1.0") in delete_remote_calls

    def test_patch_dependency_workflow(self, release_manager, mock_hgit_complete):
        """
        Integration test: Full workflow with dependent patches.

        This demonstrates the key benefit of the new workflow:
        patch 002 can depend on 001 because they're merged into
        the same release branch.
        """
        rel_mgr, repo, temp_dir, releases_dir = release_manager
        repo.hgit = mock_hgit_complete

        # Mock version calculation
        rel_mgr._calculate_next_version = Mock(return_value="0.1.0")
        mock_hgit_complete.branch_exists.return_value = True

        # Step 1: Create new release
        rel_mgr.new_release("minor")
        assert mock_hgit_complete.create_branch.call_args == call(
            "ho-release/0.1.0", from_branch="ho-prod"
        )

        # Step 2: Add patch 001 (creates table A)
        rel_mgr.add_patch_to_release("001-create-table-a", "0.1.0")

        # Verify: 001 is merged into release branch
        merge_calls = mock_hgit_complete.merge.call_args_list
        assert len(merge_calls) == 1
        assert "001-create-table-a" in str(merge_calls[0])

        # Step 3: Add patch 002 (references table A - depends on 001)
        rel_mgr.add_patch_to_release("002-add-foreign-key-to-a", "0.1.0")

        # Verify: 002 is merged into release branch (which already has 001)
        assert len(mock_hgit_complete.merge.call_args_list) == 2

        # Key insight: At this point, ho-release/0.1.0 contains both patches
        # Developer can test 002 with 001's changes present

        # Step 4: Promote to RC
        rel_mgr.promote_to_rc()
        assert mock_hgit_complete.create_tag.call_args == call('v0.1.0-rc1', 'Release Candidate %0.1.0')

        # Step 5: Promote to prod
        rel_mgr.promote_to_prod()

        # Verify: Release branch merged into ho-prod
        # Filter for merge of release branch itself (not patch branches)
        merge_to_prod = [c for c in mock_hgit_complete.merge.call_args_list
                        if c[0][0] == "ho-release/0.1.0"]  # Exact match, not patch subdirectory
        assert len(merge_to_prod) == 1

    def test_cannot_add_patch_to_nonexistent_release(self, release_manager):
        """Test that adding patch to non-existent release fails."""
        rel_mgr, repo, temp_dir, releases_dir = release_manager

        # No stage file exists
        with pytest.raises(ReleaseManagerError, match="Release 0.1.0.*not found"):
            rel_mgr.add_patch_to_release("001-first", "0.1.0")

    def test_cannot_add_nonexistent_patch_to_release(self, release_manager, mock_hgit_complete):
        """Test that adding non-existent patch fails."""
        rel_mgr, repo, temp_dir, releases_dir = release_manager
        repo.hgit = mock_hgit_complete

        # Create stage file
        stage_file = releases_dir / "0.1.0-stage.txt"
        stage_file.write_text("")

        # Mock: patch branch doesn't exist
        mock_hgit_complete.branch_exists.return_value = False

        with pytest.raises(ReleaseManagerError, match="Patch branch.*not found"):
            rel_mgr.add_patch_to_release("999-missing", "0.1.0")

    def test_returns_to_original_branch_after_operations(self, release_manager, mock_hgit_complete):
        """Test that operations return to original branch when done."""
        rel_mgr, repo, temp_dir, releases_dir = release_manager
        repo.hgit = mock_hgit_complete

        # Setup
        stage_file = releases_dir / "0.1.0-stage.txt"
        stage_file.write_text("")
        mock_hgit_complete.branch_exists.return_value = True
        mock_hgit_complete.branch = "ho-patch/003-my-work"

        # Add patch to release
        rel_mgr.add_patch_to_release("001-first", "0.1.0")

        # Should return to original branch
        checkout_calls = mock_hgit_complete.checkout.call_args_list
        # Last checkout should be to original branch
        assert checkout_calls[-1] == call("ho-patch/003-my-work")


class TestApplyReleasePatches:
    """Test the _apply_release_patches() method for correct patch application order."""

    def test_applies_patches_in_correct_order(self, release_manager):
        """Test that patches are applied in order: restore → RC patches → stage patches."""
        rel_mgr, repo, temp_dir, releases_dir = release_manager

        # Setup: create RC files and stage file
        rc1_file = releases_dir / "0.1.0-rc1.txt"
        rc1_file.write_text("001-first\n002-second\n")

        rc2_file = releases_dir / "0.1.0-rc2.txt"
        rc2_file.write_text("003-third\n")

        stage_file = releases_dir / "0.1.0-stage.txt"
        stage_file.write_text("004-fourth\n005-fifth\n")

        # Mock patch_manager
        mock_patch_manager = Mock()
        repo.patch_manager = mock_patch_manager
        repo.model = Mock()

        # Execute
        rel_mgr._apply_release_patches("0.1.0")

        # Verify restore was called first
        repo.restore_database_from_schema.assert_called_once()

        # Verify patches applied in correct order
        apply_calls = mock_patch_manager.apply_patch_files.call_args_list
        assert len(apply_calls) == 5

        # RC1 patches first
        assert apply_calls[0] == call("001-first", repo.model)
        assert apply_calls[1] == call("002-second", repo.model)

        # RC2 patches second
        assert apply_calls[2] == call("003-third", repo.model)

        # Stage patches last
        assert apply_calls[3] == call("004-fourth", repo.model)
        assert apply_calls[4] == call("005-fifth", repo.model)

    def test_restore_called_before_any_patch(self, release_manager):
        """Test that database restore happens before any patch application."""
        rel_mgr, repo, temp_dir, releases_dir = release_manager

        # Setup: create stage file only
        stage_file = releases_dir / "0.1.0-stage.txt"
        stage_file.write_text("001-first\n")

        # Track call order
        call_order = []

        def track_restore():
            call_order.append('restore')

        def track_apply(*args):
            call_order.append(f'apply:{args[0]}')

        repo.restore_database_from_schema = track_restore
        mock_patch_manager = Mock()
        mock_patch_manager.apply_patch_files.side_effect = track_apply
        repo.patch_manager = mock_patch_manager
        repo.model = Mock()

        # Execute
        rel_mgr._apply_release_patches("0.1.0")

        # Verify order
        assert call_order[0] == 'restore'
        assert call_order[1] == 'apply:001-first'

    def test_no_rc_files_applies_only_stage(self, release_manager):
        """Test that when no RC files exist, only stage patches are applied."""
        rel_mgr, repo, temp_dir, releases_dir = release_manager

        # Setup: create only stage file
        stage_file = releases_dir / "0.1.0-stage.txt"
        stage_file.write_text("001-first\n002-second\n")

        mock_patch_manager = Mock()
        repo.patch_manager = mock_patch_manager
        repo.model = Mock()

        # Execute
        rel_mgr._apply_release_patches("0.1.0")

        # Verify only stage patches applied
        apply_calls = mock_patch_manager.apply_patch_files.call_args_list
        assert len(apply_calls) == 2
        assert apply_calls[0] == call("001-first", repo.model)
        assert apply_calls[1] == call("002-second", repo.model)

    def test_empty_stage_file_applies_only_rc_patches(self, release_manager):
        """Test that empty stage file still applies RC patches."""
        rel_mgr, repo, temp_dir, releases_dir = release_manager

        # Setup: create RC file and empty stage
        rc1_file = releases_dir / "0.1.0-rc1.txt"
        rc1_file.write_text("001-first\n")

        stage_file = releases_dir / "0.1.0-stage.txt"
        stage_file.write_text("")

        mock_patch_manager = Mock()
        repo.patch_manager = mock_patch_manager
        repo.model = Mock()

        # Execute
        rel_mgr._apply_release_patches("0.1.0")

        # Verify only RC patches applied
        apply_calls = mock_patch_manager.apply_patch_files.call_args_list
        assert len(apply_calls) == 1
        assert apply_calls[0] == call("001-first", repo.model)

    def test_multiple_rc_files_applied_in_order(self, release_manager):
        """Test that RC files are applied in numerical order (rc1, rc2, rc3...)."""
        rel_mgr, repo, temp_dir, releases_dir = release_manager

        # Setup: create RC files out of order
        rc3_file = releases_dir / "0.1.0-rc3.txt"
        rc3_file.write_text("003-third\n")

        rc1_file = releases_dir / "0.1.0-rc1.txt"
        rc1_file.write_text("001-first\n")

        rc2_file = releases_dir / "0.1.0-rc2.txt"
        rc2_file.write_text("002-second\n")

        stage_file = releases_dir / "0.1.0-stage.txt"
        stage_file.write_text("")

        mock_patch_manager = Mock()
        repo.patch_manager = mock_patch_manager
        repo.model = Mock()

        # Execute
        rel_mgr._apply_release_patches("0.1.0")

        # Verify RC files applied in correct order
        apply_calls = mock_patch_manager.apply_patch_files.call_args_list
        assert len(apply_calls) == 3
        assert apply_calls[0] == call("001-first", repo.model)
        assert apply_calls[1] == call("002-second", repo.model)
        assert apply_calls[2] == call("003-third", repo.model)

    def test_handles_comments_and_empty_lines(self, release_manager):
        """Test that comments and empty lines in release files are ignored."""
        rel_mgr, repo, temp_dir, releases_dir = release_manager

        # Setup: create stage file with comments and empty lines
        stage_file = releases_dir / "0.1.0-stage.txt"
        stage_file.write_text("# This is a comment\n001-first\n\n002-second\n# Another comment\n")

        mock_patch_manager = Mock()
        repo.patch_manager = mock_patch_manager
        repo.model = Mock()

        # Execute
        rel_mgr._apply_release_patches("0.1.0")

        # Verify only actual patches applied
        apply_calls = mock_patch_manager.apply_patch_files.call_args_list
        assert len(apply_calls) == 2
        assert apply_calls[0] == call("001-first", repo.model)
        assert apply_calls[1] == call("002-second", repo.model)

    def test_no_patches_still_restores_database(self, release_manager):
        """Test that database is restored even when there are no patches."""
        rel_mgr, repo, temp_dir, releases_dir = release_manager

        # Setup: create empty stage file
        stage_file = releases_dir / "0.1.0-stage.txt"
        stage_file.write_text("")

        mock_patch_manager = Mock()
        repo.patch_manager = mock_patch_manager
        repo.model = Mock()

        # Execute
        rel_mgr._apply_release_patches("0.1.0")

        # Verify restore was still called
        repo.restore_database_from_schema.assert_called_once()

        # Verify no patches applied
        mock_patch_manager.apply_patch_files.assert_not_called()
