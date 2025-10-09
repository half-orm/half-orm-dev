"""
Tests for ReleaseManager._send_resync_notifications() method.

Focused on testing:
- Notification sent to all active patch branches except current
- Empty commit with proper message format
- Non-blocking behavior (continues on failure)
- Returns list of successfully notified branches
- Handles checkout failures gracefully
- Handles commit/push failures gracefully
- No notification sent to current patch branch
"""

import pytest
from unittest.mock import Mock, call
from git.exc import GitCommandError

from half_orm_dev.release_manager import ReleaseManager


class TestSendResyncNotifications:
    """Test _send_resync_notifications() method."""

    @pytest.fixture
    def release_manager_with_mock_hgit(self, tmp_path):
        """Create ReleaseManager with mocked HGit and patch branches."""
        mock_repo = Mock()
        mock_repo.base_dir = str(tmp_path)

        # Create releases/ directory
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        # Mock HGit
        mock_hgit = Mock()
        mock_hgit.branch = "ho-prod"  # Current branch
        mock_repo.hgit = mock_hgit

        release_mgr = ReleaseManager(mock_repo)

        return release_mgr, mock_hgit

    def test_no_active_branches_returns_empty(self, release_manager_with_mock_hgit):
        """Test returns empty list when no patch branches exist."""
        release_mgr, mock_hgit = release_manager_with_mock_hgit

        # Mock no active branches
        release_mgr._get_active_patch_branches = Mock(return_value=[])

        result = release_mgr._send_resync_notifications("456-user-auth", "1.3.6")

        # Should succeed for second branch only
        assert len(result) == 0

    def test_returns_to_original_branch(self, release_manager_with_mock_hgit):
        """Test returns to original branch after notifications."""
        release_mgr, mock_hgit = release_manager_with_mock_hgit

        # Set current branch
        mock_hgit.branch = "ho-prod"

        # Mock active branches
        release_mgr._get_active_patch_branches = Mock(return_value=[
            "ho-patch/789-security"
        ])

        result = release_mgr._send_resync_notifications("456-user-auth", "1.3.6")

        # Should return to ho-prod after notifications
        checkout_calls = [call[0][0] for call in mock_hgit.checkout.call_args_list]
        assert "ho-patch/789-security" in checkout_calls
        assert "ho-prod" == checkout_calls[-1]  # Last checkout should be back to ho-prod

    def test_commit_message_format(self, release_manager_with_mock_hgit):
        """Test notification commit message has correct format."""
        release_mgr, mock_hgit = release_manager_with_mock_hgit

        # Mock single branch
        release_mgr._get_active_patch_branches = Mock(return_value=[
            "ho-patch/789-security"
        ])

        result = release_mgr._send_resync_notifications("456-user-auth", "1.3.6")

        # Extract commit message
        commit_call = mock_hgit.commit.call_args
        commit_msg = commit_call[0][commit_call[0].index("-m") + 1]

        # Verify message format
        assert commit_msg.startswith("RESYNC REQUIRED:")
        assert "456-user-auth" in commit_msg
        assert "integrated to release" in commit_msg or "integrated" in commit_msg
        assert "1.3.6" in commit_msg

    def test_all_failures_returns_empty(self, release_manager_with_mock_hgit):
        """Test returns empty list if all notifications fail."""
        release_mgr, mock_hgit = release_manager_with_mock_hgit

        # Mock active branches
        release_mgr._get_active_patch_branches = Mock(return_value=[
            "ho-patch/789-security",
            "ho-patch/234-reports"
        ])

        # Mock checkout failure for all
        mock_hgit.checkout.side_effect = GitCommandError("checkout failed", 1)

        result = release_mgr._send_resync_notifications("456-user-auth", "1.3.6")

        # Should return empty list
        assert result == []

    def test_partial_success_returns_successful_only(self, release_manager_with_mock_hgit):
        """Test returns only branches that were successfully notified."""
        release_mgr, mock_hgit = release_manager_with_mock_hgit

        # Mock active branches
        release_mgr._get_active_patch_branches = Mock(return_value=[
            "ho-patch/789-security",
            "ho-patch/234-reports",
            "ho-patch/999-bugfix"
        ])

        # Mock failures for first and third
        checkout_count = [0]
        def checkout_side_effect(branch):
            checkout_count[0] += 1
            if checkout_count[0] in [1, 3]:
                raise GitCommandError("checkout failed", 1)

        mock_hgit.checkout.side_effect = checkout_side_effect

        result = release_mgr._send_resync_notifications("456-user-auth", "1.3.6")

        # Should only include second branch
        assert len(result) == 1
        assert "ho-patch/234-reports" in result

        # No checkout/commit/push calls
        assert mock_hgit.checkout.call_count == 4

    def test_skips_current_patch_branch(self, release_manager_with_mock_hgit):
        """Test does not send notification to current patch."""
        release_mgr, mock_hgit = release_manager_with_mock_hgit

        # Mock active branches including current patch
        release_mgr._get_active_patch_branches = Mock(return_value=[
            "ho-patch/456-user-auth",  # Current patch - should skip
            "ho-patch/789-security"
        ])

        result = release_mgr._send_resync_notifications("456-user-auth", "1.3.6")

        # Should only notify 789-security
        assert len(result) == 1
        assert "ho-patch/789-security" in result

        # Should checkout 789 then return to ho-prod (2 checkouts total)
        assert mock_hgit.checkout.call_count == 2
        mock_hgit.checkout.assert_any_call("ho-patch/789-security")
        mock_hgit.checkout.assert_any_call("ho-prod")  # Return to original

    def test_notifies_single_branch(self, release_manager_with_mock_hgit):
        """Test notification to single branch."""
        release_mgr, mock_hgit = release_manager_with_mock_hgit

        # Mock single active branch
        release_mgr._get_active_patch_branches = Mock(return_value=[
            "ho-patch/789-security"
        ])

        result = release_mgr._send_resync_notifications("456-user-auth", "1.3.6")

        # Verify notification sent
        assert result == ["ho-patch/789-security"]

        # Verify Git operations
        mock_hgit.checkout.assert_called_with("ho-prod")
        mock_hgit.commit.assert_called_once()

        # Check commit message format
        commit_call = mock_hgit.commit.call_args
        assert "--allow-empty" in commit_call[0]
        assert "-m" in commit_call[0]
        commit_msg = commit_call[0][commit_call[0].index("-m") + 1]
        assert "RESYNC REQUIRED" in commit_msg
        assert "456-user-auth" in commit_msg
        assert "1.3.6" in commit_msg

        mock_hgit.push.assert_called_once()

    def test_notifies_multiple_branches(self, release_manager_with_mock_hgit):
        """Test notifications to multiple branches."""
        release_mgr, mock_hgit = release_manager_with_mock_hgit

        # Mock multiple active branches
        release_mgr._get_active_patch_branches = Mock(return_value=[
            "ho-patch/789-security",
            "ho-patch/234-reports",
            "ho-patch/999-bugfix"
        ])

        result = release_mgr._send_resync_notifications("456-user-auth", "1.3.6")

        # Verify all branches notified
        assert len(result) == 3
        assert "ho-patch/789-security" in result
        assert "ho-patch/234-reports" in result
        assert "ho-patch/999-bugfix" in result

        # Verify checkout called for each branch
        assert mock_hgit.checkout.call_count == 4
        mock_hgit.checkout.assert_any_call("ho-patch/789-security")
        mock_hgit.checkout.assert_any_call("ho-patch/234-reports")
        mock_hgit.checkout.assert_any_call("ho-patch/999-bugfix")

        # Verify commit and push for each
        assert mock_hgit.commit.call_count == 3
        assert mock_hgit.push.call_count == 3

    def test_continues_on_checkout_failure(self, release_manager_with_mock_hgit):
        """Test continues with other branches if checkout fails."""
        release_mgr, mock_hgit = release_manager_with_mock_hgit

        # Mock active branches
        release_mgr._get_active_patch_branches = Mock(return_value=[
            "ho-patch/789-security",
            "ho-patch/234-reports",
            "ho-patch/999-bugfix"
        ])

        # Mock checkout failure for second branch
        def checkout_side_effect(branch):
            if branch == "ho-patch/234-reports":
                raise GitCommandError("checkout failed", 1)

        mock_hgit.checkout.side_effect = checkout_side_effect

        result = release_mgr._send_resync_notifications("456-user-auth", "1.3.6")

        # Should succeed for first and third, skip second
        assert len(result) == 2
        assert "ho-patch/789-security" in result
        assert "ho-patch/999-bugfix" in result
        assert "ho-patch/234-reports" not in result

    def test_continues_on_commit_failure(self, release_manager_with_mock_hgit):
        """Test continues with other branches if commit fails."""
        release_mgr, mock_hgit = release_manager_with_mock_hgit

        # Mock active branches
        release_mgr._get_active_patch_branches = Mock(return_value=[
            "ho-patch/789-security",
            "ho-patch/234-reports"
        ])

        # Mock commit failure for first branch
        commit_count = [0]
        def commit_side_effect(*args):
            commit_count[0] += 1
            if commit_count[0] == 1:
                raise GitCommandError("commit failed", 1)

        mock_hgit.commit.side_effect = commit_side_effect

        result = release_mgr._send_resync_notifications("456-user-auth", "1.3.6")

        # Should succeed for second branch only
        assert len(result) == 1
        assert "ho-patch/234-reports" in result
        assert "ho-patch/789-security" not in result

    def test_continues_on_push_failure(self, release_manager_with_mock_hgit):
        """Test continues with other branches if push fails."""
        release_mgr, mock_hgit = release_manager_with_mock_hgit

        # Mock active branches
        release_mgr._get_active_patch_branches = Mock(return_value=[
            "ho-patch/789-security",
            "ho-patch/234-reports"
        ])

        # Mock push failure for first branch
        push_count = [0]
        def push_side_effect():
            push_count[0] += 1
            if push_count[0] == 1:
                raise GitCommandError("push failed", 1)

        mock_hgit.push.side_effect = push_side_effect

        result = release_mgr._send_resync_notifications("456-user-auth", "1.3.6")
