"""
Tests for create-patch CLI command - error handling.

Focused on testing:
- PatchManagerError handling
- Click error messages
- User-friendly error output
- Unexpected error handling
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from click.testing import CliRunner

from half_orm_dev.cli.commands.create_patch import create_patch
from half_orm_dev.patch_manager import PatchManagerError


class TestCreatePatchCLIErrors:
    """Test error handling for create-patch CLI command."""

    @pytest.fixture
    def cli_runner(self):
        """Provide Click CLI test runner."""
        return CliRunner()

    def test_create_patch_not_on_ho_prod(self, cli_runner):
        """Test error when not on ho-prod branch."""
        with patch('half_orm_dev.cli.commands.create_patch.Repo') as mock_repo_class:
            mock_repo = Mock()
            mock_patch_mgr = Mock()
            mock_patch_mgr.create_patch.side_effect = PatchManagerError(
                "Must be on ho-prod branch to create patch. Current branch: main"
            )
            mock_repo.patch_manager = mock_patch_mgr
            mock_repo_class.return_value = mock_repo

            # Invoke CLI
            result = cli_runner.invoke(create_patch, ['456'])

            # Should fail with error
            assert result.exit_code != 0
            assert 'Must be on ho-prod branch' in result.output

    def test_create_patch_dirty_repo(self, cli_runner):
        """Test error when repository has uncommitted changes."""
        with patch('half_orm_dev.cli.commands.create_patch.Repo') as mock_repo_class:
            mock_repo = Mock()
            mock_patch_mgr = Mock()
            mock_patch_mgr.create_patch.side_effect = PatchManagerError(
                "Repository has uncommitted changes. Commit or stash changes before creating patch."
            )
            mock_repo.patch_manager = mock_patch_mgr
            mock_repo_class.return_value = mock_repo

            # Invoke CLI
            result = cli_runner.invoke(create_patch, ['456'])

            # Should fail with error
            assert result.exit_code != 0
            assert 'uncommitted changes' in result.output

    def test_create_patch_invalid_patch_id(self, cli_runner):
        """Test error with invalid patch ID format."""
        with patch('half_orm_dev.cli.commands.create_patch.Repo') as mock_repo_class:
            mock_repo = Mock()
            mock_patch_mgr = Mock()
            mock_patch_mgr.create_patch.side_effect = PatchManagerError(
                "Invalid patch ID: Patch ID must start with a number"
            )
            mock_repo.patch_manager = mock_patch_mgr
            mock_repo_class.return_value = mock_repo

            # Invoke CLI with invalid ID
            result = cli_runner.invoke(create_patch, ['invalid-no-number'])

            # Should fail with error
            assert result.exit_code != 0
            assert 'Invalid patch ID' in result.output

    def test_create_patch_branch_already_exists(self, cli_runner):
        """Test error when branch already exists."""
        with patch('half_orm_dev.cli.commands.create_patch.Repo') as mock_repo_class:
            mock_repo = Mock()
            mock_patch_mgr = Mock()
            mock_patch_mgr.create_patch.side_effect = PatchManagerError(
                "Branch already exists: ho-patch/456-user-auth"
            )
            mock_repo.patch_manager = mock_patch_mgr
            mock_repo_class.return_value = mock_repo

            # Invoke CLI
            result = cli_runner.invoke(create_patch, ['456-user-auth'])

            # Should fail with error
            assert result.exit_code != 0
            assert 'already exists' in result.output

    def test_create_patch_directory_already_exists(self, cli_runner):
        """Test error when patch directory already exists."""
        with patch('half_orm_dev.cli.commands.create_patch.Repo') as mock_repo_class:
            mock_repo = Mock()
            mock_patch_mgr = Mock()
            mock_patch_mgr.create_patch.side_effect = PatchManagerError(
                "Patch directory already exists: 456-user-auth"
            )
            mock_repo.patch_manager = mock_patch_mgr
            mock_repo_class.return_value = mock_repo

            # Invoke CLI
            result = cli_runner.invoke(create_patch, ['456-user-auth'])

            # Should fail with error
            assert result.exit_code != 0
            assert 'already exists' in result.output

    def test_create_patch_unexpected_error(self, cli_runner):
        """Test handling of unexpected errors."""
        with patch('half_orm_dev.cli.commands.create_patch.Repo') as mock_repo_class:
            mock_repo = Mock()
            mock_patch_mgr = Mock()
            mock_patch_mgr.create_patch.side_effect = RuntimeError("Unexpected error occurred")
            mock_repo.patch_manager = mock_patch_mgr
            mock_repo_class.return_value = mock_repo

            # Invoke CLI
            result = cli_runner.invoke(create_patch, ['456'])

            # Should fail with wrapped error
            assert result.exit_code != 0
            assert 'Unexpected error' in result.output

    def test_create_patch_error_no_success_message(self, cli_runner):
        """Test that success messages are not displayed on error."""
        with patch('half_orm_dev.cli.commands.create_patch.Repo') as mock_repo_class:
            mock_repo = Mock()
            mock_patch_mgr = Mock()
            mock_patch_mgr.create_patch.side_effect = PatchManagerError(
                "Must be on ho-prod branch"
            )
            mock_repo.patch_manager = mock_patch_mgr
            mock_repo_class.return_value = mock_repo

            # Invoke CLI
            result = cli_runner.invoke(create_patch, ['456'])

            # Should NOT display success messages
            assert 'Created patch branch' not in result.output
            assert 'Next steps' not in result.output
            assert '✓' not in result.output

    def test_create_patch_permission_error(self, cli_runner):
        """Test error when lacking permissions."""
        with patch('half_orm_dev.cli.commands.create_patch.Repo') as mock_repo_class:
            mock_repo = Mock()
            mock_patch_mgr = Mock()
            mock_patch_mgr.create_patch.side_effect = PatchManagerError(
                "Permission denied: cannot create Patches directory"
            )
            mock_repo.patch_manager = mock_patch_mgr
            mock_repo_class.return_value = mock_repo

            # Invoke CLI
            result = cli_runner.invoke(create_patch, ['456'])

            # Should fail with error
            assert result.exit_code != 0
            assert 'Permission denied' in result.output

    def test_create_patch_error_exit_code(self, cli_runner):
        """Test that errors return non-zero exit code."""
        with patch('half_orm_dev.cli.commands.create_patch.Repo') as mock_repo_class:
            mock_repo = Mock()
            mock_patch_mgr = Mock()
            mock_patch_mgr.create_patch.side_effect = PatchManagerError("Some error")
            mock_repo.patch_manager = mock_patch_mgr
            mock_repo_class.return_value = mock_repo

            # Invoke CLI
            result = cli_runner.invoke(create_patch, ['456'])

            # Should return non-zero exit code
            assert result.exit_code == 1

    def test_create_patch_missing_required_argument(self, cli_runner):
        """Test error when patch_id argument is missing."""
        # Invoke CLI without patch_id
        result = cli_runner.invoke(create_patch, [])

        # Should fail with Click error
        assert result.exit_code != 0
        assert 'Missing argument' in result.output or 'PATCH_ID' in result.output
