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
    repo.config = mock_config

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
            MockMgr.return_value.half_orm_major_change.return_value = None

            result = runner.invoke(migrate, input='y\n')

        assert result.exit_code == 0
        assert 'BREAKING CHANGES' not in result.output
        repo.run_migrations_if_needed.assert_called_once()

    def test_breaking_changes_content_is_displayed(self, runner):
        """Breaking changes content is sent to the pager before the confirmation prompt.

        The section header uses the installed version (hop_version), not the
        version from the filename.
        """
        repo = _make_mock_repo()
        bc = [{'component': 'hop', 'version': '1.0.0', 'content': 'Removed old API.'}]

        with patch('half_orm_dev.cli.commands.migrate.Repo', return_value=repo), \
             patch('half_orm_dev.utils.hop_version', return_value='1.0.0-a1'), \
             patch('half_orm_dev.cli.commands.migrate.MigrationManager') as MockMgr, \
             patch('half_orm_dev.cli.commands.migrate.click.echo_via_pager') as mock_pager:

            MockMgr.return_value.get_breaking_changes.return_value = bc
            MockMgr.return_value.half_orm_major_change.return_value = None

            runner.invoke(migrate, input='yes\n')

        mock_pager.assert_called_once()
        pager_text = mock_pager.call_args[0][0]
        assert 'BREAKING CHANGES' in pager_text
        assert 'Removed old API.' in pager_text
        # header shows installed version, not the filename version
        assert 'half-orm-dev 1.0.0-a1' in pager_text

    def test_breaking_changes_require_yes_to_proceed(self, runner):
        """Typing "yes" when breaking changes are present runs the migration."""
        repo = _make_mock_repo()
        bc = [{'component': 'hop', 'version': '1.0.0', 'content': 'Change.'}]

        with patch('half_orm_dev.cli.commands.migrate.Repo', return_value=repo), \
             patch('half_orm_dev.utils.hop_version', return_value='1.0.0'), \
             patch('half_orm_dev.cli.commands.migrate.MigrationManager') as MockMgr, \
             patch('half_orm_dev.cli.commands.migrate.click.echo_via_pager'):

            MockMgr.return_value.get_breaking_changes.return_value = bc
            MockMgr.return_value.half_orm_major_change.return_value = None

            runner.invoke(migrate, input='yes\n')

        repo.run_migrations_if_needed.assert_called_once()

    def test_breaking_changes_yn_does_not_proceed(self, runner):
        """Typing "y" (not "yes") when breaking changes are present aborts."""
        repo = _make_mock_repo()
        bc = [{'component': 'hop', 'version': '1.0.0', 'content': 'Change.'}]

        with patch('half_orm_dev.cli.commands.migrate.Repo', return_value=repo), \
             patch('half_orm_dev.utils.hop_version', return_value='1.0.0'), \
             patch('half_orm_dev.cli.commands.migrate.MigrationManager') as MockMgr, \
             patch('half_orm_dev.cli.commands.migrate.click.echo_via_pager'):

            MockMgr.return_value.get_breaking_changes.return_value = bc
            MockMgr.return_value.half_orm_major_change.return_value = None

            result = runner.invoke(migrate, input='y\n')

        repo.run_migrations_if_needed.assert_not_called()

    def test_breaking_changes_no_aborts(self, runner):
        """Typing "no" when breaking changes are present aborts the migration."""
        repo = _make_mock_repo()
        bc = [{'component': 'hop', 'version': '1.0.0', 'content': 'Change.'}]

        with patch('half_orm_dev.cli.commands.migrate.Repo', return_value=repo), \
             patch('half_orm_dev.utils.hop_version', return_value='1.0.0'), \
             patch('half_orm_dev.cli.commands.migrate.MigrationManager') as MockMgr, \
             patch('half_orm_dev.cli.commands.migrate.click.echo_via_pager'):

            MockMgr.return_value.get_breaking_changes.return_value = bc
            MockMgr.return_value.half_orm_major_change.return_value = None

            result = runner.invoke(migrate, input='no\n')

        repo.run_migrations_if_needed.assert_not_called()
        assert 'pip install' in result.output

    def test_half_orm_major_change_points_to_the_documentation(self, runner):
        """A change of half-orm's major version is announced with a link to
        its notes, not with their text, and calls for an explicit "yes"."""
        repo = _make_mock_repo('1.2.0-a1', '2.0.0-a1')

        with patch('half_orm_dev.cli.commands.migrate.Repo', return_value=repo), \
             patch('half_orm_dev.utils.hop_version', return_value='2.0.0-a1'), \
             patch('half_orm_dev.cli.commands.migrate.MigrationManager') as MockMgr, \
             patch('half_orm_dev.cli.commands.migrate.click.echo_via_pager') as mock_pager:

            MockMgr.return_value.get_breaking_changes.return_value = []
            MockMgr.return_value.half_orm_major_change.return_value = (1, 2)

            result = runner.invoke(migrate, input='y\n')

        assert 'half-orm 1.x → 2.x' in result.output
        assert ('https://half-orm.github.io/half-orm/latest/breaking-changes/'
                '#breaking-2-0-0') in result.output
        mock_pager.assert_not_called()
        # "y" is not "yes"
        repo.run_migrations_if_needed.assert_not_called()

    def test_half_orm_major_change_proceeds_on_yes(self, runner):
        repo = _make_mock_repo('1.2.0-a1', '2.0.0-a1')

        with patch('half_orm_dev.cli.commands.migrate.Repo', return_value=repo), \
             patch('half_orm_dev.utils.hop_version', return_value='2.0.0-a1'), \
             patch('half_orm_dev.cli.commands.migrate.MigrationManager') as MockMgr:

            MockMgr.return_value.get_breaking_changes.return_value = []
            MockMgr.return_value.half_orm_major_change.return_value = (1, 2)

            runner.invoke(migrate, input='yes\n')

        repo.run_migrations_if_needed.assert_called_once()


