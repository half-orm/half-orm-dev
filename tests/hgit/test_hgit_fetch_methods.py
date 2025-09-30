"""
Tests for HGit tag-based patch number reservation.

Focused on testing:
- fetch_tags(): Fetch tags from remote
- tag_exists(): Check if tag exists
- create_tag(): Create reservation tag
- push_tag(): Push tag to remote
"""

import pytest
from unittest.mock import Mock, MagicMock
from git.exc import GitCommandError

from half_orm_dev.hgit import HGit


class TestHGitTagMethods:
    """Test tag-based patch number reservation methods."""

    @pytest.fixture
    def hgit_mock_only(self):
        """Create HGit instance with mocked git repository."""
        mock_git_repo = Mock()
        hgit = HGit()
        hgit._HGit__git_repo = mock_git_repo
        return hgit, mock_git_repo

    def test_fetch_tags_success(self, hgit_mock_only):
        """Test successful tags fetch from remote."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock remote
        mock_origin = Mock()
        mock_git_repo.remote.return_value = mock_origin

        # Fetch tags
        hgit.fetch_tags()

        # Should have called fetch with tags=True
        mock_origin.fetch.assert_called_once_with(tags=True)

    def test_fetch_tags_no_remote(self, hgit_mock_only):
        """Test fetch_tags failure when no remote exists."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock remote to raise error
        mock_git_repo.remote.side_effect = GitCommandError(
            "git remote", 1, stderr="No such remote"
        )

        # Should raise GitCommandError
        with pytest.raises(GitCommandError):
            hgit.fetch_tags()

    def test_tag_exists_tag_found(self, hgit_mock_only):
        """Test tag_exists returns True when tag exists."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock tags
        mock_tag = Mock()
        mock_tag.name = "ho-patch/456"
        mock_git_repo.tags = [mock_tag]

        # Should find tag
        assert hgit.tag_exists("ho-patch/456") is True

    def test_tag_exists_tag_not_found(self, hgit_mock_only):
        """Test tag_exists returns False when tag doesn't exist."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock tags with different tag
        mock_tag = Mock()
        mock_tag.name = "ho-patch/123"
        mock_git_repo.tags = [mock_tag]

        # Should not find tag
        assert hgit.tag_exists("ho-patch/456") is False

    def test_tag_exists_empty_tags(self, hgit_mock_only):
        """Test tag_exists with no tags."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock empty tags
        mock_git_repo.tags = []

        # Should return False
        assert hgit.tag_exists("ho-patch/456") is False

    def test_tag_exists_exception_handling(self, hgit_mock_only):
        """Test tag_exists handles exceptions gracefully."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock tags to raise error
        mock_git_repo.tags = Mock(side_effect=Exception("Error"))

        # Should return False gracefully
        assert hgit.tag_exists("ho-patch/456") is False

    def test_create_tag_success(self, hgit_mock_only):
        """Test successful tag creation."""
        hgit, mock_git_repo = hgit_mock_only

        # Create tag
        hgit.create_tag("ho-patch/456", "Patch 456: User auth")

        # Should have called create_tag
        mock_git_repo.create_tag.assert_called_once_with(
            "ho-patch/456",
            message="Patch 456: User auth"
        )

    def test_create_tag_failure(self, hgit_mock_only):
        """Test create_tag handles failures."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock create_tag to fail
        mock_git_repo.create_tag.side_effect = GitCommandError(
            "git tag", 1, stderr="Tag already exists"
        )

        # Should raise GitCommandError
        with pytest.raises(GitCommandError):
            hgit.create_tag("ho-patch/456", "Message")

    def test_push_tag_success(self, hgit_mock_only):
        """Test successful tag push."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock remote
        mock_origin = Mock()
        mock_git_repo.remote.return_value = mock_origin

        # Push tag
        hgit.push_tag("ho-patch/456")

        # Should have pushed tag
        mock_origin.push.assert_called_once_with("ho-patch/456")

    def test_push_tag_failure(self, hgit_mock_only):
        """Test push_tag handles network failures."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock remote and push to fail
        mock_origin = Mock()
        mock_origin.push.side_effect = GitCommandError(
            "git push", 1, stderr="Network error"
        )
        mock_git_repo.remote.return_value = mock_origin

        # Should raise GitCommandError
        with pytest.raises(GitCommandError):
            hgit.push_tag("ho-patch/456")
