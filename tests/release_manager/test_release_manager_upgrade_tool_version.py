"""
A production upgrade applies each release with the half_orm_dev it was made
with, and refuses otherwise -- before anything is written.

The installed version used to be compared only with the release already in
production, when the CLI started; the releases about to be applied were not
checked, so a server could apply a release prepared with half_orm_dev 2.x
(and half-orm 2.x) using 1.x.
"""
from unittest.mock import Mock, patch

import pytest

from half_orm_dev.release_manager import ReleaseManager, ReleaseManagerError

INSTALLED = '2.0.0-a1'

# Taken at import, before the autouse fixture of conftest.py replaces it for
# the tests that are not about it.
_REAL_RELEASE_HOP_VERSION = ReleaseManager.__dict__['_release_hop_version']


def _manager(versions_by_release):
    repo = Mock()
    repo.base_dir = '/nowhere'
    mgr = ReleaseManager.__new__(ReleaseManager)
    mgr._repo = repo
    mgr._release_hop_version = lambda version: versions_by_release.get(version)
    return mgr


@pytest.fixture(autouse=True)
def installed():
    with patch('half_orm_dev.utils.hop_version', return_value=INSTALLED):
        yield


def test_all_releases_made_with_the_installed_version():
    _manager({'1.4.0': INSTALLED, '1.5.0': INSTALLED})._check_tool_version_for_releases(
        ['1.4.0', '1.5.0'])


def test_spelling_of_a_pre_release_does_not_matter():
    "2.0.0-a1 and 2.0.0a1 are one version"
    _manager({'1.4.0': '2.0.0a1'})._check_tool_version_for_releases(['1.4.0'])


@pytest.mark.parametrize('made_with', ['1.2.0-a1', '2.0.0-a2', '2.0.0', '2.1.0'])
def test_any_other_version_is_refused(made_with):
    "older or newer, pre-release or not: equal or nothing"
    with pytest.raises(ReleaseManagerError) as exc:
        _manager({'1.4.0': made_with})._check_tool_version_for_releases(['1.4.0'])
    message = str(exc.value)
    assert f'pip install half-orm-dev=={made_with}' in message
    assert 'Nothing was applied.' in message
    assert '--to-release' not in message


def test_a_path_crossing_two_versions_says_how_far_to_go():
    mgr = _manager({'1.3.8': INSTALLED, '1.3.9': INSTALLED, '1.4.0': '2.0.0-a2'})
    with pytest.raises(ReleaseManagerError) as exc:
        mgr._check_tool_version_for_releases(['1.3.8', '1.3.9', '1.4.0'])
    message = str(exc.value)
    assert 'Release 1.4.0 was made with half_orm_dev 2.0.0-a2' in message
    lines = [line.strip() for line in message.splitlines()]
    start = lines.index('half_orm dev upgrade --to-release 1.3.9')
    assert lines[start:start + 3] == [
        'half_orm dev upgrade --to-release 1.3.9',
        'pip install half-orm-dev==2.0.0-a2',
        'half_orm dev upgrade',
    ]


def test_an_unreadable_release_is_refused():
    with pytest.raises(ReleaseManagerError) as exc:
        _manager({})._check_tool_version_for_releases(['1.4.0'])
    assert 'ho-prod-1.4.0:.hop/config' in str(exc.value)


class TestReleaseHopVersion:
    """Reading the version a release was made with, without checking it out."""

    def _mgr(self, show):
        mgr = ReleaseManager.__new__(ReleaseManager)
        mgr._repo = Mock()
        git = mgr._repo.hgit._HGit__git_repo.git
        git.show.side_effect = show
        return mgr, git

    def test_reads_hop_version_from_the_release_branch(self):
        mgr, git = self._mgr(lambda ref: '[halfORM]\nhop_version = 1.2.0-a1\n')
        assert _REAL_RELEASE_HOP_VERSION(mgr, '1.4.0') == '1.2.0-a1'
        git.fetch.assert_called_once_with(
            'origin', 'ho-prod-1.4.0:refs/remotes/origin/ho-prod-1.4.0')
        git.show.assert_called_once_with('origin/ho-prod-1.4.0:.hop/config')

    def test_falls_back_on_the_local_branch(self):
        def show(ref):
            if ref.startswith('origin/'):
                raise Exception('unknown revision')
            return '[halfORM]\nhop_version = 2.0.0-a1\n'
        mgr, _ = self._mgr(show)
        assert _REAL_RELEASE_HOP_VERSION(mgr, '1.4.0') == '2.0.0-a1'

    @pytest.mark.parametrize('content', ['', '[halfORM]\n', 'not an ini file', '[other]\nx = 1\n'])
    def test_no_version_recorded(self, content):
        mgr, _ = self._mgr(lambda ref: content)
        assert _REAL_RELEASE_HOP_VERSION(mgr, '1.4.0') is None

    def test_branch_not_found(self):
        def show(ref):
            raise Exception('unknown revision')
        mgr, _ = self._mgr(show)
        assert _REAL_RELEASE_HOP_VERSION(mgr, '1.4.0') is None


def test_upgrade_production_checks_before_writing():
    """The check runs before the snapshot or the backup, dry run included."""
    import inspect
    source = inspect.getsource(ReleaseManager.upgrade_production)
    check = source.index('self._check_tool_version_for_releases(upgrade_path)')
    assert check < source.index('# === DRY RUN')
    assert check < source.index('SNAPSHOT OR BACKUP')
