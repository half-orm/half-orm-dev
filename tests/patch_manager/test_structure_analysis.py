"""
Tests pour l'analyse et validation de structure des patches.

Module de test focalisé sur validate_patch_structure() suivant
la philosophie KISS avec validation minimale.
"""

import pytest
from pathlib import Path

from half_orm_dev.patch_manager import (
    PatchManager,
    PatchStructure,
    PatchManagerError
)


class TestValidatePatchStructure:
    """Test patch structure validation functionality."""

    def test_validate_patch_structure_valid_directory(self, patch_manager):
        """Test validating existing patch directory."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create valid patch directory
        patch_path = patches_dir / "456-test"
        patch_path.mkdir()

        is_valid, errors = patch_mgr.validate_patch_structure("456-test")

        assert is_valid is True
        assert errors == []

    def test_validate_patch_structure_nonexistent_directory(self, patch_manager):
        """Test validating nonexistent patch directory."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        is_valid, errors = patch_mgr.validate_patch_structure("999-nonexistent")

        assert is_valid is False
        assert len(errors) == 1
        assert "does not exist" in errors[0]
        assert "999-nonexistent" in errors[0]

    def test_validate_patch_structure_file_not_directory(self, patch_manager):
        """Test validating when patch path is a file, not directory."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create file instead of directory
        patch_file = patches_dir / "456-file"
        patch_file.write_text("This is a file, not a directory")

        is_valid, errors = patch_mgr.validate_patch_structure("456-file")

        assert is_valid is False
        assert len(errors) == 1
        assert "not a directory" in errors[0]

    def test_validate_patch_structure_permission_denied(self, patch_manager):
        """Test validation with permission denied error."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create patch directory
        patch_path = patches_dir / "456-permission"
        patch_path.mkdir()

        # Make parent directory inaccessible
        patches_dir.chmod(0o000)

        try:
            is_valid, errors = patch_mgr.validate_patch_structure("456-permission")

            assert is_valid is False
            assert len(errors) == 1
            assert "Permission denied" in errors[0]

        finally:
            # Restore permissions for cleanup
            patches_dir.chmod(0o755)

    def test_validate_patch_structure_empty_directory(self, patch_manager):
        """Test validating empty patch directory - should be valid."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create empty patch directory
        patch_path = patches_dir / "456-empty"
        patch_path.mkdir()

        is_valid, errors = patch_mgr.validate_patch_structure("456-empty")

        # Empty directory should be valid (KISS principle)
        assert is_valid is True
        assert errors == []

    def test_validate_patch_structure_with_readme_only(self, patch_manager):
        """Test validating patch with only README.md - should be valid."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create patch with only README
        patch_path = patches_dir / "456-readme-only"
        patch_path.mkdir()
        (patch_path / "README.md").write_text("# Patch 456-readme-only")

        is_valid, errors = patch_mgr.validate_patch_structure("456-readme-only")

        assert is_valid is True
        assert errors == []

    def test_validate_patch_structure_with_sql_files(self, patch_manager):
        """Test validating patch with SQL files - should be valid."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create patch with SQL files
        patch_path = patches_dir / "456-sql-files"
        patch_path.mkdir()
        (patch_path / "01_create_table.sql").write_text("CREATE TABLE test (id INTEGER);")
        (patch_path / "02_add_data.sql").write_text("INSERT INTO test VALUES (1);")

        is_valid, errors = patch_mgr.validate_patch_structure("456-sql-files")

        assert is_valid is True
        assert errors == []

    def test_validate_patch_structure_with_python_files(self, patch_manager):
        """Test validating patch with Python files - should be valid."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create patch with Python files  
        patch_path = patches_dir / "456-python-files"
        patch_path.mkdir()
        (patch_path / "01_migrate.py").write_text("print('Migration script')")
        (patch_path / "02_cleanup.py").write_text("print('Cleanup script')")

        is_valid, errors = patch_mgr.validate_patch_structure("456-python-files")

        assert is_valid is True
        assert errors == []

    def test_validate_patch_structure_with_mixed_files(self, patch_manager):
        """Test validating patch with mixed file types - should be valid."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager
        
        # Create patch with various file types
        patch_path = patches_dir / "456-mixed"
        patch_path.mkdir()
        (patch_path / "README.md").write_text("# Mixed patch")
        (patch_path / "01_schema.sql").write_text("CREATE TABLE users (id INTEGER);")
        (patch_path / "02_migrate.py").write_text("# Migration logic")
        (patch_path / "data.json").write_text('{"users": []}')
        (patch_path / "config.txt").write_text("Configuration file")

        is_valid, errors = patch_mgr.validate_patch_structure("456-mixed")

        # All file types should be accepted (KISS principle)
        assert is_valid is True
        assert errors == []

    def test_validate_patch_structure_with_subdirectories(self, patch_manager):
        """Test validating patch with subdirectories - should be valid."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create patch with subdirectories
        patch_path = patches_dir / "456-with-dirs"
        patch_path.mkdir()
        (patch_path / "README.md").write_text("# Patch with subdirs")

        # Create subdirectories with files
        data_dir = patch_path / "data"
        data_dir.mkdir()
        (data_dir / "users.json").write_text('{"users": []}')

        templates_dir = patch_path / "templates"  
        templates_dir.mkdir()
        (templates_dir / "email.html").write_text("<html>Email template</html>")

        is_valid, errors = patch_mgr.validate_patch_structure("456-with-dirs")

        # Subdirectories should be allowed (flexibility for developers)
        assert is_valid is True
        assert errors == []

    def test_validate_patch_structure_weird_filenames(self, patch_manager):
        """Test validating patch with unconventional filenames - should be valid."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create patch with unconventional but valid filenames
        patch_path = patches_dir / "456-weird-names"
        patch_path.mkdir()
        (patch_path / "create table with spaces.sql").write_text("CREATE TABLE test (id INTEGER);")
        (patch_path / "script-with-dashes.py").write_text("print('test')")
        (patch_path / "NO_PREFIX.sql").write_text("SELECT 1;")
        (patch_path / "UPPERCASE.PY").write_text("print('UPPER')")

        is_valid, errors = patch_mgr.validate_patch_structure("456-weird-names")

        # No filename restrictions (developer flexibility)
        assert is_valid is True
        assert errors == []

    def test_validate_patch_structure_code_only_patch(self, patch_manager):
        """Test validating patch with only halfORM code changes - should be valid."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create patch simulating code-only changes
        patch_path = patches_dir / "456-code-only"
        patch_path.mkdir()
        (patch_path / "README.md").write_text("# Code-only patch\nUpdates business logic only.")

        # No SQL or Python execution files, just documentation
        (patch_path / "changes.md").write_text("Modified user.py authentication logic")
        (patch_path / "tests_added.txt").write_text("Added test_authentication.py")

        is_valid, errors = patch_mgr.validate_patch_structure("456-code-only")

        # Code-only patches should be perfectly valid
        assert is_valid is True
        assert errors == []

    def test_validate_patch_structure_unicode_filenames(self, patch_manager):
        """Test validating patch with unicode filenames - should be valid."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create patch with unicode filenames
        patch_path = patches_dir / "456-unicode"
        patch_path.mkdir()
        (patch_path / "测试文件.sql").write_text("-- Chinese filename")
        (patch_path / "café.py").write_text("# French accent")
        (patch_path / "файл.txt").write_text("# Russian filename")

        is_valid, errors = patch_mgr.validate_patch_structure("456-unicode")

        # Unicode filenames should be supported
        assert is_valid is True
        assert errors == []

    def test_validate_patch_structure_return_format(self, patch_manager):
        """Test that validate_patch_structure returns correct format."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Test with valid directory
        patch_path = patches_dir / "456-format-test"
        patch_path.mkdir()

        result = patch_mgr.validate_patch_structure("456-format-test")

        # Should return tuple of (bool, list)
        assert isinstance(result, tuple)
        assert len(result) == 2

        is_valid, errors = result
        assert isinstance(is_valid, bool)
        assert isinstance(errors, list)


