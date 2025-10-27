"""
Tests for ReleaseManager._cleanup_patch_branches() - Branch cleanup.

Focused on testing:
- Successful deletion of local and remote branches
- Branches already deleted (no error)
- Missing branches (skip silently)
- Multiple branches cleanup
- Error handling for deletion failures
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, call
from git.exc import GitCommandError

from half_orm_dev.release_manager import ReleaseManager, ReleaseManagerError


class TestCleanupPatchBranches:
    """Test patch branch cleanup after promote-to rc."""

    @pytest.fixture
    def release_manager_with_git(self, tmp_path):
        """Create ReleaseManager with mocked Git operations."""
        mock_repo = Mock()
        mock_repo.base_dir = str(tmp_path)

        # Create releases/ directory
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        # Mock HGit
        mock_hgit = Mock()
        mock_hgit.branch_exists = Mock(return_value=True)
        mock_hgit.delete_branch = Mock()
        mock_hgit.delete_remote_branch = Mock()

        mock_repo.hgit = mock_hgit

        release_mgr = ReleaseManager(mock_repo)

        return release_mgr, releases_dir, mock_hgit

    def test_successful_cleanup_single_branch(self, release_manager_with_git):
        """Test successful cleanup of single branch."""
        release_mgr, releases_dir, mock_hgit = release_manager_with_git

        # Create stage file with one patch
        stage_file = releases_dir / "1.3.5-stage.txt"
        stage_file.write_text("456-user-auth\n")

        version = "1.3.5"

        deleted = release_mgr._cleanup_patch_branches(version, "1.3.5-stage.txt")

        # Verify local branch deleted
        mock_hgit.delete_branch.assert_called_once_with("ho-patch/456-user-auth", force=True)

        # Verify remote branch deleted
        mock_hgit.delete_remote_branch.assert_called_once_with("ho-patch/456-user-auth")

        # Verify return value
        assert deleted == ["ho-patch/456-user-auth"]

    def test_successful_cleanup_multiple_branches(self, release_manager_with_git):
        """Test successful cleanup of multiple branches."""
        release_mgr, releases_dir, mock_hgit = release_manager_with_git

        # Create stage file with multiple patches
        stage_file = releases_dir / "1.3.5-stage.txt"
        stage_file.write_text("456-user-auth\n789-security\n234-reports\n")

        version = "1.3.5"

        deleted = release_mgr._cleanup_patch_branches(version, "1.3.5-stage.txt")

        # Verify all local branches deleted
        expected_local_calls = [
            call("ho-patch/456-user-auth", force=True),
            call("ho-patch/789-security", force=True),
            call("ho-patch/234-reports", force=True)
        ]
        assert mock_hgit.delete_branch.call_args_list == expected_local_calls

        # Verify all remote branches deleted
        expected_remote_calls = [
            call("ho-patch/456-user-auth"),
            call("ho-patch/789-security"),
            call("ho-patch/234-reports")
        ]
        assert mock_hgit.delete_remote_branch.call_args_list == expected_remote_calls

        # Verify return value
        assert deleted == ["ho-patch/456-user-auth", "ho-patch/789-security", "ho-patch/234-reports"]

    def test_empty_stage_file_no_cleanup(self, release_manager_with_git):
        """Test empty stage file (no branches to cleanup)."""
        release_mgr, releases_dir, mock_hgit = release_manager_with_git

        # Create empty stage file
        stage_file = releases_dir / "1.3.5-stage.txt"
        stage_file.write_text("")

        version = "1.3.5"

        deleted = release_mgr._cleanup_patch_branches(version, "1.3.5-stage.txt")

        # Verify no deletions attempted
        mock_hgit.delete_branch.assert_not_called()
        mock_hgit.delete_remote_branch.assert_not_called()

        # Verify empty list returned
        assert deleted == []

    def test_branch_already_deleted_locally_skips_silently(self, release_manager_with_git):
        """Test skips local branch if already deleted."""
        release_mgr, releases_dir, mock_hgit = release_manager_with_git

        # Create stage file
        stage_file = releases_dir / "1.3.5-stage.txt"
        stage_file.write_text("456-user-auth\n")

        # Mock local branch doesn't exist
        mock_hgit.delete_branch.side_effect = GitCommandError(
            "git branch -D",
            1,
            stderr="branch 'ho-patch/456-user-auth' not found"
        )

        version = "1.3.5"

        deleted = release_mgr._cleanup_patch_branches(version, "1.3.5-stage.txt")

        # Should attempt delete but not raise error
        mock_hgit.delete_branch.assert_called_once()

        # Remote deletion should still be attempted
        mock_hgit.delete_remote_branch.assert_called_once()

        # Still in deleted list (best effort)
        assert deleted == ["ho-patch/456-user-auth"]

    def test_branch_already_deleted_remotely_skips_silently(self, release_manager_with_git):
        """Test skips remote branch if already deleted."""
        release_mgr, releases_dir, mock_hgit = release_manager_with_git

        # Create stage file
        stage_file = releases_dir / "1.3.5-stage.txt"
        stage_file.write_text("456-user-auth\n")

        # Mock remote branch doesn't exist
        mock_hgit.delete_remote_branch.side_effect = GitCommandError(
            "git push --delete",
            1,
            stderr="remote ref does not exist"
        )

        version = "1.3.5"

        deleted = release_mgr._cleanup_patch_branches(version, "1.3.5-stage.txt")

        # Local deletion should succeed
        mock_hgit.delete_branch.assert_called_once()

        # Remote deletion attempted but fails silently
        mock_hgit.delete_remote_branch.assert_called_once()

        # Still in deleted list (best effort)
        assert deleted == ["ho-patch/456-user-auth"]

    def test_partial_cleanup_continues_on_error(self, release_manager_with_git):
        """Test continues cleanup even if one branch fails."""
        release_mgr, releases_dir, mock_hgit = release_manager_with_git

        # Create stage file with multiple patches
        stage_file = releases_dir / "1.3.5-stage.txt"
        stage_file.write_text("456-user-auth\n789-security\n234-reports\n")

        # First branch deletion fails, others succeed
        mock_hgit.delete_branch.side_effect = [
            GitCommandError("git branch", 1, stderr="error"),  # First fails
            None,  # Second succeeds
            None   # Third succeeds
        ]

        version = "1.3.5"

        deleted = release_mgr._cleanup_patch_branches(version, "1.3.5-stage.txt")

        # Should attempt all deletions (best effort)
        assert mock_hgit.delete_branch.call_count == 3
        assert mock_hgit.delete_remote_branch.call_count == 3

        # All branches still reported as deleted (best effort)
        assert len(deleted) == 3

    def test_ignores_comments_and_empty_lines(self, release_manager_with_git):
        """Test ignores comments and empty lines in stage file."""
        release_mgr, releases_dir, mock_hgit = release_manager_with_git

        # Create stage file with comments
        stage_file = releases_dir / "1.3.5-stage.txt"
        stage_file.write_text(
            "# Comment\n"
            "456-user-auth\n"
            "\n"
            "789-security\n"
        )

        version = "1.3.5"

        deleted = release_mgr._cleanup_patch_branches(version, "1.3.5-stage.txt")

        # Should only delete actual patches
        expected_local_calls = [
            call("ho-patch/456-user-auth", force=True),
            call("ho-patch/789-security", force=True)
        ]
        assert mock_hgit.delete_branch.call_args_list == expected_local_calls
        assert deleted == ["ho-patch/456-user-auth", "ho-patch/789-security"]

    def test_cleanup_order_matches_file_order(self, release_manager_with_git):
        """Test branches deleted in same order as stage file."""
        release_mgr, releases_dir, mock_hgit = release_manager_with_git

        # Create stage file with specific order
        stage_file = releases_dir / "1.3.5-stage.txt"
        stage_file.write_text("789-security\n234-reports\n456-user-auth\n")

        version = "1.3.5"

        deleted = release_mgr._cleanup_patch_branches(version, "1.3.5-stage.txt")

        # Verify order preserved
        expected_calls = [
            call("ho-patch/789-security", force=True),
            call("ho-patch/234-reports", force=True),
            call("ho-patch/456-user-auth", force=True)
        ]
        assert mock_hgit.delete_branch.call_args_list == expected_calls
        assert deleted == ["ho-patch/789-security", "ho-patch/234-reports", "ho-patch/456-user-auth"]

    def test_uses_force_delete_for_local_branches(self, release_manager_with_git):
        """Test uses -D (force delete) for local branches."""
        release_mgr, releases_dir, mock_hgit = release_manager_with_git

        # Create stage file
        stage_file = releases_dir / "1.3.5-stage.txt"
        stage_file.write_text("456-user-auth\n")

        version = "1.3.5"

        release_mgr._cleanup_patch_branches(version, "1.3.5-stage.txt")

        # Verify force=True used
        mock_hgit.delete_branch.assert_called_once_with("ho-patch/456-user-auth", force=True)

    def test_uses_read_release_patches_method(self, release_manager_with_git):
        """Test uses existing read_release_patches() method."""
        release_mgr, releases_dir, mock_hgit = release_manager_with_git

        # Create stage file
        stage_file = releases_dir / "1.3.5-stage.txt"
        stage_file.write_text("456-user-auth\n789-security\n")

        # Verify read_release_patches can read it
        patches_from_method = release_mgr.read_release_patches("1.3.5-stage.txt")
        assert patches_from_method == ["456-user-auth", "789-security"]

        # Should use this method internally
        version = "1.3.5"
        deleted = release_mgr._cleanup_patch_branches(version, "1.3.5-stage.txt")

        # Should delete all patches from method
        assert len(deleted) == len(patches_from_method)

    def test_constructs_correct_branch_names(self, release_manager_with_git):
        """Test constructs ho-patch/* branch names correctly."""
        release_mgr, releases_dir, mock_hgit = release_manager_with_git

        # Create stage file with patch ID
        stage_file = releases_dir / "1.3.5-stage.txt"
        stage_file.write_text("456-user-auth\n")

        version = "1.3.5"

        release_mgr._cleanup_patch_branches(version, "1.3.5-stage.txt")

        # Verify correct branch name format
        mock_hgit.delete_branch.assert_called_with("ho-patch/456-user-auth", force=True)
        mock_hgit.delete_remote_branch.assert_called_with("ho-patch/456-user-auth")
