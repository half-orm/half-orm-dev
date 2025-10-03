"""
Tests for apply-patch CLI command.

Focused on testing:
- CLI invocation with Click
- Automatic patch detection from current branch
- Success messages and formatted output
- Error handling for invalid branches and workflow failures
- Integration with Repo, HGit, and PatchManager
"""

import pytest
from unittest.mock import Mock, patch
from click.testing import CliRunner

from half_orm_dev.cli.commands.apply_patch import apply_patch
from half_orm_dev.patch_manager import PatchManagerError


class TestApplyPatchCLI:
    """Test apply-patch CLI command."""

    @pytest.fixture
    def cli_runner(self):
        """Provide Click CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def mock_repo_on_patch_branch(self):
        """
        Mock Repo environment on valid ho-patch branch.

        Returns:
            Tuple of (mock_repo, mock_hgit, mock_patch_mgr)
        """
        mock_repo = Mock()
        mock_hgit = Mock()
        mock_patch_mgr = Mock()

        # Mock branch detection
        mock_hgit.current_branch.return_value = 'ho-patch/456-user-auth'
        mock_repo.hgit = mock_hgit

        # Mock successful workflow
        mock_patch_mgr.apply_patch_complete_workflow.return_value = {
            'patch_id': '456-user-auth',
            'status': 'success',
            'applied_files': ['01_create_users.sql', '02_add_indexes.sql'],
            'generated_files': [
                'mydb/mydb/public/user.py',
                'mydb/mydb/public/user_session.py',
                'tests/mydb/public/test_user.py'
            ],
            'error': None
        }
        mock_repo.patch_manager = mock_patch_mgr

        return mock_repo, mock_hgit, mock_patch_mgr

    @pytest.fixture
    def mock_repo_on_prod_branch(self):
        """Mock Repo environment on ho-prod branch."""
        mock_repo = Mock()
        mock_hgit = Mock()

        # Mock branch detection - on ho-prod
        mock_hgit.current_branch.return_value = 'ho-prod'
        mock_repo.hgit = mock_hgit

        return mock_repo, mock_hgit

    @pytest.fixture
    def mock_repo_on_invalid_branch(self):
        """Mock Repo environment on non-ho-patch branch."""
        mock_repo = Mock()
        mock_hgit = Mock()

        # Mock branch detection - on feature branch
        mock_hgit.current_branch.return_value = 'feature/new-feature'
        mock_repo.hgit = mock_hgit

        return mock_repo, mock_hgit

    def test_apply_patch_success(self, cli_runner, mock_repo_on_patch_branch):
        """Test successful patch application with formatted output."""
        mock_repo, mock_hgit, mock_patch_mgr = mock_repo_on_patch_branch

        with patch('half_orm_dev.cli.commands.apply_patch.Repo') as mock_repo_class:
            mock_repo_class.return_value = mock_repo

            # Invoke CLI
            result = cli_runner.invoke(apply_patch, [])

            # Should succeed
            assert result.exit_code == 0

            # Verify workflow called with correct patch_id
            mock_patch_mgr.apply_patch_complete_workflow.assert_called_once_with('456-user-auth')

            # Verify output contains success indicators
            assert '456-user-auth' in result.output
            assert 'ho-patch/456-user-auth' in result.output

            # Verify applied files listed
            assert '01_create_users.sql' in result.output
            assert '02_add_indexes.sql' in result.output

            # Verify generated files listed
            assert 'mydb/mydb/public/user.py' in result.output
            assert 'mydb/mydb/public/user_session.py' in result.output
            assert 'tests/mydb/public/test_user.py' in result.output

    def test_apply_patch_on_ho_prod_branch(self, cli_runner, mock_repo_on_prod_branch):
        """Test error when running on ho-prod branch."""
        mock_repo, mock_hgit = mock_repo_on_prod_branch

        with patch('half_orm_dev.cli.commands.apply_patch.Repo') as mock_repo_class:
            mock_repo_class.return_value = mock_repo

            # Invoke CLI
            result = cli_runner.invoke(apply_patch, [])

            # Should fail with error
            assert result.exit_code != 0
            assert 'ho-patch' in result.output.lower()
            assert 'ho-prod' in result.output

    def test_apply_patch_on_invalid_branch(self, cli_runner, mock_repo_on_invalid_branch):
        """Test error when running on non-ho-patch branch."""
        mock_repo, mock_hgit = mock_repo_on_invalid_branch

        with patch('half_orm_dev.cli.commands.apply_patch.Repo') as mock_repo_class:
            mock_repo_class.return_value = mock_repo

            # Invoke CLI
            result = cli_runner.invoke(apply_patch, [])

            # Should fail with error
            assert result.exit_code != 0
            assert 'ho-patch' in result.output.lower()
            assert 'feature/new-feature' in result.output

    def test_apply_patch_workflow_failure(self, cli_runner, mock_repo_on_patch_branch):
        """Test error handling when workflow fails."""
        mock_repo, mock_hgit, mock_patch_mgr = mock_repo_on_patch_branch

        # Mock workflow to raise error
        mock_patch_mgr.apply_patch_complete_workflow.side_effect = PatchManagerError(
            "Patch directory not found: Patches/456-user-auth/"
        )

        with patch('half_orm_dev.cli.commands.apply_patch.Repo') as mock_repo_class:
            mock_repo_class.return_value = mock_repo

            # Invoke CLI
            result = cli_runner.invoke(apply_patch, [])

            # Should fail with error
            assert result.exit_code != 0
            assert 'Patch directory not found' in result.output

    def test_apply_patch_database_restoration_failure(self, cli_runner, mock_repo_on_patch_branch):
        """Test error handling when database restoration fails."""
        mock_repo, mock_hgit, mock_patch_mgr = mock_repo_on_patch_branch

        # Mock workflow to raise database error
        mock_patch_mgr.apply_patch_complete_workflow.side_effect = PatchManagerError(
            "Database restoration failed: model/schema.sql not found"
        )

        with patch('half_orm_dev.cli.commands.apply_patch.Repo') as mock_repo_class:
            mock_repo_class.return_value = mock_repo

            # Invoke CLI
            result = cli_runner.invoke(apply_patch, [])

            # Should fail with error
            assert result.exit_code != 0
            assert 'Database restoration failed' in result.output or 'schema.sql' in result.output

    def test_apply_patch_unexpected_error(self, cli_runner, mock_repo_on_patch_branch):
        """Test error handling for unexpected exceptions."""
        mock_repo, mock_hgit, mock_patch_mgr = mock_repo_on_patch_branch

        # Mock workflow to raise unexpected error
        mock_patch_mgr.apply_patch_complete_workflow.side_effect = Exception(
            "Unexpected database error"
        )

        with patch('half_orm_dev.cli.commands.apply_patch.Repo') as mock_repo_class:
            mock_repo_class.return_value = mock_repo

            # Invoke CLI
            result = cli_runner.invoke(apply_patch, [])

            # Should fail with error
            assert result.exit_code != 0
            assert 'Unexpected' in result.output or 'error' in result.output.lower()

    def test_apply_patch_empty_patch(self, cli_runner, mock_repo_on_patch_branch):
        """Test successful run with empty patch (no files applied)."""
        mock_repo, mock_hgit, mock_patch_mgr = mock_repo_on_patch_branch

        # Mock workflow with empty patch
        mock_patch_mgr.apply_patch_complete_workflow.return_value = {
            'patch_id': '456-empty',
            'status': 'success',
            'applied_files': [],  # No files
            'generated_files': [],  # No generation needed
            'error': None
        }

        with patch('half_orm_dev.cli.commands.apply_patch.Repo') as mock_repo_class:
            mock_repo_class.return_value = mock_repo

            # Invoke CLI
            result = cli_runner.invoke(apply_patch, [])

            # Should succeed
            assert result.exit_code == 0

    def test_apply_patch_branch_name_extraction(self, cli_runner):
        """Test correct extraction of patch_id from various branch names."""
        test_cases = [
            ('ho-patch/456', '456'),
            ('ho-patch/456-user-auth', '456-user-auth'),
            ('ho-patch/999-complex-feature-name', '999-complex-feature-name'),
        ]

        for branch_name, expected_patch_id in test_cases:
            mock_repo = Mock()
            mock_hgit = Mock()
            mock_patch_mgr = Mock()

            mock_hgit.current_branch.return_value = branch_name
            mock_repo.hgit = mock_hgit
            mock_repo.patch_manager = mock_patch_mgr

            mock_patch_mgr.apply_patch_complete_workflow.return_value = {
                'patch_id': expected_patch_id,
                'status': 'success',
                'applied_files': [],
                'generated_files': [],
                'error': None
            }

            with patch('half_orm_dev.cli.commands.apply_patch.Repo') as mock_repo_class:
                mock_repo_class.return_value = mock_repo

                result = cli_runner.invoke(apply_patch, [])

                # Should succeed and call with correct patch_id
                assert result.exit_code == 0
                mock_patch_mgr.apply_patch_complete_workflow.assert_called_once_with(expected_patch_id)

    def test_apply_patch_output_format_structure(self, cli_runner, mock_repo_on_patch_branch):
        """Test that output follows expected structure."""
        mock_repo, mock_hgit, mock_patch_mgr = mock_repo_on_patch_branch

        with patch('half_orm_dev.cli.commands.apply_patch.Repo') as mock_repo_class:
            mock_repo_class.return_value = mock_repo

            result = cli_runner.invoke(apply_patch, [])

            assert result.exit_code == 0

            # Output should contain these sections (in some form)
            output_lower = result.output.lower()

            # Should mention branch and patch
            assert 'branch' in output_lower or 'patch' in output_lower

            # Should list files (if present)
            assert 'sql' in output_lower or 'file' in output_lower

            # Should mention next steps or success
            assert 'success' in output_lower or 'next' in output_lower or '✓' in result.output