class TestGetPatchStructure:
    """Test patch structure analysis functionality."""

    def test_get_patch_structure_valid_patch_with_files(self, patch_manager, sample_patch_files):
        """Test analyzing valid patch structure with files."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create patch directory with sample files
        patch_path = patches_dir / "456-test"
        patch_path.mkdir()

        # Create files (excluding README for this test)
        files_to_create = {k: v for k, v in sample_patch_files.items() if k != "README.md"}
        for filename, content in files_to_create.items():
            (patch_path / filename).write_text(content)

        structure = patch_mgr.get_patch_structure("456-test")

        # Should be valid
        assert structure.is_valid is True
        assert len(structure.validation_errors) == 0

        # Check basic structure info
        assert structure.patch_id == "456-test"
        assert structure.directory_path == patch_path
        assert structure.readme_path == patch_path / "README.md"

        # Should have 4 files (excluding README.md)
        assert len(structure.files) == 4

        # Files should be in lexicographic order
        file_names = [f.name for f in structure.files]
        expected_order = ["01_create_users.sql", "02_add_indexes.sql", "03_update_permissions.py", "04_seed_data.sql"]
        assert file_names == expected_order

        # Check file properties
        sql_files = [f for f in structure.files if f.is_sql]
        python_files = [f for f in structure.files if f.is_python]
        assert len(sql_files) == 3
        assert len(python_files) == 1

        # Check specific file properties
        first_file = structure.files[0]
        assert first_file.name == "01_create_users.sql"
        assert first_file.extension == "sql"
        assert first_file.is_sql is True
        assert first_file.is_python is False
        assert first_file.exists is True

    def test_get_patch_structure_empty_patch(self, patch_manager):
        """Test analyzing empty patch directory."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create empty patch directory
        patch_path = patches_dir / "456-empty"
        patch_path.mkdir()

        structure = patch_mgr.get_patch_structure("456-empty")

        # Should be valid (empty patches allowed)
        assert structure.is_valid is True
        assert len(structure.validation_errors) == 0
        assert len(structure.files) == 0

    def test_get_patch_structure_nonexistent_patch(self, patch_manager):
        """Test analyzing nonexistent patch."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        structure = patch_mgr.get_patch_structure("999-nonexistent")

        # Should be invalid
        assert structure.is_valid is False
        assert len(structure.validation_errors) > 0
        assert "does not exist" in structure.validation_errors[0]
        assert len(structure.files) == 0

    def test_get_patch_structure_lexicographic_order(self, patch_manager):
        """Test that files are returned in lexicographic order."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create patch with files in random creation order
        patch_path = patches_dir / "456-order-test"
        patch_path.mkdir()

        # Create files out of lexicographic order
        (patch_path / "z_last.sql").write_text("-- Last file")
        (patch_path / "a_first.py").write_text("# First file")  
        (patch_path / "m_middle.sql").write_text("-- Middle file")
        (patch_path / "02_conventional.sql").write_text("-- Conventional naming")
        (patch_path / "01_also_conventional.py").write_text("# Also conventional")

        structure = patch_mgr.get_patch_structure("456-order-test")

        # Files should be in lexicographic order
        file_names = [f.name for f in structure.files]
        expected_order = ["01_also_conventional.py", "02_conventional.sql", "a_first.py", "m_middle.sql", "z_last.sql"]
        assert file_names == expected_order

    def test_get_patch_structure_mixed_file_types(self, patch_manager):
        """Test analyzing patch with mixed file types."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create patch with various file types
        patch_path = patches_dir / "456-mixed"
        patch_path.mkdir()
        (patch_path / "README.md").write_text("# Mixed patch")  # Should be excluded from files list
        (patch_path / "script.sql").write_text("SELECT 1;")
        (patch_path / "script.py").write_text("print('hello')")
        (patch_path / "data.json").write_text('{"key": "value"}')
        (patch_path / "config.txt").write_text("config data")

        structure = patch_mgr.get_patch_structure("456-mixed")

        # Should include all files except README.md
        assert len(structure.files) == 4

        # Check file type detection
        file_types = {f.name: (f.is_sql, f.is_python, f.extension) for f in structure.files}

        assert file_types["script.sql"] == (True, False, "sql")
        assert file_types["script.py"] == (False, True, "py") 
        assert file_types["data.json"] == (False, False, "json")
        assert file_types["config.txt"] == (False, False, "txt")

        # README.md should not be in files list
        readme_names = [f.name for f in structure.files if f.name == "README.md"]
        assert len(readme_names) == 0

    def test_get_patch_structure_with_subdirectories(self, patch_manager):
        """Test analyzing patch with subdirectories (should be ignored)."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create patch with subdirectories
        patch_path = patches_dir / "456-with-dirs"
        patch_path.mkdir()
        (patch_path / "script.sql").write_text("SELECT 1;")

        # Create subdirectory with files
        subdir = patch_path / "data"
        subdir.mkdir()
        (subdir / "users.json").write_text('{"users": []}')

        structure = patch_mgr.get_patch_structure("456-with-dirs")

        # Should only include files, not subdirectories
        assert len(structure.files) == 1
        assert structure.files[0].name == "script.sql"

    def test_get_patch_structure_permission_error(self, patch_manager):
        """Test handling permission errors during analysis."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create patch directory
        patch_path = patches_dir / "456-permission"
        patch_path.mkdir()
        (patch_path / "test.sql").write_text("SELECT 1;")

        # Make directory unreadable
        patch_path.chmod(0o000)

        try:
            structure = patch_mgr.get_patch_structure("456-permission")

            # Should be invalid due to permission error
            assert structure.is_valid is False
            assert any("Permission denied" in error for error in structure.validation_errors)

        finally:
            # Restore permissions for cleanup
            patch_path.chmod(0o755)

    def test_get_patch_structure_case_insensitive_sorting(self, patch_manager):
        """Test case-insensitive lexicographic sorting."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create patch with mixed case filenames
        patch_path = patches_dir / "456-case-test"
        patch_path.mkdir()
        (patch_path / "B_file.sql").write_text("-- B file")
        (patch_path / "a_file.py").write_text("# a file")
        (patch_path / "C_file.sql").write_text("-- C file")

        structure = patch_mgr.get_patch_structure("456-case-test")

        # Should be sorted case-insensitively
        file_names = [f.name for f in structure.files]
        expected_order = ["a_file.py", "B_file.sql", "C_file.sql"]
        assert file_names == expected_order

    def test_get_patch_structure_unicode_filenames(self, patch_manager):
        """Test handling unicode filenames."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create patch with unicode filenames
        patch_path = patches_dir / "456-unicode"
        patch_path.mkdir()
        (patch_path / "测试.sql").write_text("-- Chinese filename")
        (patch_path / "café.py").write_text("# French accent")
        (patch_path / "файл.txt").write_text("# Russian filename")

        structure = patch_mgr.get_patch_structure("456-unicode")

        # Should handle unicode filenames correctly
        assert structure.is_valid is True
        assert len(structure.files) == 3

        # Files should be sorted (unicode sorting behavior may vary)
        file_names = [f.name for f in structure.files]
        assert "测试.sql" in file_names
        assert "café.py" in file_names
        assert "файл.txt" in file_names

    def test_get_patch_structure_return_type(self, patch_manager):
        """Test that get_patch_structure returns PatchStructure object."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create simple patch
        patch_path = patches_dir / "456-type-test"
        patch_path.mkdir()

        result = patch_mgr.get_patch_structure("456-type-test")

        # Should return PatchStructure object
        assert isinstance(result, PatchStructure)
        assert hasattr(result, 'patch_id')
        assert hasattr(result, 'directory_path')
        assert hasattr(result, 'readme_path')
        assert hasattr(result, 'files')
        assert hasattr(result, 'is_valid')
        assert hasattr(result, 'validation_errors')

        # Check types
        assert isinstance(result.files, list)
        assert isinstance(result.is_valid, bool)
        assert isinstance(result.validation_errors, list)