class TestAutomaticMigrationPrompt:
    """`half_orm dev` with no subcommand offers the migration itself. It used
    to migrate without announcing any breaking change -- and could not get
    that far, reading the configuration from an attribute Repo does not have."""

    def _invoke(self, runner, major_change, notes, answer):
        from half_orm_dev.cli import main as cli_main
        repo = _make_mock_repo('1.2.0-a1', '2.0.0-a1')
        repo.database.production = False
        repo.needs_migration = Mock(return_value=True)
        repo.devel = True
        # Repo has no `repo` attribute; a Mock would invent one.
        del repo.repo
        with patch.object(cli_main, 'Repo', return_value=repo), \
             patch.object(cli_main, 'hop_version', return_value='2.0.0-a1'), \
             patch('half_orm_dev.cli.commands.migrate.MigrationManager') as MockMgr, \
             patch('half_orm_dev.cli.commands.migrate.click.echo_via_pager'):
            MockMgr.return_value.get_breaking_changes.return_value = notes
            MockMgr.return_value.half_orm_major_change.return_value = major_change
            result = runner.invoke(cli_main.create_cli_group(), [], input=answer)
        return repo, result

    def test_major_change_is_announced_and_needs_yes(self, runner):
        repo, result = self._invoke(runner, (1, 2), [], 'y\n')
        assert result.exception is None or isinstance(result.exception, SystemExit), result.exception
        assert '#breaking-2-0-0' in result.output
        repo.run_migrations_if_needed.assert_not_called()

    def test_major_change_proceeds_on_yes(self, runner):
        repo, result = self._invoke(runner, (1, 2), [], 'yes\n')
        assert result.exception is None or isinstance(result.exception, SystemExit), result.exception
        repo.run_migrations_if_needed.assert_called_once()

    def test_nothing_to_announce_keeps_the_y_n_prompt(self, runner):
        repo, result = self._invoke(runner, None, [], 'y\n')
        assert result.exception is None or isinstance(result.exception, SystemExit), result.exception
        assert 'BREAKING' not in result.output
        repo.run_migrations_if_needed.assert_called_once()
