"""
End-to-end tests: the branch of a detached patch is ho-detached/<id> (#61).

- `patch detach` renames ho-patch/<id> → ho-detached/<id>, locally and on
  origin;
- the frozen branch receives no .hop/ sync commit and refuses commits;
- `release attach-patch` refuses a frozen branch that differs from origin,
  renames it back to ho-patch/<id> and merges the release into it;
- the 2.0.0a5 migration renames the branches of patches detached before.
"""

import pytest

SQL = 'CREATE TABLE public.detached_t (id INT);'


def _sha(run, ref):
    return run(['git', 'rev-parse', ref]).stdout.strip()


def _remote_heads(run):
    return run(['git', 'ls-remote', '--heads', 'origin']).stdout


def _create_patch_with_work(run, project_dir, patch_id):
    run(['git', 'checkout', 'ho-release/0.1.0'])
    run(['half_orm', 'dev', 'patch', 'create', patch_id])
    run(['git', 'checkout', f'ho-patch/{patch_id}'])
    (project_dir / 'Patches' / patch_id / '01_t.sql').write_text(SQL)
    run(['git', 'add', '.'])
    run(['git', 'commit', '-m', f'Work on {patch_id}', '--no-verify'])
    run(['git', 'push', 'origin', f'ho-patch/{patch_id}'])


def _detach(run, project_dir, patch_id):
    _create_patch_with_work(run, project_dir, patch_id)
    run(['half_orm', 'dev', 'patch', 'detach', '--force'])
    run(['git', 'checkout', 'ho-release/0.1.0'])


@pytest.mark.integration
class TestDetachFreezesTheBranch:

    def test_detach_renames_the_branch_locally_and_on_origin(self, project_with_release):
        env = project_with_release
        run, project_dir = env['run'], env['project_dir']
        _create_patch_with_work(run, project_dir, '1-frozen')

        result = run(['half_orm', 'dev', 'patch', 'detach', '--force'])

        assert 'ho-detached/1-frozen' in result.stdout
        assert run(['git', 'branch', '--show-current']).stdout.strip() == 'ho-detached/1-frozen'
        heads = _remote_heads(run)
        assert 'refs/heads/ho-detached/1-frozen' in heads
        assert 'refs/heads/ho-patch/1-frozen' not in heads
        assert run(['git', 'branch', '--list', 'ho-patch/1-frozen']).stdout == ''
        assert _sha(run, 'ho-detached/1-frozen') == _sha(run, 'origin/ho-detached/1-frozen')
        # The work is on the frozen branch, in Patches/orphaned/
        assert run(['git', 'show', 'ho-detached/1-frozen:Patches/orphaned/1-frozen/01_t.sql']
                   ).stdout == SQL

    def test_frozen_branch_gets_no_sync_commit(self, project_with_release):
        env = project_with_release
        run, project_dir = env['run'], env['project_dir']
        _detach(run, project_dir, '2-frozen')
        frozen = _sha(run, 'origin/ho-detached/2-frozen')

        # Another hop operation that syncs .hop/ to the active branches
        _create_patch_with_work(run, project_dir, '3-other')
        run(['half_orm', 'dev', 'patch', 'detach', '--force'])

        run(['git', 'fetch', 'origin'])
        assert _sha(run, 'origin/ho-detached/2-frozen') == frozen

    def test_hook_refuses_commits_on_the_frozen_branch(self, project_with_release):
        env = project_with_release
        run, project_dir = env['run'], env['project_dir']
        _detach(run, project_dir, '4-frozen')

        run(['git', 'checkout', 'ho-detached/4-frozen'])
        (project_dir / 'more.txt').write_text('more\n')
        run(['git', 'add', 'more.txt'])
        result = run(['git', 'commit', '-m', 'more work'], check=False)

        assert result.returncode != 0
        assert 'frozen' in result.stdout + result.stderr
        assert 'release attach-patch 4-frozen' in result.stdout + result.stderr


