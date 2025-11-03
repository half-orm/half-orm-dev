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
from unittest.mock import Mock, patch
from click.testing import CliRunner

# from half_orm_dev.cli.commands.create_patch import create_patch
from half_orm_dev.patch_manager import PatchManagerError

@pytest.skip(allow_module_level=True)
class TestCreatePatchCLIBasic:
    """Test basic CLI functionality for create-patch command."""

    @pytest.fixture
    def cli_runner(self):
        """Provide Click CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def mock_repo_with_patch_manager(self):
        """
        Provide properly configured mock Repo with PatchManager.

        Returns a context manager that patches Repo correctly.
        """
        from contextlib import contextmanager

        @contextmanager
        def _patch():
            mock_patch_mgr = Mock()
            mock_repo_instance = Mock()

            # Assigner patch_manager comme attribut simple, pas comme propriété
            mock_repo_instance.patch_manager = mock_patch_mgr

            with patch('half_orm_dev.cli.commands.create_patch.Repo') as mock_repo_class:
                mock_repo_class.return_value = mock_repo_instance
                yield mock_repo_instance, mock_patch_mgr

        return _patch

    def test_create_patch_with_numeric_id(self, cli_runner, mock_repo_with_patch_manager):
        """Test CLI invocation with numeric patch ID."""
        with mock_repo_with_patch_manager() as (mock_repo, mock_patch_mgr):
            mock_patch_mgr.create_patch.return_value = {
                'patch_id': '456',
                'branch_name': 'ho-patch/456',
                'patch_dir': Path('Patches/456'),
                'on_branch': 'ho-patch/456'
            }

            result = cli_runner.invoke(create_patch, ['456'])

            assert result.exit_code == 0
            assert 'Created patch branch: ho-patch/456' in result.output
            assert 'Created patch directory: Patches/456' in result.output
            assert 'Switched to branch: ho-patch/456' in result.output
            mock_patch_mgr.create_patch.assert_called_once_with('456', None)

    def test_create_patch_with_full_id(self, cli_runner, mock_repo_with_patch_manager):
        """Test CLI invocation with full patch ID."""
        with mock_repo_with_patch_manager() as (mock_repo, mock_patch_mgr):
            mock_patch_mgr.create_patch.return_value = {
                'patch_id': '456-user-auth',
                'branch_name': 'ho-patch/456-user-auth',
                'patch_dir': Path('Patches/456-user-auth'),
                'on_branch': 'ho-patch/456-user-auth'
            }

            result = cli_runner.invoke(create_patch, ['456-user-auth'])

            assert result.exit_code == 0
            assert 'ho-patch/456-user-auth' in result.output
            mock_patch_mgr.create_patch.assert_called_once_with('456-user-auth', None)

    def test_create_patch_with_description_option(self, cli_runner, mock_repo_with_patch_manager):
        """Test CLI invocation with --description option."""
        with mock_repo_with_patch_manager() as (mock_repo, mock_patch_mgr):
            mock_patch_mgr.create_patch.return_value = {
                'patch_id': '456',
                'branch_name': 'ho-patch/456',
                'patch_dir': Path('Patches/456'),
                'on_branch': 'ho-patch/456'
            }

            result = cli_runner.invoke(
                create_patch,
                ['456', '--description', 'Add user authentication']
            )

            assert result.exit_code == 0
            mock_patch_mgr.create_patch.assert_called_once_with('456', 'Add user authentication')

    def test_create_patch_with_description_short_option(self, cli_runner, mock_repo_with_patch_manager):
        """Test CLI invocation with -d short option."""
        with mock_repo_with_patch_manager() as (mock_repo, mock_patch_mgr):
            mock_patch_mgr.create_patch.return_value = {
                'patch_id': '789',
                'branch_name': 'ho-patch/789',
                'patch_dir': Path('Patches/789'),
                'on_branch': 'ho-patch/789'
            }

            result = cli_runner.invoke(
                create_patch,
                ['789', '-d', 'Fix bug in login']
            )

            assert result.exit_code == 0
            mock_patch_mgr.create_patch.assert_called_once_with('789', 'Fix bug in login')

    def test_create_patch_displays_all_info(self, cli_runner, mock_repo_with_patch_manager):
        """Test that CLI displays all required information."""
        with mock_repo_with_patch_manager() as (mock_repo, mock_patch_mgr):
            mock_patch_mgr.create_patch.return_value = {
                'patch_id': '123',
                'branch_name': 'ho-patch/123-feature',
                'patch_dir': Path('Patches/123-feature'),
                'on_branch': 'ho-patch/123-feature'
            }

            result = cli_runner.invoke(create_patch, ['123-feature'])

            assert 'Created patch branch' in result.output
            assert 'ho-patch/123-feature' in result.output
            assert 'Created patch directory' in result.output
            assert 'Patches/123-feature' in result.output
            assert 'Switched to branch' in result.output

    def test_create_patch_multiline_description(self, cli_runner, mock_repo_with_patch_manager):
        """Test CLI with multiline description."""
        with mock_repo_with_patch_manager() as (mock_repo, mock_patch_mgr):
            mock_patch_mgr.create_patch.return_value = {
                'patch_id': '999',
                'branch_name': 'ho-patch/999',
                'patch_dir': Path('Patches/999'),
                'on_branch': 'ho-patch/999'
            }

            multiline_desc = "Add feature\nWith multiple lines\nOf description"
            result = cli_runner.invoke(
                create_patch,
                ['999', '-d', multiline_desc]
            )

            assert result.exit_code == 0
            mock_patch_mgr.create_patch.assert_called_once_with('999', multiline_desc)

    def test_create_patch_without_description(self, cli_runner, mock_repo_with_patch_manager):
        """Test CLI without description passes None."""
        with mock_repo_with_patch_manager() as (mock_repo, mock_patch_mgr):
            mock_patch_mgr.create_patch.return_value = {
                'patch_id': '111',
                'branch_name': 'ho-patch/111',
                'patch_dir': Path('Patches/111'),
                'on_branch': 'ho-patch/111'
            }

            result = cli_runner.invoke(create_patch, ['111'])

            mock_patch_mgr.create_patch.assert_called_once_with('111', None)

    def test_create_patch_success_exit_code(self, cli_runner, mock_repo_with_patch_manager):
        """Test successful command returns exit code 0."""
        with mock_repo_with_patch_manager() as (mock_repo, mock_patch_mgr):
            mock_patch_mgr.create_patch.return_value = {
                'patch_id': '555',
                'branch_name': 'ho-patch/555',
                'patch_dir': Path('Patches/555'),
                'on_branch': 'ho-patch/555'
            }

            result = cli_runner.invoke(create_patch, ['555'])

            assert result.exit_code == 0