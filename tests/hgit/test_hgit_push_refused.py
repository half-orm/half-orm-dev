"""
Pushes refused by the remote, on real git repositories.

GitPython's `Remote.push()` returns a ref the remote refused instead of
raising: HGit must turn the refusal into an error, or hop reports a
success while nothing reached origin (sync of a diverged branch, patch
number reservation by a tag that already exists, ...).
"""

import subprocess

import git
import pytest
from git.exc import GitCommandError

from half_orm_dev.hgit import HGit


def _git(cwd, *args):
    return subprocess.run(
        ['git', *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def two_clones(tmp_path):
    """A bare origin with a `main` branch, and two clones of it, `a` and `b`."""
    origin = tmp_path / 'origin.git'
    _git(tmp_path, 'init', '-q', '--bare', '-b', 'main', str(origin))
    clones = {}
    for name in ('a', 'b'):
        _git(tmp_path, 'clone', '-q', str(origin), name)
        clone = tmp_path / name
        _git(clone, 'config', 'user.email', 'test@example.com')
        _git(clone, 'config', 'user.name', 'Test')
        _git(clone, 'config', 'commit.gpgsign', 'false')
        _git(clone, 'config', 'tag.gpgsign', 'false')
        clones[name] = clone
    _git(clones['a'], 'commit', '-q', '--allow-empty', '-m', 'init')
    _git(clones['a'], 'push', '-q', 'origin', 'HEAD:main')
    _git(clones['b'], 'pull', '-q', 'origin', 'main')
    return origin, clones


def _hgit(path):
    hgit = HGit()
    hgit._HGit__git_repo = git.Repo(path)
    return hgit


class TestPushRefused:

    def test_push_branch_refused_raises(self, two_clones):
        """A non-fast-forward push is refused: push_branch raises."""
        _, clones = two_clones
        # b rewrites main on origin
        _git(clones['b'], 'commit', '-q', '--amend', '--allow-empty', '-m', 'rewritten')
        _git(clones['b'], 'push', '-q', '-f', 'origin', 'main')
        # a commits on top of the old history
        _git(clones['a'], 'commit', '-q', '--allow-empty', '-m', 'on old history')

        with pytest.raises(GitCommandError, match='rejected'):
            _hgit(clones['a']).push_branch('main')

    def test_push_tag_already_on_remote_raises(self, two_clones):
        """A tag already on origin is refused: push_tag raises.

        This is how a patch number is reserved: two developers must not
        both get it.
        """
        _, clones = two_clones
        _git(clones['b'], 'tag', 'ho-patch/42')
        _git(clones['b'], 'push', '-q', 'origin', 'ho-patch/42')
        _git(clones['a'], 'commit', '-q', '--allow-empty', '-m', 'other')
        _git(clones['a'], 'tag', 'ho-patch/42')

        with pytest.raises(GitCommandError, match='already exists'):
            _hgit(clones['a']).push_tag('ho-patch/42')

    def test_push_branch_accepted(self, two_clones):
        """An accepted push does not raise."""
        origin, clones = two_clones
        _git(clones['a'], 'commit', '-q', '--allow-empty', '-m', 'next')
        _hgit(clones['a']).push_branch('main')
        assert _git(origin, 'rev-parse', 'main') == _git(clones['a'], 'rev-parse', 'main')


class TestRenameBranchWithRemote:

    def test_rename_local_and_remote(self, two_clones):
        origin, clones = two_clones
        a = clones['a']
        _git(a, 'checkout', '-q', '-b', 'ho-patch/42-x')
        _git(a, 'commit', '-q', '--allow-empty', '-m', 'work')
        _git(a, 'push', '-q', '-u', 'origin', 'ho-patch/42-x')
        sha = _git(a, 'rev-parse', 'HEAD')

        _hgit(a).rename_branch_with_remote('ho-patch/42-x', 'ho-detached/42-x')

        assert _git(origin, 'branch', '--list', 'ho-patch/42-x') == ''
        assert _git(origin, 'rev-parse', 'ho-detached/42-x') == sha
        assert _git(a, 'branch', '--show-current') == 'ho-detached/42-x'
        assert _git(a, 'rev-parse', '--abbrev-ref', 'ho-detached/42-x@{upstream}') \
            == 'origin/ho-detached/42-x'

    def test_rename_remote_only_branch(self, two_clones):
        """The branch exists only on origin (never checked out in this clone)."""
        origin, clones = two_clones
        _git(clones['b'], 'checkout', '-q', '-b', 'ho-patch/42-x')
        _git(clones['b'], 'commit', '-q', '--allow-empty', '-m', 'work')
        _git(clones['b'], 'push', '-q', 'origin', 'ho-patch/42-x')
        sha = _git(clones['b'], 'rev-parse', 'HEAD')
        a = clones['a']
        _git(a, 'fetch', '-q', 'origin')

        _hgit(a).rename_branch_with_remote('ho-patch/42-x', 'ho-detached/42-x')

        assert _git(origin, 'branch', '--list', 'ho-patch/42-x') == ''
        assert _git(origin, 'rev-parse', 'ho-detached/42-x') == sha
        assert _git(a, 'rev-parse', 'ho-detached/42-x') == sha

    def test_refused_push_leaves_everything_unchanged(self, two_clones):
        """If origin refuses the new name, neither side is renamed."""
        origin, clones = two_clones
        a, b = clones['a'], clones['b']
        _git(a, 'checkout', '-q', '-b', 'ho-patch/42-x')
        _git(a, 'push', '-q', '-u', 'origin', 'ho-patch/42-x')
        # The new name appears on origin after a's last fetch
        _git(b, 'push', '-q', 'origin', 'main:ho-detached/42-x')
        _git(b, 'commit', '-q', '--allow-empty', '-m', 'move')
        _git(b, 'push', '-q', '-f', 'origin', 'HEAD:ho-detached/42-x')

        with pytest.raises(GitCommandError):
            _hgit(a).rename_branch_with_remote('ho-patch/42-x', 'ho-detached/42-x')

        assert _git(origin, 'branch', '--list', 'ho-patch/42-x') != ''
        assert _git(a, 'branch', '--show-current') == 'ho-patch/42-x'

    def test_new_name_already_exists(self, two_clones):
        _, clones = two_clones
        a = clones['a']
        _git(a, 'branch', 'ho-patch/42-x')
        _git(a, 'branch', 'ho-detached/42-x')
        with pytest.raises(GitCommandError, match='already exists'):
            _hgit(a).rename_branch_with_remote('ho-patch/42-x', 'ho-detached/42-x')
