"""
Tests for HGit.get_remote_commit_hash() method.

Focused on testing:
- Retrieving commit hash for remote branches
- Error handling for non-existent remote branches
- Handling different remote names
- Requires prior fetch for accurate results
"""

import pytest
from unittest.mock import Mock
from git.exc import GitCommandError

from half_orm_dev.hgit import HGit


class TestHGitGetRemoteCommitHash:
    """Test get_remote_commit_hash() method."""

    @pytest.fixture
    def hgit_mock_only(self):
        """Create HGit instance with mocked git repository."""
        mock_git_repo = Mock()
        hgit = HGit()
        hgit._HGit__git_repo = mock_git_repo
        return hgit, mock_git_repo

    def test_get_remote_commit_hash_success(self, hgit_mock_only):
        """Test successful retrieval of remote commit hash."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock remote reference
        mock_remote_ref = Mock()
        mock_commit = Mock()
        mock_commit.hexsha = "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0"
        mock_remote_ref.commit = mock_commit

        # Mock remote with refs
        mock_remote = Mock()
        mock_remote.refs = {"ho-prod": mock_remote_ref}
        mock_git_repo.remote.return_value = mock_remote

        # Get remote commit hash
        result = hgit.get_remote_commit_hash("ho-prod")

        # Should return full hash
        assert result == "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0"
        assert len(result) == 40

    def test_get_remote_commit_hash_branch_not_found(self, hgit_mock_only):
        """Test error when branch doesn't exist on remote."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock remote with empty refs
        mock_remote = Mock()
        mock_remote.refs = {}
        mock_git_repo.remote.return_value = mock_remote

        # Should raise GitCommandError
        with pytest.raises(GitCommandError, match="not found on remote"):
            hgit.get_remote_commit_hash("nonexistent-branch")

    def test_get_remote_commit_hash_no_remote(self, hgit_mock_only):
        """Test error when remote doesn't exist."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock remote to raise error
        mock_git_repo.remote.side_effect = GitCommandError(
            "git remote", 1, stderr="No such remote 'origin'"
        )

        # Should raise GitCommandError
        with pytest.raises(GitCommandError, match="No such remote"):
            hgit.get_remote_commit_hash("ho-prod")

    def test_get_remote_commit_hash_custom_remote(self, hgit_mock_only):
        """Test hash retrieval with custom remote name."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock upstream remote
        mock_remote_ref = Mock()
        mock_commit = Mock()
        mock_commit.hexsha = "upstream123abc456def789ghi012jkl345mno678"
        mock_remote_ref.commit = mock_commit

        mock_remote = Mock()
        mock_remote.refs = {"ho-prod": mock_remote_ref}
        mock_git_repo.remote.return_value = mock_remote

        # Get hash from upstream remote
        result = hgit.get_remote_commit_hash("ho-prod", remote="upstream")

        # Should have queried upstream
        mock_git_repo.remote.assert_called_once_with("upstream")
        assert result == "upstream123abc456def789ghi012jkl345mno678"

    def test_get_remote_commit_hash_patch_branch(self, hgit_mock_only):
        """Test hash retrieval for remote patch branch."""
        hgit, mock_git_repo = hgit_mock_only

        mock_remote_ref = Mock()
        mock_commit = Mock()
        mock_commit.hexsha = "patch456def789ghi012jkl345mno678pqr901st2"
        mock_remote_ref.commit = mock_commit

        mock_remote = Mock()
        mock_remote.refs = {"ho-patch/456-user-auth": mock_remote_ref}
        mock_git_repo.remote.return_value = mock_remote

        result = hgit.get_remote_commit_hash("ho-patch/456-user-auth")

        assert result == "patch456def789ghi012jkl345mno678pqr901st2"

    def test_get_remote_commit_hash_multiple_branches(self, hgit_mock_only):
        """Test hash retrieval for multiple remote branches."""
        hgit, mock_git_repo = hgit_mock_only

        # Setup multiple remote branches
        branches = {
            "ho-prod": "aaa111bbb222ccc333ddd444eee555fff666ggg7",
            "ho-patch/123": "bbb222ccc333ddd444eee555fff666ggg777hhh8",
            "ho-patch/456-feature": "ccc333ddd444eee555fff666ggg777hhh888iii9"
        }

        mock_refs = {}
        for branch_name, commit_hash in branches.items():
            mock_remote_ref = Mock()
            mock_commit = Mock()
            mock_commit.hexsha = commit_hash
            mock_remote_ref.commit = mock_commit
            mock_refs[branch_name] = mock_remote_ref

        mock_remote = Mock()
        mock_remote.refs = mock_refs
        mock_git_repo.remote.return_value = mock_remote

        # Verify each branch returns correct hash
        for branch_name, expected_hash in branches.items():
            result = hgit.get_remote_commit_hash(branch_name)
            assert result == expected_hash

    def test_get_remote_commit_hash_default_remote_is_origin(self, hgit_mock_only):
        """Test that default remote is 'origin'."""
        hgit, mock_git_repo = hgit_mock_only

        mock_remote_ref = Mock()
        mock_commit = Mock()
        mock_commit.hexsha = "default123456789abc123456789abc123456789a"
        mock_remote_ref.commit = mock_commit

        mock_remote = Mock()
        mock_remote.refs = {"ho-prod": mock_remote_ref}
        mock_git_repo.remote.return_value = mock_remote

        # Call without specifying remote
        result = hgit.get_remote_commit_hash("ho-prod")

        # Should have queried 'origin'
        mock_git_repo.remote.assert_called_once_with("origin")
        assert result == "default123456789abc123456789abc123456789a"
