"""
Unit tests for the interactive upgrade CLI command.

Tests the upgrade command's interactive flow:
- Fetches and displays available releases
- Interactive version selection (or --to-release bypass)
- Confirmation prompt (or --yes bypass)
- --dry-run simulation
- Already up-to-date early exit
"""

import pytest
from unittest.mock import MagicMock, patch
from click.testing import CliRunner

from half_orm_dev.cli.commands.upgrade import upgrade


# === Fixtures ===

_UPDATE_INFO_TWO_RELEASES = {
    'current_version': '0.3.2',
    'has_updates': True,
    'available_releases': [
        {'version': '0.3.3', 'patches': ['1-fix', '2-feat'], 'type': 'production'},
        {'version': '0.4.0', 'patches': ['3-big-feature'], 'type': 'production'},
    ],
    'upgrade_path': ['0.3.3', '0.4.0'],
}

_UPDATE_INFO_UP_TO_DATE = {
    'current_version': '0.3.2',
    'has_updates': False,
    'available_releases': [],
    'upgrade_path': [],
}

_UPDATE_INFO_ONE_RELEASE = {
    'current_version': '0.3.2',
    'has_updates': True,
    'available_releases': [
        {'version': '0.3.3', 'patches': ['1-fix'], 'type': 'production'},
    ],
    'upgrade_path': ['0.3.3'],
}

_UPGRADE_RESULT_FULL = {
    'status': 'success',
    'dry_run': False,
    'current_version': '0.3.2',
    'final_version': '0.4.0',
    'target_version': None,
    'releases_applied': ['0.3.3', '0.4.0'],
    'patches_applied': {
        '0.3.3': ['1-fix', '2-feat'],
        '0.4.0': ['3-big-feature'],
    },
    'backup_created': None,
    'snapshot_used': 'mydb_hop_snap_0_3_2',
    'message': '',
}

_UPGRADE_RESULT_DRY_RUN = {
    'status': 'dry_run',
    'dry_run': True,
    'current_version': '0.3.2',
    'final_version': '0.4.0',
    'target_version': None,
    'releases_would_apply': ['0.3.3', '0.4.0'],
    'patches_would_apply': {
        '0.3.3': ['1-fix', '2-feat'],
        '0.4.0': ['3-big-feature'],
    },
    'backup_would_be_created': 'backups/0.3.2.sql',
}


def _invoke(args, input_text='', update_info=None, upgrade_result=None):
    """Invoke the upgrade command with mocked Repo."""
    runner = CliRunner()
    mock_repo = MagicMock()
    mock_repo.release_manager.update_production.return_value = (
        update_info or _UPDATE_INFO_TWO_RELEASES
    )
    mock_repo.release_manager.upgrade_production.return_value = (
        upgrade_result or _UPGRADE_RESULT_FULL
    )

    with patch('half_orm_dev.cli.commands.upgrade.Repo', return_value=mock_repo):
        return runner.invoke(upgrade, args, input=input_text, catch_exceptions=False)


# === Tests ===

class TestUpgradeAlreadyUpToDate:
    def test_exits_cleanly_when_no_updates(self):
        result = _invoke([], update_info=_UPDATE_INFO_UP_TO_DATE)
        assert result.exit_code == 0
        assert 'already at latest' in result.output.lower()

    def test_does_not_call_upgrade_production_when_up_to_date(self):
        runner = CliRunner()
        mock_repo = MagicMock()
        mock_repo.release_manager.update_production.return_value = _UPDATE_INFO_UP_TO_DATE
        with patch('half_orm_dev.cli.commands.upgrade.Repo', return_value=mock_repo):
            runner.invoke(upgrade, [], catch_exceptions=False)
        mock_repo.release_manager.upgrade_production.assert_not_called()


class TestUpgradeDryRun:
    def test_shows_dry_run_header(self):
        result = _invoke(['--dry-run'], upgrade_result=_UPGRADE_RESULT_DRY_RUN)
        assert 'DRY RUN' in result.output

    def test_shows_available_releases(self):
        result = _invoke(['--dry-run'], upgrade_result=_UPGRADE_RESULT_DRY_RUN)
        assert '0.3.3' in result.output
        assert '0.4.0' in result.output

    def test_shows_would_apply(self):
        result = _invoke(['--dry-run'], upgrade_result=_UPGRADE_RESULT_DRY_RUN)
        assert 'Would apply' in result.output or 'would apply' in result.output.lower()

    def test_no_confirmation_prompt(self):
        result = _invoke(['--dry-run'], upgrade_result=_UPGRADE_RESULT_DRY_RUN)
        assert 'Proceed?' not in result.output

    def test_no_interactive_prompt(self):
        result = _invoke(['--dry-run'], upgrade_result=_UPGRADE_RESULT_DRY_RUN)
        assert 'Target version' not in result.output


