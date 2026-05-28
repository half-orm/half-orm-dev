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
        repo.config = Mock()
        repo.config.hop_version = "0.17.0"

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
            MockConfig.return_value = repo.config

            result = repo.sync_hop_to_active_branches("test")

        # Should sync to ho-prod, ho-release and other patch branch (not self)
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
            MockConfig.return_value = repo.config

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
            MockConfig.return_value = repo.config

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
            MockConfig.return_value = repo.config

            result = repo.sync_hop_to_active_branches("test sync")

        # Verify all branches synced
        assert len(result['synced_branches']) == 3
        assert 'ho-patch/123-test' in result['synced_branches']
        assert 'ho-patch/456-feature' in result['synced_branches']
        assert 'ho-release/0.17.0' in result['synced_branches']

    def test_sync_branch_checkout_error_raises(self, mock_repo):
        """Phase 1 checkout failure on a non-ho-prod branch raises RepoError and rolls back."""
        from half_orm_dev.repo import RepoError
        repo, tmp_path = mock_repo
        # Use ho-prod as source so it is excluded from targets; only patch
        # branches remain, keeping ordering predictable.
        repo.hgit.branch = 'ho-prod'

        repo.hgit.get_active_branches_status.return_value = {
            'patch_branches': [
                {'name': 'ho-patch/123-test'},
                {'name': 'ho-patch/456-feature'}
            ],
            'release_branches': []
        }

        def checkout_side_effect(branch):
            if branch == 'ho-patch/123-test':
                raise Exception("Checkout failed")

        repo.hgit.checkout = Mock(side_effect=checkout_side_effect)
        repo.hgit.add = Mock()
        repo.hgit.commit = Mock()
        repo.hgit.push_branch = Mock()
        repo.hgit._HGit__git_repo.git.checkout = Mock()
        repo.hgit._HGit__git_repo.git.reset = Mock()
        repo.hgit._HGit__git_repo.git.status = Mock(return_value='M .hop/config\n')

        with patch('half_orm_dev.repo.Config') as MockConfig:
            MockConfig.return_value = repo.config
            with pytest.raises(RepoError, match="Sync commit failed on 'ho-patch/123-test'"):
                repo.sync_hop_to_active_branches("test sync")

        # ho-patch/456-feature was never checked out
        checked_out = [str(c) for c in repo.hgit.checkout.call_args_list]
        assert not any('456-feature' in c for c in checked_out)
        # No push happened (Phase 2 never reached)
        repo.hgit.push_branch.assert_not_called()

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
            MockConfig.return_value = repo.config

            result = repo.sync_hop_to_active_branches("test sync")

        # Verify returned to ho-prod
        repo.hgit.checkout.assert_called_with('ho-prod')
        # Should be called twice: once for branch, once to return
        assert repo.hgit.checkout.call_count == 2

    def test_sync_does_not_reset_ahead_branch(self, mock_repo):
        """Regression: a branch 'ahead' of origin must NOT be reset --hard.

        When a patch branch has local commits not yet pushed (e.g. the
        'Create patch directory' commit created by `hop patch create`),
        sync_hop_to_active_branches must add the .hop/ sync commit ON TOP of
        those commits — not destroy them via `git reset --hard origin/<branch>`.

        Previously the code did `if not synced: reset --hard`, which fired for
        'ahead' status and orphaned any unpushed commit on the patch branch.
        """
        repo, tmp_path = mock_repo
        repo.hgit.branch = 'ho-prod'

        repo.hgit.get_active_branches_status.return_value = {
            'patch_branches': [{'name': 'ho-patch/8-fkeys'}],
            'release_branches': [],
            'staged_branches': [],
        }

        # The patch branch has a local commit not yet on remote → "ahead"
        repo.hgit.is_branch_synced = Mock(return_value=(False, "ahead"))

        repo.hgit.checkout = Mock()
        repo.hgit.add = Mock()
        repo.hgit.commit = Mock()
        repo.hgit.push_branch = Mock()
        repo.hgit._HGit__git_repo.git.checkout = Mock()
        repo.hgit._HGit__git_repo.git.reset = Mock()
        repo.hgit._HGit__git_repo.git.status = Mock(return_value='M .hop/config\n')

        with patch('half_orm_dev.repo.Config') as MockConfig:
            MockConfig.return_value = repo.config
            repo.sync_hop_to_active_branches("migration 0.18.0-a2 → 1.0.0-a1")

        # reset --hard must NOT have been called — that would orphan unpushed commits
        repo.hgit._HGit__git_repo.git.reset.assert_not_called()

    def test_sync_does_reset_behind_branch(self, mock_repo):
        """A branch 'behind' origin IS reset --hard (pull fast-forward equivalent)."""
        repo, tmp_path = mock_repo
        repo.hgit.branch = 'ho-prod'

        repo.hgit.get_active_branches_status.return_value = {
            'patch_branches': [{'name': 'ho-patch/9-other'}],
            'release_branches': [],
            'staged_branches': [],
        }

        repo.hgit.is_branch_synced = Mock(return_value=(False, "behind"))

        repo.hgit.checkout = Mock()
        repo.hgit.add = Mock()
        repo.hgit.commit = Mock()
        repo.hgit.push_branch = Mock()
        repo.hgit._HGit__git_repo.git.checkout = Mock()
        repo.hgit._HGit__git_repo.git.reset = Mock()
        repo.hgit._HGit__git_repo.git.status = Mock(return_value='M .hop/config\n')

        with patch('half_orm_dev.repo.Config') as MockConfig:
            MockConfig.return_value = repo.config
            repo.sync_hop_to_active_branches("migration")

        repo.hgit._HGit__git_repo.git.reset.assert_called_once_with(
            '--hard', 'origin/ho-patch/9-other'
        )

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
            MockConfig.return_value = repo.config

            result = repo.sync_hop_to_active_branches("migration 0.17.0 → 0.17.1")

        # Verify commit message
        commit_call = repo.hgit.commit.call_args
        assert commit_call is not None
        commit_msg = commit_call[0][1]  # Second argument to commit()
        assert "[HOP] Sync .hop/ from ho-prod" in commit_msg
        assert "migration 0.17.0 → 0.17.1" in commit_msg


