"""
Tests for Repo.recover() and the sync-lock guard in sync_and_validate_ho_prod().
"""

import os
import pytest
from unittest.mock import Mock, MagicMock, patch, call
from git.exc import GitCommandError
from half_orm_dev.repo import Repo, RepoError


BEFORE_SHA = 'aabbccdd' * 4
CURRENT_SHA = 'deadbeef' * 4
LOCK_TAG = 'lock-ho-release-1.0.0-1704123456789'


class TestRecoverLockGuard:
    """Guard in sync_and_validate_ho_prod blocks when lock file exists."""

    @pytest.fixture
    def mock_repo(self, tmp_path):
        git_dir = tmp_path / '.git'
        git_dir.mkdir()
        repo = Mock(spec=Repo)
        repo.base_dir = str(tmp_path)
        repo.hgit = Mock()
        repo.hgit.git_repo = Mock()
        repo.hgit.git_repo.active_branch.name = 'ho-release/1.0.0'
        repo.hgit.git_repo.is_dirty.return_value = False
        repo.sync_and_validate_ho_prod = Repo.sync_and_validate_ho_prod.__get__(repo, Repo)
        return repo, tmp_path

    def test_guard_raises_when_lock_file_present(self, mock_repo):
        repo, tmp_path = mock_repo
        lock_file = tmp_path / '.git' / 'hop-sync-lock'
        lock_file.write_text(LOCK_TAG)

        with pytest.raises(RepoError, match="hop recover"):
            repo.sync_and_validate_ho_prod()

    def test_guard_passes_when_no_lock_file(self, mock_repo):
        repo, tmp_path = mock_repo
        # No lock file — should proceed (will fail later on git ops, but not on our guard)
        try:
            repo.sync_and_validate_ho_prod()
        except RepoError as e:
            assert "hop recover" not in str(e)
        except Exception:
            pass  # other git errors are fine here


