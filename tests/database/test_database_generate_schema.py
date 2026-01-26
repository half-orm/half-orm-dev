"""
Tests for Database._generate_schema_sql() method.

Focused on testing:
- Versioned schema SQL generation using pg_dump
- Symlink creation and updates
- Error handling for various failure scenarios
- Version format validation
"""

import pytest
import os
from pathlib import Path
from unittest.mock import Mock, patch, call

from half_orm_dev.database import Database


class TestGenerateSchemaSql:
    """Test _generate_schema_sql() method."""

    def test_generate_schema_sql_creates_versioned_file(self, mock_database_for_schema_generation, tmp_path):
        """Test schema file creation with version."""
        model_dir = tmp_path / "model"
        model_dir.mkdir()

        database = mock_database_for_schema_generation

        # Call method
        result = Database._generate_schema_sql(database, "0.0.0", model_dir)

        # Should create schema-0.0.0.sql
        expected_file = model_dir / "schema-0.0.0.sql"
        assert result == expected_file

        # Should call execute_pg_command twice: once for schema, once for metadata
        assert database.execute_pg_command.call_count == 2

        # First call: schema dump
        schema_call = database.execute_pg_command.call_args_list[0]
        assert 'pg_dump' in schema_call[0]
        assert '--schema-only' in schema_call[0]

        # Second call: metadata dump
        metadata_call = database.execute_pg_command.call_args_list[1]
        assert 'pg_dump' in metadata_call[0]
        assert '--data-only' in metadata_call[0]
        assert '--table=half_orm_meta.database' in metadata_call[0]

    def test_generate_schema_sql_creates_symlink(self, mock_database_for_schema_generation, tmp_path):
        """Test symlink creation to versioned file."""
        model_dir = tmp_path / "model"
        model_dir.mkdir()

        database = mock_database_for_schema_generation

        Database._generate_schema_sql(database, "1.3.4", model_dir)

        # Should create symlink schema.sql → schema-1.3.4.sql
        symlink = model_dir / "schema.sql"
        assert symlink.is_symlink()
        assert symlink.resolve().name == "schema-1.3.4.sql"

    def test_generate_schema_sql_updates_existing_symlink(self, mock_database_for_schema_generation, tmp_path):
        """Test updating existing symlink to new version."""
        model_dir = tmp_path / "model"
        model_dir.mkdir()

        # Create existing symlink to old version
        old_file = model_dir / "schema-1.2.0.sql"
        old_file.touch()
        symlink = model_dir / "schema.sql"
        symlink.symlink_to("schema-1.2.0.sql")

        database = mock_database_for_schema_generation

        # Generate new version
        Database._generate_schema_sql(database, "1.3.4", model_dir)

        # Symlink should now point to new version
        assert symlink.is_symlink()
        assert symlink.resolve().name == "schema-1.3.4.sql"

    def test_generate_schema_sql_overwrites_existing_version(self, mock_database_for_schema_generation, tmp_path):
        """Test overwriting existing schema file (hotfix scenario)."""
        model_dir = tmp_path / "model"
        model_dir.mkdir()

        # Create existing version file
        existing_file = model_dir / "schema-1.3.4.sql"
        existing_file.write_text("OLD SCHEMA CONTENT")

        database = mock_database_for_schema_generation

        # Generate same version (overwrites)
        Database._generate_schema_sql(database, "1.3.4", model_dir)

        # Should call execute_pg_command twice (schema + metadata)
        assert database.execute_pg_command.call_count == 2

    def test_generate_schema_sql_model_dir_not_exists(self, mock_database_for_schema_generation, tmp_path):
        """Test error when model directory doesn't exist."""
        model_dir = tmp_path / "nonexistent_model"

        database = mock_database_for_schema_generation

        with pytest.raises(FileNotFoundError, match="Model directory does not exist"):
            Database._generate_schema_sql(database, "1.0.0", model_dir)

    def test_generate_schema_sql_pg_dump_fails(self, mock_database_for_schema_generation, tmp_path):
        """Test handling of pg_dump command failure."""
        model_dir = tmp_path / "model"
        model_dir.mkdir()

        database = mock_database_for_schema_generation
        # Mock execute_pg_command to fail on first call (schema generation)
        database.execute_pg_command = Mock(side_effect=Exception("pg_dump failed"))

        with pytest.raises(Exception, match="Failed to generate schema SQL"):
            Database._generate_schema_sql(database, "1.0.0", model_dir)

    def test_generate_schema_sql_permission_denied_write(self, mock_database_for_schema_generation, tmp_path):
        """Test handling of permission denied when writing schema file."""
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        model_dir.chmod(0o444)  # Read-only

        database = mock_database_for_schema_generation

        try:
            with pytest.raises(PermissionError):
                Database._generate_schema_sql(database, "1.0.0", model_dir)
        finally:
            model_dir.chmod(0o755)  # Restore for cleanup

    def test_generate_schema_sql_permission_denied_symlink(self, mock_database_for_schema_generation, tmp_path):
        """Test handling of permission denied when creating symlink."""
        model_dir = tmp_path / "model"
        model_dir.mkdir()

        # Create schema file and temp file, then make directory read-only
        schema_file = model_dir / "schema-1.0.0.sql"
        schema_file.touch()
        temp_schema_file = model_dir / ".schema-1.0.0.sql.tmp"
        temp_schema_file.write_text("-- test content\nCREATE TABLE test();")
        temp_metadata_file = model_dir / ".metadata-1.0.0.sql.tmp"
        temp_metadata_file.write_text("COPY half_orm_meta.hop_release FROM stdin;\n0\t0\t0\n\\.")
        model_dir.chmod(0o555)  # Read + execute only

        database = mock_database_for_schema_generation
        # Override mock to not write files (directory is read-only)
        database.execute_pg_command = Mock()

        try:
            with pytest.raises(PermissionError):
                Database._generate_schema_sql(database, "1.0.0", model_dir)
        finally:
            model_dir.chmod(0o755)  # Restore for cleanup

    def test_generate_schema_sql_invalid_version_format(self, mock_database_for_schema_generation, tmp_path):
        """Test validation of version format."""
        model_dir = tmp_path / "model"
        model_dir.mkdir()

        database = mock_database_for_schema_generation

        # Test various invalid formats
        invalid_versions = ["", "1", "1.2", "v1.2.3", "1.2.3.4", "abc", "1.x.3"]

        for invalid_version in invalid_versions:
            with pytest.raises(ValueError, match="Invalid version format"):
                Database._generate_schema_sql(database, invalid_version, model_dir)

    def test_generate_schema_sql_valid_version_formats(self, mock_database_for_schema_generation, tmp_path):
        """Test acceptance of valid version formats."""
        model_dir = tmp_path / "model"
        model_dir.mkdir()

        database = mock_database_for_schema_generation

        # Test valid formats
        valid_versions = ["0.0.0", "1.0.0", "1.3.4", "10.20.30"]

        for valid_version in valid_versions:
            result = Database._generate_schema_sql(database, valid_version, model_dir)
            assert result.name == f"schema-{valid_version}.sql"

    def test_generate_schema_sql_symlink_is_relative(self, mock_database_for_schema_generation, tmp_path):
        """Test that symlink uses relative path, not absolute."""
        model_dir = tmp_path / "model"
        model_dir.mkdir()

        database = mock_database_for_schema_generation

        Database._generate_schema_sql(database, "1.0.0", model_dir)

        symlink = model_dir / "schema.sql"

        # Read the symlink target (should be relative)
        link_target = os.readlink(symlink)
        assert not os.path.isabs(link_target)
        assert link_target == "schema-1.0.0.sql"

    def test_generate_schema_sql_returns_correct_path(self, mock_database_for_schema_generation, tmp_path):
        """Test that method returns correct Path object."""
        model_dir = tmp_path / "model"
        model_dir.mkdir()

        database = mock_database_for_schema_generation

        result = Database._generate_schema_sql(database, "2.5.1", model_dir)

        assert isinstance(result, Path)
        assert result == model_dir / "schema-2.5.1.sql"
        assert result.parent == model_dir

    def test_generate_schema_sql_uses_schema_only_flag(self, mock_database_for_schema_generation, tmp_path):
        """Test that pg_dump uses --schema-only flag (no data)."""
        model_dir = tmp_path / "model"
        model_dir.mkdir()

        database = mock_database_for_schema_generation

        Database._generate_schema_sql(database, "1.0.0", model_dir)

        # Verify --schema-only is in the FIRST pg_dump call (schema)
        schema_call = database.execute_pg_command.call_args_list[0]
        assert '--schema-only' in schema_call[0]

    def test_generate_schema_sql_creates_metadata_file(self, mock_database_for_schema_generation, tmp_path):
        """Test metadata file creation alongside schema."""
        model_dir = tmp_path / "model"
        model_dir.mkdir()

        database = mock_database_for_schema_generation

        # Call method
        Database._generate_schema_sql(database, "1.2.3", model_dir)

        # Should create both files
        schema_file = model_dir / "schema-1.2.3.sql"
        metadata_file = model_dir / "metadata-1.2.3.sql"
        temp_metadata_file = model_dir / ".metadata-1.2.3.sql.tmp"

        # Verify both calls were made
        assert database.execute_pg_command.call_count == 2

        # Second call should be for metadata with correct tables (writes to temp file)
        metadata_call = database.execute_pg_command.call_args_list[1]
        call_args = metadata_call[0]

        assert 'pg_dump' in call_args
        assert '--data-only' in call_args
        assert '--table=half_orm_meta.database' in call_args
        assert '--table=half_orm_meta.hop_release' in call_args
        assert '--table=half_orm_meta.hop_release_issue' in call_args
        # Now dumps to temp file which is then filtered
        assert str(temp_metadata_file) in call_args

        # Final metadata file should exist (created from filtered temp content)
        assert metadata_file.exists()


    def test_generate_schema_sql_no_metadata_symlink(self, mock_database_for_schema_generation, tmp_path):
        """Test that no symlink is created for metadata file."""
        model_dir = tmp_path / "model"
        model_dir.mkdir()

        database = mock_database_for_schema_generation

        Database._generate_schema_sql(database, "1.0.0", model_dir)

        # Schema symlink should exist
        schema_symlink = model_dir / "schema.sql"
        assert schema_symlink.is_symlink()

        # Metadata symlink should NOT exist
        metadata_symlink = model_dir / "metadata.sql"
        assert not metadata_symlink.exists()


    def test_generate_schema_sql_metadata_failure(self, mock_database_for_schema_generation, tmp_path):
        """Test handling of metadata generation failure."""
        model_dir = tmp_path / "model"
        model_dir.mkdir()

        database = mock_database_for_schema_generation

        # Create temp schema file that would be created by first pg_dump call
        temp_schema_file = model_dir / ".schema-1.0.0.sql.tmp"

        def mock_schema_then_fail(*args):
            """First call creates temp file, second call fails."""
            if '--schema-only' in args:
                temp_schema_file.write_text("-- test schema\nCREATE TABLE test();")
            else:
                raise Exception("metadata dump failed")

        # Mock: schema succeeds (creates temp file), metadata fails
        database.execute_pg_command = Mock(side_effect=mock_schema_then_fail)

        with pytest.raises(Exception, match="Failed to generate metadata SQL"):
            Database._generate_schema_sql(database, "1.0.0", model_dir)