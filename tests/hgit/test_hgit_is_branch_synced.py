"""
Tests for HGit.is_branch_synced() method.

Focused on testing:
- Synced status (local == remote)
- Ahead status (local has commits not on remote)
- Behind status (remote has commits not in local)
- Diverged status (both have different commits)
- Integration with get_local_commit_hash and get_remote_commit_hash
"""

import pytest
from unittest.mock import Mock, patch
from git.exc import GitCommandError

from half_orm_dev.hgit import HGit


class TestHGitIsBranchSynced:
    """Test is_branch_synced() method."""

    @pytest.fixture
    def hgit_mock_only(self):
        """Create HGit instance with mocked git repository."""
        mock_git_repo = Mock()
        hgit = HGit()
        hgit._HGit__git_repo = mock_git_repo
        return hgit, mock_git_repo

    def test_is_branch_synced_when_synced(self, hgit_mock_only):
        """Test synced status when local and remote are identical."""
        hgit, mock_git_repo = hgit_mock_only

        same_hash = "abc123def456abc123def456abc123def456abc1"

        # Mock local branch
        mock_local_branch = Mock()
        mock_local_commit = Mock()
        mock_local_commit.hexsha = same_hash
        mock_local_branch.commit = mock_local_commit
        mock_git_repo.heads = {"ho-prod": mock_local_branch}

        # Mock remote branch
        mock_remote_ref = Mock()
        mock_remote_commit = Mock()
        mock_remote_commit.hexsha = same_hash
        mock_remote_ref.commit = mock_remote_commit
        mock_remote = Mock()
        mock_remote.refs = {"ho-prod": mock_remote_ref}
        mock_git_repo.remote.return_value = mock_remote

        # Check sync status
        is_synced, status = hgit.is_branch_synced("ho-prod")

        assert is_synced is True
        assert status == "synced"

    def test_is_branch_synced_when_ahead(self, hgit_mock_only):
        """Test ahead status when local has commits not on remote."""
        hgit, mock_git_repo = hgit_mock_only

        local_hash = "ahead111222333444555666777888999aaabbbccc"
        remote_hash = "behind000111222333444555666777888999aaabbb"

        # Mock local branch (ahead)
        mock_local_branch = Mock()
        mock_local_commit = Mock()
        mock_local_commit.hexsha = local_hash
        mock_local_branch.commit = mock_local_commit
        mock_git_repo.heads = {"ho-prod": mock_local_branch}

        # Mock remote branch (behind)
        mock_remote_ref = Mock()
        mock_remote_commit = Mock()
        mock_remote_commit.hexsha = remote_hash
        mock_remote_ref.commit = mock_remote_commit
        mock_remote = Mock()
        mock_remote.refs = {"ho-prod": mock_remote_ref}
        mock_git_repo.remote.return_value = mock_remote

        # Mock merge_base to simulate ahead status
        with patch.object(mock_git_repo, 'merge_base') as mock_merge_base:
            mock_merge_base_commit = Mock()
            mock_merge_base_commit.hexsha = remote_hash  # merge base = remote
            mock_merge_base.return_value = [mock_merge_base_commit]

            is_synced, status = hgit.is_branch_synced("ho-prod")

        assert is_synced is False
        assert status == "ahead"

    def test_is_branch_synced_when_behind(self, hgit_mock_only):
        """Test behind status when remote has commits not in local."""
        hgit, mock_git_repo = hgit_mock_only

        local_hash = "behind000111222333444555666777888999aaabbb"
        remote_hash = "ahead111222333444555666777888999aaabbbccc"

        # Mock local branch (behind)
        mock_local_branch = Mock()
        mock_local_commit = Mock()
        mock_local_commit.hexsha = local_hash
        mock_local_branch.commit = mock_local_commit
        mock_git_repo.heads = {"ho-prod": mock_local_branch}

        # Mock remote branch (ahead)
        mock_remote_ref = Mock()
        mock_remote_commit = Mock()
        mock_remote_commit.hexsha = remote_hash
        mock_remote_ref.commit = mock_remote_commit
        mock_remote = Mock()
        mock_remote.refs = {"ho-prod": mock_remote_ref}
        mock_git_repo.remote.return_value = mock_remote

        # Mock merge_base to simulate behind status
        with patch.object(mock_git_repo, 'merge_base') as mock_merge_base:
            mock_merge_base_commit = Mock()
            mock_merge_base_commit.hexsha = local_hash  # merge base = local
            mock_merge_base.return_value = [mock_merge_base_commit]

            is_synced, status = hgit.is_branch_synced("ho-prod")

        assert is_synced is False
        assert status == "behind"

    def test_is_branch_synced_when_diverged(self, hgit_mock_only):
        """Test diverged status when both have different commits."""
        hgit, mock_git_repo = hgit_mock_only

        local_hash = "local111222333444555666777888999aaabbbccc"
        remote_hash = "remote222333444555666777888999aaabbbcccddd"
        merge_base_hash = "base000111222333444555666777888999aaabbb"

        # Mock local branch
        mock_local_branch = Mock()
        mock_local_commit = Mock()
        mock_local_commit.hexsha = local_hash
        mock_local_branch.commit = mock_local_commit
        mock_git_repo.heads = {"ho-prod": mock_local_branch}

        # Mock remote branch
        mock_remote_ref = Mock()
        mock_remote_commit = Mock()
        mock_remote_commit.hexsha = remote_hash
        mock_remote_ref.commit = mock_remote_commit
        mock_remote = Mock()
        mock_remote.refs = {"ho-prod": mock_remote_ref}
        mock_git_repo.remote.return_value = mock_remote

        # Mock merge_base to simulate diverged status
        with patch.object(mock_git_repo, 'merge_base') as mock_merge_base:
            mock_merge_base_commit = Mock()
            mock_merge_base_commit.hexsha = merge_base_hash  # different from both
            mock_merge_base.return_value = [mock_merge_base_commit]

            is_synced, status = hgit.is_branch_synced("ho-prod")

        assert is_synced is False
        assert status == "diverged"

    def test_is_branch_synced_custom_remote(self, hgit_mock_only):
        """Test sync check with custom remote name."""
        hgit, mock_git_repo = hgit_mock_only

        same_hash = "custom123456789abc123456789abc123456789ab"

        # Mock local branch
        mock_local_branch = Mock()
        mock_local_commit = Mock()
        mock_local_commit.hexsha = same_hash
        mock_local_branch.commit = mock_local_commit
        mock_git_repo.heads = {"ho-prod": mock_local_branch}

        # Mock upstream remote
        mock_remote_ref = Mock()
        mock_remote_commit = Mock()
        mock_remote_commit.hexsha = same_hash
        mock_remote_ref.commit = mock_remote_commit
        mock_remote = Mock()
        mock_remote.refs = {"ho-prod": mock_remote_ref}
        mock_git_repo.remote.return_value = mock_remote

        # Check against upstream
        is_synced, status = hgit.is_branch_synced("ho-prod", remote="upstream")

        mock_git_repo.remote.assert_called_with("upstream")
        assert is_synced is True
        assert status == "synced"

    def test_is_branch_synced_branch_not_found_locally(self, hgit_mock_only):
        """Test error when branch doesn't exist locally."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock empty local heads
        mock_git_repo.heads = {}

        # Should raise GitCommandError from get_local_commit_hash
        with pytest.raises(GitCommandError, match="not found"):
            hgit.is_branch_synced("nonexistent-branch")

    def test_is_branch_synced_branch_not_found_on_remote(self, hgit_mock_only):
        """Test error when branch doesn't exist on remote."""
        hgit, mock_git_repo = hgit_mock_only

        # Mock local branch exists
        mock_local_branch = Mock()
        mock_local_commit = Mock()
        mock_local_commit.hexsha = "local123"
        mock_local_branch.commit = mock_local_commit
        mock_git_repo.heads = {"ho-prod": mock_local_branch}

        # Mock remote without branch
        mock_remote = Mock()
        mock_remote.refs = {}
        mock_git_repo.remote.return_value = mock_remote

        # Should raise GitCommandError from get_remote_commit_hash
        with pytest.raises(GitCommandError, match="not found on remote"):
            hgit.is_branch_synced("ho-prod")

    def test_is_branch_synced_patch_branch(self, hgit_mock_only):
        """Test sync check for patch branch."""
        hgit, mock_git_repo = hgit_mock_only

        same_hash = "patch456def789ghi012jkl345mno678pqr901st2"

        # Mock local patch branch
        mock_local_branch = Mock()
        mock_local_commit = Mock()
        mock_local_commit.hexsha = same_hash
        mock_local_branch.commit = mock_local_commit
        mock_git_repo.heads = {"ho-patch/456-user-auth": mock_local_branch}

        # Mock remote patch branch
        mock_remote_ref = Mock()
        mock_remote_commit = Mock()
        mock_remote_commit.hexsha = same_hash
        mock_remote_ref.commit = mock_remote_commit
        mock_remote = Mock()
        mock_remote.refs = {"ho-patch/456-user-auth": mock_remote_ref}
        mock_git_repo.remote.return_value = mock_remote

        is_synced, status = hgit.is_branch_synced("ho-patch/456-user-auth")

        assert is_synced is True
        assert status == "synced"
