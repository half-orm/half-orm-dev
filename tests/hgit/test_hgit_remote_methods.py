"""
Tests for HGit remote operations.

Focused on testing:
- has_remote(): Check if origin remote configured
- push_branch(): Push branch to remote for patch ID reservation
"""

import pytest
from unittest.mock import Mock, patch
from git.exc import GitCommandError

from half_orm_dev.hgit import HGit


class TestHGitRemoteMethods:
    """Test remote-related methods for patch ID reservation."""

    @pytest.fixture
    def hgit_mock_only(self):
        """Create HGit instance with mocked git repository."""
        mock_git_repo = Mock()
        hgit = HGit()
        hgit._HGit__git_repo = mock_git_repo
        return hgit, mock_git_repo

    def test_has_remote_with_origin(self, hgit_mock_only):
        """Test has_remote returns True when origin exists."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock remotes list with origin
        mock_origin = Mock()
        mock_origin.name = 'origin'
        mock_git_repo.remotes = [mock_origin]

        # Should return True
        assert hgit.has_remote() is True

    def test_has_remote_no_remotes(self, hgit_mock_only):
        """Test has_remote returns False when no remotes configured."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock empty remotes list
        mock_git_repo.remotes = []

        # Should return False
        assert hgit.has_remote() is False

    def test_has_remote_multiple_remotes_with_origin(self, hgit_mock_only):
        """Test has_remote with multiple remotes including origin."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock multiple remotes including origin
        mock_origin = Mock()
        mock_origin.name = 'origin'
        mock_upstream = Mock()
        mock_upstream.name = 'upstream'
        mock_git_repo.remotes = [mock_origin, mock_upstream]

        # Should return True
        assert hgit.has_remote() is True

    def test_has_remote_only_non_origin_remote(self, hgit_mock_only):
        """Test has_remote returns False when only non-origin remotes exist."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock remote that is not origin
        mock_upstream = Mock()
        mock_upstream.name = 'upstream'
        mock_git_repo.remotes = [mock_upstream]

        # Should return False (we specifically check for 'origin')
        assert hgit.has_remote() is False

    def test_has_remote_exception_handling(self, hgit_mock_only):
        """Test has_remote handles exceptions gracefully."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock remotes to raise exception
        mock_git_repo.remotes = Mock(side_effect=GitCommandError("git remote", 1))

        # Should return False on exception (graceful handling)
        assert hgit.has_remote() is False

    def test_push_branch_with_upstream(self, hgit_mock_only):
        """Test push_branch with upstream tracking."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock remote
        mock_origin = Mock()
        mock_git_repo.remote.return_value = mock_origin

        # Push with upstream
        hgit.push_branch("ho-patch/456-user-auth")

        # Should push with -u flag
        mock_git_repo.remote.assert_called_once_with('origin')
        mock_origin.push.assert_called_once_with(
            'ho-patch/456-user-auth',
            set_upstream=True
        )

    def test_push_branch_without_upstream(self, hgit_mock_only):
        """Test push_branch without upstream tracking."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock remote
        mock_origin = Mock()
        mock_git_repo.remote.return_value = mock_origin

        # Push without upstream
        hgit.push_branch("ho-patch/456-user-auth", set_upstream=False)

        # Should push without -u flag
        mock_origin.push.assert_called_once_with(
            'ho-patch/456-user-auth',
            set_upstream=False
        )

    def test_push_branch_no_remote(self, hgit_mock_only):
        """Test push_branch raises error when no remote exists."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock remote to raise error
        mock_git_repo.remote.side_effect = GitCommandError(
            "git remote", 1, stderr="No such remote 'origin'"
        )

        # Should raise GitCommandError
        with pytest.raises(GitCommandError, match="No such remote"):
            hgit.push_branch("ho-patch/456-user-auth")

    def test_push_branch_authentication_failure(self, hgit_mock_only):
        """Test push_branch raises error on authentication failure."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock remote and push to raise auth error
        mock_origin = Mock()
        mock_origin.push.side_effect = GitCommandError(
            "git push", 1, stderr="Authentication failed"
        )
        mock_git_repo.remote.return_value = mock_origin

        # Should raise GitCommandError
        with pytest.raises(GitCommandError, match="Authentication failed"):
            hgit.push_branch("ho-patch/456-user-auth")

    def test_push_branch_network_error(self, hgit_mock_only):
        """Test push_branch raises error on network failure."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock remote and push to raise network error
        mock_origin = Mock()
        mock_origin.push.side_effect = GitCommandError(
            "git push", 1, stderr="Could not resolve host"
        )
        mock_git_repo.remote.return_value = mock_origin

        # Should raise GitCommandError
        with pytest.raises(GitCommandError, match="Could not resolve host"):
            hgit.push_branch("ho-patch/456-user-auth")

    def test_push_branch_different_branch_names(self, hgit_mock_only):
        """Test push_branch works with various branch naming patterns."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock remote
        mock_origin = Mock()
        mock_git_repo.remote.return_value = mock_origin

        # Test various branch names
        branch_names = [
            "ho-patch/123",
            "ho-patch/456-user-auth",
            "ho-patch/789-complex-feature-name"
        ]

        for branch_name in branch_names:
            mock_origin.reset_mock()
            hgit.push_branch(branch_name)
            mock_origin.push.assert_called_once_with(branch_name, set_upstream=True)
