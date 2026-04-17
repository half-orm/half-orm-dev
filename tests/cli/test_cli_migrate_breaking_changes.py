"""
Tests for the migrate CLI command — breaking changes confirmation flow.

Verifies:
- No breaking changes → normal y/n confirmation
- Breaking changes present → content displayed + "yes" required
- Typing anything other than "yes" aborts the migration
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from click.testing import CliRunner

from half_orm_dev.cli.commands.migrate import migrate


def _make_mock_repo(config_version='0.17.0', installed_version='1.0.0'):
    """Return a minimal mock Repo suitable for migrate CLI tests."""
    repo = Mock()
    repo.checked = True

    mock_config = Mock()
    mock_config.hop_version = config_version
    repo._Repo__config = mock_config

    mock_hgit = Mock()
    mock_hgit.branch = 'ho-prod'
    repo.hgit = mock_hgit

    repo.run_migrations_if_needed = Mock(return_value={
        'migration_run': True,
        'errors': [],
    })
    return repo


@pytest.fixture
def runner():
    return CliRunner()


class TestMigrateCLIBreakingChanges:
    """Test migrate CLI confirmation flow with and without breaking changes."""

    def test_no_breaking_changes_uses_yn_confirm(self, runner):
        """When no breaking changes exist, a simple y/n prompt is shown."""
        repo = _make_mock_repo()

        with patch('half_orm_dev.cli.commands.migrate.Repo', return_value=repo), \
             patch('half_orm_dev.utils.hop_version', return_value='1.0.0'), \
             patch('half_orm_dev.cli.commands.migrate.MigrationManager') as MockMgr:

            MockMgr.return_value.get_breaking_changes.return_value = []

            result = runner.invoke(migrate, input='y\n')

        assert result.exit_code == 0
        assert 'BREAKING CHANGES' not in result.output
        repo.run_migrations_if_needed.assert_called_once()

    def test_breaking_changes_content_is_displayed(self, runner):
        """Breaking changes content is printed before the confirmation prompt."""
        repo = _make_mock_repo()
        bc = [{'component': 'hop', 'version': '1.0.0', 'content': 'Removed old API.'}]

        with patch('half_orm_dev.cli.commands.migrate.Repo', return_value=repo), \
             patch('half_orm_dev.utils.hop_version', return_value='1.0.0'), \
             patch('half_orm_dev.cli.commands.migrate.MigrationManager') as MockMgr:

            MockMgr.return_value.get_breaking_changes.return_value = bc

            result = runner.invoke(migrate, input='yes\n')

        assert 'BREAKING CHANGES' in result.output
        assert 'Removed old API.' in result.output
        assert 'half-orm-dev 1.0.0' in result.output

    def test_breaking_changes_require_yes_to_proceed(self, runner):
        """Typing "yes" when breaking changes are present runs the migration."""
        repo = _make_mock_repo()
        bc = [{'component': 'hop', 'version': '1.0.0', 'content': 'Change.'}]

        with patch('half_orm_dev.cli.commands.migrate.Repo', return_value=repo), \
             patch('half_orm_dev.utils.hop_version', return_value='1.0.0'), \
             patch('half_orm_dev.cli.commands.migrate.MigrationManager') as MockMgr:

            MockMgr.return_value.get_breaking_changes.return_value = bc

            result = runner.invoke(migrate, input='yes\n')

        repo.run_migrations_if_needed.assert_called_once()

    def test_breaking_changes_yn_does_not_proceed(self, runner):
        """Typing "y" (not "yes") when breaking changes are present aborts."""
        repo = _make_mock_repo()
        bc = [{'component': 'hop', 'version': '1.0.0', 'content': 'Change.'}]

        with patch('half_orm_dev.cli.commands.migrate.Repo', return_value=repo), \
             patch('half_orm_dev.utils.hop_version', return_value='1.0.0'), \
             patch('half_orm_dev.cli.commands.migrate.MigrationManager') as MockMgr:

            MockMgr.return_value.get_breaking_changes.return_value = bc

            result = runner.invoke(migrate, input='y\n')

        repo.run_migrations_if_needed.assert_not_called()

    def test_breaking_changes_no_aborts(self, runner):
        """Typing "no" when breaking changes are present aborts the migration."""
        repo = _make_mock_repo()
        bc = [{'component': 'hop', 'version': '1.0.0', 'content': 'Change.'}]

        with patch('half_orm_dev.cli.commands.migrate.Repo', return_value=repo), \
             patch('half_orm_dev.utils.hop_version', return_value='1.0.0'), \
             patch('half_orm_dev.cli.commands.migrate.MigrationManager') as MockMgr:

            MockMgr.return_value.get_breaking_changes.return_value = bc

            result = runner.invoke(migrate, input='no\n')

        repo.run_migrations_if_needed.assert_not_called()
        assert 'pip install' in result.output

    def test_half_orm_component_label_displayed(self, runner):
        """half_orm component shows as "half-orm" in the output."""
        repo = _make_mock_repo()
        bc = [{'component': 'half_orm', 'version': '1.0.0', 'content': 'ho_get changed.'}]

        with patch('half_orm_dev.cli.commands.migrate.Repo', return_value=repo), \
             patch('half_orm_dev.utils.hop_version', return_value='1.0.0'), \
             patch('half_orm_dev.cli.commands.migrate.MigrationManager') as MockMgr:

            MockMgr.return_value.get_breaking_changes.return_value = bc

            result = runner.invoke(migrate, input='yes\n')

        assert 'half-orm 1.0.0' in result.output
        assert 'ho_get changed.' in result.output
