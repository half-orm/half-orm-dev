"""
E2E tests for migration sync behaviour.

Verifies that when a migration is triggered from a non-ho-prod branch:
  1. All active branches receive the .hop/ sync commit.
  2. After migration the current branch is restored to the originating branch.
  3. The Patches/ directory is left intact on both the release and patch branches.
"""
import configparser
import re
import pytest

from half_orm_dev.utils import hop_version as installed_hop_version


def _get_hop_version_on_branch(run, project_dir, branch):
    """Return the hop_version stored in .hop/config on *branch*."""
    run(['git', 'checkout', branch])
    config = configparser.ConfigParser()
    config.read(project_dir / '.hop' / 'config')
    return config['halfORM']['hop_version']


def _set_hop_version_on_branch(run, project_dir, branch, version_str):
    """Overwrite hop_version in .hop/config on *branch*, commit and push."""
    run(['git', 'checkout', branch])
    config_path = project_dir / '.hop' / 'config'
    content = config_path.read_text()
    content = re.sub(r'(hop_version\s*=\s*)\S+', rf'\g<1>{version_str}', content)
    config_path.write_text(content)
    run(['git', 'add', str(config_path)])
    # --no-verify bypasses the commit hook that prevents direct commits on
    # protected branches (ho-prod).  This is intentional: the hook guards the
    # normal workflow; bypassing it here is acceptable for test setup only.
    run(['git', 'commit', '--no-verify', '-m', f'test: downgrade hop_version to {version_str}'])
    run(['git', 'push', '--no-verify', 'origin', branch])


@pytest.mark.e2e
def test_migration_from_patch_branch_syncs_all_branches(project_with_fk_patch, old_hop_version):
    """
    Running a migration while on a patch branch must:
    - sync the updated .hop/ (new hop_version) to every active branch
    - leave the caller back on the originating patch branch
    - leave Patches/ directories intact
    """
    env = project_with_fk_patch
    run = env['run']
    project_dir = env['project_dir']

    active_branches = ['ho-prod', 'ho-release/0.1.0', 'ho-patch/1-author-post']
    installed_version = installed_hop_version()

    # Clean the working tree before switching branches for setup commits.
    # patch apply leaves generated module files (untracked/modified) that
    # would prevent checkout and git commit on other branches.
    run(['git', 'stash', '-u'], check=False)

    # Downgrade hop_version on every active branch so migration is needed.
    # old_hop_version is one pre-release step below the installed version and
    # shares the same release tuple — no real migration scripts exist between
    # the two, so get_pending_migrations detects a mismatch without running
    # interactive scripts.
    for branch in active_branches:
        _set_hop_version_on_branch(run, project_dir, branch, old_hop_version)

    # Trigger migration from the patch branch
    run(['git', 'checkout', 'ho-patch/1-author-post'])
    run(['half_orm', 'dev', 'migrate'], input_text='y\n')

    # 1. Current branch must be restored to the originating patch branch
    result = run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
    assert result.stdout.strip() == 'ho-patch/1-author-post', (
        "After migration the current branch should be ho-patch/1-author-post, "
        f"got: {result.stdout.strip()!r}"
    )

    # 2. All active branches must have the updated hop_version
    for branch in active_branches:
        v = _get_hop_version_on_branch(run, project_dir, branch)
        assert v == installed_version, (
            f"{branch}: expected hop_version={installed_version!r}, got {v!r}"
        )

    # 3. Patches/ directory must be intact on both the release and patch branches
    run(['git', 'checkout', 'ho-release/0.1.0'])
    assert (project_dir / 'Patches').exists(), \
        "Patches/ directory missing on ho-release/0.1.0 after migration"

    run(['git', 'checkout', 'ho-patch/1-author-post'])
    assert (project_dir / 'Patches' / '1-author-post').exists(), \
        "Patch directory Patches/1-author-post missing on ho-patch/1-author-post after migration"
