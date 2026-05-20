"""
Test CLI behavior when half_orm_dev version is older than required.

When the installed version is older than what .hop/config requires,
the CLI auto-installs the correct version and re-executes the command.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, call
import subprocess as _sp
from click.testing import CliRunner

from half_orm_dev.repo import Repo, OutdatedHalfORMDevError
from half_orm_dev.cli import create_cli_group


@pytest.fixture
def temp_hop_dir(tmp_path):
    """Create a temporary directory with .hop/config requiring version 0.18.0."""
    Repo.clear_instances()

    hop_dir = tmp_path / '.hop'
    hop_dir.mkdir()

    config_content = """[halfORM]
hop_version = 0.18.0
devel = True
"""
    (hop_dir / 'config').write_text(config_content)

    yield tmp_path

    Repo.clear_instances()


def _make_cli_and_invoke(temp_hop_dir, installed_version, args=None):
    """
    Build CLI with version mismatch and invoke it with subprocess/execv mocked.
    Returns (result, mock_pip, mock_execv).
    """
    runner = CliRunner()
    args = args or []

    with patch('half_orm_dev.repo.Repo._find_base_dir', return_value=str(temp_hop_dir)):
        with patch('half_orm_dev.repo.hop_version', return_value=installed_version):
            Repo.clear_instances()
            cli = create_cli_group()
            with patch('half_orm_dev.cli.main.subprocess.run') as mock_pip:
                with patch('half_orm_dev.cli.main.os.execv') as mock_execv:
                    result = runner.invoke(cli, args, catch_exceptions=False)
                    return result, mock_pip, mock_execv


def test_auto_installs_required_version(temp_hop_dir):
    """On version mismatch, pip-installs the required version."""
    result, mock_pip, mock_execv = _make_cli_and_invoke(temp_hop_dir, '0.17.2')

    mock_pip.assert_called_once()
    call_args = mock_pip.call_args[0][0]
    assert 'pip' in call_args
    assert 'install' in call_args
    assert 'half-orm-dev==0.18.0' in call_args


def test_re_executes_after_install(temp_hop_dir):
    """After successful install, re-executes the same command via os.execv."""
    result, mock_pip, mock_execv = _make_cli_and_invoke(temp_hop_dir, '0.17.2')

    mock_execv.assert_called_once()


def test_shows_version_info_message(temp_hop_dir):
    """Shows required and installed versions before installing."""
    result, _, _ = _make_cli_and_invoke(temp_hop_dir, '0.17.2')

    assert '0.18.0' in result.output
    assert '0.17.2' in result.output


def test_shows_relaunch_message(temp_hop_dir):
    """Shows relaunch message after successful install."""
    result, _, _ = _make_cli_and_invoke(temp_hop_dir, '0.17.2')

    assert 'Relance en cours' in result.output


def test_pip_failure_exits_with_error(temp_hop_dir):
    """If pip install fails, shows manual install instructions and exits 1."""
    runner = CliRunner()

    with patch('half_orm_dev.repo.Repo._find_base_dir', return_value=str(temp_hop_dir)):
        with patch('half_orm_dev.repo.hop_version', return_value='0.17.2'):
            Repo.clear_instances()
            cli = create_cli_group()
            with patch('half_orm_dev.cli.main.subprocess.run',
                       side_effect=_sp.CalledProcessError(1, 'pip')):
                result = runner.invoke(cli, [])

    assert result.exit_code == 1
    assert 'pip install half-orm-dev==0.18.0' in result.output


def test_major_version_mismatch_auto_installs(tmp_path):
    """Auto-install also triggered for major version mismatches."""
    Repo.clear_instances()

    hop_dir = tmp_path / '.hop'
    hop_dir.mkdir()
    (hop_dir / 'config').write_text("[halfORM]\nhop_version = 1.0.0\ndevel = True\n")

    result, mock_pip, mock_execv = _make_cli_and_invoke(tmp_path, '0.17.2')

    mock_pip.assert_called_once()
    assert 'half-orm-dev==1.0.0' in mock_pip.call_args[0][0]

    Repo.clear_instances()


def test_alpha_version_older_than_required_auto_installs(tmp_path):
    """Alpha installed version older than required triggers auto-install."""
    Repo.clear_instances()

    hop_dir = tmp_path / '.hop'
    hop_dir.mkdir()
    (hop_dir / 'config').write_text("[halfORM]\nhop_version = 0.18.0\ndevel = True\n")

    result, mock_pip, _ = _make_cli_and_invoke(tmp_path, '0.18.0-a1')

    mock_pip.assert_called_once()

    Repo.clear_instances()


def test_outdated_error_exception_attributes():
    """OutdatedHalfORMDevError carries required and installed version."""
    error = OutdatedHalfORMDevError('0.18.0', '0.17.2')

    assert error.required_version == '0.18.0'
    assert error.installed_version == '0.17.2'
    assert '0.18.0' in str(error)
    assert '0.17.2' in str(error)