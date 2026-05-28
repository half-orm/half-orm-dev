"""
Tests for HGit snapshot API:
  capture_branches_snapshot(), rollback_to_snapshot(),
  snapshot property, update_snapshot().
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from git.exc import GitCommandError

from half_orm_dev.hgit import HGit


@pytest.fixture
def hgit():
    """HGit instance with mocked internals."""
    instance = HGit.__new__(HGit)
    instance._HGit__git_repo = Mock()
    instance._HGit__repo = None
    instance._HGit__snapshot = {}
    return instance


def _make_branches_status(
    prod='ho-prod',
    release_branches=None,
    patch_branches=None,
):
    """Build a branches_status dict as returned by get_active_branches_status."""
    return {
        'prod_branch': {'name': prod} if prod else None,
        'release_branches': release_branches or [],
        'patch_branches': patch_branches or [],
        'staged_branches': [],
    }


class TestCaptureBranchesSnapshot:

    def test_returns_sha_for_all_active_branches(self, hgit):
        status = _make_branches_status(
            release_branches=[{'name': 'ho-release/0.1.0', 'exists_on_remote': True}],
            patch_branches=[{'name': 'ho-patch/1-feat', 'exists_on_remote': True}],
        )
        hgit.get_active_branches_status = Mock(return_value=status)

        def head(name):
            m = Mock()
            m.commit.hexsha = f'sha-{name}'
            return m

        hgit._HGit__git_repo.heads.__getitem__ = Mock(side_effect=head)

        snapshot = hgit.capture_branches_snapshot()

        assert snapshot == {
            'ho-prod': 'sha-ho-prod',
            'ho-release/0.1.0': 'sha-ho-release/0.1.0',
            'ho-patch/1-feat': 'sha-ho-patch/1-feat',
        }

    def test_skips_stale_branches(self, hgit):
        status = _make_branches_status(
            patch_branches=[
                {'name': 'ho-patch/1-feat', 'exists_on_remote': True},
                {'name': 'ho-patch/2-stale', 'exists_on_remote': False},
            ],
        )
        hgit.get_active_branches_status = Mock(return_value=status)

        def head(name):
            m = Mock()
            m.commit.hexsha = f'sha-{name}'
            return m

        hgit._HGit__git_repo.heads.__getitem__ = Mock(side_effect=head)

        snapshot = hgit.capture_branches_snapshot()

        assert 'ho-patch/2-stale' not in snapshot
        assert 'ho-patch/1-feat' in snapshot

    def test_returns_empty_dict_when_status_raises(self, hgit):
        hgit.get_active_branches_status = Mock(side_effect=Exception("network error"))

        snapshot = hgit.capture_branches_snapshot()

        assert snapshot == {}

    def test_skips_branch_when_head_missing(self, hgit):
        status = _make_branches_status(
            patch_branches=[{'name': 'ho-patch/missing', 'exists_on_remote': True}],
        )
        hgit.get_active_branches_status = Mock(return_value=status)
        hgit._HGit__git_repo.heads.__getitem__ = Mock(side_effect=KeyError('not found'))

        snapshot = hgit.capture_branches_snapshot()

        assert 'ho-patch/missing' not in snapshot

    def test_no_prod_branch(self, hgit):
        status = _make_branches_status(prod=None)
        hgit.get_active_branches_status = Mock(return_value=status)
        hgit._HGit__git_repo.heads.__getitem__ = Mock()

        snapshot = hgit.capture_branches_snapshot()

        assert snapshot == {}


class TestSnapshotProperty:

    def test_snapshot_property_returns_stored_snapshot(self, hgit):
        hgit._HGit__snapshot = {'ho-prod': 'sha-abc'}
        assert hgit.snapshot == {'ho-prod': 'sha-abc'}

    def test_snapshot_property_initially_empty(self, hgit):
        assert hgit.snapshot == {}

    def test_update_snapshot_refreshes_stored_snapshot(self, hgit):
        status = _make_branches_status(
            patch_branches=[{'name': 'ho-patch/1-feat', 'exists_on_remote': True}],
        )
        hgit.get_active_branches_status = Mock(return_value=status)

        def head(name):
            m = Mock()
            m.commit.hexsha = f'sha-{name}'
            return m

        hgit._HGit__git_repo.heads.__getitem__ = Mock(side_effect=head)

        hgit.update_snapshot()

        assert hgit.snapshot == {
            'ho-prod': 'sha-ho-prod',
            'ho-patch/1-feat': 'sha-ho-patch/1-feat',
        }

    def test_update_snapshot_replaces_previous(self, hgit):
        hgit._HGit__snapshot = {'ho-prod': 'old-sha'}
        hgit.get_active_branches_status = Mock(return_value=_make_branches_status())

        def head(name):
            m = Mock()
            m.commit.hexsha = 'new-sha'
            return m

        hgit._HGit__git_repo.heads.__getitem__ = Mock(side_effect=head)

        hgit.update_snapshot()

        assert hgit.snapshot['ho-prod'] == 'new-sha'


def _mock_active_branch(hgit, branch_name: str):
    """Set active_branch.__str__ so hgit.branch returns branch_name."""
    hgit._HGit__git_repo.active_branch.__str__ = Mock(return_value=branch_name)


class TestRollbackToSnapshot:

    def test_resets_each_branch_and_returns_to_original(self, hgit):
        _mock_active_branch(hgit, 'ho-prod')

        snapshot = {
            'ho-prod': 'sha-prod',
            'ho-release/0.1.0': 'sha-rel',
            'ho-patch/1-feat': 'sha-patch',
        }

        mock_head = Mock()
        hgit._HGit__git_repo.heads.__getitem__ = Mock(return_value=mock_head)

        result = hgit.rollback_to_snapshot(snapshot)

        assert set(result['reset']) == set(snapshot.keys())
        assert result['errors'] == []
        hgit._HGit__git_repo.heads.__getitem__.assert_called_with('ho-prod')

    def test_uses_stored_snapshot_when_no_arg(self, hgit):
        _mock_active_branch(hgit, 'ho-prod')
        hgit._HGit__snapshot = {'ho-prod': 'sha-stored'}

        mock_head = Mock()
        hgit._HGit__git_repo.heads.__getitem__ = Mock(return_value=mock_head)

        result = hgit.rollback_to_snapshot()

        assert 'ho-prod' in result['reset']
        assert result['errors'] == []

    def test_reports_error_for_failed_branch(self, hgit):
        _mock_active_branch(hgit, 'ho-prod')

        snapshot = {
            'ho-prod': 'sha-prod',
            'ho-patch/1-broken': 'sha-broken',
        }

        def head(name):
            if name == 'ho-patch/1-broken':
                raise GitCommandError('checkout', 128)
            return Mock()

        hgit._HGit__git_repo.heads.__getitem__ = Mock(side_effect=head)

        result = hgit.rollback_to_snapshot(snapshot)

        failed_branches = [b for b, _ in result['errors']]
        assert 'ho-patch/1-broken' in failed_branches
        assert 'ho-prod' in result['reset']

    def test_empty_snapshot_returns_to_original(self, hgit):
        _mock_active_branch(hgit, 'ho-prod')
        mock_head = Mock()
        hgit._HGit__git_repo.heads.__getitem__ = Mock(return_value=mock_head)

        result = hgit.rollback_to_snapshot({})

        assert result['reset'] == []
        assert result['errors'] == []
        hgit._HGit__git_repo.heads.__getitem__.assert_called_once_with('ho-prod')

    def test_empty_stored_snapshot_returns_to_original(self, hgit):
        _mock_active_branch(hgit, 'ho-prod')
        mock_head = Mock()
        hgit._HGit__git_repo.heads.__getitem__ = Mock(return_value=mock_head)

        result = hgit.rollback_to_snapshot()  # no arg, uses empty __snapshot

        assert result['reset'] == []
        assert result['errors'] == []
