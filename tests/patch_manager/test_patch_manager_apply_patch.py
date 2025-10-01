"""
Tests for PatchManager.apply_patch_complete_workflow() method.

Focused on testing complete workflow orchestration including:
- Database restoration
- Patch file application
- Code generation via modules.generate()
- Rollback on failure
- Return structure validation
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, call

from half_orm_dev.patch_manager import PatchManager, PatchManagerError


@pytest.fixture
def mock_workflow_environment(patch_manager):
    """
    Setup complete mock environment for workflow tests.
    
    Provides:
    - patch_manager with temp directories
    - mock Model with disconnect/ping
    - mock Database.execute_pg_command
    - mock modules.generate
    - valid patch directory with files
    
    Returns:
        Tuple of (patch_mgr, repo, schema_file, mock_model, mock_execute, mock_generate)
    """
    patch_mgr, repo, temp_dir, patches_dir = patch_manager
    
    # Create model/schema.sql
    model_dir = Path(temp_dir) / "model"
    model_dir.mkdir()
    schema_file = model_dir / "schema.sql"
    schema_file.write_text("CREATE TABLE users (id SERIAL PRIMARY KEY);")
    
    # Create valid patch with files
    patch_path = patches_dir / "456-user-auth"
    patch_path.mkdir()
    (patch_path / "01_create_users.sql").write_text("CREATE TABLE users (id INT);")
    (patch_path / "02_add_indexes.sql").write_text("CREATE INDEX idx_users ON users(id);")
    
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
    
    return patch_mgr, repo, schema_file, mock_model, mock_execute, mock_generate


class TestApplyPatchCompleteWorkflow:
    """Test complete workflow orchestration."""

    def test_workflow_success_complete(self, mock_workflow_environment):
        """Test successful complete workflow execution."""
        patch_mgr, repo, schema_file, mock_model, mock_execute, mock_generate = mock_workflow_environment
        
        # Execute complete workflow
        with patch('half_orm_dev.modules.generate', mock_generate):
            result = patch_mgr.apply_patch_complete_workflow("456-user-auth")
        
        # Verify all steps executed in order
        # 1. Database restoration
        mock_model.disconnect.assert_called_once()
        assert mock_execute.call_count == 3  # dropdb, createdb, psql
        mock_model.ping.assert_called_once()
        
        # 2. Patch application
        assert mock_model.execute_query.call_count == 2  # 2 SQL files
        
        # 3. Code generation
        mock_generate.assert_called_once_with(repo)
        
        # Verify return structure
        assert result['status'] == 'success'
        assert result['patch_id'] == '456-user-auth'
        assert len(result['applied_files']) == 2
        assert '01_create_users.sql' in result['applied_files']
        assert '02_add_indexes.sql' in result['applied_files']
        assert 'generated_files' in result
        assert result['error'] is None

    def test_workflow_rollback_on_restore_failure(self, mock_workflow_environment):
        """Test rollback when database restoration fails."""
        patch_mgr, repo, schema_file, mock_model, mock_execute, mock_generate = mock_workflow_environment
        
        # Mock restore to fail on dropdb
        mock_execute.side_effect = Exception("dropdb failed")
        
        # Should raise PatchManagerError
        with pytest.raises(PatchManagerError, match="dropdb failed|Database restoration failed"):
            with patch('half_orm_dev.modules.generate', mock_generate):
                patch_mgr.apply_patch_complete_workflow("456-user-auth")
        
        # Patch files should not be applied
        mock_model.execute_query.assert_not_called()
        
        # Code generation should not be triggered
        mock_generate.assert_not_called()

    def test_workflow_rollback_on_apply_failure(self, mock_workflow_environment):
        """Test rollback when patch application fails."""
        patch_mgr, repo, schema_file, mock_model, mock_execute, mock_generate = mock_workflow_environment
        
        # Mock restore to succeed, but apply to fail
        mock_execute.side_effect = [None, None, None]  # restore steps succeed
        mock_model.execute_query.side_effect = Exception("SQL execution failed")
        
        # Should raise PatchManagerError and trigger rollback
        with pytest.raises(PatchManagerError, match="SQL execution failed"):
            with patch('half_orm_dev.modules.generate', mock_generate):
                patch_mgr.apply_patch_complete_workflow("456-user-auth")
        
        # Code generation should not be triggered
        mock_generate.assert_not_called()
        
        # Rollback: restore should be called again
        # Total calls: 3 (initial restore) + 3 (rollback restore) = 6
        # But we need to verify rollback happened
        # This will be implementation-specific

    def test_workflow_rollback_on_generate_failure(self, mock_workflow_environment):
        """Test rollback when code generation fails."""
        patch_mgr, repo, schema_file, mock_model, mock_execute, mock_generate = mock_workflow_environment
        
        # Mock restore and apply to succeed, but generate to fail
        mock_execute.side_effect = [None, None, None]  # restore succeeds
        mock_generate.side_effect = Exception("Code generation failed")
        
        # Should raise PatchManagerError and trigger rollback
        with pytest.raises(PatchManagerError, match="Code generation failed"):
            with patch('half_orm_dev.modules.generate', mock_generate):
                patch_mgr.apply_patch_complete_workflow("456-user-auth")
        
        # Generate was called
        mock_generate.assert_called_once()
        
        # Rollback should restore database
        # Will verify in implementation

    def test_workflow_return_structure(self, mock_workflow_environment):
        """Test workflow return dictionary structure."""
        patch_mgr, repo, schema_file, mock_model, mock_execute, mock_generate = mock_workflow_environment
        
        # Execute workflow
        with patch('half_orm_dev.modules.generate', mock_generate):
            result = patch_mgr.apply_patch_complete_workflow("456-user-auth")
        
        # Verify all required keys present
        required_keys = {'patch_id', 'applied_files', 'generated_files', 'status', 'error'}
        assert set(result.keys()) == required_keys
        
        # Verify types
        assert isinstance(result['patch_id'], str)
        assert isinstance(result['applied_files'], list)
        assert isinstance(result['generated_files'], list)
        assert isinstance(result['status'], str)
        assert result['error'] is None or isinstance(result['error'], str)
        
        # Verify values
        assert result['status'] in ['success', 'failed']

    def test_workflow_invalid_patch_id(self, mock_workflow_environment):
        """Test workflow with invalid patch ID."""
        patch_mgr, repo, schema_file, mock_model, mock_execute, mock_generate = mock_workflow_environment
        
        # Should raise PatchManagerError before code generation
        with pytest.raises(PatchManagerError, match="Patch.*not.*exist|invalid|Cannot apply invalid patch"):
            with patch('half_orm_dev.modules.generate', mock_generate):
                patch_mgr.apply_patch_complete_workflow("999-nonexistent")
        
        # Code generation should not be called
        mock_generate.assert_not_called()
        
        # Note: disconnect/execute may be called during restore, then rollback
        # The important check is that generate is not called

    def test_workflow_schema_file_missing(self, mock_workflow_environment):
        """Test workflow when model/schema.sql is missing."""
        patch_mgr, repo, schema_file, mock_model, mock_execute, mock_generate = mock_workflow_environment
        
        # Remove schema file
        schema_file.unlink()
        
        # Should raise PatchManagerError with appropriate message
        with pytest.raises(PatchManagerError, match="[Ss]chema.*not found|Cannot restore"):
            with patch('half_orm_dev.modules.generate', mock_generate):
                patch_mgr.apply_patch_complete_workflow("456-user-auth")
        
        # No patch application or generation
        mock_model.execute_query.assert_not_called()
        mock_generate.assert_not_called()

    def test_workflow_empty_patch(self, mock_workflow_environment):
        """Test workflow with patch containing no SQL/Python files."""
        patch_mgr, repo, schema_file, mock_model, mock_execute, mock_generate = mock_workflow_environment
        
        # Create empty patch
        empty_patch = Path(repo.base_dir) / "Patches" / "789-empty"
        empty_patch.mkdir()
        
        # Execute workflow
        with patch('half_orm_dev.modules.generate', mock_generate):
            result = patch_mgr.apply_patch_complete_workflow("789-empty")
        
        # Should succeed but with no files applied
        assert result['status'] == 'success'
        assert result['applied_files'] == []
        
        # Database restore and generate should still run
        mock_model.disconnect.assert_called_once()
        mock_model.ping.assert_called_once()
        mock_generate.assert_called_once()

    def test_workflow_execution_order(self, mock_workflow_environment):
        """Test that workflow steps execute in correct order."""
        patch_mgr, repo, schema_file, mock_model, mock_execute, mock_generate = mock_workflow_environment
        
        # Track call order
        call_order = []
        
        # Use side_effect that accepts any arguments including kwargs
        def track_disconnect():
            call_order.append('disconnect')
        
        def track_execute(*args, **kwargs):
            if len(args) > 0:
                call_order.append(f'execute_{args[0]}')
        
        def track_ping():
            call_order.append('ping')
        
        def track_apply_sql(*args, **kwargs):
            call_order.append('apply_sql')
        
        def track_generate(repo):
            call_order.append('generate')
        
        mock_model.disconnect.side_effect = track_disconnect
        mock_execute.side_effect = track_execute
        mock_model.ping.side_effect = track_ping
        mock_model.execute_query.side_effect = track_apply_sql
        mock_generate.side_effect = track_generate
        
        # Execute workflow
        with patch('half_orm_dev.modules.generate', mock_generate):
            patch_mgr.apply_patch_complete_workflow("456-user-auth")
        
        # Verify order: restore → apply → generate
        assert call_order[0] == 'disconnect'
        assert 'execute_dropdb' in call_order
        assert 'execute_createdb' in call_order
        assert 'execute_psql' in call_order
        assert 'ping' in call_order
        assert 'apply_sql' in call_order
        assert call_order[-1] == 'generate'