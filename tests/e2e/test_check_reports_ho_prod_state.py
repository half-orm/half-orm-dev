"""
E2E regression test: `hop check` reports the repository state, not the
current branch's stale copy of it.

Reported symptom: on a patch branch whose remote was deleted, `hop check`
kept printing production 0.3.9 and a release 0.3.10 that had long been
promoted - unchanged however many times it ran - while a fresh clone of
the same repository showed production 0.3.11.

Everything in that panel was read from the working tree: the
model/schema.sql symlink and .hop/releases/*.toml of the branch the
developer stood on. On any branch, .hop/ is a synced copy frozen at the
last sync that branch received; a branch that stopped receiving them
keeps answering with a world that no longer exists. Meanwhile
check_and_update() had already pulled ho-prod, so the right answer was
sitting in the repository.

Both are now read on ho-prod with `git show`, and the gap is reported
instead of hidden.
"""
import pytest


pytestmark = pytest.mark.e2e


class TestCheckReportsHoProdState:
    """`hop check` must not report a stale branch's view as fact."""

    def test_production_version_comes_from_ho_prod(self, project_with_release):
        env = project_with_release
        run = env['run']
        project_dir = env['project_dir']
        version = env['release_version']

        run(['git', 'checkout', f'ho-release/{version}'])
        run(['half_orm', 'dev', 'patch', 'create', '1-alpha'])
        run(['git', 'checkout', f'ho-release/{version}'])
        run(['half_orm', 'dev', 'patch', 'create', '2-beta'])

        # Where the orphan branch will be pinned: before any propagation.
        sha_before = run(['git', 'rev-parse', 'ho-patch/2-beta']).stdout.strip()

        run(['git', 'checkout', 'ho-patch/1-alpha'])
        (project_dir / 'Patches' / '1-alpha' / '01_alpha.sql').write_text(
            'CREATE TABLE alpha (id SERIAL PRIMARY KEY);'
        )
        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Add alpha'])
        run(['half_orm', 'dev', 'patch', 'merge'], input_text='y\n')

        # Production moves to 0.1.0.
        run(['git', 'checkout', 'ho-prod'])
        run(['half_orm', 'dev', 'release', 'promote', 'prod'],
            input_text='y\ny\n', check=False)

        # The reported situation: branch gone from origin, local copy
        # left where it stood before the promotion's .hop/ sync.
        run(['git', 'push', 'origin', '--delete', 'ho-patch/2-beta'], check=False)
        run(['git', 'checkout', 'ho-patch/2-beta'])
        run(['git', 'reset', '--hard', sha_before])

        assert 'schema-0.0.0.sql' in run(
            ['readlink', '.hop/model/schema.sql']
        ).stdout, "precondition: the branch still records the old production"

        result = run(['half_orm', 'dev', 'check'], input_text='n\n', check=False)
        assert result.returncode == 0, (
            f"check should succeed.\nSTDOUT: {result.stdout}\n"
            f"STDERR: {result.stderr}"
        )

        assert 'Production version: 0.1.0' in result.stdout, (
            "check must report the production version recorded on ho-prod, "
            f"not the current branch's stale copy.\nSTDOUT: {result.stdout}"
        )
        assert 'Production version: 0.0.0' not in result.stdout

        # The release the branch still believes in was promoted; ho-prod
        # has no patches file for it any more.
        assert f'Release {version} ' not in result.stdout, (
            f"release {version} was promoted to production and must not be "
            f"listed as in preparation.\nSTDOUT: {result.stdout}"
        )

        # And the gap is stated rather than left to be guessed.
        assert 'ho-patch/2-beta' in result.stdout
        assert 'still records production' in result.stdout
        assert 'git merge ho-prod' in result.stdout
