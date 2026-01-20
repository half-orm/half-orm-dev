"""
Tests for Repo.restore_database_from_schema() method.

Focused on testing database restoration from model/schema.sql including:
- Successful restoration workflow
- Error handling for missing schema file
- PostgreSQL command failures (schema drop, psql)
- Model metadata cache reload
- Symlink vs regular file handling
- Loading data files (model/data-*.sql)
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, call
import subprocess

from half_orm_dev.patch_manager import PatchManager
from half_orm_dev.repo import Repo, RepoError


@pytest.fixture
def mock_restore_environment(patch_manager):
    """
    Setup mock environment for database restoration tests.

    Creates:
    - model/ directory with schema.sql file
    - Mock Model with desc(), execute_query(), and reconnect() methods
    - Mock Database.execute_pg_command()

    Returns:
        Tuple of (patch_mgr, repo, schema_file, mock_model, mock_execute)
    """
    patch_mgr, repo, temp_dir, patches_dir = patch_manager

    # Create model/schema.sql file
    model_dir = Path(temp_dir) / ".hop" / "model"
    model_dir.mkdir(parents=True)
    schema_file = model_dir / "schema.sql"
    schema_file.write_text("CREATE TABLE users (id SERIAL PRIMARY KEY);")
    repo.model_dir = str(model_dir)

    # Mock Model methods
    mock_model = Mock()
    # Mock desc() for _reset_database_schemas
    mock_model.desc = Mock(return_value=[
        ('r', ('test_database', 'public', 'users'), [])
    ])
    # Mock execute_query() for DROP SCHEMA
    mock_model.execute_query = Mock()
    # Mock reconnect(reload=True) instead of ping()
    mock_model.reconnect = Mock()
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

        # Patch _reset_database_schemas to track calls
        with patch.object(repo, '_reset_database_schemas') as mock_reset:
            # Execute restoration
            repo.restore_database_from_schema()

            # Verify workflow steps
            # 1. _reset_database_schemas called
            mock_reset.assert_called_once()

            # 2. Schema loaded via psql -f
            psql_call = call('psql', '-d', 'test_database', '-f', str(schema_file))
            assert psql_call in mock_execute.call_args_list

            # 3. Model metadata cache reloaded
            mock_model.reconnect.assert_called_once_with(reload=True)

            # 4. Verify psql was called (at least once for schema.sql, maybe twice with metadata)
            assert mock_execute.call_count >= 1

    def test_restore_database_schema_file_missing(self, patch_manager):
        """Test restoration fails when model/schema.sql doesn't exist."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # DEBUG: Afficher les chemins
        print(f"\nDEBUG temp_dir: {temp_dir}")
        print(f"DEBUG repo.base_dir: {repo.base_dir}")
        print(f"DEBUG model exists: {(Path(temp_dir) / 'model').exists()}")

        schema_path = Path(temp_dir) / "model" / "schema.sql"
        print(f"DEBUG schema_path: {schema_path}")
        print(f"DEBUG schema exists: {schema_path.exists()}")

        # model/ directory doesn't exist
        # No schema.sql file

        # Mock Model (shouldn't be called)
        mock_model = Mock()
        repo.model = mock_model
        repo.model_dir = str(Path(temp_dir) / ".hop" / "model")

        # Should raise RepoError
        with pytest.raises(RepoError, match="Schema file not found"):
            repo.restore_database_from_schema()

    def test_restore_database_model_dir_missing(self, patch_manager):
        """Test restoration fails when model/ directory doesn't exist."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # model/ directory doesn't exist at all

        # Mock Model
        mock_model = Mock()
        repo.model = mock_model
        repo.model_dir = str(Path(temp_dir) / ".hop" / "model")

        # Should raise RepoError
        with pytest.raises(RepoError, match="Model.*not found|Schema file not found"):
            repo.restore_database_from_schema()

    def test_restore_database_dropdb_fails(self, mock_restore_environment):
        """Test restoration fails when schema drop fails."""
        patch_mgr, repo, schema_file, mock_model, mock_execute = mock_restore_environment

        # Mock _reset_database_schemas to fail
        with patch.object(repo, '_reset_database_schemas', side_effect=RepoError("Failed to reset database schemas: DROP SCHEMA failed")):
            # Should raise RepoError
            with pytest.raises(RepoError, match="schema.*failed|Database restoration failed"):
                repo.restore_database_from_schema()

            # reconnect should not be called (restoration failed)
            mock_model.reconnect.assert_not_called()

    def test_restore_database_createdb_fails(self, mock_restore_environment):
        """Test restoration fails when schema load (psql) fails."""
        patch_mgr, repo, schema_file, mock_model, mock_execute = mock_restore_environment

        # Mock execute_pg_command: schema drop succeeds, psql fails
        mock_execute.side_effect = Exception("psql failed: syntax error in schema.sql")

        # Should raise RepoError
        with pytest.raises(RepoError, match="schema load.*failed|Failed to load schema|Database restoration failed"):
            repo.restore_database_from_schema()

        # execute_pg_command should have been called (psql attempt)
        assert mock_execute.called

        # reconnect not called (restoration failed)
        mock_model.reconnect.assert_not_called()

    def test_restore_database_psql_fails(self, mock_restore_environment):
        """Test restoration fails when psql schema load fails."""
        patch_mgr, repo, schema_file, mock_model, mock_execute = mock_restore_environment

        # Mock execute_pg_command: schema drop succeeds, psql fails
        mock_execute.side_effect = Exception("psql failed: syntax error")

        # Should raise RepoError
        with pytest.raises(RepoError, match="psql.*failed|schema load.*failed|Failed to load schema|Database restoration failed"):
            repo.restore_database_from_schema()

        # execute_pg_command should have been called
        assert mock_execute.called

        # reconnect not called (restoration failed)
        mock_model.reconnect.assert_not_called()

    def test_restore_database_with_symlink(self, patch_manager):
        """Test restoration works with schema.sql as symlink."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create model/ directory
        model_dir = Path(temp_dir) / ".hop" / "model"
        model_dir.mkdir(parents=True)

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
        # Mock desc() for _reset_database_schemas
        mock_model.desc = Mock(return_value=[
            ('r', ('test_database', 'public', 'users'), [])
        ])
        # Mock execute_query() for DROP SCHEMA
        mock_model.execute_query = Mock()
        # Mock reconnect(reload=True)
        mock_model.reconnect = Mock()
        repo.model = mock_model
        repo.model_dir = str(model_dir)

        # Mock execute_pg_command
        mock_execute = Mock()
        repo.database.execute_pg_command = mock_execute

        # Execute restoration
        repo.restore_database_from_schema()

        # Should work with symlink (psql follows symlinks automatically)
        psql_call = call('psql', '-d', 'test_database', '-f', str(schema_symlink))
        assert psql_call in mock_execute.call_args_list

        # Workflow should complete successfully
        mock_model.reconnect.assert_called_once_with(reload=True)

    def test_restore_database_with_regular_file(self, patch_manager):
        """Test restoration works with schema.sql as regular file."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create model/schema.sql as regular file (no symlink)
        model_dir = Path(temp_dir) / ".hop" / "model"
        model_dir.mkdir(parents=True)
        schema_file = model_dir / "schema.sql"
        schema_file.write_text("CREATE TABLE test (id SERIAL PRIMARY KEY);")

        # Verify it's a regular file, not a symlink
        assert not schema_file.is_symlink()
        assert schema_file.is_file()

        # Mock Model
        mock_model = Mock()
        # Mock desc() for _reset_database_schemas
        mock_model.desc = Mock(return_value=[
            ('r', ('test_database', 'public', 'test'), [])
        ])
        # Mock execute_query() for DROP SCHEMA
        mock_model.execute_query = Mock()
        # Mock reconnect(reload=True)
        mock_model.reconnect = Mock()
        repo.model = mock_model
        repo.model_dir = str(model_dir)

        # Mock execute_pg_command
        mock_execute = Mock()
        repo.database.execute_pg_command = mock_execute

        # Execute restoration
        repo.restore_database_from_schema()

        # Should work with regular file
        psql_call = call('psql', '-d', 'test_database', '-f', str(schema_file))
        assert psql_call in mock_execute.call_args_list

        # Workflow should complete
        mock_model.reconnect.assert_called_once_with(reload=True)


class TestLoadDataFiles:
    """Test _load_data_files method for loading reference data."""

    def test_load_data_files_single_version(self, patch_manager):
        """Test loading single data file matching schema version."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Bind _load_data_files to the mock repo
        repo._load_data_files = Repo._load_data_files.__get__(repo, type(repo))

        # Create model directory with schema symlink
        model_dir = Path(temp_dir) / ".hop" / "model"
        model_dir.mkdir(parents=True)

        # Create versioned schema file
        versioned_schema = model_dir / "schema-1.0.0.sql"
        versioned_schema.write_text("CREATE TABLE test (id SERIAL);")

        # Create symlink schema.sql -> schema-1.0.0.sql
        schema_symlink = model_dir / "schema.sql"
        schema_symlink.symlink_to("schema-1.0.0.sql")

        # Create data file
        data_file = model_dir / "data-1.0.0.sql"
        data_file.write_text("INSERT INTO test (id) VALUES (1);")

        repo.model_dir = str(model_dir)

        # Mock execute_pg_command
        mock_execute = Mock()
        repo.database.execute_pg_command = mock_execute

        # Load data files
        repo._load_data_files(schema_symlink)

        # Verify data file was loaded
        psql_call = call('psql', '-d', 'test_database', '-f', str(data_file))
        assert psql_call in mock_execute.call_args_list

    def test_load_data_files_multiple_versions_ordered(self, patch_manager):
        """Test loading multiple data files in version order."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Bind _load_data_files to the mock repo
        repo._load_data_files = Repo._load_data_files.__get__(repo, type(repo))

        # Create model directory with schema symlink
        model_dir = Path(temp_dir) / ".hop" / "model"
        model_dir.mkdir(parents=True)

        # Create versioned schema file
        versioned_schema = model_dir / "schema-1.2.0.sql"
        versioned_schema.write_text("CREATE TABLE test (id SERIAL);")

        # Create symlink schema.sql -> schema-1.2.0.sql
        schema_symlink = model_dir / "schema.sql"
        schema_symlink.symlink_to("schema-1.2.0.sql")

        # Create data files in various versions
        data_files = [
            model_dir / "data-0.1.0.sql",
            model_dir / "data-1.0.0.sql",
            model_dir / "data-1.2.0.sql",
            model_dir / "data-2.0.0.sql",  # Should NOT be loaded (beyond current version)
        ]
        for df in data_files:
            df.write_text(f"-- Data for {df.name}")

        repo.model_dir = str(model_dir)

        # Mock execute_pg_command
        mock_execute = Mock()
        repo.database.execute_pg_command = mock_execute

        # Load data files
        repo._load_data_files(schema_symlink)

        # Verify only files up to 1.2.0 were loaded, in order
        calls = mock_execute.call_args_list
        assert len(calls) == 3  # 0.1.0, 1.0.0, 1.2.0

        # Verify order
        assert "data-0.1.0.sql" in str(calls[0])
        assert "data-1.0.0.sql" in str(calls[1])
        assert "data-1.2.0.sql" in str(calls[2])

    def test_load_data_files_skips_future_versions(self, patch_manager):
        """Test that data files for future versions are skipped."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Bind _load_data_files to the mock repo
        repo._load_data_files = Repo._load_data_files.__get__(repo, type(repo))

        # Create model directory with schema symlink
        model_dir = Path(temp_dir) / ".hop" / "model"
        model_dir.mkdir(parents=True)

        # Create versioned schema file at 1.0.0
        versioned_schema = model_dir / "schema-1.0.0.sql"
        versioned_schema.write_text("CREATE TABLE test (id SERIAL);")

        # Create symlink schema.sql -> schema-1.0.0.sql
        schema_symlink = model_dir / "schema.sql"
        schema_symlink.symlink_to("schema-1.0.0.sql")

        # Create data files
        data_current = model_dir / "data-1.0.0.sql"
        data_current.write_text("-- Current version data")

        data_future = model_dir / "data-2.0.0.sql"
        data_future.write_text("-- Future version data")

        repo.model_dir = str(model_dir)

        # Mock execute_pg_command
        mock_execute = Mock()
        repo.database.execute_pg_command = mock_execute

        # Load data files
        repo._load_data_files(schema_symlink)

        # Verify only 1.0.0 was loaded
        assert mock_execute.call_count == 1
        assert "data-1.0.0.sql" in str(mock_execute.call_args_list[0])

    def test_load_data_files_no_data_files(self, patch_manager):
        """Test that no error occurs when no data files exist."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Bind _load_data_files to the mock repo
        repo._load_data_files = Repo._load_data_files.__get__(repo, type(repo))

        # Create model directory with schema symlink
        model_dir = Path(temp_dir) / ".hop" / "model"
        model_dir.mkdir(parents=True)

        # Create versioned schema file
        versioned_schema = model_dir / "schema-1.0.0.sql"
        versioned_schema.write_text("CREATE TABLE test (id SERIAL);")

        # Create symlink schema.sql -> schema-1.0.0.sql
        schema_symlink = model_dir / "schema.sql"
        schema_symlink.symlink_to("schema-1.0.0.sql")

        # No data files created

        repo.model_dir = str(model_dir)

        # Mock execute_pg_command
        mock_execute = Mock()
        repo.database.execute_pg_command = mock_execute

        # Load data files - should not raise
        repo._load_data_files(schema_symlink)

        # Verify no psql calls were made for data
        assert mock_execute.call_count == 0

    def test_load_data_files_regular_schema_file(self, patch_manager):
        """Test that data loading is skipped for regular schema file (no symlink)."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Bind _load_data_files to the mock repo
        repo._load_data_files = Repo._load_data_files.__get__(repo, type(repo))

        # Create model directory with regular schema file (no symlink)
        model_dir = Path(temp_dir) / ".hop" / "model"
        model_dir.mkdir(parents=True)

        schema_file = model_dir / "schema.sql"
        schema_file.write_text("CREATE TABLE test (id SERIAL);")

        # Create data file
        data_file = model_dir / "data-1.0.0.sql"
        data_file.write_text("INSERT INTO test (id) VALUES (1);")

        repo.model_dir = str(model_dir)

        # Mock execute_pg_command
        mock_execute = Mock()
        repo.database.execute_pg_command = mock_execute

        # Load data files - should skip because no version can be deduced
        repo._load_data_files(schema_file)

        # Verify no psql calls were made
        assert mock_execute.call_count == 0

    def test_load_data_files_error_handling(self, patch_manager):
        """Test error handling when data file loading fails."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Bind _load_data_files to the mock repo
        repo._load_data_files = Repo._load_data_files.__get__(repo, type(repo))

        # Create model directory with schema symlink
        model_dir = Path(temp_dir) / ".hop" / "model"
        model_dir.mkdir(parents=True)

        # Create versioned schema file
        versioned_schema = model_dir / "schema-1.0.0.sql"
        versioned_schema.write_text("CREATE TABLE test (id SERIAL);")

        # Create symlink schema.sql -> schema-1.0.0.sql
        schema_symlink = model_dir / "schema.sql"
        schema_symlink.symlink_to("schema-1.0.0.sql")

        # Create data file
        data_file = model_dir / "data-1.0.0.sql"
        data_file.write_text("INVALID SQL;")

        repo.model_dir = str(model_dir)

        # Mock execute_pg_command to fail
        mock_execute = Mock(side_effect=Exception("psql failed: syntax error"))
        repo.database.execute_pg_command = mock_execute

        # Load data files - should raise RepoError
        with pytest.raises(RepoError, match="Failed to load data"):
            repo._load_data_files(schema_symlink)
