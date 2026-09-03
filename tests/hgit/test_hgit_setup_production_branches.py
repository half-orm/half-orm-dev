"""
Tests for HGit.setup_production_branches().
"""

import pytest
from unittest.mock import Mock

from half_orm_dev.hgit import HGit


@pytest.fixture
def hgit():
    """HGit instance with mocked internals."""
    instance = HGit.__new__(HGit)
    instance._HGit__git_repo = Mock()
    instance._HGit__repo = None
    instance._HGit__snapshot = {}
    return instance


def _make_remote_ref(name):
    ref = Mock()
    ref.name = f'origin/{name}'
    return ref


class _FakeRefs:
    """Supports both iteration and refs[branch_name] lookup, like git.Remote.refs."""

    def __init__(self, refs):
        self._by_name = {r.name.replace('origin/', ''): r for r in refs}

    def __iter__(self):
        return iter(self._by_name.values())

    def __getitem__(self, branch_name):
        return self._by_name[branch_name]


class TestSetupProductionBranches:
    def test_creates_local_tracking_branch_for_each_remote_ho_prod_branch(self, hgit):
        git_repo = hgit._HGit__git_repo
        git_repo.remote.return_value.refs = _FakeRefs([
            _make_remote_ref('ho-prod'),
            _make_remote_ref('ho-prod-1.0.0'),
        ])
        git_repo.branches = []

        hgit.setup_production_branches()

        assert git_repo.create_head.call_count == 2
        created = {c.args[0] for c in git_repo.create_head.call_args_list}
        assert created == {'ho-prod', 'ho-prod-1.0.0'}

    def test_skips_branch_that_already_exists_locally(self, hgit):
        git_repo = hgit._HGit__git_repo
        git_repo.remote.return_value.refs = _FakeRefs([_make_remote_ref('ho-prod')])
        existing_branch = Mock()
        existing_branch.name = 'ho-prod'
        git_repo.branches = [existing_branch]

        hgit.setup_production_branches()

        git_repo.create_head.assert_not_called()

    def test_warns_on_stderr_when_branch_creation_fails(self, hgit, capsys):
        """
        Regression: a branch that fails to be created here silently breaks
        `hop rollback` for that version later - must be visible now, and
        must not block creating the other branches.
        """
        git_repo = hgit._HGit__git_repo
        git_repo.remote.return_value.refs = _FakeRefs([
            _make_remote_ref('ho-prod'),
            _make_remote_ref('ho-prod-1.0.0'),
        ])
        git_repo.branches = []
        git_repo.create_head.side_effect = [Exception("boom"), Mock()]

        hgit.setup_production_branches()

        stderr = capsys.readouterr().err
        assert 'ho-prod' in stderr
        assert 'boom' in stderr
        # The second branch still gets created despite the first failing
        assert git_repo.create_head.call_count == 2
