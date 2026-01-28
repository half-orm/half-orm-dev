"""
Test candidate migration during promote_to_prod.

This module tests the automatic migration of candidate patches when promoting
a release to production. The workflow:
1. User runs promote_to_prod with candidates in TOML
2. System prompts to migrate to X.Y.Z+1
3. If accepted, creates new release and rebases patches
4. Tracks rebased commit SHAs in metadata
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call
from datetime import datetime, timezone

from half_orm_dev.release_manager import ReleaseManager, ReleaseManagerError
from half_orm_dev.release_file import ReleaseFile


@pytest.fixture
def release_manager_with_candidates(tmp_path):
    """Create ReleaseManager with mocked Repo and candidates."""
    # Create directory structure
    releases_dir = tmp_path / ".hop" / "releases"
    releases_dir.mkdir(parents=True, exist_ok=True)

    model_dir = tmp_path / ".hop" / "model"
    model_dir.mkdir(parents=True, exist_ok=True)

    # Create mock repo
    mock_repo = Mock()
    mock_repo.base_dir = str(tmp_path)
    mock_repo.releases_dir = str(releases_dir)
    mock_repo.model_dir = str(model_dir)

    # Create release manager
    rel_mgr = ReleaseManager(mock_repo)

    return rel_mgr, mock_repo, tmp_path, releases_dir


class TestCandidateMigrationPrompt:
    """Test prompting user for candidate migration."""

    def test_promote_prod_with_candidates_prompts_migration(self, release_manager_with_candidates):
        """Test that promote_to_prod prompts for migration when candidates exist."""
        rel_mgr, repo, tmp_path, releases_dir = release_manager_with_candidates

        # Setup: create TOML with staged and candidates
        release_file = ReleaseFile("0.17.1", releases_dir)
        release_file.create_empty()
        release_file.add_patch("42-feature")
        release_file.add_patch("43-bugfix")
        release_file.move_to_staged("42-feature", "commit42")
        # 43-bugfix stays as candidate

        # Mock HGit
        mock_hgit = Mock()
        mock_hgit.get_repo.return_value = Mock()
        repo.hgit = mock_hgit

        # Mock user input: reject migration
        with patch('builtins.input', return_value='n'):
            with pytest.raises(ReleaseManagerError, match="Promotion cancelled"):
                rel_mgr.promote_to_prod()

    def test_promote_prod_without_candidates_proceeds(self, release_manager_with_candidates):
        """Test that promote_to_prod proceeds normally without candidates."""
        rel_mgr, repo, tmp_path, releases_dir = release_manager_with_candidates

        # Setup: create TOML with only staged patches
        release_file = ReleaseFile("0.17.1", releases_dir)
        release_file.create_empty()
        release_file.add_patch("42-feature")
        release_file.move_to_staged("42-feature", "commit42")

        # Mock HGit and other dependencies
        mock_hgit = Mock()
        mock_hgit.get_repo.return_value = Mock()
        repo.hgit = mock_hgit
        repo.patch_manager = Mock()
        repo.patch_manager._collect_data_files_from_patches = Mock(return_value=[])  # No data files
        repo.database = Mock()
        repo.database._generate_schema_sql = Mock()
        repo.restore_database_from_schema = Mock()
        repo.model = Mock()

        # Should not prompt for migration
        result = rel_mgr.promote_to_prod()

        # Should complete successfully
        assert result['version'] == "0.17.1"
        assert result.get('migrated_to') is None


class TestCandidateMigration:
    """Test candidate migration workflow."""

    @patch('builtins.input', return_value='y')
    @patch('builtins.print')
    def test_migration_creates_new_release(self, mock_print, mock_input, release_manager_with_candidates):
        """Test that migration creates X.Y.Z+1 release."""
        rel_mgr, repo, tmp_path, releases_dir = release_manager_with_candidates

        # Setup: TOML with candidates
        release_file = ReleaseFile("0.17.1", releases_dir)
        release_file.create_empty()
        release_file.add_patch("42-feature")
        release_file.add_patch("43-bugfix")
        # Both stay as candidates

        # Mock HGit
        mock_hgit = Mock()
        mock_hgit.get_repo.return_value.head.commit.hexsha = "a1b2c3d4e5f6"
        mock_hgit.get_repo.return_value.branches = []
        repo.hgit = mock_hgit

        # Mock other dependencies
        repo.patch_manager = Mock()
        repo.patch_manager.get_data_files = Mock(return_value=[])
        repo.database = Mock()
        repo.database._generate_schema_sql = Mock()
        repo.restore_database_from_schema = Mock()
        repo.model = Mock()

        # Execute
        result = rel_mgr.promote_to_prod()

        # Should create new release branch
        assert call("-b", "ho-release/0.17.2") in mock_hgit.checkout.call_args_list

        # Should push new release branch
        assert call("ho-release/0.17.2", set_upstream=True) in mock_hgit.push_branch.call_args_list

        # Should return migration info
        assert result['migrated_to'] == "0.17.2"
        assert set(result['migrated_patches']) == {"42-feature", "43-bugfix"}

    @patch('builtins.input', return_value='y')
    @patch('builtins.print')
    def test_migration_rebases_patch_branches(self, mock_print, mock_input, release_manager_with_candidates):
        """Test that migration rebases patch branches onto new release."""
        rel_mgr, repo, tmp_path, releases_dir = release_manager_with_candidates

        # Setup: TOML with candidates
        release_file = ReleaseFile("0.17.1", releases_dir)
        release_file.create_empty()
        release_file.add_patch("42-feature")
        release_file.add_patch("43-bugfix")

        # Mock HGit with commit SHAs
        mock_hgit = Mock()
        mock_repo = Mock()
        mock_repo.head.commit.hexsha = "a1b2c3d4e5f6789012345678"
        mock_repo.branches = []
        mock_hgit.get_repo.return_value = mock_repo
        repo.hgit = mock_hgit

        # Mock other dependencies
        repo.patch_manager = Mock()
        repo.patch_manager.get_data_files = Mock(return_value=[])
        repo.database = Mock()
        repo.database._generate_schema_sql = Mock()
        repo.restore_database_from_schema = Mock()
        repo.model = Mock()

        # Execute
        result = rel_mgr.promote_to_prod()

        # Should rebase each patch
        rebase_calls = [c for c in mock_hgit.rebase.call_args_list if c[0][0] == "--onto"]
        assert len(rebase_calls) == 2  # One for each candidate

        # Should rebase onto new release from old release
        assert call("--onto", "ho-release/0.17.2", "ho-release/0.17.1", "ho-patch/42-feature") in mock_hgit.rebase.call_args_list
        assert call("--onto", "ho-release/0.17.2", "ho-release/0.17.1", "ho-patch/43-bugfix") in mock_hgit.rebase.call_args_list

        # Should force-push rebased branches
        assert call("ho-patch/42-feature", force=True) in mock_hgit.push_branch.call_args_list
        assert call("ho-patch/43-bugfix", force=True) in mock_hgit.push_branch.call_args_list

    @patch('builtins.input', return_value='y')
    @patch('builtins.print')
    def test_migration_tracks_rebased_commits(self, mock_print, mock_input, release_manager_with_candidates):
        """Test that migration stores rebased commit SHAs in metadata."""
        rel_mgr, repo, tmp_path, releases_dir = release_manager_with_candidates

        # Setup: TOML with candidates
        release_file = ReleaseFile("0.17.1", releases_dir)
        release_file.create_empty()
        release_file.add_patch("42-feature")
        release_file.add_patch("43-bugfix")

        # Mock HGit with different SHAs for each checkout
        mock_hgit = Mock()
        mock_commit = Mock()
        mock_commit.hexsha = "a1b2c3d4e5f6789012345678"
        mock_head = Mock()
        mock_head.commit = mock_commit
        mock_repo = Mock()
        mock_repo.head = mock_head
        mock_repo.branches = []
        mock_hgit.get_repo.return_value = mock_repo
        repo.hgit = mock_hgit

        # Mock other dependencies
        repo.patch_manager = Mock()
        repo.patch_manager._collect_data_files_from_patches = Mock(return_value=[])  # No data files
        repo.database = Mock()
        repo.database._generate_schema_sql = Mock()
        repo.restore_database_from_schema = Mock()
        repo.model = Mock()

        # Execute
        rel_mgr.promote_to_prod()

        # Check new TOML has metadata
        new_release_file = ReleaseFile("0.17.2", releases_dir)
        metadata = new_release_file.get_metadata()

        assert metadata['created_from_promotion'] is True
        assert metadata['source_version'] == "0.17.1"
        assert 'migrated_at' in metadata
        assert 'rebased_commits' in metadata

        # Should track both patches
        rebased = metadata['rebased_commits']
        assert '42-feature' in rebased
        assert '43-bugfix' in rebased

    @patch('builtins.input', return_value='y')
    @patch('builtins.print')
    def test_migration_deletes_old_toml(self, mock_print, mock_input, release_manager_with_candidates):
        """Test that migration deletes source TOML file."""
        rel_mgr, repo, tmp_path, releases_dir = release_manager_with_candidates

        # Setup: TOML with candidates
        release_file = ReleaseFile("0.17.1", releases_dir)
        release_file.create_empty()
        release_file.add_patch("42-feature")

        # Mock HGit
        mock_hgit = Mock()
        mock_repo = Mock()
        mock_repo.head.commit.hexsha = "a1b2c3d4e5f6789012345678"
        mock_repo.branches = []
        mock_hgit.get_repo.return_value = mock_repo
        repo.hgit = mock_hgit

        # Mock other dependencies
        repo.patch_manager = Mock()
        repo.patch_manager.get_data_files = Mock(return_value=[])
        repo.database = Mock()
        repo.database._generate_schema_sql = Mock()
        repo.restore_database_from_schema = Mock()
        repo.model = Mock()

        # Old TOML should exist before
        assert release_file.file_path.exists()

        # Execute
        rel_mgr.promote_to_prod()

        # Old TOML should be deleted
        assert not release_file.file_path.exists()

        # New TOML should exist
        new_release_file = ReleaseFile("0.17.2", releases_dir)
        assert new_release_file.file_path.exists()


class TestMigrationVersionCalculation:
    """Test version calculation for migration."""

    @patch('builtins.input', return_value='y')
    @patch('builtins.print')
    def test_migration_increments_patch_version(self, mock_print, mock_input, release_manager_with_candidates):
        """Test that migration correctly increments patch version."""
        rel_mgr, repo, tmp_path, releases_dir = release_manager_with_candidates

        # Test cases for version increment
        test_cases = [
            ("0.17.1", "0.17.2"),
            ("0.17.9", "0.17.10"),
            ("1.0.0", "1.0.1"),
            ("2.15.99", "2.15.100"),
        ]

        for source_version, expected_target in test_cases:
            # Setup
            release_file = ReleaseFile(source_version, releases_dir)
            release_file.create_empty()
            release_file.add_patch("test-patch")

            # Mock HGit
            mock_hgit = Mock()
            mock_repo = Mock()
            mock_repo.head.commit.hexsha = "a1b2c3d4e5f6789012345678"
            mock_repo.branches = []
            mock_hgit.get_repo.return_value = mock_repo
            repo.hgit = mock_hgit

            # Mock other dependencies
            repo.patch_manager = Mock()
            repo.patch_manager.get_data_files = Mock(return_value=[])
            repo.database = Mock()
            repo.database._generate_schema_sql = Mock()
            repo.restore_database_from_schema = Mock()
            repo.model = Mock()

            # Execute
            result = rel_mgr.promote_to_prod()

            # Verify version calculation
            assert result['migrated_to'] == expected_target

            # Cleanup for next iteration
            if release_file.file_path.exists():
                release_file.file_path.unlink()
            new_release_file = ReleaseFile(expected_target, releases_dir)
            if new_release_file.file_path.exists():
                new_release_file.file_path.unlink()


class TestMigrationErrorHandling:
    """Test error handling during migration."""

    @patch('builtins.input', return_value='y')
    @patch('builtins.print')
    def test_migration_handles_rebase_conflict(self, mock_print, mock_input, release_manager_with_candidates):
        """Test that rebase conflicts are handled gracefully."""
        rel_mgr, repo, tmp_path, releases_dir = release_manager_with_candidates

        # Setup: TOML with candidates
        release_file = ReleaseFile("0.17.1", releases_dir)
        release_file.create_empty()
        release_file.add_patch("42-feature")

        # Mock HGit to fail on rebase
        mock_hgit = Mock()
        mock_repo = Mock()
        mock_repo.branches = []
        mock_hgit.get_repo.return_value = mock_repo
        mock_hgit.rebase.side_effect = Exception("CONFLICT: Merge conflict in file.sql")
        repo.hgit = mock_hgit

        # Mock other dependencies
        repo.patch_manager = Mock()
        repo.patch_manager.get_data_files = Mock(return_value=[])
        repo.database = Mock()
        repo.database._generate_schema_sql = Mock()
        repo.restore_database_from_schema = Mock()
        repo.model = Mock()

        # Should raise error with helpful message
        with pytest.raises(ReleaseManagerError, match="Failed to rebase patch 42-feature"):
            rel_mgr.promote_to_prod()

        # Should abort rebase
        mock_hgit.rebase.assert_any_call("--abort")


class TestMetadataFormat:
    """Test metadata format in TOML file."""

    def test_metadata_has_correct_structure(self, release_manager_with_candidates):
        """Test that metadata has all required fields."""
        rel_mgr, repo, tmp_path, releases_dir = release_manager_with_candidates

        # Manually create metadata as migration would
        release_file = ReleaseFile("0.17.2", releases_dir)
        release_file.create_empty()
        release_file.add_patch("42-feature")
        release_file.add_patch("43-bugfix")

        metadata = {
            "created_from_promotion": True,
            "source_version": "0.17.1",
            "migrated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "rebased_commits": {
                "42-feature": "a1b2c3d4",
                "43-bugfix": "f6e5d4c3"
            }
        }
        release_file.set_metadata(metadata)

        # Read back and verify
        read_metadata = release_file.get_metadata()

        assert read_metadata['created_from_promotion'] is True
        assert read_metadata['source_version'] == "0.17.1"
        assert 'migrated_at' in read_metadata
        assert isinstance(read_metadata['rebased_commits'], dict)
        assert len(read_metadata['rebased_commits']) == 2

    def test_sha_format_is_8_chars(self, release_manager_with_candidates):
        """Test that SHA tracking uses 8-character format."""
        rel_mgr, repo, tmp_path, releases_dir = release_manager_with_candidates

        release_file = ReleaseFile("0.17.2", releases_dir)
        release_file.create_empty()
        release_file.add_patch("42-feature")

        metadata = {
            "created_from_promotion": True,
            "source_version": "0.17.1",
            "migrated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "rebased_commits": {
                "42-feature": "a1b2c3d4"
            }
        }
        release_file.set_metadata(metadata)

        # Verify SHA length
        read_metadata = release_file.get_metadata()
        for patch_id, sha in read_metadata['rebased_commits'].items():
            assert len(sha) == 8, f"SHA for {patch_id} should be 8 chars, got {len(sha)}"
