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

    def test_create_patch_not_on_ho_prod(self, cli_runner, mock_repo_with_patch_manager):
        """Test error when not on ho-prod branch."""
        with mock_repo_with_patch_manager() as (mock_repo, mock_patch_mgr):
            mock_patch_mgr.create_patch.side_effect = PatchManagerError(
                "Must be on ho-prod branch to create patch. Current branch: main"
            )

            result = cli_runner.invoke(create_patch, ['456'])

            assert result.exit_code != 0
            assert 'Must be on ho-prod branch' in result.output

    def test_create_patch_dirty_repo(self, cli_runner, mock_repo_with_patch_manager):
        """Test error when repository has uncommitted changes."""
        with mock_repo_with_patch_manager() as (mock_repo, mock_patch_mgr):
            mock_patch_mgr.create_patch.side_effect = PatchManagerError(
                "Repository has uncommitted changes. Commit or stash changes before creating patch."
            )

            result = cli_runner.invoke(create_patch, ['456'])

            assert result.exit_code != 0
            assert 'uncommitted changes' in result.output

    def test_create_patch_invalid_patch_id(self, cli_runner, mock_repo_with_patch_manager):
        """Test error with invalid patch ID format."""
        with mock_repo_with_patch_manager() as (mock_repo, mock_patch_mgr):
            mock_patch_mgr.create_patch.side_effect = PatchManagerError(
                "Invalid patch ID format: 'invalid@patch'"
            )

            result = cli_runner.invoke(create_patch, ['invalid@patch'])

            assert result.exit_code != 0
            assert 'Invalid patch ID' in result.output

    def test_create_patch_already_exists(self, cli_runner, mock_repo_with_patch_manager):
        """Test error when patch already exists."""
        with mock_repo_with_patch_manager() as (mock_repo, mock_patch_mgr):
            mock_patch_mgr.create_patch.side_effect = PatchManagerError(
                "Patch directory already exists: Patches/456"
            )

            result = cli_runner.invoke(create_patch, ['456'])

            assert result.exit_code != 0
            assert 'already exists' in result.output

    def test_create_patch_branch_already_exists(self, cli_runner, mock_repo_with_patch_manager):
        """Test error when branch already exists."""
        with mock_repo_with_patch_manager() as (mock_repo, mock_patch_mgr):
            mock_patch_mgr.create_patch.side_effect = PatchManagerError(
                "Branch ho-patch/456 already exists"
            )

            result = cli_runner.invoke(create_patch, ['456'])

            assert result.exit_code != 0
            assert 'already exists' in result.output

    def test_create_patch_not_synced_with_origin(self, cli_runner, mock_repo_with_patch_manager):
        """Test error when not synced with origin."""
        with mock_repo_with_patch_manager() as (mock_repo, mock_patch_mgr):
            mock_patch_mgr.create_patch.side_effect = PatchManagerError(
                "ho-prod is not synced with origin/ho-prod. Pull changes first."
            )

            result = cli_runner.invoke(create_patch, ['456'])

            assert result.exit_code != 0
            assert 'not synced' in result.output or 'Pull changes' in result.output

    def test_create_patch_git_error(self, cli_runner, mock_repo_with_patch_manager):
        """Test handling of Git-related errors."""
        with mock_repo_with_patch_manager() as (mock_repo, mock_patch_mgr):
            mock_patch_mgr.create_patch.side_effect = PatchManagerError(
                "Git operation failed: unable to create branch"
            )

            result = cli_runner.invoke(create_patch, ['456'])

            assert result.exit_code != 0
            assert 'Git operation failed' in result.output or 'unable to create' in result.output

    def test_create_patch_permission_error(self, cli_runner, mock_repo_with_patch_manager):
        """Test handling of permission errors."""
        with mock_repo_with_patch_manager() as (mock_repo, mock_patch_mgr):
            mock_patch_mgr.create_patch.side_effect = PatchManagerError(
                "Permission denied: cannot create directory Patches/456"
            )

            result = cli_runner.invoke(create_patch, ['456'])

            assert result.exit_code != 0
            assert 'Permission denied' in result.output

    def test_create_patch_error_messages_to_stderr(self, cli_runner, mock_repo_with_patch_manager):
        """Test that error messages are written to stderr."""
        with mock_repo_with_patch_manager() as (mock_repo, mock_patch_mgr):
            mock_patch_mgr.create_patch.side_effect = PatchManagerError("Test error")

            result = cli_runner.invoke(create_patch, ['456'])

            # Click writes errors to output in test mode, but we verify exit code
            assert result.exit_code != 0
            assert 'Test error' in result.output

    def test_create_patch_missing_argument(self, cli_runner):
        """Test error when patch_id argument is missing."""
        # Invoke CLI without patch_id
        result = cli_runner.invoke(create_patch, [])

        # Should fail with Click error
        assert result.exit_code != 0
        assert 'Missing argument' in result.output or 'PATCH_ID' in result.output

    def test_create_patch_empty_patch_id(self, cli_runner, mock_repo_with_patch_manager):
        """Test error with empty patch ID."""
        with mock_repo_with_patch_manager() as (mock_repo, mock_patch_mgr):
            mock_patch_mgr.create_patch.side_effect = PatchManagerError(
                "Invalid patch ID: empty or whitespace"
            )

            result = cli_runner.invoke(create_patch, ['   '])

            assert result.exit_code != 0

    def test_create_patch_no_remote_configured(self, cli_runner, mock_repo_with_patch_manager):
        """Test error when no Git remote is configured."""
        with mock_repo_with_patch_manager() as (mock_repo, mock_patch_mgr):
            mock_patch_mgr.create_patch.side_effect = PatchManagerError(
                "No remote 'origin' configured. Configure remote first."
            )

            result = cli_runner.invoke(create_patch, ['456'])

            assert result.exit_code != 0
            assert 'remote' in result.output.lower() or 'origin' in result.output

    def test_create_patch_error_preserves_message(self, cli_runner, mock_repo_with_patch_manager):
        """Test that error message from PatchManager is preserved."""
        with mock_repo_with_patch_manager() as (mock_repo, mock_patch_mgr):
            specific_error = "Very specific error message that should be preserved"
            mock_patch_mgr.create_patch.side_effect = PatchManagerError(specific_error)

            result = cli_runner.invoke(create_patch, ['456'])

            # Exact error message should appear in output
            assert specific_error in result.output