@pytest.mark.integration
class TestAttachThawsTheBranch:

    def test_attach_renames_back_and_merges_the_release(self, project_with_release):
        env = project_with_release
        run, project_dir = env['run'], env['project_dir']
        _detach(run, project_dir, '5-thawed')
        # The release moves on while the patch is detached
        _create_patch_with_work(run, project_dir, '6-meanwhile')
        run(['git', 'checkout', 'ho-release/0.1.0'])

        result = run(['half_orm', 'dev', 'release', 'attach-patch', '5-thawed', '--force'])

        assert 'ho-patch/5-thawed' in result.stdout
        heads = _remote_heads(run)
        assert 'refs/heads/ho-patch/5-thawed' in heads
        assert 'refs/heads/ho-detached/5-thawed' not in heads
        assert run(['git', 'branch', '--show-current']).stdout.strip() == 'ho-release/0.1.0'
        # The patch branch contains the release, and is pushed
        assert run(['git', 'merge-base', '--is-ancestor', 'ho-release/0.1.0', 'ho-patch/5-thawed'],
                   check=False).returncode == 0
        assert _sha(run, 'ho-patch/5-thawed') == _sha(run, 'origin/ho-patch/5-thawed')
        # Its directory is back at Patches/<id>, its .hop/ is the release's
        assert run(['git', 'show', 'ho-patch/5-thawed:Patches/5-thawed/01_t.sql']).stdout == SQL
        assert run(['git', 'ls-tree', '-d', 'ho-patch/5-thawed', 'Patches/orphaned/5-thawed']
                   ).stdout == ''
        assert run(['git', 'diff', '--stat', 'ho-release/0.1.0', 'ho-patch/5-thawed', '--', '.hop/']
                   ).stdout == ''
        assert run(['git', 'status', '--porcelain']).stdout == ''

    def test_attached_patch_can_be_applied(self, project_with_release):
        env = project_with_release
        run, project_dir = env['run'], env['project_dir']
        _detach(run, project_dir, '7-applied')
        r = run(['half_orm', 'dev', 'release', 'attach-patch', '7-applied', '--force'], check=False)
        assert r.returncode == 0, r.stdout + r.stderr

        run(['git', 'checkout', 'ho-patch/7-applied'])
        result = run(['half_orm', 'dev', 'patch', 'apply'], check=False)

        assert result.returncode == 0, f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"

    def test_attach_refuses_a_frozen_branch_rewritten_locally(self, project_with_release):
        env = project_with_release
        run, project_dir = env['run'], env['project_dir']
        _detach(run, project_dir, '8-rewritten')
        toml = (project_dir / '.hop' / 'releases' / '0.1.0-patches.toml').read_text()

        # Someone rewrites the frozen branch here (bypassing the hook)
        run(['git', 'checkout', 'ho-detached/8-rewritten'])
        run(['git', 'commit', '--amend', '--no-verify', '-m', 'rewritten'])
        run(['git', 'checkout', 'ho-release/0.1.0'])

        result = run(['half_orm', 'dev', 'release', 'attach-patch', '8-rewritten', '--force'],
                     check=False)

        assert result.returncode != 0
        assert 'diverged' in result.stdout + result.stderr
        assert (project_dir / '.hop' / 'releases' / '0.1.0-patches.toml').read_text() == toml
        assert 'refs/heads/ho-detached/8-rewritten' in _remote_heads(run)


@pytest.mark.integration
class TestMigrationFreezesLegacyBranches:

    def test_migration_renames_the_branch_of_an_orphaned_patch(self, project_with_release):
        env = project_with_release
        run, project_dir = env['run'], env['project_dir']
        _detach(run, project_dir, '9-legacy')
        # As before #61: the orphaned patch still has its ho-patch/ branch
        run(['git', 'push', 'origin',
             'ho-detached/9-legacy:refs/heads/ho-patch/9-legacy', ':refs/heads/ho-detached/9-legacy'])
        run(['git', 'branch', '-m', 'ho-detached/9-legacy', 'ho-patch/9-legacy'])
        run(['git', 'fetch', '--prune', 'origin'])

        result = run(['python', '-c', '''
import importlib.util, pathlib, half_orm_dev
from half_orm_dev.repo import Repo
path = (pathlib.Path(half_orm_dev.__file__).parent
        / "migrations/2/0/0/a5/00_freeze_detached_patch_branches.py")
spec = importlib.util.spec_from_file_location("m", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(module.migrate(Repo()))
'''])

        assert 'ho-patch/9-legacy → ho-detached/9-legacy' in result.stdout
        heads = _remote_heads(run)
        assert 'refs/heads/ho-detached/9-legacy' in heads
        assert 'refs/heads/ho-patch/9-legacy' not in heads
