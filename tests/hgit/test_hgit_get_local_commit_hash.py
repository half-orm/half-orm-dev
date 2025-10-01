"""
Tests for HGit.get_local_commit_hash() method.

Focused on testing:
- Retrieving commit hash for existing local branches
- Error handling for non-existent branches
- Handling different branch name formats
"""

import pytest
from unittest.mock import Mock
from git.exc import GitCommandError

from half_orm_dev.hgit import HGit


class TestHGitGetLocalCommitHash:
    """Test get_local_commit_hash() method."""

    @pytest.fixture
    def hgit_mock_only(self):
        """Create HGit instance with mocked git repository."""
        mock_git_repo = Mock()
        hgit = HGit()
        hgit._HGit__git_repo = mock_git_repo
        return hgit, mock_git_repo

    def test_get_local_commit_hash_success(self, hgit_mock_only):
        """Test successful retrieval of local commit hash."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock branch with commit
        mock_branch = Mock()
        mock_commit = Mock()
        mock_commit.hexsha = "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0"
        mock_branch.commit = mock_commit
        
        # Mock heads to return our branch
        mock_git_repo.heads = {"ho-prod": mock_branch}

        # Get commit hash
        result = hgit.get_local_commit_hash("ho-prod")

        # Should return full hash
        assert result == "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0"
        assert len(result) == 40

    def test_get_local_commit_hash_branch_not_found(self, hgit_mock_only):
        """Test error when branch doesn't exist locally."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock empty heads (no branches)
        mock_git_repo.heads = {}

        # Should raise GitCommandError
        with pytest.raises(GitCommandError, match="not found"):
            hgit.get_local_commit_hash("nonexistent-branch")

    def test_get_local_commit_hash_ho_prod(self, hgit_mock_only):
        """Test hash retrieval for ho-prod branch."""
        hgit, mock_git_repo = hgit_mock_only

        mock_branch = Mock()
        mock_commit = Mock()
        mock_commit.hexsha = "abc123def456abc123def456abc123def456abc1"
        mock_branch.commit = mock_commit
        mock_git_repo.heads = {"ho-prod": mock_branch}

        result = hgit.get_local_commit_hash("ho-prod")

        assert result == "abc123def456abc123def456abc123def456abc1"

    def test_get_local_commit_hash_patch_branch(self, hgit_mock_only):
        """Test hash retrieval for patch branch."""
        hgit, mock_git_repo = hgit_mock_only

        mock_branch = Mock()
        mock_commit = Mock()
        mock_commit.hexsha = "456def789ghi456def789ghi456def789ghi456d"
        mock_branch.commit = mock_commit
        mock_git_repo.heads = {"ho-patch/456-user-auth": mock_branch}

        result = hgit.get_local_commit_hash("ho-patch/456-user-auth")

        assert result == "456def789ghi456def789ghi456def789ghi456d"

    def test_get_local_commit_hash_different_branches(self, hgit_mock_only):
        """Test hash retrieval for multiple branches."""
        hgit, mock_git_repo = hgit_mock_only

        # Setup multiple branches
        branches = {
            "ho-prod": "aaa111bbb222ccc333ddd444eee555fff666ggg7",
            "ho-patch/123": "bbb222ccc333ddd444eee555fff666ggg777hhh8",
            "ho-patch/456-feature": "ccc333ddd444eee555fff666ggg777hhh888iii9"
        }

        mock_heads = {}
        for branch_name, commit_hash in branches.items():
            mock_branch = Mock()
            mock_commit = Mock()
            mock_commit.hexsha = commit_hash
            mock_branch.commit = mock_commit
            mock_heads[branch_name] = mock_branch

        mock_git_repo.heads = mock_heads

        # Verify each branch returns correct hash
        for branch_name, expected_hash in branches.items():
            result = hgit.get_local_commit_hash(branch_name)
            assert result == expected_hash

    def test_get_local_commit_hash_invalid_branch_name(self, hgit_mock_only):
        """Test error with invalid branch name characters."""
        hgit, mock_git_repo = hgit_mock_only

        mock_git_repo.heads = {}

        # Should raise error for non-existent branch
        with pytest.raises(GitCommandError):
            hgit.get_local_commit_hash("invalid@branch#name")