class TestRecover:
    """Tests for Repo.recover()."""

    @pytest.fixture
    def mock_repo(self, tmp_path):
        git_dir = tmp_path / '.git'
        git_dir.mkdir()

        repo = Mock(spec=Repo)
        repo.base_dir = str(tmp_path)
        repo.hgit = Mock()
        repo.hgit._HGit__git_repo = Mock()
        repo.hgit._HGit__git_repo.active_branch.name = 'ho-release/1.0.0'

        repo.recover = Repo.recover.__get__(repo, Repo)
        repo._recover_cleanup_refs = Repo._recover_cleanup_refs.__get__(repo, Repo)
        return repo, tmp_path

    def _write_lock(self, tmp_path, tag=LOCK_TAG):
        (tmp_path / '.git' / 'hop-sync-lock').write_text(tag)

    def _write_before_ref(self, repo, branch, sha=BEFORE_SHA):
        repo.hgit._HGit__git_repo.git.for_each_ref.return_value = (
            f'refs/hop/sync/before/{branch} {sha}'
        )

    # --- No lock file ---

    def test_no_lock_file_returns_error(self, mock_repo):
        repo, tmp_path = mock_repo
        result = repo.recover()
        assert result['errors']
        assert 'hop-sync-lock' in result['errors'][0]
        assert result['pushed_branches'] == []
        assert result['cleaned_branches'] == []

    # --- Lock not on origin ---

    def test_lock_expired_on_origin_cleans_up(self, mock_repo):
        repo, tmp_path = mock_repo
        self._write_lock(tmp_path)
        repo.hgit._HGit__git_repo.git.ls_remote.return_value = ''  # not found
        repo.hgit._HGit__git_repo.git.for_each_ref.return_value = ''

        result = repo.recover()

        assert any('Lock tag not found' in e for e in result['errors'])
        assert not (tmp_path / '.git' / 'hop-sync-lock').exists()

    # --- Phase 2 completion: branch has sync commit, push it ---

    def test_phase2_pushes_committed_branch(self, mock_repo):
        repo, tmp_path = mock_repo
        self._write_lock(tmp_path)

        branch = 'ho-release/1.0.0'
        repo.hgit._HGit__git_repo.git.ls_remote.return_value = f'abc\trefs/tags/{LOCK_TAG}'
        repo.hgit._HGit__git_repo.git.for_each_ref.return_value = (
            f'refs/hop/sync/before/{branch} {BEFORE_SHA}'
        )
        # Current HEAD differs from before → Phase 1 commit is present
        repo.hgit._HGit__git_repo.head.commit.hexsha = CURRENT_SHA

        result = repo.recover()

        repo.hgit.push_branch.assert_called_once_with(branch)
        assert branch in result['pushed_branches']
        assert result['cleaned_branches'] == []
        assert not (tmp_path / '.git' / 'hop-sync-lock').exists()

    # --- Phase 1 cleanup: branch still at before-SHA, restore clean state ---

    def test_phase1_cleanup_restores_clean_state(self, mock_repo):
        repo, tmp_path = mock_repo
        self._write_lock(tmp_path)

        branch = 'ho-release/1.0.0'
        repo.hgit._HGit__git_repo.git.ls_remote.return_value = f'abc\trefs/tags/{LOCK_TAG}'
        repo.hgit._HGit__git_repo.git.for_each_ref.return_value = (
            f'refs/hop/sync/before/{branch} {BEFORE_SHA}'
        )
        # Current HEAD equals before → Phase 1 did not complete
        repo.hgit._HGit__git_repo.head.commit.hexsha = BEFORE_SHA

        result = repo.recover()

        git = repo.hgit._HGit__git_repo.git
        git.reset.assert_called_once_with('HEAD')
        git.checkout.assert_called_once_with('--', '.hop/')
        assert branch in result['cleaned_branches']
        assert result['pushed_branches'] == []
        repo.hgit.push_branch.assert_not_called()
        assert not (tmp_path / '.git' / 'hop-sync-lock').exists()

    # --- Mixed: two branches, one pushed one cleaned ---

    def test_mixed_branches(self, mock_repo):
        repo, tmp_path = mock_repo
        self._write_lock(tmp_path)

        branch_push = 'ho-release/1.0.0'
        branch_clean = 'ho-patch/42-foo'
        repo.hgit._HGit__git_repo.git.ls_remote.return_value = f'abc\trefs/tags/{LOCK_TAG}'
        repo.hgit._HGit__git_repo.git.for_each_ref.return_value = (
            f'refs/hop/sync/before/{branch_push} {BEFORE_SHA}\n'
            f'refs/hop/sync/before/{branch_clean} {BEFORE_SHA}'
        )

        # Set hexsha via checkout side_effect so each branch sees its own HEAD state
        shas = {branch_push: CURRENT_SHA, branch_clean: BEFORE_SHA}
        def set_head_on_checkout(branch):
            repo.hgit._HGit__git_repo.head.commit.hexsha = shas[branch]
        repo.hgit.checkout = Mock(side_effect=set_head_on_checkout)

        result = repo.recover()

        assert branch_push in result['pushed_branches']
        assert branch_clean in result['cleaned_branches']
        assert result['errors'] == []

    # --- Lock released correctly ---

    def test_lock_released_after_recovery(self, mock_repo):
        repo, tmp_path = mock_repo
        self._write_lock(tmp_path)

        repo.hgit._HGit__git_repo.git.ls_remote.return_value = f'abc\trefs/tags/{LOCK_TAG}'
        repo.hgit._HGit__git_repo.git.for_each_ref.return_value = ''

        result = repo.recover()

        repo.hgit.release_branch_lock.assert_called_once_with(LOCK_TAG)
        assert result['lock_tag'] == LOCK_TAG

    # --- Checkout failure on a branch ---

    def test_checkout_failure_recorded_in_errors(self, mock_repo):
        repo, tmp_path = mock_repo
        self._write_lock(tmp_path)

        branch = 'ho-release/1.0.0'
        repo.hgit._HGit__git_repo.git.ls_remote.return_value = f'abc\trefs/tags/{LOCK_TAG}'
        repo.hgit._HGit__git_repo.git.for_each_ref.return_value = (
            f'refs/hop/sync/before/{branch} {BEFORE_SHA}'
        )
        repo.hgit.checkout.side_effect = GitCommandError('checkout', 128)

        result = repo.recover()

        assert any(branch in e and 'checkout failed' in e for e in result['errors'])
        assert result['pushed_branches'] == []
        assert result['cleaned_branches'] == []