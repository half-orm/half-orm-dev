"""
Test CLI behavior when half_orm_dev version is downgraded.

Ensures that when a user has a repository requiring a newer version
of half_orm_dev than what's installed, all commands are blocked with
a clear, user-friendly error message.
"""

import pytest
from pathlib import Path
from unittest.mock import patch
from click.testing import CliRunner

from half_orm_dev.repo import Repo, OutdatedHalfORMDevError
from half_orm_dev.cli import create_cli_group


@pytest.fixture
def temp_hop_dir(tmp_path):
    """Create a temporary directory with .hop structure."""
    Repo.clear_instances()

    hop_dir = tmp_path / '.hop'
    hop_dir.mkdir()

    # Create config requiring version 0.18.0
    config_content = """[halfORM]
hop_version = 0.18.0
devel = True
"""
    (hop_dir / 'config').write_text(config_content)

    yield tmp_path

    Repo.clear_instances()


def test_cli_blocks_all_commands_on_downgrade(temp_hop_dir):
    """Test that CLI displays error and blocks when version is downgraded."""
    runner = CliRunner()

    with patch('half_orm_dev.repo.Repo._find_base_dir', return_value=str(temp_hop_dir)):
        with patch('half_orm_dev.repo.hop_version', return_value='0.17.2'):
            Repo.clear_instances()

            # Create CLI group - should handle the error gracefully
            cli = create_cli_group()

            # Test 1: Try to run without any command (invoke the group directly)
            result = runner.invoke(cli, [])

            # Should exit with error
            assert result.exit_code != 0

            # Should display formatted error message
            assert '❌ OUTDATED half_orm_dev VERSION' in result.stderr
            assert 'Repository requires: 0.18.0' in result.stderr
            assert 'Installed version:   0.17.2' in result.stderr
            assert 'Your installed version is OLDER' in result.stderr
            assert 'All commands are blocked for safety' in result.stderr
            assert 'pip install --upgrade half_orm_dev' in result.stderr
            assert '=' * 70 in result.stderr

            # Test 2: Try to invoke a specific command - should also be blocked
            result2 = runner.invoke(cli, ['check'])

            # Should also exit with error
            assert result2.exit_code != 0

            # Should display the same error message (not "No such command")
            assert '❌ OUTDATED half_orm_dev VERSION' in result2.stderr
            assert 'Repository requires: 0.18.0' in result2.stderr
            assert 'All commands are blocked for safety' in result2.stderr

            # Should NOT display Click's "No such command" error
            assert 'No such command' not in result2.stderr


def test_cli_error_message_format(temp_hop_dir):
    """Test the exact format of the downgrade error message."""
    runner = CliRunner()

    with patch('half_orm_dev.repo.Repo._find_base_dir', return_value=str(temp_hop_dir)):
        with patch('half_orm_dev.repo.hop_version', return_value='0.17.2'):
            Repo.clear_instances()

            cli = create_cli_group()
            result = runner.invoke(cli, [])

            # Verify error structure
            stderr_lines = result.stderr.split('\n')

            # Should have separator lines
            separator_lines = [line for line in stderr_lines if '=' * 70 in line]
            assert len(separator_lines) >= 2, "Should have opening and closing separators"

            # Should mention both versions
            assert any('0.18.0' in line for line in stderr_lines)
            assert any('0.17.2' in line for line in stderr_lines)

            # Should provide upgrade command
            assert any('pip install --upgrade half_orm_dev' in line for line in stderr_lines)


def test_outdated_error_exception_attributes():
    """Test OutdatedHalfORMDevError exception attributes."""
    error = OutdatedHalfORMDevError('0.18.0', '0.17.2')

    assert error.required_version == '0.18.0'
    assert error.installed_version == '0.17.2'

    error_msg = str(error)
    assert '0.18.0' in error_msg
    assert '0.17.2' in error_msg
    assert 'pip install --upgrade half_orm_dev' in error_msg


def test_cli_blocks_with_major_version_mismatch(tmp_path):
    """Test CLI blocks with major version incompatibility."""
    Repo.clear_instances()

    hop_dir = tmp_path / '.hop'
    hop_dir.mkdir()

    # Repository requires version 1.0.0
    config_content = """[halfORM]
hop_version = 1.0.0
devel = True
"""
    (hop_dir / 'config').write_text(config_content)

    runner = CliRunner()

    with patch('half_orm_dev.repo.Repo._find_base_dir', return_value=str(tmp_path)):
        with patch('half_orm_dev.repo.hop_version', return_value='0.17.2'):
            Repo.clear_instances()

            cli = create_cli_group()
            result = runner.invoke(cli, [])

            # Should exit with error
            assert result.exit_code != 0

            # Should display error with correct versions
            assert '1.0.0' in result.stderr
            assert '0.17.2' in result.stderr

    Repo.clear_instances()


def test_cli_blocks_with_alpha_version_downgrade(tmp_path):
    """Test CLI blocks when alpha version is older than required."""
    Repo.clear_instances()

    hop_dir = tmp_path / '.hop'
    hop_dir.mkdir()

    # Repository requires stable 0.18.0
    config_content = """[halfORM]
hop_version = 0.18.0
devel = True
"""
    (hop_dir / 'config').write_text(config_content)

    runner = CliRunner()

    with patch('half_orm_dev.repo.Repo._find_base_dir', return_value=str(tmp_path)):
        # User has alpha version that's older
        with patch('half_orm_dev.repo.hop_version', return_value='0.18.0-a1'):
            Repo.clear_instances()

            cli = create_cli_group()
            result = runner.invoke(cli, [])

            # Should exit with error (alpha < stable release)
            assert result.exit_code != 0

            # Should display error
            assert '0.18.0' in result.stderr
            assert '0.18.0-a1' in result.stderr

    Repo.clear_instances()
