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
    releases_dir.mkdir()

    # Create Patches/ directory
    patches_dir = tmp_path / "Patches"
    patches_dir.mkdir()

    # Mock Repo
    mock_repo = Mock()
    mock_repo.base_dir = str(tmp_path)

    # Mock database
    mock_database = Mock()
    mock_repo.database = mock_database

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
        result = rel_mgr.add_patch_to_release("001-first", "0.1.0")

        # Should rename patch branch to archived name
        mock_hgit_complete.rename_branch.assert_called_once_with(
            "ho-patch/001-first",
            "ho-archive/0.1.0/001-first"
        )

        # Should push archived branch
        assert call("ho-archive/0.1.0/001-first") in mock_hgit_complete.push_branch.call_args_list

        # Should checkout release branch
        checkout_calls = [c for c in mock_hgit_complete.checkout.call_args_list
                         if c == call("ho-release/0.1.0")]
        assert len(checkout_calls) > 0

        # Should merge archived patch into release branch
        mock_hgit_complete.merge.assert_called_once_with(
            "ho-archive/0.1.0/001-first",
            no_ff=True,
            message="Merge patch 001-first into release 0.1.0"
        )

        # Should update stage file
        assert "001-first" in stage_file.read_text()

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
        rel_mgr.add_patch_to_release("001-first", "0.1.0")

        # Add second patch
        rel_mgr.add_patch_to_release("002-second", "0.1.0")

        # Both should be merged
        merge_calls = mock_hgit_complete.merge.call_args_list
        assert len(merge_calls) == 2
        assert merge_calls[0] == call(
            "ho-archive/0.1.0/001-first",
            no_ff=True,
            message="Merge patch 001-first into release 0.1.0"
        )
        assert merge_calls[1] == call(
            "ho-archive/0.1.0/002-second",
            no_ff=True,
            message="Merge patch 002-second into release 0.1.0"
        )

        # Stage file should contain both
        content = stage_file.read_text()
        assert "001-first" in content
        assert "002-second" in content

    def test_promote_rc_tags_release_branch(self, release_manager, mock_hgit_complete):
        """Test that 'promote rc' creates tag on release branch."""
        rel_mgr, repo, temp_dir, releases_dir = release_manager
        repo.hgit = mock_hgit_complete

        # Setup: create stage file
        stage_file = releases_dir / "0.1.0-stage.txt"
        stage_file.write_text("001-first\n")

        # Promote to RC
        result = rel_mgr.promote_to_rc("0.1.0")

        # Should checkout release branch
        assert call("ho-release/0.1.0") in mock_hgit_complete.checkout.call_args_list

        # Should create tag on release branch
        mock_hgit_complete.create_tag.assert_called_once_with('v0.1.0-rc1', 'Release Candidate 0.1.0')

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
        result = rel_mgr.promote_to_prod("0.1.0")

        # Should checkout ho-prod
        assert call("ho-prod") in mock_hgit_complete.checkout.call_args_list

        # Should merge release branch into ho-prod (fast-forward)
        mock_hgit_complete.merge.assert_called_once_with(
            "ho-release/0.1.0",
            ff_only=True,
            message="Merge release 0.1.0 into production"
        )

        # Should create prod tag on ho-prod
        mock_hgit_complete.create_tag.assert_called_once_with('v0.1.0', 'Production release 0.1.0')

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
        stage_file.write_text("001-first\n002-second\n")

        # Promote to prod
        rel_mgr.promote_to_prod()

        # Should delete patch branches (local and remote)
        delete_branch_calls = mock_hgit_complete.delete_branch.call_args_list
        assert call("ho-archive/0.1.0/001-first", force=True) in delete_branch_calls
        assert call("ho-archive/0.1.0/002-second", force=True) in delete_branch_calls

        delete_remote_calls = mock_hgit_complete.delete_remote_branch.call_args_list
        assert call("ho-archive/0.1.0/001-first") in delete_remote_calls
        assert call("ho-archive/0.1.0/002-second") in delete_remote_calls

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
        rel_mgr.promote_to_rc("0.1.0")
        assert mock_hgit_complete.create_tag.call_args == call('v0.1.0-rc1', 'Release Candidate 0.1.0')

        # Step 5: Promote to prod
        rel_mgr.promote_to_prod("0.1.0")

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
