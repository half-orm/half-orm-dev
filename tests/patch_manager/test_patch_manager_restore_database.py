"""
Tests for PatchManager.restore_database_from_schema() method.

Focused on testing database restoration from model/schema.sql including:
- Successful restoration workflow
- Error handling for missing schema file
- PostgreSQL command failures (dropdb, createdb, psql)
- Model disconnection and reconnection
- Symlink vs regular file handling
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, call
import subprocess

from half_orm_dev.patch_manager import PatchManager, PatchManagerError


@pytest.fixture
def mock_restore_environment(patch_manager):
    """
    Setup mock environment for database restoration tests.

    Creates:
    - model/ directory with schema.sql file
    - Mock Model with disconnect() and ping() methods
    - Mock Database.execute_pg_command()

    Returns:
        Tuple of (patch_mgr, repo, schema_file, mock_model, mock_execute)
    """
    patch_mgr, repo, temp_dir, patches_dir = patch_manager

    # Create model/schema.sql file
    model_dir = Path(temp_dir) / "model"
    model_dir.mkdir()
    schema_file = model_dir / "schema.sql"
    schema_file.write_text("CREATE TABLE users (id SERIAL PRIMARY KEY);")

    # Mock Model methods
    mock_model = Mock()
    mock_model.disconnect = Mock()
    mock_model.ping = Mock()
    repo.model = mock_model

    # Mock Database.execute_pg_command
    mock_execute = Mock()
    repo.database.execute_pg_command = mock_execute

    return patch_mgr, repo, schema_file, mock_model, mock_execute


class TestRestoreDatabaseFromSchema:
    """Test database restoration from model/schema.sql."""

    def test_restore_database_success(self, mock_restore_environment):
        """Test successful database restoration workflow."""
        patch_mgr, repo, schema_file, mock_model, mock_execute = mock_restore_environment

        # Execute restoration
        patch_mgr.restore_database_from_schema()

        # Verify workflow steps
        # 1. Model disconnected
        mock_model.disconnect.assert_called_once()

        # 2. Database dropped
        mock_execute.assert_any_call('dropdb', 'test_database')

        # 3. Database created
        mock_execute.assert_any_call('createdb', 'test_database')

        # 4. Schema loaded via psql -f
        psql_call = call('psql', '-d', 'test_database', '-f', str(schema_file))
        assert psql_call in mock_execute.call_args_list

        # 5. Model reconnected
        mock_model.ping.assert_called_once()

        # 6. Verify call order
        assert mock_execute.call_count == 3  # dropdb, createdb, psql

    def test_restore_database_schema_file_missing(self, patch_manager):
        """Test restoration fails when model/schema.sql doesn't exist."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # model/ directory doesn't exist
        # No schema.sql file

        # Mock Model (shouldn't be called)
        mock_model = Mock()
        repo.model = mock_model

        # Should raise PatchManagerError
        with pytest.raises(PatchManagerError, match="Schema file not found"):
            patch_mgr.restore_database_from_schema()

        # Model should not be disconnected if file missing
        mock_model.disconnect.assert_not_called()

    def test_restore_database_model_dir_missing(self, patch_manager):
        """Test restoration fails when model/ directory doesn't exist."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # model/ directory doesn't exist at all

        # Mock Model
        mock_model = Mock()
        repo.model = mock_model

        # Should raise PatchManagerError
        with pytest.raises(PatchManagerError, match="Model.*not found|Schema file not found"):
            patch_mgr.restore_database_from_schema()

        # Model should not be disconnected
        mock_model.disconnect.assert_not_called()

    def test_restore_database_dropdb_fails(self, mock_restore_environment):
        """Test restoration fails when dropdb command fails."""
        patch_mgr, repo, schema_file, mock_model, mock_execute = mock_restore_environment

        # Mock execute_pg_command to fail on dropdb
        mock_execute.side_effect = [
            Exception("dropdb failed: database in use"),  # dropdb fails
        ]

        # Should raise PatchManagerError
        with pytest.raises(PatchManagerError, match="dropdb.*failed|Database restoration failed"):
            patch_mgr.restore_database_from_schema()

        # Model should have been disconnected before dropdb
        mock_model.disconnect.assert_called_once()

        # Ping should not be called (restoration failed)
        mock_model.ping.assert_not_called()

    def test_restore_database_createdb_fails(self, mock_restore_environment):
        """Test restoration fails when createdb command fails."""
        patch_mgr, repo, schema_file, mock_model, mock_execute = mock_restore_environment

        # Mock execute_pg_command: dropdb succeeds, createdb fails
        mock_execute.side_effect = [
            None,  # dropdb succeeds
            Exception("createdb failed: permission denied"),  # createdb fails
        ]

        # Should raise PatchManagerError
        with pytest.raises(PatchManagerError, match="createdb.*failed|Database restoration failed"):
            patch_mgr.restore_database_from_schema()

        # Model disconnected, dropdb called, but not createdb or psql
        mock_model.disconnect.assert_called_once()
        assert mock_execute.call_count == 2  # dropdb + createdb attempt

        # Ping not called
        mock_model.ping.assert_not_called()

    def test_restore_database_psql_fails(self, mock_restore_environment):
        """Test restoration fails when psql schema load fails."""
        patch_mgr, repo, schema_file, mock_model, mock_execute = mock_restore_environment

        # Mock execute_pg_command: dropdb and createdb succeed, psql fails
        mock_execute.side_effect = [
            None,  # dropdb succeeds
            None,  # createdb succeeds
            Exception("psql failed: syntax error"),  # psql fails
        ]

        # Should raise PatchManagerError
        with pytest.raises(PatchManagerError, match="psql.*failed|schema load.*failed|Database restoration failed"):
            patch_mgr.restore_database_from_schema()

        # All commands attempted
        assert mock_execute.call_count == 3

        # Ping not called (restoration failed)
        mock_model.ping.assert_not_called()

    def test_restore_database_with_symlink(self, patch_manager):
        """Test restoration works with schema.sql as symlink."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create model/ directory
        model_dir = Path(temp_dir) / "model"
        model_dir.mkdir()

        # Create versioned schema file
        versioned_schema = model_dir / "schema-1.2.3.sql"
        versioned_schema.write_text("CREATE TABLE users (id SERIAL PRIMARY KEY);")

        # Create symlink schema.sql -> schema-1.2.3.sql
        schema_symlink = model_dir / "schema.sql"
        schema_symlink.symlink_to("schema-1.2.3.sql")

        # Verify symlink created correctly
        assert schema_symlink.is_symlink()
        assert schema_symlink.exists()

        # Mock Model
        mock_model = Mock()
        mock_model.disconnect = Mock()
        mock_model.ping = Mock()
        repo.model = mock_model

        # Mock execute_pg_command
        mock_execute = Mock()
        repo.database.execute_pg_command = mock_execute

        # Execute restoration
        patch_mgr.restore_database_from_schema()

        # Should work with symlink (psql follows symlinks automatically)
        psql_call = call('psql', '-d', 'test_database', '-f', str(schema_symlink))
        assert psql_call in mock_execute.call_args_list

        # Workflow should complete successfully
        mock_model.disconnect.assert_called_once()
        mock_model.ping.assert_called_once()

    def test_restore_database_with_regular_file(self, patch_manager):
        """Test restoration works with schema.sql as regular file."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create model/schema.sql as regular file (no symlink)
        model_dir = Path(temp_dir) / "model"
        model_dir.mkdir()
        schema_file = model_dir / "schema.sql"
        schema_file.write_text("CREATE TABLE test (id SERIAL PRIMARY KEY);")

        # Verify it's a regular file, not a symlink
        assert not schema_file.is_symlink()
        assert schema_file.is_file()

        # Mock Model
        mock_model = Mock()
        mock_model.disconnect = Mock()
        mock_model.ping = Mock()
        repo.model = mock_model

        # Mock execute_pg_command
        mock_execute = Mock()
        repo.database.execute_pg_command = mock_execute

        # Execute restoration
        patch_mgr.restore_database_from_schema()

        # Should work with regular file
        psql_call = call('psql', '-d', 'test_database', '-f', str(schema_file))
        assert psql_call in mock_execute.call_args_list

        # Workflow should complete
        mock_model.disconnect.assert_called_once()
        mock_model.ping.assert_called_once()
