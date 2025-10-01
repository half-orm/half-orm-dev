"""
Tests for HGit.delete_local_branch() and delete_local_tag() methods.
"""

import pytest
from unittest.mock import Mock
from git.exc import GitCommandError

from half_orm_dev.hgit import HGit


class TestHGitDeleteMethods:
    """Test branch and tag deletion methods."""

    @pytest.fixture
    def hgit_mock_only(self):
        """Create HGit instance with mocked git repository."""
        mock_git_repo = Mock()
        mock_git_repo.git = Mock()
        hgit = HGit()
        hgit._HGit__git_repo = mock_git_repo
        return hgit, mock_git_repo

    def test_delete_local_branch_success(self, hgit_mock_only):
        """Test successful local branch deletion."""
        hgit, mock_git_repo = hgit_mock_only

        # Delete branch
        hgit.delete_local_branch("ho-patch/456-user-auth")

        # Should call git branch -D
        mock_git_repo.git.branch.assert_called_once_with('-D', 'ho-patch/456-user-auth')

    def test_delete_local_branch_not_found(self, hgit_mock_only):
        """Test branch deletion when branch doesn't exist."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock branch command to fail
        mock_git_repo.git.branch.side_effect = GitCommandError(
            "git branch", 1, stderr="branch 'ho-patch/456' not found"
        )

        # Should raise GitCommandError
        with pytest.raises(GitCommandError, match="not found"):
            hgit.delete_local_branch("ho-patch/456")

    def test_delete_local_branch_current_branch_error(self, hgit_mock_only):
        """Test branch deletion when trying to delete current branch."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock branch command to fail (cannot delete current branch)
        mock_git_repo.git.branch.side_effect = GitCommandError(
            "git branch", 1, stderr="Cannot delete branch currently checked out"
        )

        # Should raise GitCommandError
        with pytest.raises(GitCommandError, match="currently checked out"):
            hgit.delete_local_branch("ho-patch/456")

    def test_delete_local_tag_success(self, hgit_mock_only):
        """Test successful local tag deletion."""
        hgit, mock_git_repo = hgit_mock_only

        # Delete tag
        hgit.delete_local_tag("ho-patch/456")

        # Should call git tag -d
        mock_git_repo.git.tag.assert_called_once_with('-d', 'ho-patch/456')

    def test_delete_local_tag_not_found(self, hgit_mock_only):
        """Test tag deletion when tag doesn't exist."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock tag command to fail
        mock_git_repo.git.tag.side_effect = GitCommandError(
            "git tag", 1, stderr="tag 'ho-patch/456' not found"
        )

        # Should raise GitCommandError
        with pytest.raises(GitCommandError, match="not found"):
            hgit.delete_local_tag("ho-patch/456")

    def test_delete_local_branch_numeric_id(self, hgit_mock_only):
        """Test branch deletion with numeric-only patch ID."""
        hgit, mock_git_repo = hgit_mock_only

        # Delete branch with numeric ID
        hgit.delete_local_branch("ho-patch/456")

        # Should call git branch -D
        mock_git_repo.git.branch.assert_called_once_with('-D', 'ho-patch/456')

    def test_delete_local_tag_numeric_id(self, hgit_mock_only):
        """Test tag deletion with numeric-only patch ID."""
        hgit, mock_git_repo = hgit_mock_only

        # Delete tag with numeric ID
        hgit.delete_local_tag("ho-patch/456")

        # Should call git tag -d
        mock_git_repo.git.tag.assert_called_once_with('-d', 'ho-patch/456')

    def test_delete_operations_independent(self, hgit_mock_only):
        """Test branch and tag deletions are independent operations."""
        hgit, mock_git_repo = hgit_mock_only

        # Delete branch
        hgit.delete_local_branch("ho-patch/456")

        # Delete tag
        hgit.delete_local_tag("ho-patch/456")

        # Should have called both independently
        mock_git_repo.git.branch.assert_called_once()
        mock_git_repo.git.tag.assert_called_once()
