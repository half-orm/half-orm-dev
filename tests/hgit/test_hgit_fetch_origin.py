"""
Tests for HGit.fetch_from_origin() method.
"""

import pytest
from unittest.mock import Mock
from git.exc import GitCommandError

from half_orm_dev.hgit import HGit


class TestHGitFetchFromOrigin:
    """Test fetch_from_origin() method."""

    @pytest.fixture
    def hgit_mock_only(self):
        """Create HGit instance with mocked git repository."""
        mock_git_repo = Mock()
        hgit = HGit()
        hgit._HGit__git_repo = mock_git_repo
        return hgit, mock_git_repo

    def test_fetch_from_origin_success(self, hgit_mock_only):
        """Test successful fetch from origin."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock remote
        mock_origin = Mock()
        mock_git_repo.remote.return_value = mock_origin

        # Fetch from origin
        hgit.fetch_from_origin()

        # Should have called fetch (without specific args = fetch everything)
        mock_git_repo.remote.assert_called_once_with('origin')
        mock_origin.fetch.assert_called_once()

    def test_fetch_from_origin_no_remote(self, hgit_mock_only):
        """Test fetch failure when no remote exists."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock remote to raise error
        mock_git_repo.remote.side_effect = GitCommandError(
            "git remote", 1, stderr="No such remote 'origin'"
        )

        # Should raise GitCommandError
        with pytest.raises(GitCommandError, match="No such remote"):
            hgit.fetch_from_origin()

    def test_fetch_from_origin_network_error(self, hgit_mock_only):
        """Test fetch failure due to network error."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock remote and fetch to fail
        mock_origin = Mock()
        mock_origin.fetch.side_effect = GitCommandError(
            "git fetch", 1, stderr="Network unreachable"
        )
        mock_git_repo.remote.return_value = mock_origin

        # Should raise GitCommandError
        with pytest.raises(GitCommandError, match="Network unreachable"):
            hgit.fetch_from_origin()

    def test_fetch_from_origin_authentication_error(self, hgit_mock_only):
        """Test fetch failure due to authentication."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock remote and fetch to fail with auth error
        mock_origin = Mock()
        mock_origin.fetch.side_effect = GitCommandError(
            "git fetch", 1, stderr="Authentication failed"
        )
        mock_git_repo.remote.return_value = mock_origin

        # Should raise GitCommandError
        with pytest.raises(GitCommandError, match="Authentication failed"):
            hgit.fetch_from_origin()

    def test_fetch_from_origin_fetches_all_refs(self, hgit_mock_only):
        """Test that fetch_from_origin fetches all references."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock remote
        mock_origin = Mock()
        mock_git_repo.remote.return_value = mock_origin

        # Fetch from origin
        hgit.fetch_from_origin()

        # Should call fetch() without arguments (fetches all refs)
        # vs fetch_tags() which calls fetch(tags=True)
        mock_origin.fetch.assert_called_once_with(prune=True)  # No tags=True argument
