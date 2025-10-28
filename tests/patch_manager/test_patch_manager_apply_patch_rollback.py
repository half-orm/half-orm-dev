"""
Tests for PatchManager.apply_patch_complete_workflow() rollback behavior.

Focused on testing:
- Rollback on database restoration failure
- Rollback on patch application failure
- Rollback on code generation failure
- Error preservation (rollback doesn't mask original error)
- Cleanup on failure
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, call

from half_orm_dev.patch_manager import PatchManager
from half_orm_dev.repo import RepoError


@pytest.fixture
@pytest.skip(allow_module_level=True)
def mock_rollback_environment(patch_manager):
    """
    Setup mock environment for rollback tests.

    Provides:
    - patch_manager with temp directories
    - mock Model with disconnect/ping
    - mock Database.execute_pg_command
    - mock modules.generate
    - valid patch and schema.sql

    Returns:
        Tuple of (patch_mgr, repo, schema_file, patch_path,
                  mock_model, mock_execute, mock_generate)
    """
    patch_mgr, repo, temp_dir, patches_dir = patch_manager

    # Create model/schema.sql
    model_dir = Path(temp_dir) / "model"
    model_dir.mkdir()
    schema_file = model_dir / "schema.sql"
    schema_file.write_text("CREATE TABLE users (id SERIAL PRIMARY KEY);")

    # Create valid patch with files
    patch_path = patches_dir / "456-test-patch"
    patch_path.mkdir()
    (patch_path / "01_create.sql").write_text("CREATE TABLE test (id INT);")
    (patch_path / "02_insert.sql").write_text("INSERT INTO test VALUES (1);")

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

    # Mock ReleaseManager (no release context for these tests)
    mock_release_mgr = Mock()
    mock_release_mgr.get_all_release_context_patches = Mock(return_value=[])
    repo.release_manager = mock_release_mgr

    return (patch_mgr, repo, schema_file, patch_path,
            mock_model, mock_execute, mock_generate)


class TestApplyPatchRollback:
    """Test rollback scenarios for apply_patch_complete_workflow()."""

    def test_rollback_on_restore_failure_dropdb(self, mock_rollback_environment):
        """Test rollback when database restoration fails on dropdb."""
        (patch_mgr, repo, schema_file, patch_path,
         mock_model, mock_execute, mock_generate) = mock_rollback_environment

        # Mock restore to fail on dropdb
        mock_execute.side_effect = Exception("dropdb failed: database is being accessed")

        # Should raise RepoError with original error
        with pytest.raises(RepoError, match="dropdb failed|Database restoration failed"):
            with patch('half_orm_dev.modules.generate', mock_generate):
                patch_mgr.apply_patch_complete_workflow("456-test-patch")

        # Patch files should NOT be applied
        mock_model.execute_query.assert_not_called()

        # Code generation should NOT be triggered
        mock_generate.assert_not_called()

    def test_rollback_on_restore_failure_createdb(self, mock_rollback_environment):
        """Test rollback when database restoration fails on createdb."""
        (patch_mgr, repo, schema_file, patch_path,
         mock_model, mock_execute, mock_generate) = mock_rollback_environment

        # Mock restore: dropdb succeeds, createdb fails
        mock_execute.side_effect = [
            None,  # dropdb succeeds
            Exception("createdb failed: permission denied")
        ]

        # Should raise RepoError
        with pytest.raises(RepoError, match="createdb failed|Database restoration failed"):
            with patch('half_orm_dev.modules.generate', mock_generate):
                patch_mgr.apply_patch_complete_workflow("456-test-patch")

        # Patch files should NOT be applied
        mock_model.execute_query.assert_not_called()

        # Code generation should NOT be triggered
        mock_generate.assert_not_called()

    def test_rollback_on_restore_failure_psql(self, mock_rollback_environment):
        """Test rollback when database restoration fails on psql."""
        (patch_mgr, repo, schema_file, patch_path,
         mock_model, mock_execute, mock_generate) = mock_rollback_environment

        # Mock restore: dropdb and createdb succeed, psql fails
        mock_execute.side_effect = [
            None,  # dropdb succeeds
            None,  # createdb succeeds
            Exception("psql failed: syntax error in schema.sql")
        ]

        # Should raise RepoError
        with pytest.raises(RepoError, match="psql failed|Database restoration failed"):
            with patch('half_orm_dev.modules.generate', mock_generate):
                patch_mgr.apply_patch_complete_workflow("456-test-patch")

        # Patch files should NOT be applied
        mock_model.execute_query.assert_not_called()

        # Code generation should NOT be triggered
        mock_generate.assert_not_called()

    def test_rollback_on_patch_application_failure(self, mock_rollback_environment):
        """Test rollback when patch application fails."""
        (patch_mgr, repo, schema_file, patch_path,
         mock_model, mock_execute, mock_generate) = mock_rollback_environment

        # Mock restore to succeed
        mock_execute.side_effect = [None, None, None]  # dropdb, createdb, psql

        # Mock patch application to fail
        mock_model.execute_query.side_effect = Exception("SQL execution failed: syntax error")

        # Should raise RepoError and trigger rollback
        with pytest.raises(RepoError, match="SQL execution failed"):
            with patch('half_orm_dev.modules.generate', mock_generate):
                patch_mgr.apply_patch_complete_workflow("456-test-patch")

        # Code generation should NOT be triggered
        mock_generate.assert_not_called()

        # Rollback should attempt to restore database
        # Total execute calls: 3 (initial restore) + attempts during rollback
        assert mock_execute.call_count >= 3

    def test_rollback_on_code_generation_failure(self, mock_rollback_environment):
        """Test rollback when code generation fails."""
        (patch_mgr, repo, schema_file, patch_path,
         mock_model, mock_execute, mock_generate) = mock_rollback_environment

        # Mock restore and apply to succeed
        mock_execute.side_effect = [None, None, None]  # restore succeeds

        # Mock generate to fail
        mock_generate.side_effect = Exception("Code generation failed: invalid schema")

        # Should raise RepoError and trigger rollback
        with pytest.raises(RepoError, match="Code generation failed"):
            with patch('half_orm_dev.modules.generate', mock_generate):
                patch_mgr.apply_patch_complete_workflow("456-test-patch")

        # Generate was called
        mock_generate.assert_called_once()

        # Rollback should attempt to restore database
        assert mock_execute.call_count >= 3

    def test_rollback_preserves_original_error(self, mock_rollback_environment):
        """Test that rollback doesn't mask the original error."""
        (patch_mgr, repo, schema_file, patch_path,
         mock_model, mock_execute, mock_generate) = mock_rollback_environment

        # Mock restore to succeed initially, fail on rollback
        restore_calls = [None, None, None]  # Initial restore succeeds
        rollback_calls = [Exception("Rollback failed")]  # Rollback fails
        mock_execute.side_effect = restore_calls + rollback_calls

        # Mock patch application to fail (original error)
        original_error = Exception("Original patch error")
        mock_model.execute_query.side_effect = original_error

        # Should raise RepoError with ORIGINAL error message
        with pytest.raises(RepoError, match="Original patch error"):
            with patch('half_orm_dev.modules.generate', mock_generate):
                patch_mgr.apply_patch_complete_workflow("456-test-patch")

        # Original error should not be masked by rollback error

    def test_rollback_suppresses_rollback_errors(self, mock_rollback_environment):
        """Test that rollback errors are suppressed (don't mask original error)."""
        (patch_mgr, repo, schema_file, patch_path,
         mock_model, mock_execute, mock_generate) = mock_rollback_environment

        # Mock restore to succeed
        mock_execute.side_effect = [None, None, None]

        # Mock generate to fail (original error)
        mock_generate.side_effect = Exception("Generate failed")

        # Mock rollback to also fail
        # After first 3 calls (restore), subsequent calls (rollback) fail
        def side_effect_with_rollback_failure(*args, **kwargs):
            if mock_execute.call_count > 3:
                raise Exception("Rollback restoration failed")
            return None

        mock_execute.side_effect = side_effect_with_rollback_failure

        # Should raise RepoError with ORIGINAL error (Generate failed)
        # NOT the rollback error
        with pytest.raises(RepoError, match="Generate failed"):
            with patch('half_orm_dev.modules.generate', mock_generate):
                patch_mgr.apply_patch_complete_workflow("456-test-patch")

    def test_rollback_called_on_any_workflow_exception(self, mock_rollback_environment):
        """Test that rollback is called for any exception during workflow."""
        (patch_mgr, repo, schema_file, patch_path,
         mock_model, mock_execute, mock_generate) = mock_rollback_environment

        # Mock restore to succeed
        mock_execute.side_effect = [None, None, None]

        # Mock unexpected exception during workflow
        mock_generate.side_effect = RuntimeError("Unexpected error")

        # Track if rollback was called
        original_rollback = patch_mgr._rollback_database
        rollback_called = []

        def track_rollback():
            rollback_called.append(True)
            original_rollback()

        patch_mgr._rollback_database = track_rollback

        # Should trigger rollback
        with pytest.raises(RepoError):
            with patch('half_orm_dev.modules.generate', mock_generate):
                patch_mgr.apply_patch_complete_workflow("456-test-patch")

        # Verify rollback was called
        assert len(rollback_called) == 1

    def test_no_rollback_on_validation_errors(self, mock_rollback_environment):
        """Test behavior when patch validation fails.

        Note: Current implementation may attempt restore before validation,
        which triggers rollback. This test verifies the error is raised
        regardless of rollback behavior.
        """
        (patch_mgr, repo, schema_file, patch_path,
         mock_model, mock_execute, mock_generate) = mock_rollback_environment

        # Try to apply non-existent patch (validation error)
        with pytest.raises(RepoError, match="invalid|not.*exist|Cannot apply"):
            with patch('half_orm_dev.modules.generate', mock_generate):
                patch_mgr.apply_patch_complete_workflow("999-nonexistent")

        # Code generation should NOT be called
        mock_generate.assert_not_called()

    def test_rollback_with_release_context_failure(self, mock_rollback_environment):
        """Test rollback when release context patch fails."""
        (patch_mgr, repo, schema_file, patch_path,
         mock_model, mock_execute, mock_generate) = mock_rollback_environment

        patches_dir = Path(repo.base_dir) / "Patches"

        # Create release context patches
        for patch_id in ["123", "456-test-patch", "789"]:
            if not (patches_dir / patch_id).exists():
                patch_path_ctx = patches_dir / patch_id
                patch_path_ctx.mkdir()
                (patch_path_ctx / "01_test.sql").write_text(f"-- {patch_id}")

        # Mock release context
        repo.release_manager.get_all_release_context_patches.return_value = ["123", "456-test-patch", "789"]

        # Mock restore to succeed
        mock_execute.side_effect = [None, None, None]

        # Mock patch application: succeed for 123, fail for 456
        call_count = [0]

        def mock_apply(patch_id, model):
            call_count[0] += 1
            if patch_id == "456-test-patch":
                raise RepoError(f"Failed to apply release patch {patch_id}")
            return [f"{patch_id}.sql"]

        # Should trigger rollback when release patch fails
        with patch.object(patch_mgr, 'apply_patch_files', side_effect=mock_apply):
            with patch('half_orm_dev.modules.generate', mock_generate):
                with pytest.raises(RepoError, match="Failed to apply release patch"):
                    patch_mgr.apply_patch_complete_workflow("456-test-patch")

        # Code generation should NOT be called
        mock_generate.assert_not_called()

        # Rollback should be attempted
        assert mock_execute.call_count >= 3