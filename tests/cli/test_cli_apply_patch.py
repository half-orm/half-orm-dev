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

# from half_orm_dev.cli.commands.apply_patch import apply_patch
from half_orm_dev.patch_manager import PatchManagerError

@pytest.skip(allow_module_level=True)
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

        Returns a context manager that patches Repo correctly.
        """
        from contextlib import contextmanager

        @contextmanager
        def _patch():
            mock_hgit = Mock()
            mock_patch_mgr = Mock()
            mock_repo_instance = Mock()

            # Mock branch detection
            mock_hgit.current_branch.return_value = 'ho-patch/456-user-auth'
            mock_repo_instance.hgit = mock_hgit

            # Mock successful workflow
            mock_patch_mgr.apply_patch_complete_workflow.return_value = {
                'patch_id': '456-user-auth',
                'status': 'success',
                'applied_current_files': ['01_create_users.sql', '02_add_indexes.sql'],
                'generated_files': [
                    'mydb/mydb/public/user.py',
                    'mydb/mydb/public/user_session.py',
                    'tests/mydb/public/test_user.py'
                ],
                'error': None
            }
            mock_repo_instance.patch_manager = mock_patch_mgr

            with patch('half_orm_dev.cli.commands.apply_patch.Repo') as mock_repo_class:
                mock_repo_class.return_value = mock_repo_instance
                yield mock_repo_instance, mock_hgit, mock_patch_mgr

        return _patch

    @pytest.fixture
    def mock_repo_on_prod_branch(self):
        """Mock Repo environment on ho-prod branch."""
        from contextlib import contextmanager

        @contextmanager
        def _patch():
            mock_hgit = Mock()
            mock_repo_instance = Mock()

            # Mock branch detection - on ho-prod
            mock_hgit.current_branch.return_value = 'ho-prod'
            mock_repo_instance.hgit = mock_hgit

            with patch('half_orm_dev.cli.commands.apply_patch.Repo') as mock_repo_class:
                mock_repo_class.return_value = mock_repo_instance
                yield mock_repo_instance, mock_hgit

        return _patch

    @pytest.fixture
    def mock_repo_on_invalid_branch(self):
        """Mock Repo environment on non-ho-patch branch."""
        from contextlib import contextmanager

        @contextmanager
        def _patch():
            mock_hgit = Mock()
            mock_repo_instance = Mock()

            # Mock branch detection - on feature branch
            mock_hgit.current_branch.return_value = 'feature/new-feature'
            mock_repo_instance.hgit = mock_hgit

            with patch('half_orm_dev.cli.commands.apply_patch.Repo') as mock_repo_class:
                mock_repo_class.return_value = mock_repo_instance
                yield mock_repo_instance, mock_hgit

        return _patch

    def test_apply_patch_success(self, cli_runner, mock_repo_on_patch_branch):
        """Test successful patch application with formatted output."""
        with mock_repo_on_patch_branch() as (mock_repo, mock_hgit, mock_patch_mgr):
            result = cli_runner.invoke(apply_patch, [])

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
        with mock_repo_on_prod_branch() as (mock_repo, mock_hgit):
            result = cli_runner.invoke(apply_patch, [])

            assert result.exit_code != 0
            assert 'ho-patch' in result.output.lower()
            assert 'ho-prod' in result.output

    def test_apply_patch_on_invalid_branch(self, cli_runner, mock_repo_on_invalid_branch):
        """Test error when running on non-ho-patch branch."""
        with mock_repo_on_invalid_branch() as (mock_repo, mock_hgit):
            result = cli_runner.invoke(apply_patch, [])

            assert result.exit_code != 0
            assert 'ho-patch' in result.output.lower()
            assert 'feature/new-feature' in result.output

    def test_apply_patch_workflow_failure(self, cli_runner, mock_repo_on_patch_branch):
        """Test error handling when workflow fails."""
        with mock_repo_on_patch_branch() as (mock_repo, mock_hgit, mock_patch_mgr):
            # Mock workflow to raise error
            mock_patch_mgr.apply_patch_complete_workflow.side_effect = PatchManagerError(
                "Patch directory not found: Patches/456-user-auth/"
            )

            result = cli_runner.invoke(apply_patch, [])

            assert result.exit_code != 0
            assert 'Patch directory not found' in result.output

    def test_apply_patch_database_restoration_failure(self, cli_runner, mock_repo_on_patch_branch):
        """Test error handling when database restoration fails."""
        with mock_repo_on_patch_branch() as (mock_repo, mock_hgit, mock_patch_mgr):
            # Mock workflow to raise database error
            mock_patch_mgr.apply_patch_complete_workflow.side_effect = PatchManagerError(
                "Database restoration failed: model/schema.sql not found"
            )

            result = cli_runner.invoke(apply_patch, [])

            assert result.exit_code != 0
            assert 'Database restoration failed' in result.output or 'schema.sql' in result.output

    def test_apply_patch_empty_patch(self, cli_runner, mock_repo_on_patch_branch):
        """Test successful run with empty patch (no files applied)."""
        with mock_repo_on_patch_branch() as (mock_repo, mock_hgit, mock_patch_mgr):
            # Mock workflow with empty patch
            mock_patch_mgr.apply_patch_complete_workflow.return_value = {
                'patch_id': '456-empty',
                'status': 'success',
                'applied_files': [],  # No files
                'generated_files': [],  # No generation needed
                'error': None
            }

            result = cli_runner.invoke(apply_patch, [])

            assert result.exit_code == 0

    def test_apply_patch_branch_name_extraction(self, cli_runner):
        """Test correct extraction of patch_id from various branch names."""
        from contextlib import contextmanager

        test_cases = [
            ('ho-patch/456', '456'),
            ('ho-patch/456-user-auth', '456-user-auth'),
            ('ho-patch/999-complex-feature-name', '999-complex-feature-name'),
        ]

        for branch_name, expected_patch_id in test_cases:
            @contextmanager
            def create_mock():
                mock_hgit = Mock()
                mock_patch_mgr = Mock()
                mock_repo_instance = Mock()

                mock_hgit.current_branch.return_value = branch_name
                mock_repo_instance.hgit = mock_hgit
                mock_repo_instance.patch_manager = mock_patch_mgr

                mock_patch_mgr.apply_patch_complete_workflow.return_value = {
                    'patch_id': expected_patch_id,
                    'status': 'success',
                    'applied_files': [],
                    'generated_files': [],
                    'error': None
                }

                with patch('half_orm_dev.cli.commands.apply_patch.Repo') as mock_repo_class:
                    mock_repo_class.return_value = mock_repo_instance
                    yield mock_patch_mgr

            with create_mock() as mock_patch_mgr:
                result = cli_runner.invoke(apply_patch, [])

                # Should succeed and call with correct patch_id
                assert result.exit_code == 0
                mock_patch_mgr.apply_patch_complete_workflow.assert_called_once_with(expected_patch_id)

    def test_apply_patch_output_format_structure(self, cli_runner, mock_repo_on_patch_branch):
        """Test that output follows expected structure."""
        with mock_repo_on_patch_branch() as (mock_repo, mock_hgit, mock_patch_mgr):
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
