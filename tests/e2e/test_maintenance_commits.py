"""
E2E tests for maintenance commit behaviour and migration dirty-check logic.

Verifies:
  1. hop check auto-commits .gitignore changes with a [HOP] prefix commit,
     leaving the working tree clean.
  2. hop migrate fails immediately if the working tree is dirty at invocation.
  3. hop migrate succeeds when the tree is clean at start, even though internal
     operations (sync_and_validate_ho_prod) would normally raise on dirty state.
"""
import re
import configparser
import pytest

from tests.e2e.conftest import run_cmd
from half_orm_dev.utils import hop_version as installed_hop_version


def _downgrade_hop_version(run, project_dir, branch, old_version):
    """Write old_version into .hop/config on branch, commit and push."""
    run(['git', 'checkout', branch])
    config_path = project_dir / '.hop' / 'config'
    content = config_path.read_text()
    content = re.sub(r'(hop_version\s*=\s*)\S+', rf'\g<1>{old_version}', content)
    config_path.write_text(content)
    run(['git', 'add', str(config_path)])
    run(['git', 'commit', '--no-verify', '-m', f'test: downgrade hop_version to {old_version}'])
    run(['git', 'push', '--no-verify', 'origin', branch])


@pytest.mark.e2e
class TestHopCheckMaintenanceCommit:
    """hop check commits .gitignore updates automatically with [HOP] prefix."""

    def test_check_commits_gitignore_with_hop_prefix(self, initialized_project):
        """When .gitignore is missing hop entries, hop check commits them as [HOP]."""
        env = initialized_project
        run = env['run']
        project_dir = env['project_dir']

        run(['git', 'checkout', 'ho-prod'])

        # Remove the hop-specific entries from .gitignore, then commit so the
        # tree is clean but the entries are missing.
        gitignore = project_dir / '.gitignore'
        original = gitignore.read_text()
        stripped = '\n'.join(
            line for line in original.splitlines()
            if line not in ('.hop/production', '.hop/.fetching')
        )
        gitignore.write_text(stripped)
        run(['git', 'add', '.gitignore'])
        run(['git', 'commit', '--no-verify', '-m', 'test: remove hop gitignore entries'])
        run(['git', 'push', '--no-verify', 'origin', 'ho-prod'])

        # hop check should detect the missing entries and auto-commit them.
        run(['half_orm', 'dev', 'check'])

        # Working tree must be clean after check.
        status = run(['git', 'status', '--short'])
        assert status.stdout.strip() == '', (
            f"Working tree should be clean after hop check, got:\n{status.stdout}"
        )

        # The last commit must carry the [HOP] prefix.
        last_msg = run(['git', 'log', '-1', '--format=%s']).stdout.strip()
        assert last_msg.startswith('[HOP]'), (
            f"Expected last commit to start with [HOP], got: {last_msg!r}"
        )

        # The entries must be present in .gitignore.
        content = gitignore.read_text()
        assert '.hop/production' in content
        assert '.hop/.fetching' in content


@pytest.mark.e2e
class TestMigrateDirtyCheck:
    """hop migrate performs a single dirty check before any operation."""

    def test_migrate_fails_if_tree_dirty_at_start(self, initialized_project, old_hop_version):
        """hop migrate exits immediately when uncommitted changes exist."""
        env = initialized_project
        run = env['run']
        project_dir = env['project_dir']

        _downgrade_hop_version(run, project_dir, 'ho-prod', old_hop_version)
        run(['git', 'checkout', 'ho-prod'])

        # Modify a tracked file without staging it.
        gitignore = project_dir / '.gitignore'
        gitignore.write_text(gitignore.read_text() + '\n# dirty\n')

        result = run(['half_orm', 'dev', 'migrate'], input_text='y\n', check=False)

        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert 'uncommitted changes' in combined.lower() or 'dirty' in combined.lower()

        # Restore
        run(['git', 'checkout', '--', '.gitignore'])

    def test_migrate_succeeds_with_clean_tree(self, initialized_project, old_hop_version):
        """hop migrate completes successfully when the tree is clean at start."""
        env = initialized_project
        run = env['run']
        project_dir = env['project_dir']

        _downgrade_hop_version(run, project_dir, 'ho-prod', old_hop_version)
        run(['git', 'checkout', 'ho-prod'])

        # Tree must be clean before migration.
        status = run(['git', 'status', '--short'])
        assert status.stdout.strip() == '', "Tree should be clean before migration"

        result = run(['half_orm', 'dev', 'migrate'], input_text='y\n', check=False)

        assert result.returncode == 0, (
            f"hop migrate should succeed with clean tree.\n"
            f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )

        # hop_version in .hop/config must be updated.
        config = configparser.ConfigParser()
        config.read(project_dir / '.hop' / 'config')
        assert config['halfORM']['hop_version'] == installed_hop_version()
