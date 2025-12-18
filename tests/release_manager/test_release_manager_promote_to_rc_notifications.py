"""
Tests for ReleaseManager._send_rebase_notifications() - Rebase notifications.

Focused on testing:
- Sending rebase notifications to active patch branches
- No active branches (empty list)
- Notification message format
- Return to ho-prod after notifications
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, call, ANY
from git.exc import GitCommandError

from half_orm_dev.release_manager import ReleaseManager, ReleaseManagerError


class TestSendRebaseNotifications:
    """Test rebase notifications after promote-to rc."""

    @pytest.fixture
    def release_manager_with_git(self, tmp_path):
        """Create ReleaseManager with mocked Git operations."""
        mock_repo = Mock()
        mock_repo.base_dir = str(tmp_path)
        mock_repo.model_dir = str(tmp_path / ".hop" / "model")

        # Create releases/ directory
        releases_dir = tmp_path / ".hop" / "releases"
        releases_dir.mkdir(parents=True, exist_ok=True)
        mock_repo.releases_dir = str(releases_dir)

        # Mock HGit
        mock_hgit = Mock()
        mock_hgit.get_remote_branches = Mock(return_value=[])
        mock_hgit.checkout = Mock()
        mock_hgit.commit = Mock()
        mock_hgit.push = Mock()
        mock_hgit.branch = "ho-prod"

        mock_repo.hgit = mock_hgit

        release_mgr = ReleaseManager(mock_repo)

        return release_mgr, releases_dir, mock_hgit

    def test_no_active_branches_returns_empty(self, release_manager_with_git):
        """Test returns empty list when no active patch branches."""
        release_mgr, releases_dir, mock_hgit = release_manager_with_git

        # No remote branches
        mock_hgit.get_remote_branches.return_value = []

        version = "1.3.5"
        rc_number = 1

        notified = release_mgr._send_rebase_notifications(version, rc_number)

        # Verify no checkouts attempted
        mock_hgit.checkout.assert_not_called()

        # Verify empty list returned
        assert notified == []

    def test_notifications_sent_to_active_branches(self, release_manager_with_git):
        """Test notifications sent to all active patch branches."""
        release_mgr, releases_dir, mock_hgit = release_manager_with_git

        # Mock active patch branches
        mock_hgit.get_remote_branches.return_value = [
            "origin/ho-patch/999-reports",
            "origin/ho-patch/888-api"
        ]

        version = "1.3.5"
        rc_number = 1

        notified = release_mgr._send_rebase_notifications(version, 'rc', rc_number)

        # Verify checkouts
        expected_checkouts = [
            call("ho-patch/999-reports"),
            call("ho-patch/888-api"),
            call("ho-prod")  # Return to ho-prod
        ]
        assert mock_hgit.checkout.call_args_list == expected_checkouts

        # Verify commits (2 notifications + return to ho-prod = 2 commits)
        assert mock_hgit.commit.call_count == 2

        # Verify pushes (2 notifications)
        assert mock_hgit.push.call_count == 2

        # Verify return value
        assert notified == ["ho-patch/999-reports", "ho-patch/888-api"]

    def test_ignores_non_patch_branches(self, release_manager_with_git):
        """Test ignores branches that are not ho-patch/*."""
        release_mgr, releases_dir, mock_hgit = release_manager_with_git

        # Mock mixed branches
        mock_hgit.get_remote_branches.return_value = [
            "origin/ho-patch/999-reports",
            "origin/ho-prod",
            "origin/ho-release/1.3.5/456-user-auth",
            "origin/main",
            "origin/ho-patch/888-api"
        ]

        version = "1.3.5"
        rc_number = 1

        notified = release_mgr._send_rebase_notifications(version, rc_number)

        # Should only notify ho-patch/* branches
        assert notified == ["ho-patch/999-reports", "ho-patch/888-api"]

        # Verify only 2 patch branches + return to ho-prod
        expected_checkouts = [
            call("ho-patch/999-reports"),
            call("ho-patch/888-api"),
            call("ho-prod")
        ]
        assert mock_hgit.checkout.call_args_list == expected_checkouts

    def test_notification_message_format(self, release_manager_with_git):
        """Test notification commit message has correct format."""
        release_mgr, releases_dir, mock_hgit = release_manager_with_git

        # Mock one active branch
        mock_hgit.get_remote_branches.return_value = [
            "origin/ho-patch/999-reports"
        ]

        version = "1.3.5"
        rc_number = 1

        release_mgr._send_rebase_notifications(version, "rc", rc_number)

        # Verify commit message format
        mock_hgit.commit.assert_called_once()
        commit_call = mock_hgit.commit.call_args

        # Check message contains key elements
        message = commit_call.args[2]
        assert "[ho]" in message
        assert "1.3.5-rc1" in message
        assert "MERGE REQUIRED" in message or "rebase" in message.lower()

    def test_returns_to_ho_prod_after_notifications(self, release_manager_with_git):
        """Test returns to ho-prod branch after sending notifications."""
        release_mgr, releases_dir, mock_hgit = release_manager_with_git

        # Mock active branches
        mock_hgit.get_remote_branches.return_value = [
            "origin/ho-patch/999-reports"
        ]

        version = "1.3.5"
        rc_number = 1

        release_mgr._send_rebase_notifications(version, "rc", rc_number)

        # Last checkout should be ho-prod
        last_checkout = mock_hgit.checkout.call_args_list[-1]
        assert last_checkout == call("ho-prod")

    def test_continues_on_notification_error(self, release_manager_with_git):
        """Test continues notifications even if one fails."""
        release_mgr, releases_dir, mock_hgit = release_manager_with_git

        # Mock active branches
        mock_hgit.get_remote_branches.return_value = [
            "origin/ho-patch/999-reports",
            "origin/ho-patch/888-api"
        ]

        # First notification fails, second succeeds
        mock_hgit.push.side_effect = [
            GitCommandError("git push", 1),  # First fails
            None  # Second succeeds
        ]

        version = "1.3.5"
        rc_number = 1

        notified = release_mgr._send_rebase_notifications(version, rc_number)

        # Should attempt both notifications (best effort)
        assert mock_hgit.checkout.call_count >= 3  # At least 2 branches + return
        assert mock_hgit.commit.call_count == 2

        # Both reported as notified (best effort)
        assert len(notified) == 1
        assert notified == ["ho-patch/888-api"]

    def test_uses_allow_empty_commit(self, release_manager_with_git):
        """Test uses --allow-empty for notification commits."""
        release_mgr, releases_dir, mock_hgit = release_manager_with_git

        # Mock one active branch
        mock_hgit.get_remote_branches.return_value = [
            "origin/ho-patch/999-reports"
        ]

        version = "1.3.5"
        rc_number = 1

        release_mgr._send_rebase_notifications(version, rc_number)

        # Verify commit called with allow_empty=True
        mock_hgit.commit.assert_called_once()
        commit_call = mock_hgit.commit.call_args
        mock_hgit.commit.assert_called_once()
        commit_call = mock_hgit.commit.call_args
        assert '--allow-empty' in commit_call.args

    def test_incremental_rc_notifications(self, release_manager_with_git):
        """Test notification message differs for rc1 vs rc2."""
        release_mgr, releases_dir, mock_hgit = release_manager_with_git

        # Mock one active branch
        mock_hgit.get_remote_branches.return_value = [
            "origin/ho-patch/999-reports"
        ]

        # Test rc1
        release_mgr._send_rebase_notifications("1.3.5", "rc", 1)
        message_rc1 = mock_hgit.commit.call_args.args[2]
        assert "1.3.5-rc1" in message_rc1

        # Reset mock
        mock_hgit.commit.reset_mock()

        # Test rc2
        release_mgr._send_rebase_notifications("1.3.5", "rc", 2)
        message_rc2 = mock_hgit.commit.call_args.args[2]
        assert "1.3.5-rc2" in message_rc2

    def test_strips_origin_prefix_from_branch_names(self, release_manager_with_git):
        """Test strips 'origin/' prefix from remote branch names."""
        release_mgr, releases_dir, mock_hgit = release_manager_with_git

        # Mock remote branches with origin/ prefix
        mock_hgit.get_remote_branches.return_value = [
            "origin/ho-patch/999-reports"
        ]

        version = "1.3.5"
        rc_number = 1

        notified = release_mgr._send_rebase_notifications(version, rc_number)

        # Verify checkout called without origin/ prefix
        assert mock_hgit.checkout.call_args_list[0] == call("ho-patch/999-reports")

        # Verify return value without origin/ prefix
        assert notified == ["ho-patch/999-reports"]

    def test_empty_result_if_only_ho_prod_exists(self, release_manager_with_git):
        """Test returns empty if only ho-prod branch exists remotely."""
        release_mgr, releases_dir, mock_hgit = release_manager_with_git

        # Only ho-prod exists
        mock_hgit.get_remote_branches.return_value = [
            "origin/ho-prod"
        ]

        version = "1.3.5"
        rc_number = 1

        notified = release_mgr._send_rebase_notifications(version, rc_number)

        # Should not notify ho-prod
        assert notified == []

        # Should not checkout any branches (already on ho-prod)
        mock_hgit.checkout.assert_not_called()