class TestSyncHopStaleAndErrors:
    """Regression tests for stale-branch cascade and error recovery in sync."""

    @pytest.fixture
    def mock_repo(self, tmp_path):
        hop_dir = tmp_path / '.hop'
        hop_dir.mkdir()
        (hop_dir / 'config').write_text('[halfORM]\nhop_version = "0.17.0"\n')

        repo = Mock(spec=Repo)
        repo.base_dir = str(tmp_path)
        repo.config = Mock()
        repo.config.hop_version = "0.17.0"
        repo.hgit = Mock()
        repo.hgit.branch = 'ho-release/0.17.0'
        repo.hgit._HGit__git_repo = Mock()
        repo.hgit.is_branch_synced = Mock(return_value=(True, "synced"))
        repo.sync_hop_to_active_branches = Repo.sync_hop_to_active_branches.__get__(repo, Repo)
        return repo, tmp_path

    def test_stale_branch_skipped(self, mock_repo):
        """Branch with exists_on_remote=False is excluded from sync targets."""
        repo, tmp_path = mock_repo

        repo.hgit.get_active_branches_status.return_value = {
            'patch_branches': [
                {'name': 'ho-patch/144-stale', 'exists_on_remote': False},
                {'name': 'ho-patch/151-active', 'exists_on_remote': True},
            ],
            'release_branches': [],
        }
        repo.hgit.checkout = Mock()
        repo.hgit.add = Mock()
        repo.hgit.commit = Mock()
        repo.hgit.push_branch = Mock()
        repo.hgit._HGit__git_repo.git.checkout = Mock()
        repo.hgit._HGit__git_repo.git.status = Mock(return_value='M .hop/config\n')

        with patch('half_orm_dev.repo.Config') as MockConfig:
            MockConfig.return_value = repo.config
            result = repo.sync_hop_to_active_branches("test")

        synced = result['synced_branches']
        assert 'ho-patch/151-active' in synced
        assert 'ho-patch/144-stale' not in synced
        # Checkout was never attempted for the stale branch
        checked_out = [str(c) for c in repo.hgit.checkout.call_args_list]
        assert not any('144-stale' in c for c in checked_out)

    def test_failed_commit_raises_and_rolls_back(self, mock_repo):
        """Phase 1 commit failure raises RepoError and rolls back via git reset --hard."""
        from half_orm_dev.repo import RepoError
        repo, tmp_path = mock_repo
        repo.hgit.branch = 'ho-prod'

        repo.hgit.get_active_branches_status.return_value = {
            'patch_branches': [
                {'name': 'ho-patch/100-fails', 'exists_on_remote': True},
                {'name': 'ho-patch/101-ok',    'exists_on_remote': True},
            ],
            'release_branches': [],
        }
        repo.hgit.checkout = Mock()
        repo.hgit.add = Mock()
        repo.hgit.push_branch = Mock()
        repo.hgit._HGit__git_repo.git.checkout = Mock()
        repo.hgit._HGit__git_repo.git.status = Mock(return_value='M .hop/config\n')
        repo.hgit._HGit__git_repo.git.reset = Mock()

        rollback_sha = 'deadbeef1234'
        repo.hgit._HGit__git_repo.head.commit.hexsha = rollback_sha

        # commit always raises (first call — ho-patch/100-fails)
        repo.hgit.commit = Mock(side_effect=Exception("pre-commit hook rejected"))

        with patch('half_orm_dev.repo.Config') as MockConfig:
            MockConfig.return_value = repo.config
            with pytest.raises(RepoError, match="Sync commit failed on 'ho-patch/100-fails'"):
                repo.sync_hop_to_active_branches("test")

        # Rollback: git reset --hard was called with the recorded SHA
        repo.hgit._HGit__git_repo.git.reset.assert_called_with('--hard', rollback_sha)

        # Second branch was never attempted, no push ever happened
        repo.hgit.push_branch.assert_not_called()

    def test_ho_prod_commit_failure_is_soft_skip(self, mock_repo):
        """ho-prod commit failure is non-fatal: staged state cleaned, loop continues."""
        repo, tmp_path = mock_repo

        repo.hgit.get_active_branches_status.return_value = {
            'patch_branches': [{'name': 'ho-patch/151-active', 'exists_on_remote': True}],
            'release_branches': [],
        }
        repo.hgit.add = Mock()
        repo.hgit.push_branch = Mock()
        repo.hgit._HGit__git_repo.git.checkout = Mock()
        repo.hgit._HGit__git_repo.git.status = Mock(return_value='M .hop/config\n')
        repo.hgit._HGit__git_repo.git.reset = Mock()
        repo.hgit._HGit__git_repo.head.commit.hexsha = 'abc123'

        # Track which branch was last checked out to simulate per-branch commit behaviour
        last_branch = ['']

        def checkout_side_effect(branch):
            last_branch[0] = branch

        repo.hgit.checkout = Mock(side_effect=checkout_side_effect)

        def commit_side_effect(*args, **kwargs):
            if last_branch[0] == 'ho-prod':
                raise Exception("Direct commits on ho-prod are not allowed")
            return 'sha-151'

        repo.hgit.commit = Mock(side_effect=commit_side_effect)

        with patch('half_orm_dev.repo.Config') as MockConfig:
            MockConfig.return_value = repo.config
            result = repo.sync_hop_to_active_branches("test")

        # Patch branch synced despite ho-prod failure
        assert 'ho-patch/151-active' in result['synced_branches']
        # ho-prod error collected as warning, not raised
        assert any('ho-prod' in e for e in result['errors'])
        # staged state was cleaned (reset HEAD called)
        repo.hgit._HGit__git_repo.git.reset.assert_any_call('HEAD')
