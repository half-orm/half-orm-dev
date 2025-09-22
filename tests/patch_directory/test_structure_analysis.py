"""
Tests pour l'analyse et validation de structure des patches.

Module de test focalisé sur validate_patch_structure() suivant
la philosophie KISS avec validation minimale.
"""

import pytest
from pathlib import Path

from half_orm_dev.patch_directory import (
    PatchDirectory,
    PatchDirectoryError
)


class TestValidatePatchStructure:
    """Test patch structure validation functionality."""

    def test_validate_patch_structure_valid_directory(self, patch_directory):
        """Test validating existing patch directory."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory

        # Create valid patch directory
        patch_path = schema_patches_dir / "456-test"
        patch_path.mkdir()

        is_valid, errors = patch_dir.validate_patch_structure("456-test")

        assert is_valid is True
        assert errors == []

    def test_validate_patch_structure_nonexistent_directory(self, patch_directory):
        """Test validating nonexistent patch directory."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory

        is_valid, errors = patch_dir.validate_patch_structure("999-nonexistent")

        assert is_valid is False
        assert len(errors) == 1
        assert "does not exist" in errors[0]
        assert "999-nonexistent" in errors[0]

    def test_validate_patch_structure_file_not_directory(self, patch_directory):
        """Test validating when patch path is a file, not directory."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory

        # Create file instead of directory
        patch_file = schema_patches_dir / "456-file"
        patch_file.write_text("This is a file, not a directory")

        is_valid, errors = patch_dir.validate_patch_structure("456-file")

        assert is_valid is False
        assert len(errors) == 1
        assert "not a directory" in errors[0]

    def test_validate_patch_structure_permission_denied(self, patch_directory):
        """Test validation with permission denied error."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory

        # Create patch directory
        patch_path = schema_patches_dir / "456-permission"
        patch_path.mkdir()

        # Make parent directory inaccessible
        schema_patches_dir.chmod(0o000)

        try:
            is_valid, errors = patch_dir.validate_patch_structure("456-permission")

            assert is_valid is False
            assert len(errors) == 1
            assert "Permission denied" in errors[0]

        finally:
            # Restore permissions for cleanup
            schema_patches_dir.chmod(0o755)

    def test_validate_patch_structure_empty_directory(self, patch_directory):
        """Test validating empty patch directory - should be valid."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory

        # Create empty patch directory
        patch_path = schema_patches_dir / "456-empty"
        patch_path.mkdir()

        is_valid, errors = patch_dir.validate_patch_structure("456-empty")

        # Empty directory should be valid (KISS principle)
        assert is_valid is True
        assert errors == []

    def test_validate_patch_structure_with_readme_only(self, patch_directory):
        """Test validating patch with only README.md - should be valid."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory

        # Create patch with only README
        patch_path = schema_patches_dir / "456-readme-only"
        patch_path.mkdir()
        (patch_path / "README.md").write_text("# Patch 456-readme-only")

        is_valid, errors = patch_dir.validate_patch_structure("456-readme-only")

        assert is_valid is True
        assert errors == []

    def test_validate_patch_structure_with_sql_files(self, patch_directory):
        """Test validating patch with SQL files - should be valid."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory

        # Create patch with SQL files
        patch_path = schema_patches_dir / "456-sql-files"
        patch_path.mkdir()
        (patch_path / "01_create_table.sql").write_text("CREATE TABLE test (id INTEGER);")
        (patch_path / "02_add_data.sql").write_text("INSERT INTO test VALUES (1);")

        is_valid, errors = patch_dir.validate_patch_structure("456-sql-files")

        assert is_valid is True
        assert errors == []

    def test_validate_patch_structure_with_python_files(self, patch_directory):
        """Test validating patch with Python files - should be valid."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory

        # Create patch with Python files  
        patch_path = schema_patches_dir / "456-python-files"
        patch_path.mkdir()
        (patch_path / "01_migrate.py").write_text("print('Migration script')")
        (patch_path / "02_cleanup.py").write_text("print('Cleanup script')")

        is_valid, errors = patch_dir.validate_patch_structure("456-python-files")

        assert is_valid is True
        assert errors == []

    def test_validate_patch_structure_with_mixed_files(self, patch_directory):
        """Test validating patch with mixed file types - should be valid."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory

        # Create patch with various file types
        patch_path = schema_patches_dir / "456-mixed"
        patch_path.mkdir()
        (patch_path / "README.md").write_text("# Mixed patch")
        (patch_path / "01_schema.sql").write_text("CREATE TABLE users (id INTEGER);")
        (patch_path / "02_migrate.py").write_text("# Migration logic")
        (patch_path / "data.json").write_text('{"users": []}')
        (patch_path / "config.txt").write_text("Configuration file")

        is_valid, errors = patch_dir.validate_patch_structure("456-mixed")

        # All file types should be accepted (KISS principle)
        assert is_valid is True
        assert errors == []

    def test_validate_patch_structure_with_subdirectories(self, patch_directory):
        """Test validating patch with subdirectories - should be valid."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory

        # Create patch with subdirectories
        patch_path = schema_patches_dir / "456-with-dirs"
        patch_path.mkdir()
        (patch_path / "README.md").write_text("# Patch with subdirs")

        # Create subdirectories with files
        data_dir = patch_path / "data"
        data_dir.mkdir()
        (data_dir / "users.json").write_text('{"users": []}')

        templates_dir = patch_path / "templates"  
        templates_dir.mkdir()
        (templates_dir / "email.html").write_text("<html>Email template</html>")

        is_valid, errors = patch_dir.validate_patch_structure("456-with-dirs")

        # Subdirectories should be allowed (flexibility for developers)
        assert is_valid is True
        assert errors == []

    def test_validate_patch_structure_weird_filenames(self, patch_directory):
        """Test validating patch with unconventional filenames - should be valid."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory

        # Create patch with unconventional but valid filenames
        patch_path = schema_patches_dir / "456-weird-names"
        patch_path.mkdir()
        (patch_path / "create table with spaces.sql").write_text("CREATE TABLE test (id INTEGER);")
        (patch_path / "script-with-dashes.py").write_text("print('test')")
        (patch_path / "NO_PREFIX.sql").write_text("SELECT 1;")
        (patch_path / "UPPERCASE.PY").write_text("print('UPPER')")

        is_valid, errors = patch_dir.validate_patch_structure("456-weird-names")

        # No filename restrictions (developer flexibility)
        assert is_valid is True
        assert errors == []

    def test_validate_patch_structure_code_only_patch(self, patch_directory):
        """Test validating patch with only halfORM code changes - should be valid."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory

        # Create patch simulating code-only changes
        patch_path = schema_patches_dir / "456-code-only"
        patch_path.mkdir()
        (patch_path / "README.md").write_text("# Code-only patch\nUpdates business logic only.")

        # No SQL or Python execution files, just documentation
        (patch_path / "changes.md").write_text("Modified user.py authentication logic")
        (patch_path / "tests_added.txt").write_text("Added test_authentication.py")

        is_valid, errors = patch_dir.validate_patch_structure("456-code-only")

        # Code-only patches should be perfectly valid
        assert is_valid is True
        assert errors == []

    def test_validate_patch_structure_unicode_filenames(self, patch_directory):
        """Test validating patch with unicode filenames - should be valid."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory

        # Create patch with unicode filenames
        patch_path = schema_patches_dir / "456-unicode"
        patch_path.mkdir()
        (patch_path / "测试文件.sql").write_text("-- Chinese filename")
        (patch_path / "café.py").write_text("# French accent")
        (patch_path / "файл.txt").write_text("# Russian filename")

        is_valid, errors = patch_dir.validate_patch_structure("456-unicode")

        # Unicode filenames should be supported
        assert is_valid is True
        assert errors == []

    def test_validate_patch_structure_return_format(self, patch_directory):
        """Test that validate_patch_structure returns correct format."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory

        # Test with valid directory
        patch_path = schema_patches_dir / "456-format-test"
        patch_path.mkdir()

        result = patch_dir.validate_patch_structure("456-format-test")

        # Should return tuple of (bool, list)
        assert isinstance(result, tuple)
        assert len(result) == 2

        is_valid, errors = result
        assert isinstance(is_valid, bool)
        assert isinstance(errors, list)
