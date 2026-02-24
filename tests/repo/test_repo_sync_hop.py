"""
Tests for Repo.sync_hop_to_active_branches() method.

Tests the automatic synchronization of .hop/ directory from ho-prod to active branches.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call
from half_orm_dev.repo import Repo


class TestRepoSyncHop:
    """Test Repo.sync_hop_to_active_branches() method."""

    @pytest.fixture
    def mock_repo(self, tmp_path):
        """Create a mock Repo with necessary structure."""
        # Create .hop directory
        hop_dir = tmp_path / '.hop'
        hop_dir.mkdir()
        (hop_dir / 'config').write_text('[halfORM]\nhop_version = "0.17.0"\n')

        # Mock Repo instance
        repo = Mock(spec=Repo)
        repo.base_dir = str(tmp_path)
        repo._Repo__config = Mock()
        repo._Repo__config.hop_version = "0.17.0"

        # Mock HGit
        repo.hgit = Mock()
        repo.hgit.branch = 'ho-prod'
        repo.hgit._HGit__git_repo = Mock()
        repo.hgit.is_branch_synced = Mock(return_value=(True, "synced"))

        # Bind the real method to the mock
        repo.sync_hop_to_active_branches = Repo.sync_hop_to_active_branches.__get__(repo, Repo)

        return repo, tmp_path

    def test_sync_from_patch_branch(self, mock_repo):
        """Test sync works from any branch (e.g., patch branch)."""
        repo, tmp_path = mock_repo
        repo.hgit.branch = 'ho-patch/123-test'

        # Mock get_active_branches_status
        repo.hgit.get_active_branches_status.return_value = {
            'patch_branches': [{'name': 'ho-patch/123-test'}, {'name': 'ho-patch/456-other'}],
            'release_branches': [{'name': 'ho-release/0.17.0'}]
        }

        # Mock git operations
        repo.hgit.checkout = Mock()
        repo.hgit.add = Mock()
        repo.hgit.commit = Mock()
        repo.hgit.push_branch = Mock()
        repo.hgit._HGit__git_repo.git.checkout = Mock()
        repo.hgit._HGit__git_repo.git.status = Mock(return_value='M .hop/config\n')

        # Mock Config reload
        with patch('half_orm_dev.repo.Config') as MockConfig:
            MockConfig.return_value = repo._Repo__config

            result = repo.sync_hop_to_active_branches("test")

        # Should sync to ho-prod, ho-release, and other patch branch (not self)
        assert len(result['synced_branches']) == 3
        assert 'ho-prod' in result['synced_branches']
        assert 'ho-release/0.17.0' in result['synced_branches']
        assert 'ho-patch/456-other' in result['synced_branches']
        assert 'ho-patch/123-test' not in result['synced_branches']  # Not self

    def test_sync_no_active_branches(self, mock_repo):
        """Test sync with no active branches."""
        repo, tmp_path = mock_repo

        # Mock get_active_branches_status to return empty lists
        repo.hgit.get_active_branches_status.return_value = {
            'patch_branches': [],
            'release_branches': []
        }

        result = repo.sync_hop_to_active_branches("test")

        assert len(result['synced_branches']) == 0
        assert len(result['errors']) == 0

    def test_sync_single_branch_with_changes(self, mock_repo):
        """Test sync to single branch with changes."""
        repo, tmp_path = mock_repo

        # Mock get_active_branches_status
        repo.hgit.get_active_branches_status.return_value = {
            'patch_branches': [{'name': 'ho-patch/123-test'}],
            'release_branches': []
        }

        # Mock git operations
        repo.hgit.checkout = Mock()
        repo.hgit.add = Mock()
        repo.hgit.commit = Mock()
        repo.hgit.push_branch = Mock()
        repo.hgit._HGit__git_repo.git.checkout = Mock()
        repo.hgit._HGit__git_repo.git.status = Mock(return_value='M .hop/config\n')

        # Mock Config reload
        with patch('half_orm_dev.repo.Config') as MockConfig:
            MockConfig.return_value = repo._Repo__config

            result = repo.sync_hop_to_active_branches("test sync")

        # Verify sync was successful
        assert len(result['synced_branches']) == 1
        assert 'ho-patch/123-test' in result['synced_branches']
        assert len(result['errors']) == 0

        # Verify git operations
        repo.hgit.checkout.assert_any_call('ho-patch/123-test')
        repo.hgit._HGit__git_repo.git.checkout.assert_called_with('ho-prod', '--', '.hop/')
        repo.hgit.add.assert_called_with('.hop/')
        repo.hgit.commit.assert_called_once()
        repo.hgit.push_branch.assert_called_with('ho-patch/123-test')

    def test_sync_branch_no_changes(self, mock_repo):
        """Test sync to branch with no changes."""
        repo, tmp_path = mock_repo

        # Mock get_active_branches_status
        repo.hgit.get_active_branches_status.return_value = {
            'patch_branches': [{'name': 'ho-patch/123-test'}],
            'release_branches': []
        }

        # Mock git operations - no changes
        repo.hgit.checkout = Mock()
        repo.hgit.add = Mock()
        repo.hgit._HGit__git_repo.git.checkout = Mock()
        repo.hgit._HGit__git_repo.git.status = Mock(return_value='')  # Empty = no changes

        # Mock Config reload
        with patch('half_orm_dev.repo.Config') as MockConfig:
            MockConfig.return_value = repo._Repo__config

            result = repo.sync_hop_to_active_branches("test sync")

        # Verify branch was skipped
        assert len(result['skipped_branches']) == 1
        assert 'ho-patch/123-test' in result['skipped_branches']
        assert len(result['synced_branches']) == 0

    def test_sync_multiple_branches(self, mock_repo):
        """Test sync to multiple branches."""
        repo, tmp_path = mock_repo

        # Mock get_active_branches_status
        repo.hgit.get_active_branches_status.return_value = {
            'patch_branches': [
                {'name': 'ho-patch/123-test'},
                {'name': 'ho-patch/456-feature'}
            ],
            'release_branches': [
                {'name': 'ho-release/0.17.0'}
            ]
        }

        # Mock git operations
        repo.hgit.checkout = Mock()
        repo.hgit.add = Mock()
        repo.hgit.commit = Mock()
        repo.hgit.push_branch = Mock()
        repo.hgit._HGit__git_repo.git.checkout = Mock()
        repo.hgit._HGit__git_repo.git.status = Mock(return_value='M .hop/config\n')

        # Mock Config reload
        with patch('half_orm_dev.repo.Config') as MockConfig:
            MockConfig.return_value = repo._Repo__config

            result = repo.sync_hop_to_active_branches("test sync")

        # Verify all branches synced
        assert len(result['synced_branches']) == 3
        assert 'ho-patch/123-test' in result['synced_branches']
        assert 'ho-patch/456-feature' in result['synced_branches']
        assert 'ho-release/0.17.0' in result['synced_branches']

    def test_sync_branch_error_continues(self, mock_repo):
        """Test sync continues on error for one branch."""
        repo, tmp_path = mock_repo

        # Mock get_active_branches_status
        repo.hgit.get_active_branches_status.return_value = {
            'patch_branches': [
                {'name': 'ho-patch/123-test'},
                {'name': 'ho-patch/456-feature'}
            ],
            'release_branches': []
        }

        # Mock git operations
        call_count = [0]

        def checkout_side_effect(branch):
            call_count[0] += 1
            if call_count[0] == 1:  # First branch fails
                raise Exception("Checkout failed")

        repo.hgit.checkout = Mock(side_effect=checkout_side_effect)
        repo.hgit.add = Mock()
        repo.hgit.commit = Mock()
        repo.hgit.push_branch = Mock()
        repo.hgit._HGit__git_repo.git.checkout = Mock()
        repo.hgit._HGit__git_repo.git.status = Mock(return_value='M .hop/config\n')

        # Mock Config reload
        with patch('half_orm_dev.repo.Config') as MockConfig:
            MockConfig.return_value = repo._Repo__config

            result = repo.sync_hop_to_active_branches("test sync")

        # Verify first branch failed, second succeeded
        assert len(result['errors']) >= 1
        assert 'ho-patch/123-test' in result['errors'][0]
        # Second branch should succeed (checkout is called 3 times: fail, success, return)
        assert call_count[0] >= 2

    def test_sync_returns_to_original_branch(self, mock_repo):
        """Test sync returns to original branch after completion."""
        repo, tmp_path = mock_repo
        repo.hgit.branch = 'ho-prod'

        # Mock get_active_branches_status
        repo.hgit.get_active_branches_status.return_value = {
            'patch_branches': [{'name': 'ho-patch/123-test'}],
            'release_branches': []
        }

        # Mock git operations
        repo.hgit.checkout = Mock()
        repo.hgit.add = Mock()
        repo.hgit.commit = Mock()
        repo.hgit.push_branch = Mock()
        repo.hgit._HGit__git_repo.git.checkout = Mock()
        repo.hgit._HGit__git_repo.git.status = Mock(return_value='M .hop/config\n')

        # Mock Config reload
        with patch('half_orm_dev.repo.Config') as MockConfig:
            MockConfig.return_value = repo._Repo__config

            result = repo.sync_hop_to_active_branches("test sync")

        # Verify returned to ho-prod
        repo.hgit.checkout.assert_called_with('ho-prod')
        # Should be called twice: once for branch, once to return
        assert repo.hgit.checkout.call_count == 2

    def test_sync_commit_message_format(self, mock_repo):
        """Test sync commit message includes reason."""
        repo, tmp_path = mock_repo

        # Mock get_active_branches_status
        repo.hgit.get_active_branches_status.return_value = {
            'patch_branches': [{'name': 'ho-patch/123-test'}],
            'release_branches': []
        }

        # Mock git operations
        repo.hgit.checkout = Mock()
        repo.hgit.add = Mock()
        repo.hgit.commit = Mock()
        repo.hgit.push_branch = Mock()
        repo.hgit._HGit__git_repo.git.checkout = Mock()
        repo.hgit._HGit__git_repo.git.status = Mock(return_value='M .hop/config\n')

        # Mock Config reload
        with patch('half_orm_dev.repo.Config') as MockConfig:
            MockConfig.return_value = repo._Repo__config

            result = repo.sync_hop_to_active_branches("migration 0.17.0 → 0.17.1")

        # Verify commit message
        commit_call = repo.hgit.commit.call_args
        assert commit_call is not None
        commit_msg = commit_call[0][1]  # Second argument to commit()
        assert "[HOP] Sync .hop/ from ho-prod" in commit_msg
        assert "migration 0.17.0 → 0.17.1" in commit_msg
