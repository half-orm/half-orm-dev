"""
Tests for create-patch CLI command - basic functionality.

Focused on testing:
- CLI invocation with Click
- Arguments and options handling
- Success messages and output
- Integration with Repo and PatchManager
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from click.testing import CliRunner

from half_orm_dev.cli.commands.create_patch import create_patch
from half_orm_dev.patch_manager import PatchManagerError


class TestCreatePatchCLIBasic:
    """Test basic CLI functionality for create-patch command."""

    @pytest.fixture
    def cli_runner(self):
        """Provide Click CLI test runner."""
        return CliRunner()

    def test_create_patch_with_numeric_id(self, cli_runner):
        """Test CLI invocation with numeric patch ID."""
        # Mock Repo and PatchManager
        with patch('half_orm_dev.cli.commands.create_patch.Repo') as mock_repo_class:
            mock_repo = Mock()
            mock_patch_mgr = Mock()
            mock_patch_mgr.create_patch.return_value = {
                'patch_id': '456',
                'branch_name': 'ho-patch/456',
                'patch_dir': Path('Patches/456'),
                'on_branch': 'ho-patch/456'
            }
            mock_repo.patch_manager = mock_patch_mgr
            mock_repo_class.return_value = mock_repo

            # Invoke CLI
            result = cli_runner.invoke(create_patch, ['456'])

            # Should succeed
            assert result.exit_code == 0
            assert 'Created patch branch: ho-patch/456' in result.output
            assert 'Created patch directory: Patches/456' in result.output
            assert 'Switched to branch: ho-patch/456' in result.output

            # Should call PatchManager.create_patch
            mock_patch_mgr.create_patch.assert_called_once_with('456', None)

    def test_create_patch_with_full_id(self, cli_runner):
        """Test CLI invocation with full patch ID."""
        with patch('half_orm_dev.cli.commands.create_patch.Repo') as mock_repo_class:
            mock_repo = Mock()
            mock_patch_mgr = Mock()
            mock_patch_mgr.create_patch.return_value = {
                'patch_id': '456-user-auth',
                'branch_name': 'ho-patch/456-user-auth',
                'patch_dir': Path('Patches/456-user-auth'),
                'on_branch': 'ho-patch/456-user-auth'
            }
            mock_repo.patch_manager = mock_patch_mgr
            mock_repo_class.return_value = mock_repo

            # Invoke CLI
            result = cli_runner.invoke(create_patch, ['456-user-auth'])

            # Should succeed
            assert result.exit_code == 0
            assert 'ho-patch/456-user-auth' in result.output
            assert 'Patches/456-user-auth' in result.output

            # Should call PatchManager.create_patch
            mock_patch_mgr.create_patch.assert_called_once_with('456-user-auth', None)

    def test_create_patch_with_description_short_option(self, cli_runner):
        """Test CLI with --description short option (-d)."""
        with patch('half_orm_dev.cli.commands.create_patch.Repo') as mock_repo_class:
            mock_repo = Mock()
            mock_patch_mgr = Mock()
            mock_patch_mgr.create_patch.return_value = {
                'patch_id': '456-user-auth',
                'branch_name': 'ho-patch/456-user-auth',
                'patch_dir': Path('Patches/456-user-auth'),
                'on_branch': 'ho-patch/456-user-auth'
            }
            mock_repo.patch_manager = mock_patch_mgr
            mock_repo_class.return_value = mock_repo

            # Invoke CLI with -d option
            result = cli_runner.invoke(
                create_patch,
                ['456-user-auth', '-d', 'Add user authentication']
            )

            # Should succeed
            assert result.exit_code == 0

            # Should pass description to PatchManager
            mock_patch_mgr.create_patch.assert_called_once_with(
                '456-user-auth',
                'Add user authentication'
            )

    def test_create_patch_with_description_long_option(self, cli_runner):
        """Test CLI with --description long option."""
        with patch('half_orm_dev.cli.commands.create_patch.Repo') as mock_repo_class:
            mock_repo = Mock()
            mock_patch_mgr = Mock()
            mock_patch_mgr.create_patch.return_value = {
                'patch_id': '456-user-auth',
                'branch_name': 'ho-patch/456-user-auth',
                'patch_dir': Path('Patches/456-user-auth'),
                'on_branch': 'ho-patch/456-user-auth'
            }
            mock_repo.patch_manager = mock_patch_mgr
            mock_repo_class.return_value = mock_repo

            # Invoke CLI with --description option
            result = cli_runner.invoke(
                create_patch,
                ['456-user-auth', '--description', 'Add user authentication']
            )

            # Should succeed
            assert result.exit_code == 0

            # Should pass description to PatchManager
            mock_patch_mgr.create_patch.assert_called_once_with(
                '456-user-auth',
                'Add user authentication'
            )

    def test_create_patch_displays_next_steps(self, cli_runner):
        """Test that CLI displays next steps after success."""
        with patch('half_orm_dev.cli.commands.create_patch.Repo') as mock_repo_class:
            mock_repo = Mock()
            mock_patch_mgr = Mock()
            mock_patch_mgr.create_patch.return_value = {
                'patch_id': '456',
                'branch_name': 'ho-patch/456',
                'patch_dir': Path('Patches/456'),
                'on_branch': 'ho-patch/456'
            }
            mock_repo.patch_manager = mock_patch_mgr
            mock_repo_class.return_value = mock_repo

            # Invoke CLI
            result = cli_runner.invoke(create_patch, ['456'])

            # Should display next steps
            assert 'Next steps:' in result.output
            assert 'Add SQL/Python files to Patches/456/' in result.output
            assert 'half_orm dev apply-patch' in result.output
            assert 'Test your changes' in result.output
            assert 'half_orm dev add-to-release' in result.output

    def test_create_patch_uses_repo_singleton(self, cli_runner):
        """Test that CLI uses Repo singleton correctly."""
        with patch('half_orm_dev.cli.commands.create_patch.Repo') as mock_repo_class:
            mock_repo = Mock()
            mock_patch_mgr = Mock()
            mock_patch_mgr.create_patch.return_value = {
                'patch_id': '456',
                'branch_name': 'ho-patch/456',
                'patch_dir': Path('Patches/456'),
                'on_branch': 'ho-patch/456'
            }
            mock_repo.patch_manager = mock_patch_mgr
            mock_repo_class.return_value = mock_repo

            # Invoke CLI
            result = cli_runner.invoke(create_patch, ['456'])

            # Should call Repo() once
            mock_repo_class.assert_called_once_with()

            # Should access patch_manager property
            assert mock_repo.patch_manager.create_patch.called

    def test_create_patch_success_symbols(self, cli_runner):
        """Test that success messages include checkmark symbols."""
        with patch('half_orm_dev.cli.commands.create_patch.Repo') as mock_repo_class:
            mock_repo = Mock()
            mock_patch_mgr = Mock()
            mock_patch_mgr.create_patch.return_value = {
                'patch_id': '456',
                'branch_name': 'ho-patch/456',
                'patch_dir': Path('Patches/456'),
                'on_branch': 'ho-patch/456'
            }
            mock_repo.patch_manager = mock_patch_mgr
            mock_repo_class.return_value = mock_repo

            # Invoke CLI
            result = cli_runner.invoke(create_patch, ['456'])

            # Should have checkmark symbols (✓)
            assert '✓' in result.output or 'Created' in result.output

    def test_create_patch_without_description_option(self, cli_runner):
        """Test that description defaults to None when not provided."""
        with patch('half_orm_dev.cli.commands.create_patch.Repo') as mock_repo_class:
            mock_repo = Mock()
            mock_patch_mgr = Mock()
            mock_patch_mgr.create_patch.return_value = {
                'patch_id': '456',
                'branch_name': 'ho-patch/456',
                'patch_dir': Path('Patches/456'),
                'on_branch': 'ho-patch/456'
            }
            mock_repo.patch_manager = mock_patch_mgr
            mock_repo_class.return_value = mock_repo

            # Invoke CLI without description
            result = cli_runner.invoke(create_patch, ['456'])

            # Should pass None as description
            mock_patch_mgr.create_patch.assert_called_once_with('456', None)

    def test_create_patch_multiline_description(self, cli_runner):
        """Test CLI with multiline description."""
        with patch('half_orm_dev.cli.commands.create_patch.Repo') as mock_repo_class:
            mock_repo = Mock()
            mock_patch_mgr = Mock()
            mock_patch_mgr.create_patch.return_value = {
                'patch_id': '456',
                'branch_name': 'ho-patch/456',
                'patch_dir': Path('Patches/456'),
                'on_branch': 'ho-patch/456'
            }
            mock_repo.patch_manager = mock_patch_mgr
            mock_repo_class.return_value = mock_repo

            # Multiline description
            description = "Add user authentication\nWith JWT support\nAnd password hashing"

            # Invoke CLI
            result = cli_runner.invoke(
                create_patch,
                ['456', '-d', description]
            )

            # Should succeed and pass full description
            assert result.exit_code == 0
            mock_patch_mgr.create_patch.assert_called_once_with('456', description)
