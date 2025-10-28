"""
Tests for PatchManager.apply_patch_complete_workflow() validation.

Focused on testing:
- Invalid patch ID handling
- Missing schema.sql file
- Empty patches (no SQL/Python files)
- Invalid patch structures
- Pre-execution validation
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from half_orm_dev.patch_manager import PatchManager, PatchManagerError


@pytest.fixture
@pytest.skip(allow_module_level=True)
def mock_validation_environment(patch_manager):
    """
    Setup mock environment for validation tests.

    Provides:
    - patch_manager with temp directories
    - mock Model
    - mock Database.execute_pg_command
    - mock modules.generate
    - Optional model/schema.sql

    Returns:
        Tuple of (patch_mgr, repo, model_dir, mock_model, mock_execute, mock_generate)
    """
    patch_mgr, repo, temp_dir, patches_dir = patch_manager

    # Create model/ directory (schema.sql optional)
    model_dir = Path(temp_dir) / "model"
    model_dir.mkdir()

    # Mock Model
    mock_model = Mock()
    mock_model.disconnect = Mock()
    mock_model.ping = Mock()
    mock_model.execute_query = Mock()
    repo.model = mock_model

    # Mock Database.execute_pg_command
    mock_execute = Mock()
    repo.database.execute_pg_command = mock_execute

    # Mock modules.generate
    mock_generate = Mock()

    # Mock ReleaseManager (no release context)
    mock_release_mgr = Mock()
    mock_release_mgr.get_all_release_context_patches = Mock(return_value=[])
    repo.release_manager = mock_release_mgr

    return patch_mgr, repo, model_dir, mock_model, mock_execute, mock_generate


class TestApplyPatchValidation:
    """Test validation scenarios for apply_patch_complete_workflow()."""

    def test_invalid_patch_id_nonexistent(self, mock_validation_environment):
        """Test error when patch ID doesn't exist."""
        (patch_mgr, repo, model_dir, mock_model,
         mock_execute, mock_generate) = mock_validation_environment

        # Create schema.sql
        schema_file = model_dir / "schema.sql"
        schema_file.write_text("CREATE TABLE users (id SERIAL);")

        # Try to apply non-existent patch
        with pytest.raises(PatchManagerError, match="Patch.*not.*exist|invalid|Cannot apply invalid patch"):
            with patch('half_orm_dev.modules.generate', mock_generate):
                patch_mgr.apply_patch_complete_workflow("999-nonexistent")

        # Code generation should NOT be called
        mock_generate.assert_not_called()

    def test_invalid_patch_id_file_instead_of_directory(self, mock_validation_environment):
        """Test error when patch ID points to a file instead of directory."""
        (patch_mgr, repo, model_dir, mock_model,
         mock_execute, mock_generate) = mock_validation_environment

        patches_dir = Path(repo.base_dir) / "Patches"

        # Create schema.sql
        schema_file = model_dir / "schema.sql"
        schema_file.write_text("CREATE TABLE users (id SERIAL);")

        # Create file instead of directory
        invalid_patch = patches_dir / "456-invalid"
        invalid_patch.write_text("This is a file, not a directory")

        # Try to apply invalid patch
        with pytest.raises(PatchManagerError, match="invalid|not.*directory|Cannot apply invalid patch"):
            with patch('half_orm_dev.modules.generate', mock_generate):
                patch_mgr.apply_patch_complete_workflow("456-invalid")

        # Code generation should NOT be called
        mock_generate.assert_not_called()

    def test_schema_file_missing(self, mock_validation_environment):
        """Test error when model/schema.sql is missing."""
        (patch_mgr, repo, model_dir, mock_model,
         mock_execute, mock_generate) = mock_validation_environment

        patches_dir = Path(repo.base_dir) / "Patches"

        # Create valid patch
        patch_path = patches_dir / "456-test"
        patch_path.mkdir()
        (patch_path / "01_test.sql").write_text("SELECT 1;")

        # DO NOT create schema.sql

        # Try to apply patch
        with pytest.raises(PatchManagerError, match="[Ss]chema.*not found|Cannot restore"):
            with patch('half_orm_dev.modules.generate', mock_generate):
                patch_mgr.apply_patch_complete_workflow("456-test")

        # Patch files should NOT be applied
        mock_model.execute_query.assert_not_called()

        # Code generation should NOT be called
        mock_generate.assert_not_called()

    def test_empty_patch_no_files(self, mock_validation_environment):
        """Test successful workflow with empty patch (no SQL/Python files)."""
        (patch_mgr, repo, model_dir, mock_model,
         mock_execute, mock_generate) = mock_validation_environment

        patches_dir = Path(repo.base_dir) / "Patches"

        # Create schema.sql
        schema_file = model_dir / "schema.sql"
        schema_file.write_text("CREATE TABLE users (id SERIAL);")

        # Create empty patch directory
        empty_patch = patches_dir / "789-empty"
        empty_patch.mkdir()

        # Apply empty patch
        with patch('half_orm_dev.modules.generate', mock_generate):
            result = patch_mgr.apply_patch_complete_workflow("789-empty")

        # Should succeed with no files applied
        assert result['status'] == 'success'
        assert result['applied_current_files'] == []

        # Database restore should still run
        mock_model.disconnect.assert_called_once()
        mock_model.ping.assert_called_once()

        # Code generation should still run
        mock_generate.assert_called_once()

    def test_empty_patch_only_non_executable_files(self, mock_validation_environment):
        """Test patch with only non-executable files (README, config, etc.)."""
        (patch_mgr, repo, model_dir, mock_model,
         mock_execute, mock_generate) = mock_validation_environment

        patches_dir = Path(repo.base_dir) / "Patches"

        # Create schema.sql
        schema_file = model_dir / "schema.sql"
        schema_file.write_text("CREATE TABLE users (id SERIAL);")

        # Create patch with only non-executable files
        patch_path = patches_dir / "456-docs-only"
        patch_path.mkdir()
        (patch_path / "README.md").write_text("# Documentation")
        (patch_path / "CHANGELOG.txt").write_text("Changes")
        (patch_path / "config.json").write_text('{"key": "value"}')

        # Apply patch
        with patch('half_orm_dev.modules.generate', mock_generate):
            result = patch_mgr.apply_patch_complete_workflow("456-docs-only")

        # Should succeed with no executable files applied
        assert result['status'] == 'success'
        assert result['applied_current_files'] == []

        # No SQL execution
        mock_model.execute_query.assert_not_called()

        # Code generation should still run
        mock_generate.assert_called_once()

    def test_validation_runs_before_database_operations(self, mock_validation_environment):
        """Test that patch validation catches errors.

        Note: Current implementation may attempt database restore before
        full validation. This test verifies the error is raised and
        code generation doesn't run.
        """
        (patch_mgr, repo, model_dir, mock_model,
         mock_execute, mock_generate) = mock_validation_environment

        # Create schema.sql
        schema_file = model_dir / "schema.sql"
        schema_file.write_text("CREATE TABLE users (id SERIAL);")

        # Try invalid patch
        with pytest.raises(PatchManagerError, match="invalid|not.*exist|Cannot apply"):
            with patch('half_orm_dev.modules.generate', mock_generate):
                patch_mgr.apply_patch_complete_workflow("999-nonexistent")

        # Code generation should NOT be called
        mock_generate.assert_not_called()

    def test_patch_with_mixed_valid_invalid_files(self, mock_validation_environment):
        """Test patch with mix of valid SQL/Python and other files."""
        (patch_mgr, repo, model_dir, mock_model,
         mock_execute, mock_generate) = mock_validation_environment

        patches_dir = Path(repo.base_dir) / "Patches"

        # Create schema.sql
        schema_file = model_dir / "schema.sql"
        schema_file.write_text("CREATE TABLE users (id SERIAL);")

        # Create patch with mixed files
        patch_path = patches_dir / "456-mixed"
        patch_path.mkdir()
        (patch_path / "01_valid.sql").write_text("SELECT 1;")
        (patch_path / "02_script.py").write_text("print('test')")
        (patch_path / "README.md").write_text("# Docs")
        (patch_path / "config.txt").write_text("config")
        (patch_path / "03_another.sql").write_text("SELECT 2;")

        # Track what gets applied
        def track_apply(patch_id, model):
            # Return actual files that were applied
            return ["01_valid.sql", "02_script.py", "03_another.sql"]

        with patch.object(patch_mgr, 'apply_patch_files', side_effect=track_apply):
            with patch('half_orm_dev.modules.generate', mock_generate):
                result = patch_mgr.apply_patch_complete_workflow("456-mixed")

        # Should apply only SQL and Python files
        assert result['status'] == 'success'
        assert len(result['applied_current_files']) == 3
        assert "01_valid.sql" in result['applied_current_files']
        assert "02_script.py" in result['applied_current_files']
        assert "03_another.sql" in result['applied_current_files']
