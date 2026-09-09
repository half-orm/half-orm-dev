"""
E2E test: `hop check` brings the local repository in line with origin,
without destroying work along the way.

Origin is the source of truth, so a ho-* branch deleted there has no
reason to survive locally - including the one currently checked out,
which used to be silently exempt (exclude_current=True) and therefore
survived every `hop check`, no matter how many times it ran.

The counterpart is that deletion must not be blind: `prune_local_branches`
used `git branch -D`, so a single "yes" to a blanket prompt destroyed a
patch branch whose remote had been deleted before its work was merged -
the last copy of that work. Those branches are now listed apart and need
their own explicit confirmation.
"""
import pytest


pytestmark = pytest.mark.e2e


def _local_branches(run):
    result = run(['git', 'branch', '--format=%(refname:short)'])
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _current_branch(run):
    return run(['git', 'rev-parse', '--abbrev-ref', 'HEAD']).stdout.strip()


@pytest.fixture
def stale_branches(project_with_release):
    """A stale branch with work on it, and one with nothing of its own."""
    env = project_with_release
    run = env['run']
    project_dir = env['project_dir']
    version = env['release_version']

    # Carries a commit of its own, and is not on origin
    run(['git', 'checkout', f'ho-release/{version}'])
    run(['half_orm', 'dev', 'patch', 'create', '2-beta'])
    (project_dir / 'Patches' / '2-beta' / '01_beta.sql').write_text(
        'CREATE TABLE beta (id SERIAL PRIMARY KEY);'
    )
    run(['git', 'add', '.'])
    run(['git', 'commit', '-m', 'Work that only exists here'])
    run(['git', 'push', 'origin', '--delete', 'ho-patch/2-beta'], check=False)

    # Points at ho-prod: stale, but holds nothing that would be lost
    run(['git', 'checkout', 'ho-prod'])
    run(['git', 'branch', 'ho-patch/9-nothing-of-its-own', 'ho-prod'])

    return env


class TestCheckStaleBranchCleanup:
    """Stale branches go, unmerged work does not."""

    def test_blanket_confirmation_spares_unmerged_work(self, stale_branches):
        run = stale_branches['run']

        # yes to the plain branches, no to the ones holding work
        result = run(['half_orm', 'dev', 'check'], input_text='y\nn\n', check=False)
        assert result.returncode == 0, (
            f"check should succeed.\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )

        assert 'unmerged commit' in result.stdout, (
            f"check must say which branches hold work.\nSTDOUT: {result.stdout}"
        )

        branches = _local_branches(run)
        assert 'ho-patch/9-nothing-of-its-own' not in branches, (
            "a stale branch holding nothing of its own should be gone"
        )
        assert 'ho-patch/2-beta' in branches, (
            "a stale branch holding unmerged work must survive a blanket yes"
        )

    def test_second_confirmation_deletes_unmerged_branch(self, stale_branches):
        run = stale_branches['run']

        run(['half_orm', 'dev', 'check'], input_text='y\ny\n', check=False)

        assert 'ho-patch/2-beta' not in _local_branches(run), (
            "an explicit second confirmation must delete it"
        )

    def test_current_stale_branch_is_deleted_too(self, stale_branches):
        run = stale_branches['run']

        # Standing on the stale branch that holds no work of its own
        run(['git', 'checkout', 'ho-patch/9-nothing-of-its-own'])
        assert _current_branch(run) == 'ho-patch/9-nothing-of-its-own'

        result = run(['half_orm', 'dev', 'check'], input_text='y\nn\n', check=False)
        assert result.returncode == 0, (
            f"check should succeed.\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )

        assert 'ho-patch/9-nothing-of-its-own' not in _local_branches(run), (
            "the branch checked out must not be exempt from the cleanup"
        )
        assert _current_branch(run) == 'ho-prod', (
            "check should leave the developer on ho-prod after removing the "
            "branch they stood on"
        )
        assert 'now on' in result.stdout, (
            f"the branch switch must be reported.\nSTDOUT: {result.stdout}"
        )
