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

    def test_generate_schema_sql_creates_versioned_file(self, tmp_path):
        """Test schema file creation with version."""
        model_dir = tmp_path / "model"
        model_dir.mkdir()

        # Mock Database instance
        database = Mock(spec=Database)
        database._name = "test_db"
        database._execute_pg_command = Mock()

        # Call method
        result = Database._generate_schema_sql(database, "0.0.0", model_dir)

        # Should create schema-0.0.0.sql
        expected_file = model_dir / "schema-0.0.0.sql"
        assert result == expected_file

        # Should call pg_dump with correct arguments
        database._execute_pg_command.assert_called_once_with(
            'pg_dump', '--schema-only', '-f', str(expected_file)
        )

    def test_generate_schema_sql_creates_symlink(self, tmp_path):
        """Test symlink creation to versioned file."""
        model_dir = tmp_path / "model"
        model_dir.mkdir()

        database = Mock(spec=Database)
        database._name = "test_db"
        database._execute_pg_command = Mock()

        Database._generate_schema_sql(database, "1.3.4", model_dir)

        # Should create symlink schema.sql → schema-1.3.4.sql
        symlink = model_dir / "schema.sql"
        assert symlink.is_symlink()
        assert symlink.resolve().name == "schema-1.3.4.sql"

    def test_generate_schema_sql_updates_existing_symlink(self, tmp_path):
        """Test updating existing symlink to new version."""
        model_dir = tmp_path / "model"
        model_dir.mkdir()

        # Create existing symlink to old version
        old_file = model_dir / "schema-1.2.0.sql"
        old_file.touch()
        symlink = model_dir / "schema.sql"
        symlink.symlink_to("schema-1.2.0.sql")

        database = Mock(spec=Database)
        database._name = "test_db"
        database._execute_pg_command = Mock()

        # Generate new version
        Database._generate_schema_sql(database, "1.3.4", model_dir)

        # Symlink should now point to new version
        assert symlink.is_symlink()
        assert symlink.resolve().name == "schema-1.3.4.sql"

    def test_generate_schema_sql_overwrites_existing_version(self, tmp_path):
        """Test overwriting existing schema file (hotfix scenario)."""
        model_dir = tmp_path / "model"
        model_dir.mkdir()

        # Create existing version file
        existing_file = model_dir / "schema-1.3.4.sql"
        existing_file.write_text("OLD SCHEMA CONTENT")

        database = Mock(spec=Database)
        database._name = "test_db"
        database._execute_pg_command = Mock()

        # Generate same version (overwrites)
        Database._generate_schema_sql(database, "1.3.4", model_dir)

        # Should call pg_dump (which overwrites the file)
        database._execute_pg_command.assert_called_once()

    def test_generate_schema_sql_model_dir_not_exists(self, tmp_path):
        """Test error when model directory doesn't exist."""
        model_dir = tmp_path / "nonexistent_model"

        database = Mock(spec=Database)
        database._name = "test_db"

        with pytest.raises(FileNotFoundError, match="Model.*directory.*not exist"):
            Database._generate_schema_sql(database, "1.0.0", model_dir)

    def test_generate_schema_sql_pg_dump_fails(self, tmp_path):
        """Test handling of pg_dump command failure."""
        model_dir = tmp_path / "model"
        model_dir.mkdir()

        database = Mock(spec=Database)
        database._name = "test_db"
        database._execute_pg_command = Mock(side_effect=Exception("pg_dump failed"))

        with pytest.raises(Exception, match="pg_dump failed"):
            Database._generate_schema_sql(database, "1.0.0", model_dir)

    def test_generate_schema_sql_permission_denied_write(self, tmp_path):
        """Test handling of permission denied when writing schema file."""
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        model_dir.chmod(0o444)  # Read-only

        database = Mock(spec=Database)
        database._name = "test_db"
        database._execute_pg_command = Mock()

        try:
            with pytest.raises(PermissionError):
                Database._generate_schema_sql(database, "1.0.0", model_dir)
        finally:
            model_dir.chmod(0o755)  # Restore for cleanup

    def test_generate_schema_sql_permission_denied_symlink(self, tmp_path):
        """Test handling of permission denied when creating symlink."""
        model_dir = tmp_path / "model"
        model_dir.mkdir()

        # Create schema file but make directory read-only after
        schema_file = model_dir / "schema-1.0.0.sql"
        schema_file.touch()
        model_dir.chmod(0o555)  # Read + execute only

        database = Mock(spec=Database)
        database._name = "test_db"
        database._execute_pg_command = Mock()

        try:
            with pytest.raises(PermissionError):
                Database._generate_schema_sql(database, "1.0.0", model_dir)
        finally:
            model_dir.chmod(0o755)  # Restore for cleanup

    def test_generate_schema_sql_invalid_version_format(self, tmp_path):
        """Test validation of version format."""
        model_dir = tmp_path / "model"
        model_dir.mkdir()

        database = Mock(spec=Database)
        database._name = "test_db"

        # Test various invalid formats
        invalid_versions = ["", "1", "1.2", "v1.2.3", "1.2.3.4", "abc", "1.x.3"]

        for invalid_version in invalid_versions:
            with pytest.raises(ValueError, match="Invalid version format"):
                Database._generate_schema_sql(database, invalid_version, model_dir)

    def test_generate_schema_sql_valid_version_formats(self, tmp_path):
        """Test acceptance of valid version formats."""
        model_dir = tmp_path / "model"
        model_dir.mkdir()

        database = Mock(spec=Database)
        database._name = "test_db"
        database._execute_pg_command = Mock()

        # Test valid formats
        valid_versions = ["0.0.0", "1.0.0", "1.3.4", "10.20.30"]

        for valid_version in valid_versions:
            result = Database._generate_schema_sql(database, valid_version, model_dir)
            assert result.name == f"schema-{valid_version}.sql"

    def test_generate_schema_sql_symlink_is_relative(self, tmp_path):
        """Test that symlink uses relative path, not absolute."""
        model_dir = tmp_path / "model"
        model_dir.mkdir()

        database = Mock(spec=Database)
        database._name = "test_db"
        database._execute_pg_command = Mock()

        Database._generate_schema_sql(database, "1.0.0", model_dir)

        symlink = model_dir / "schema.sql"
        
        # Read the symlink target (should be relative)
        link_target = os.readlink(symlink)
        assert not os.path.isabs(link_target)
        assert link_target == "schema-1.0.0.sql"

    def test_generate_schema_sql_returns_correct_path(self, tmp_path):
        """Test that method returns correct Path object."""
        model_dir = tmp_path / "model"
        model_dir.mkdir()

        database = Mock(spec=Database)
        database._name = "test_db"
        database._execute_pg_command = Mock()

        result = Database._generate_schema_sql(database, "2.5.1", model_dir)

        assert isinstance(result, Path)
        assert result == model_dir / "schema-2.5.1.sql"
        assert result.parent == model_dir

    def test_generate_schema_sql_uses_schema_only_flag(self, tmp_path):
        """Test that pg_dump uses --schema-only flag (no data)."""
        model_dir = tmp_path / "model"
        model_dir.mkdir()

        database = Mock(spec=Database)
        database._name = "test_db"
        database._execute_pg_command = Mock()

        Database._generate_schema_sql(database, "1.0.0", model_dir)

        # Verify --schema-only is in the pg_dump call
        call_args = database._execute_pg_command.call_args[0]
        assert '--schema-only' in call_args
