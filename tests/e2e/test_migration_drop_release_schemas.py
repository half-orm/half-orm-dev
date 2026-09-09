"""
E2E test for migration 1.0.0a36 (drop model/release-X.Y.Z.sql).

The release schema mechanism is gone: nothing generates or reads
model/release-{version}.sql any more, and the copies still tracked in
existing repositories keep producing modify/delete conflicts during
`patch merge`. This migration deletes them, unconditionally - unlike
a35, which only cleaned the projects whose release schemas predated the
metadata->data switch.

Since nothing produces those files any longer, the legacy layout is
seeded by hand: a copy on the release branch, on the patch branch cut
from it, and on ho-prod (where .hop/ syncing used to put one).

This verifies the end-to-end behaviour on a real repository:
  - the release schema is removed from ho-prod, the release branch and
    the patch branch alike
  - no model/metadata-*.sql is needed for it to happen: a project whose
    release schemas a35 deliberately spared is cleaned too
"""
import re

import pytest

from half_orm_dev.utils import hop_version as installed_hop_version
from packaging.version import Version


MIGRATION_VERSION = '1.0.0a36'

# The project must start *strictly below* the migration under test:
# get_pending_migrations() keeps `current < v <= target`. The
# old_hop_version fixture gives one pre-release step below the installed
# version, which moves with every release - at 1.0.0a37 it downgrades to
# a36 and the a36 migration is no longer pending, so `migrate` succeeds
# having done nothing and the test fails for a reason unrelated to what
# it tests. Pin it instead.
VERSION_BEFORE_MIGRATION = '1.0.0-a35'

pytestmark = pytest.mark.skipif(
    Version(installed_hop_version()) < Version(MIGRATION_VERSION),
    reason=f"migration {MIGRATION_VERSION} only runs once that version is released",
)


def _downgrade_hop_version(run, project_dir, old_version):
    """Write old_version into .hop/config on ho-prod, commit and push."""
    run(['git', 'checkout', 'ho-prod'])
    config_path = project_dir / '.hop' / 'config'
    content = config_path.read_text()
    content = re.sub(r'(hop_version\s*=\s*)\S+', rf'\g<1>{old_version}', content)
    config_path.write_text(content)
    run(['git', 'add', str(config_path)])
    run(['git', 'commit', '--no-verify', '-m', f'test: downgrade to {old_version}'])
    run(['git', 'push', '--no-verify', 'origin', 'ho-prod'])


def _seed_release_schema(run, project_dir, branch, version):
    """Commit a release-X.Y.Z.sql on branch, as older hop versions did."""
    run(['git', 'checkout', branch])
    legacy = project_dir / '.hop' / 'model' / f'release-{version}.sql'
    legacy.write_text("-- release schema left over from a previous hop version\n")
    run(['git', 'add', str(legacy)])
    run(['git', 'commit', '--no-verify', '-m', f'test: release schema on {branch}'])
    run(['git', 'push', '--no-verify', 'origin', branch])


def _file_on_branch(run, branch, relative_path):
    """True when relative_path is tracked on branch."""
    result = run(
        ['git', 'ls-tree', '-r', '--name-only', branch, relative_path],
        check=False,
    )
    return bool(result.stdout.strip())


@pytest.mark.e2e
class TestMigrationDropsReleaseSchemas:
    """Migration 1.0.0a36 removes release schemas from every active branch."""

    def test_removes_release_schema_on_every_branch(self, project_with_release):
        """ho-prod, the release branch and the patch branch are all cleaned."""
        env = project_with_release
        run = env['run']
        project_dir = env['project_dir']
        version = env['release_version']
        release_branch = f'ho-release/{version}'
        release_schema = f'.hop/model/release-{version}.sql'

        patch_id = '1-carries-release-schema'
        run(['half_orm', 'dev', 'patch', 'create', patch_id])
        patch_branch = f'ho-patch/{patch_id}'

        for branch in ('ho-prod', release_branch, patch_branch):
            _seed_release_schema(run, project_dir, branch, version)
            assert _file_on_branch(run, branch, release_schema), (
                f"precondition: {branch} must carry the release schema"
            )

        _downgrade_hop_version(run, project_dir, VERSION_BEFORE_MIGRATION)

        result = run(['half_orm', 'dev', 'migrate'], input_text='y\n', check=False)
        assert result.returncode == 0, (
            f"migrate should succeed.\n"
            f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )

        # Reported as one picture rather than one branch at a time: when
        # this fails, which branches kept the file - and what migrate
        # said while doing it - is the whole diagnosis.
        left = [
            branch for branch in ('ho-prod', release_branch, patch_branch)
            if _file_on_branch(run, branch, release_schema)
        ]
        assert not left, (
            f"{release_schema} should be gone from every branch, still on: "
            f"{', '.join(left)}\n\n"
            f"--- migrate STDOUT ---\n{result.stdout}\n"
            f"--- migrate STDERR ---\n{result.stderr}"
        )

    def test_removes_release_schema_without_legacy_metadata(self, project_with_release):
        """No model/metadata-*.sql is required: the deletion is unconditional.

        a35 skipped these projects on purpose - their release schemas
        carried the full data and were still usable. They are useless
        now, so they go too.
        """
        env = project_with_release
        run = env['run']
        project_dir = env['project_dir']
        version = env['release_version']
        release_branch = f'ho-release/{version}'
        release_schema = f'.hop/model/release-{version}.sql'

        _seed_release_schema(run, project_dir, 'ho-prod', version)
        _seed_release_schema(run, project_dir, release_branch, version)

        # No legacy metadata-*.sql is created here.
        _downgrade_hop_version(run, project_dir, VERSION_BEFORE_MIGRATION)

        result = run(['half_orm', 'dev', 'migrate'], input_text='y\n', check=False)
        assert result.returncode == 0, (
            f"migrate should succeed.\n"
            f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )

        assert not _file_on_branch(run, release_branch, release_schema), (
            f"{release_schema} should be gone from {release_branch}"
        )
        assert not _file_on_branch(run, 'ho-prod', release_schema), (
            f"{release_schema} should be gone from ho-prod"
        )