class TestUpgradeInteractivePrompt:
    def test_shows_target_version_prompt(self):
        # Send Enter to accept default, then Y to confirm
        result = _invoke([], input_text='\ny\n')
        assert 'Target version' in result.output

    def test_default_selects_latest(self):
        result = _invoke([], input_text='\ny\n')
        mock_call = None
        runner = CliRunner()
        mock_repo = MagicMock()
        mock_repo.release_manager.update_production.return_value = _UPDATE_INFO_TWO_RELEASES
        mock_repo.release_manager.upgrade_production.return_value = _UPGRADE_RESULT_FULL
        with patch('half_orm_dev.cli.commands.upgrade.Repo', return_value=mock_repo):
            runner.invoke(upgrade, [], input='\ny\n', catch_exceptions=False)
        # Default (Enter) → to_version=None (upgrade all)
        call_kwargs = mock_repo.release_manager.upgrade_production.call_args
        assert call_kwargs.kwargs.get('to_version') is None

    def test_select_intermediate_version(self):
        runner = CliRunner()
        mock_repo = MagicMock()
        mock_repo.release_manager.update_production.return_value = _UPDATE_INFO_TWO_RELEASES
        mock_repo.release_manager.upgrade_production.return_value = _UPGRADE_RESULT_FULL
        with patch('half_orm_dev.cli.commands.upgrade.Repo', return_value=mock_repo):
            runner.invoke(upgrade, [], input='0.3.3\ny\n', catch_exceptions=False)
        call_kwargs = mock_repo.release_manager.upgrade_production.call_args
        assert call_kwargs.kwargs.get('to_version') == '0.3.3'

    def test_invalid_version_aborts(self):
        result = _invoke([], input_text='9.9.9\n')
        assert result.exit_code != 0
        assert '9.9.9' in result.output

    def test_shows_confirmation_prompt(self):
        result = _invoke([], input_text='\ny\n')
        assert 'Proceed?' in result.output

    def test_decline_confirmation_cancels(self):
        runner = CliRunner()
        mock_repo = MagicMock()
        mock_repo.release_manager.update_production.return_value = _UPDATE_INFO_TWO_RELEASES
        with patch('half_orm_dev.cli.commands.upgrade.Repo', return_value=mock_repo):
            runner.invoke(upgrade, [], input='\nn\n', catch_exceptions=False)
        mock_repo.release_manager.upgrade_production.assert_not_called()


class TestUpgradeFlags:
    def test_yes_flag_skips_confirmation(self):
        runner = CliRunner()
        mock_repo = MagicMock()
        mock_repo.release_manager.update_production.return_value = _UPDATE_INFO_TWO_RELEASES
        mock_repo.release_manager.upgrade_production.return_value = _UPGRADE_RESULT_FULL
        with patch('half_orm_dev.cli.commands.upgrade.Repo', return_value=mock_repo):
            result = runner.invoke(upgrade, ['--yes'], input='\n', catch_exceptions=False)
        assert 'Proceed?' not in result.output
        mock_repo.release_manager.upgrade_production.assert_called_once()

    def test_to_release_flag_skips_interactive_prompt(self):
        runner = CliRunner()
        mock_repo = MagicMock()
        mock_repo.release_manager.update_production.return_value = _UPDATE_INFO_TWO_RELEASES
        mock_repo.release_manager.upgrade_production.return_value = _UPGRADE_RESULT_FULL
        with patch('half_orm_dev.cli.commands.upgrade.Repo', return_value=mock_repo):
            result = runner.invoke(
                upgrade, ['--to-release=0.3.3', '--yes'], catch_exceptions=False
            )
        assert 'Target version' not in result.output
        call_kwargs = mock_repo.release_manager.upgrade_production.call_args
        assert call_kwargs.kwargs.get('to_version') == '0.3.3'

    def test_update_info_passed_to_upgrade_production(self):
        """CLI passes pre-fetched update_info to avoid double git fetch."""
        runner = CliRunner()
        mock_repo = MagicMock()
        mock_repo.release_manager.update_production.return_value = _UPDATE_INFO_TWO_RELEASES
        mock_repo.release_manager.upgrade_production.return_value = _UPGRADE_RESULT_FULL
        with patch('half_orm_dev.cli.commands.upgrade.Repo', return_value=mock_repo):
            runner.invoke(upgrade, ['--yes'], input='\n', catch_exceptions=False)
        call_kwargs = mock_repo.release_manager.upgrade_production.call_args
        assert call_kwargs.kwargs.get('update_info') is _UPDATE_INFO_TWO_RELEASES
        # update_production() called only once (not twice)
        assert mock_repo.release_manager.update_production.call_count == 1
