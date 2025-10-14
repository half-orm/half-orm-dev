"""
Tests for ReleaseManager._merge_archived_patches_to_ho_prod() - Code merge.

Focused on testing THE CRITICAL OPERATION where code enters ho-prod:
- Successful merge of archived branches
- Merge conflict handling
- Missing archived branch errors
- Empty stage file (no patches)
- Multiple patches merged in order
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, call
from git.exc import GitCommandError

from half_orm_dev.release_manager import ReleaseManager, ReleaseManagerError


class TestMergeArchivedPatchesToHoProd:
    """Test merging archived patch code into ho-prod."""

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
        mock_hgit.merge = Mock()  # Successful merge by default

        mock_repo.hgit = mock_hgit

        release_mgr = ReleaseManager(mock_repo)

        return release_mgr, releases_dir, mock_hgit

    def test_successful_merge_single_patch(self, release_manager_with_git):
        """Test successful merge of single archived patch."""
        release_mgr, releases_dir, mock_hgit = release_manager_with_git

        # Create stage file with one patch
        stage_file = releases_dir / "1.3.5-stage.txt"
        stage_file.write_text("456-user-auth\n")

        version = "1.3.5"

        patches = release_mgr._merge_archived_patches_to_ho_prod(version, "1.3.5-stage.txt")

        # Verify merge was called
        mock_hgit.merge.assert_called_once_with("ho-release/1.3.5/456-user-auth", squash=True)

        # Verify return value
        assert patches == ["456-user-auth"]

    def test_successful_merge_multiple_patches(self, release_manager_with_git):
        """Test successful merge of multiple archived patches."""
        release_mgr, releases_dir, mock_hgit = release_manager_with_git

        # Create stage file with multiple patches
        stage_file = releases_dir / "1.3.5-stage.txt"
        stage_file.write_text("456-user-auth\n789-security\n234-reports\n")

        version = "1.3.5"

        patches = release_mgr._merge_archived_patches_to_ho_prod(version, "1.3.5-stage.txt")

        # Verify all merges were called in order
        expected_calls = [
            call("ho-release/1.3.5/456-user-auth", squash=True),
            call("ho-release/1.3.5/789-security", squash=True),
            call("ho-release/1.3.5/234-reports", squash=True)
        ]
        assert mock_hgit.merge.call_args_list == expected_calls

        # Verify return value
        assert patches == ["456-user-auth", "789-security", "234-reports"]

    def test_empty_stage_file_no_patches(self, release_manager_with_git):
        """Test empty stage file (no patches to merge)."""
        release_mgr, releases_dir, mock_hgit = release_manager_with_git

        # Create empty stage file
        stage_file = releases_dir / "1.3.5-stage.txt"
        stage_file.write_text("")

        version = "1.3.5"

        patches = release_mgr._merge_archived_patches_to_ho_prod(version, "1.3.5-stage.txt")

        # Verify no merges attempted
        mock_hgit.merge.assert_not_called()

        # Verify empty list returned
        assert patches == []

    def test_merge_conflict_raises_error(self, release_manager_with_git):
        """Test merge conflict raises error with details."""
        release_mgr, releases_dir, mock_hgit = release_manager_with_git

        # Create stage file
        stage_file = releases_dir / "1.3.5-stage.txt"
        stage_file.write_text("456-user-auth\n")

        # Mock merge conflict
        mock_hgit.merge.side_effect = GitCommandError(
            "git merge",
            1,
            stderr="CONFLICT (content): Merge conflict in file.py"
        )

        version = "1.3.5"

        with pytest.raises(ReleaseManagerError, match="Merge conflict|456-user-auth"):
            release_mgr._merge_archived_patches_to_ho_prod(version, "1.3.5-stage.txt")

    def test_missing_archived_branch_raises_error(self, release_manager_with_git):
        """Test error when archived branch doesn't exist."""
        release_mgr, releases_dir, mock_hgit = release_manager_with_git

        # Create stage file
        stage_file = releases_dir / "1.3.5-stage.txt"
        stage_file.write_text("456-user-auth\n")

        # Mock branch doesn't exist
        mock_hgit.branch_exists.return_value = False

        version = "1.3.5"

        with pytest.raises(ReleaseManagerError, match="Archived branch not found|ho-release/1.3.5/456-user-auth"):
            release_mgr._merge_archived_patches_to_ho_prod(version, "1.3.5-stage.txt")

    def test_partial_merge_conflict_stops_at_error(self, release_manager_with_git):
        """Test that merge stops at first conflict."""
        release_mgr, releases_dir, mock_hgit = release_manager_with_git

        # Create stage file with multiple patches
        stage_file = releases_dir / "1.3.5-stage.txt"
        stage_file.write_text("456-user-auth\n789-security\n234-reports\n")

        # First merge succeeds, second fails
        mock_hgit.merge.side_effect = [
            None,  # First merge OK
            GitCommandError("git merge", 1, stderr="CONFLICT"),  # Second fails
        ]

        version = "1.3.5"

        with pytest.raises(ReleaseManagerError):
            release_mgr._merge_archived_patches_to_ho_prod(version, "1.3.5-stage.txt")

        # Verify only 2 merges attempted (stopped at error)
        assert mock_hgit.merge.call_count == 2

    def test_ignores_comments_and_empty_lines(self, release_manager_with_git):
        """Test that comments and empty lines in stage file are ignored."""
        release_mgr, releases_dir, mock_hgit = release_manager_with_git

        # Create stage file with comments and empty lines
        stage_file = releases_dir / "1.3.5-stage.txt"
        stage_file.write_text(
            "# This is a comment\n"
            "456-user-auth\n"
            "\n"
            "# Another comment\n"
            "789-security\n"
            "\n"
        )

        version = "1.3.5"

        patches = release_mgr._merge_archived_patches_to_ho_prod(version, "1.3.5-stage.txt")

        # Should only merge actual patches (not comments)
        expected_calls = [
            call("ho-release/1.3.5/456-user-auth", squash=True),
            call("ho-release/1.3.5/789-security", squash=True)
        ]
        assert mock_hgit.merge.call_args_list == expected_calls
        assert patches == ["456-user-auth", "789-security"]

    def test_preserves_patch_order(self, release_manager_with_git):
        """Test that patches are merged in exact order from stage file."""
        release_mgr, releases_dir, mock_hgit = release_manager_with_git

        # Create stage file with specific order
        stage_file = releases_dir / "1.3.5-stage.txt"
        stage_file.write_text("789-security\n234-reports\n456-user-auth\n")

        version = "1.3.5"

        patches = release_mgr._merge_archived_patches_to_ho_prod(version, "1.3.5-stage.txt")

        # Verify order preserved
        expected_calls = [
            call("ho-release/1.3.5/789-security", squash=True),
            call("ho-release/1.3.5/234-reports", squash=True),
            call("ho-release/1.3.5/456-user-auth", squash=True)
        ]
        assert mock_hgit.merge.call_args_list == expected_calls
        assert patches == ["789-security", "234-reports", "456-user-auth"]

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
        patches = release_mgr._merge_archived_patches_to_ho_prod(version, "1.3.5-stage.txt")

        assert patches == patches_from_method

    def test_error_message_includes_patch_id(self, release_manager_with_git):
        """Test error message includes which patch caused the problem."""
        release_mgr, releases_dir, mock_hgit = release_manager_with_git

        # Create stage file
        stage_file = releases_dir / "1.3.5-stage.txt"
        stage_file.write_text("456-user-auth\n")

        # Mock merge conflict
        mock_hgit.merge.side_effect = GitCommandError("git merge", 1)

        version = "1.3.5"

        with pytest.raises(ReleaseManagerError) as exc_info:
            release_mgr._merge_archived_patches_to_ho_prod(version, "1.3.5-stage.txt")

        error_msg = str(exc_info.value)
        assert "456-user-auth" in error_msg
