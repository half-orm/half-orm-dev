"""
Tests for the new release integration workflow with release branches.

This module tests the enhanced workflow where:
1. `release create` creates a release branch (ho-release/{version})
2. `patch merge` merges patches into the release branch
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
from half_orm_dev.release_file import ReleaseFile


def create_patches_file(releases_dir: Path, version: str, patches: list = None, as_staged: bool = True, as_candidates: bool = False):
    """
    Helper to create TOML patches file for testing.

    Args:
        releases_dir: Path to releases directory
        version: Version string (e.g., "0.1.0")
        patches: List of patch IDs, or None for empty file
        as_staged: If True, patches will be marked as staged (default)
        as_candidates: If True, patches will be marked as candidates
    """
    release_file = ReleaseFile(version, releases_dir)
    release_file.create_empty()

    if patches:
        for i, patch_id in enumerate(patches):
            release_file.add_patch(patch_id)
            if as_staged and not as_candidates:
                release_file.move_to_staged(patch_id, f"commit{i:03d}")
            # If as_candidates is True, leave as candidates

    return release_file.file_path


@pytest.fixture
def release_manager(tmp_path):
    """Create ReleaseManager with mocked Repo for testing."""
    # Create releases/ directory
    releases_dir = tmp_path / ".hop" / "releases"
    releases_dir.mkdir(parents=True, exist_ok=True)

    # Create Patches/ directory
    patches_dir = tmp_path / "Patches"
    patches_dir.mkdir()

    # Create model/ directory with schema-0.0.1.sql and symlink (required for create_release)
    model_dir = tmp_path / ".hop" / "model"
    model_dir.mkdir(parents=True)
    schema_versioned = model_dir / "schema-0.0.1.sql"
    schema_versioned.write_text("-- schema for version 0.0.1")
    schema_symlink = model_dir / "schema.sql"
    schema_symlink.symlink_to("schema-0.0.1.sql")

    # Mock Repo
    mock_repo = Mock()
    mock_repo.base_dir = str(tmp_path)
    mock_repo.releases_dir = str(releases_dir)
    mock_repo.model_dir = str(model_dir)

    # Mock commit_and_sync_to_active_branches
    mock_repo.commit_and_sync_to_active_branches = Mock(return_value={
        'commit_hash': 'abc123',
        'pushed_branch': 'ho-prod',
        'sync_result': {'synced_branches': [], 'skipped_branches': [], 'errors': []}
    })

    # Mock database
    mock_database = Mock()
    mock_repo.database = mock_database

    # Mock patch_manager for data file generation
    mock_patch_manager = Mock()
    mock_patch_manager._collect_data_files_from_patches = Mock(return_value=[])
    mock_patch_manager._sync_release_files_to_ho_prod = Mock()
    mock_repo.patch_manager = mock_patch_manager

    # Mock get_release_schema_path to return non-existent path
    # This forces the old workflow (restore from schema.sql + apply patches)
    non_existent_path = tmp_path / ".hop" / "model" / "release-nonexistent.sql"
    mock_repo.get_release_schema_path = Mock(return_value=non_existent_path)

    # Create ReleaseManager
    rel_mgr = ReleaseManager(mock_repo)

    return rel_mgr, mock_repo, tmp_path, releases_dir


class TestReleaseIntegrationWorkflow:
    """Test the new workflow with release branches for patch integration."""

    def test_new_release_creates_branch(self, release_manager, mock_hgit_complete):
        """Test that 'release create' creates a release branch."""
        rel_mgr, repo, temp_dir, releases_dir = release_manager
        repo.hgit = mock_hgit_complete

        # Mock version calculation
        rel_mgr._calculate_next_version = Mock(return_value="0.1.0")

        # Create new release
        result = rel_mgr.create_release("minor")

        # Should create branch ho-release/0.1.0 from ho-prod
        mock_hgit_complete.create_branch.assert_called_once_with(
            "ho-release/0.1.0",
            from_branch="ho-prod"
        )

        # Should push the branch
        assert call("ho-release/0.1.0") in mock_hgit_complete.push_branch.call_args_list

        # Should create empty TOML patches file
        patches_file = releases_dir / "0.1.0-patches.toml"
        assert patches_file.exists()

        # Should return version
        assert result['version'] == "0.1.0"
        assert result['branch'] == "ho-release/0.1.0"

    def test_promote_rc_tags_release_branch(self, release_manager, mock_hgit_complete):
        """Test that 'promote rc' creates tag on release branch."""
        rel_mgr, repo, temp_dir, releases_dir = release_manager
        repo.hgit = mock_hgit_complete

        # Setup: create TOML patches file


        create_patches_file(releases_dir, "0.1.0", ["001-first"])

        # Promote to RC
        result = rel_mgr.promote_to_rc()

        # Should checkout release branch
        assert call("ho-release/0.1.0") in mock_hgit_complete.checkout.call_args_list

        # Should create tag on release branch
        mock_hgit_complete.create_tag.assert_called_once_with('v0.1.0-rc1', 'Release Candidate %0.1.0')

        # Should push tag
        mock_hgit_complete.push_tag.assert_called_once_with('v0.1.0-rc1')

        # Should create RC snapshot and keep TOML patches file
        rc_file = releases_dir / "0.1.0-rc1.txt"
        assert rc_file.exists()
        patches_file = releases_dir / "0.1.0-patches.toml"
        assert patches_file.exists()

    def test_promote_prod_merges_release_into_ho_prod(self, release_manager, mock_hgit_complete):
        """Test that 'promote prod' merges release branch into ho-prod."""
        rel_mgr, repo, temp_dir, releases_dir = release_manager
        repo.hgit = mock_hgit_complete

        # Setup: create rc file (with proper rc number)
        # Format: patch_id:merge_commit
        rc_file = releases_dir / "0.1.0-rc1.txt"
        rc_file.write_text("001-first:abc123\n002-second:def456\n")

        # Setup: create TOML patches file


        create_patches_file(releases_dir, "0.1.0", ["001-first", "002-second"])

        # Promote to prod
        result = rel_mgr.promote_to_prod()

        # Should checkout ho-prod
        assert call("ho-prod") in mock_hgit_complete.checkout.call_args_list

        # Should merge release branch into ho-prod (fast-forward)
        merge_args = [call for call in mock_hgit_complete.merge.call_args_list]
        assert merge_args == [
            call('ho-release/0.1.0', ff_only=True, message='[HOP] Merge release %0.1.0 into production'),
            call('ho-promote/0.1.0-prod', message='[HOP] Promote release %0.1.0 to production')]

        # Should create prod tag on ho-prod
        mock_hgit_complete.create_tag.assert_called_once_with('v0.1.0', 'Production release %0.1.0')

        # Push is handled by commit_and_sync_to_active_branches
        mock_hgit_complete.push_tag.assert_called_once_with("v0.1.0")

        # Should create production file
        prod_file = releases_dir / "0.1.0.txt"
        assert prod_file.exists()
        # TOML patches file should be deleted after promote_to_prod
        patches_file = releases_dir / "0.1.0-patches.toml"
        assert not patches_file.exists()

    def test_promote_prod_cleans_up_branches(self, release_manager, mock_hgit_complete):
        """Test that 'promote prod' deletes patch and release branches."""
        rel_mgr, repo, temp_dir, releases_dir = release_manager
        repo.hgit = mock_hgit_complete

        # Setup: create TOML patches file


        create_patches_file(releases_dir, "0.1.0", ["1-first", "2-second"])

        # Promote to prod
        rel_mgr.promote_to_prod()

        # Should delete patch branches (local and remote)
        delete_branch_calls = mock_hgit_complete.delete_branch.call_args_list
        delete_remote_calls = mock_hgit_complete.delete_remote_branch.call_args_list

        # Should delete release branch
        assert call("ho-release/0.1.0", force=True) in delete_branch_calls
        assert call("ho-release/0.1.0") in delete_remote_calls


class TestApplyReleasePatches:
    """Test the _apply_release_patches() method for correct patch application order."""

    def test_applies_patches_in_correct_order(self, release_manager):
        """Test that patches are applied in order: restore → RC patches → TOML patches."""
        rel_mgr, repo, temp_dir, releases_dir = release_manager

        # Setup: create RC files and TOML patches file
        # Format: patch_id:merge_commit
        rc1_file = releases_dir / "0.1.0-rc1.txt"
        rc1_file.write_text("001-first:abc123\n002-second:def456\n")

        rc2_file = releases_dir / "0.1.0-rc2.txt"
        rc2_file.write_text("003-third:ghi789\n")

        create_patches_file(releases_dir, "0.1.0", ["004-fourth", "005-fifth"])

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

        # TOML patches last
        assert apply_calls[3] == call("004-fourth", repo.model)
        assert apply_calls[4] == call("005-fifth", repo.model)

    def test_restore_called_before_any_patch(self, release_manager):
        """Test that database restore happens before any patch application."""
        rel_mgr, repo, temp_dir, releases_dir = release_manager

        # Setup: create stage file only
        create_patches_file(releases_dir, "0.1.0", ["001-first"])

        # Track call order
        call_order = []

        def track_restore(**kwargs):
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
        """Test that when no RC files exist, only TOML patches are applied."""
        rel_mgr, repo, temp_dir, releases_dir = release_manager

        # Setup: create only TOML patches file
        create_patches_file(releases_dir, "0.1.0", ["001-first", "002-second"])

        mock_patch_manager = Mock()
        repo.patch_manager = mock_patch_manager
        repo.model = Mock()

        # Execute
        rel_mgr._apply_release_patches("0.1.0")

        # Verify only TOML patches applied
        apply_calls = mock_patch_manager.apply_patch_files.call_args_list
        assert len(apply_calls) == 2
        assert apply_calls[0] == call("001-first", repo.model)
        assert apply_calls[1] == call("002-second", repo.model)

    def test_empty_stage_file_applies_only_rc_patches(self, release_manager):
        """Test that empty TOML file still applies RC patches."""
        rel_mgr, repo, temp_dir, releases_dir = release_manager

        # Setup: create RC file and empty TOML
        # Format: patch_id:merge_commit
        rc1_file = releases_dir / "0.1.0-rc1.txt"
        rc1_file.write_text("001-first:abc123\n")

        create_patches_file(releases_dir, "0.1.0")  # Empty TOML file

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
        # Format: patch_id:merge_commit
        rc3_file = releases_dir / "0.1.0-rc3.txt"
        rc3_file.write_text("003-third:ghi789\n")

        rc1_file = releases_dir / "0.1.0-rc1.txt"
        rc1_file.write_text("001-first:abc123\n")

        rc2_file = releases_dir / "0.1.0-rc2.txt"
        rc2_file.write_text("002-second:def456\n")

        create_patches_file(releases_dir, "0.1.0")  # Empty TOML file

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
        """Test that TOML format properly handles patches (no comments in TOML patch IDs)."""
        rel_mgr, repo, temp_dir, releases_dir = release_manager

        # Setup: create TOML patches file (TOML doesn't have inline comments)
        create_patches_file(releases_dir, "0.1.0", ["001-first", "002-second"])

        mock_patch_manager = Mock()
        repo.patch_manager = mock_patch_manager
        repo.model = Mock()

        # Execute
        rel_mgr._apply_release_patches("0.1.0")

        # Verify patches applied
        apply_calls = mock_patch_manager.apply_patch_files.call_args_list
        assert len(apply_calls) == 2
        assert apply_calls[0] == call("001-first", repo.model)
        assert apply_calls[1] == call("002-second", repo.model)

    def test_no_patches_still_restores_database(self, release_manager):
        """Test that database is restored even when there are no patches."""
        rel_mgr, repo, temp_dir, releases_dir = release_manager

        # Setup: create empty TOML patches file
        create_patches_file(releases_dir, "0.1.0")

        mock_patch_manager = Mock()
        repo.patch_manager = mock_patch_manager
        repo.model = Mock()

        # Execute
        rel_mgr._apply_release_patches("0.1.0")

        # Verify restore was still called
        repo.restore_database_from_schema.assert_called_once()

        # Verify no patches applied
        mock_patch_manager.apply_patch_files.assert_not_called()
