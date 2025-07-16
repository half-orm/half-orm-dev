#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Comprehensive Tests for PatchDirectory Module

Test-Driven Development for PatchDirectory - all tests should FAIL initially
since methods are not implemented (only pass statements).

Coverage:
- PatchFile dataclass (5 test methods)
- PatchDirectory core functionality (25+ test methods)  
- Edge cases, error conditions, and integration scenarios
- Real filesystem operations with temporary directories
- Mock halfORM integration for database operations

Run with: pytest test_patch_directory.py -v
"""

import os
import tempfile
import shutil
import ast
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from dataclasses import FrozenInstanceError
import pytest

# Import the classes we're testing
from half_orm_dev.schema_patches.patch_directory import PatchDirectory, PatchFile
from half_orm_dev.schema_patches.exceptions import (
    PatchValidationError, 
    SchemaPatchesError
)


@pytest.fixture
def temp_schema_patches_dir():
    """Create temporary SchemaPatches directory structure"""
    temp_dir = tempfile.mkdtemp()
    schema_patches_dir = os.path.join(temp_dir, 'SchemaPatches')
    os.makedirs(schema_patches_dir)
    
    yield temp_dir, schema_patches_dir
    
    shutil.rmtree(temp_dir)


@pytest.fixture
def mock_hgit():
    """Create mock HGit instance with necessary attributes"""
    mock_hgit = Mock()
    mock_hgit._HGit__repo = Mock()
    mock_hgit._HGit__repo.base_dir = "/fake/repo"
    mock_hgit._HGit__git_repo = Mock()
    
    # Mock halfORM model
    mock_model = Mock()
    mock_model.execute_query = Mock(return_value={"affected_rows": 0})
    mock_hgit._HGit__repo.model = mock_model
    
    return mock_hgit


@pytest.fixture
def sample_patch_directory(temp_schema_patches_dir, mock_hgit):
    """Create sample patch directory with test files"""
    temp_dir, schema_patches_dir = temp_schema_patches_dir
    
    # Create patch directory
    patch_dir = os.path.join(schema_patches_dir, '456-performance')
    os.makedirs(patch_dir)
    
    # Create sample files
    test_files = {
        '00_prerequisites.sql': 'CREATE EXTENSION IF NOT EXISTS pg_stat_statements;',
        '01_create_indexes.sql': 'CREATE INDEX idx_users_email ON users(email);',
        '02_populate_cache.py': 'print("Populating cache...")\n# Cache population logic',
        '03_analyze_tables.sql': 'ANALYZE users; ANALYZE orders;',
        'README.md': '# Performance improvements patch'
    }
    
    for filename, content in test_files.items():
        file_path = os.path.join(patch_dir, filename)
        with open(file_path, 'w') as f:
            f.write(content)
    
    # Update mock to use real temp directory
    mock_hgit._HGit__repo.base_dir = temp_dir
    
    return PatchDirectory('456-performance', mock_hgit, Path(temp_dir))


class TestPatchFile:
    """Test suite for PatchFile dataclass"""
    
    def test_patch_file_creation_sql(self):
        """Should create PatchFile for SQL file"""
        patch_file = PatchFile(
            name="01_create_table.sql",
            path=Path("/fake/path/01_create_table.sql"),
            extension="sql",
            sequence=1
        )
        
        assert patch_file.name == "01_create_table.sql"
        assert patch_file.path == Path("/fake/path/01_create_table.sql")
        assert patch_file.extension == "sql"
        assert patch_file.sequence == 1
        assert patch_file.content is None
    
    def test_patch_file_creation_python(self):
        """Should create PatchFile for Python file"""
        patch_file = PatchFile(
            name="02_migration.py",
            path=Path("/fake/path/02_migration.py"),
            extension="py",
            sequence=2
        )
        
        assert patch_file.name == "02_migration.py"
        assert patch_file.extension == "py"
        assert patch_file.sequence == 2
    
    def test_patch_file_load_content(self, temp_schema_patches_dir):
        """Should load file content from disk"""
        temp_dir, schema_patches_dir = temp_schema_patches_dir
        
        # Create test file
        test_content = "SELECT * FROM users;"
        test_file = os.path.join(schema_patches_dir, "test.sql")
        with open(test_file, 'w') as f:
            f.write(test_content)
        
        patch_file = PatchFile(
            name="test.sql",
            path=Path(test_file),
            extension="sql",
            sequence=1
        )
        
        content = patch_file.load_content()
        assert content == test_content
    
    def test_patch_file_load_content_file_not_found(self):
        """Should raise PatchValidationError when file doesn't exist"""
        patch_file = PatchFile(
            name="nonexistent.sql",
            path=Path("/nonexistent/path.sql"),
            extension="sql",
            sequence=1
        )
        
        with pytest.raises(PatchValidationError):
            patch_file.load_content()
    
    def test_patch_file_validate_syntax_sql(self):
        """Should validate SQL syntax"""
        patch_file = PatchFile(
            name="valid.sql",
            path=Path("/fake/path"),
            extension="sql",
            sequence=1,
            content="CREATE TABLE users (id SERIAL PRIMARY KEY);"
        )
        
        is_valid = patch_file.validate_syntax()
        assert is_valid is True
    
    def test_patch_file_validate_syntax_python(self):
        """Should validate Python syntax"""
        patch_file = PatchFile(
            name="valid.py",
            path=Path("/fake/path"),
            extension="py",
            sequence=1,
            content="print('Hello world')\nx = 1 + 2"
        )
        
        is_valid = patch_file.validate_syntax()
        assert is_valid is True
    
    def test_patch_file_validate_syntax_invalid_sql(self):
        """Should detect invalid SQL syntax"""
        patch_file = PatchFile(
            name="invalid.sql",
            path=Path("/fake/path"),
            extension="sql",
            sequence=1,
            content="INVALID SQL SYNTAX CREATE TABLE"
        )
        
        with pytest.raises(PatchValidationError):
            patch_file.validate_syntax()
    
    def test_patch_file_validate_syntax_invalid_python(self):
        """Should detect invalid Python syntax"""
        patch_file = PatchFile(
            name="invalid.py",
            path=Path("/fake/path"),
            extension="py",
            sequence=1,
            content="print('unclosed string"
        )
        
        with pytest.raises(PatchValidationError):
            patch_file.validate_syntax()
    
    def test_patch_file_comparison_sorting(self):
        """Should enable sorting by sequence number"""
        file1 = PatchFile("01_first.sql", Path("/fake"), "sql", 1)
        file2 = PatchFile("02_second.sql", Path("/fake"), "sql", 2)
        file3 = PatchFile("00_zeroth.sql", Path("/fake"), "sql", 0)
        
        files = [file2, file1, file3]
        sorted_files = sorted(files)
        
        assert sorted_files[0].sequence == 0
        assert sorted_files[1].sequence == 1
        assert sorted_files[2].sequence == 2


class TestPatchDirectoryInitialization:
    """Test PatchDirectory initialization and basic properties"""
    
    def test_patch_directory_init_valid(self, mock_hgit):
        """Should initialize PatchDirectory with valid parameters"""
        patch_dir = PatchDirectory("456-performance", mock_hgit)
        
        assert patch_dir is not None
        # These assertions will fail until __init__ is implemented
        assert hasattr(patch_dir, '_patch_id')
        assert hasattr(patch_dir, '_hgit_instance')
    
    def test_patch_directory_init_invalid_patch_id(self, mock_hgit):
        """Should raise PatchValidationError for invalid patch_id"""
        with pytest.raises(PatchValidationError):
            PatchDirectory("", mock_hgit)  # Empty patch_id
        
        with pytest.raises(PatchValidationError):
            PatchDirectory("invalid format with spaces", mock_hgit)
        
        with pytest.raises(PatchValidationError):
            PatchDirectory("../path-traversal", mock_hgit)
    
    def test_patch_directory_init_invalid_hgit(self):
        """Should raise SchemaPatchesError for invalid hgit_instance"""
        with pytest.raises(SchemaPatchesError):
            PatchDirectory("456-performance", None)
        
        with pytest.raises(SchemaPatchesError):
            PatchDirectory("456-performance", "not-an-hgit-instance")
    
    def test_patch_directory_init_custom_base_dir(self, mock_hgit):
        """Should accept custom base directory"""
        custom_base = Path("/custom/base/dir")
        patch_dir = PatchDirectory("456-performance", mock_hgit, custom_base)
        
        # This will fail until base_dir handling is implemented
        assert patch_dir._base_dir == custom_base


class TestPatchDirectoryValidation:
    """Test patch directory structure validation"""
    
    def test_validate_structure_valid_directory(self, sample_patch_directory):
        """Should validate directory with proper SQL/Python files"""
        is_valid = sample_patch_directory.validate_structure()
        assert is_valid is True
    
    def test_validate_structure_empty_directory(self, temp_schema_patches_dir, mock_hgit):
        """Should reject empty directory"""
        temp_dir, schema_patches_dir = temp_schema_patches_dir
        
        # Create empty patch directory
        patch_dir_path = os.path.join(schema_patches_dir, '999-empty')
        os.makedirs(patch_dir_path)
        
        mock_hgit._HGit__repo.base_dir = temp_dir
        patch_dir = PatchDirectory('999-empty', mock_hgit, Path(temp_dir))
        
        with pytest.raises(PatchValidationError, match="no applicable files"):
            patch_dir.validate_structure()
    
    def test_validate_structure_directory_not_exist(self, temp_schema_patches_dir, mock_hgit):
        """Should raise error when directory doesn't exist"""
        temp_dir, schema_patches_dir = temp_schema_patches_dir
        mock_hgit._HGit__repo.base_dir = temp_dir
        
        patch_dir = PatchDirectory('999-nonexistent', mock_hgit, Path(temp_dir))
        
        with pytest.raises(PatchValidationError, match="does not exist"):
            patch_dir.validate_structure()
    
    def test_validate_structure_invalid_file_names(self, temp_schema_patches_dir, mock_hgit):
        """Should reject files with invalid naming convention"""
        temp_dir, schema_patches_dir = temp_schema_patches_dir
        
        # Create patch directory with invalid file names
        patch_dir_path = os.path.join(schema_patches_dir, '999-invalid')
        os.makedirs(patch_dir_path)
        
        # Invalid file names (missing sequence prefix)
        invalid_files = {
            'create_table.sql': 'CREATE TABLE test();',
            'migration.py': 'print("test")',
            'no_extension': 'content'
        }
        
        for filename, content in invalid_files.items():
            file_path = os.path.join(patch_dir_path, filename)
            with open(file_path, 'w') as f:
                f.write(content)
        
        mock_hgit._HGit__repo.base_dir = temp_dir
        patch_dir = PatchDirectory('999-invalid', mock_hgit, Path(temp_dir))
        
        with pytest.raises(PatchValidationError, match="naming convention"):
            patch_dir.validate_structure()
    
    def test_validate_structure_duplicate_sequence_numbers(self, temp_schema_patches_dir, mock_hgit):
        """Should reject duplicate sequence numbers"""
        temp_dir, schema_patches_dir = temp_schema_patches_dir
        
        # Create patch directory with duplicate sequences
        patch_dir_path = os.path.join(schema_patches_dir, '999-duplicate')
        os.makedirs(patch_dir_path)
        
        duplicate_files = {
            '01_first.sql': 'CREATE TABLE first();',
            '01_second.sql': 'CREATE TABLE second();'  # Duplicate sequence 01
        }
        
        for filename, content in duplicate_files.items():
            file_path = os.path.join(patch_dir_path, filename)
            with open(file_path, 'w') as f:
                f.write(content)
        
        mock_hgit._HGit__repo.base_dir = temp_dir
        patch_dir = PatchDirectory('999-duplicate', mock_hgit, Path(temp_dir))
        
        with pytest.raises(PatchValidationError, match="duplicate sequence"):
            patch_dir.validate_structure()


class TestPatchDirectoryFileScanning:
    """Test file discovery and parsing functionality"""
    
    def test_scan_files_success(self, sample_patch_directory):
        """Should discover and parse all patch files"""
        files = sample_patch_directory.scan_files()
        
        # Should find 4 patch files (3 SQL + 1 Python, ignore README.md)
        assert len(files) == 4
        
        # Verify file types
        sql_files = [f for f in files if f.extension == 'sql']
        py_files = [f for f in files if f.extension == 'py']
        
        assert len(sql_files) == 3
        assert len(py_files) == 1
    
    def test_scan_files_empty_directory(self, temp_schema_patches_dir, mock_hgit):
        """Should return empty list for directory with no patch files"""
        temp_dir, schema_patches_dir = temp_schema_patches_dir
        
        # Create directory with only non-patch files
        patch_dir_path = os.path.join(schema_patches_dir, '999-empty')
        os.makedirs(patch_dir_path)
        
        # Add non-patch files
        non_patch_files = ['README.md', 'notes.txt', '.hidden_file']
        for filename in non_patch_files:
            file_path = os.path.join(patch_dir_path, filename)
            with open(file_path, 'w') as f:
                f.write('content')
        
        mock_hgit._HGit__repo.base_dir = temp_dir
        patch_dir = PatchDirectory('999-empty', mock_hgit, Path(temp_dir))
        
        files = patch_dir.scan_files()
        assert len(files) == 0
    
    def test_get_execution_order(self, sample_patch_directory):
        """Should return files in correct execution order"""
        files = sample_patch_directory.get_execution_order()
        
        # Verify chronological order by sequence
        sequences = [f.sequence for f in files]
        assert sequences == sorted(sequences)
        
        # Verify specific order
        expected_names = [
            '00_prerequisites.sql',
            '01_create_indexes.sql', 
            '02_populate_cache.py',
            '03_analyze_tables.sql'
        ]
        actual_names = [f.name for f in files]
        assert actual_names == expected_names
    
    def test_get_execution_order_mixed_sequences(self, temp_schema_patches_dir, mock_hgit):
        """Should handle mixed and out-of-order sequence numbers"""
        temp_dir, schema_patches_dir = temp_schema_patches_dir
        
        patch_dir_path = os.path.join(schema_patches_dir, '999-mixed')
        os.makedirs(patch_dir_path)
        
        # Create files with mixed sequences
        mixed_files = {
            '05_last.sql': 'SELECT 5;',
            '01_first.sql': 'SELECT 1;',
            '03_middle.sql': 'SELECT 3;',
            '02_second.py': 'print(2)'
        }
        
        for filename, content in mixed_files.items():
            file_path = os.path.join(patch_dir_path, filename)
            with open(file_path, 'w') as f:
                f.write(content)
        
        mock_hgit._HGit__repo.base_dir = temp_dir
        patch_dir = PatchDirectory('999-mixed', mock_hgit, Path(temp_dir))
        
        files = patch_dir.get_execution_order()
        sequences = [f.sequence for f in files]
        
        assert sequences == [1, 2, 3, 5]  # Sorted order


class TestPatchDirectoryApplicability:
    """Test patch applicability checks"""
    
    def test_is_applicable_valid_state(self, sample_patch_directory):
        """Should return True when patch can be applied"""
        is_applicable = sample_patch_directory.is_applicable()
        assert is_applicable is True
    
    def test_is_applicable_no_database_connection(self, temp_schema_patches_dir, mock_hgit):
        """Should return False when database connection unavailable"""
        # Mock database connection failure
        mock_hgit._HGit__repo.model.execute_query.side_effect = Exception("Connection failed")
        
        temp_dir, _ = temp_schema_patches_dir
        mock_hgit._HGit__repo.base_dir = temp_dir
        
        patch_dir = PatchDirectory('456-performance', mock_hgit, Path(temp_dir))
        
        is_applicable = patch_dir.is_applicable()
        assert is_applicable is False
    
    def test_is_applicable_missing_dependencies(self, sample_patch_directory):
        """Should return False when dependencies not satisfied"""
        # Mock dependency check to return missing dependencies
        with patch.object(sample_patch_directory, 'get_dependencies', return_value=['missing-dependency']):
            is_applicable = sample_patch_directory.is_applicable()
            assert is_applicable is False


class TestPatchDirectoryExecution:
    """Test patch file execution functionality"""
    
    def test_apply_all_files_success(self, sample_patch_directory):
        """Should successfully apply all patch files"""
        result = sample_patch_directory.apply_all_files()
        
        assert result['success'] is True
        assert result['files_applied'] == 4  # 3 SQL + 1 Python
        assert 'execution_time' in result
        assert result['execution_time'] > 0
    
    def test_apply_all_files_with_sql_error(self, sample_patch_directory):
        """Should handle SQL execution errors with rollback"""
        # Mock SQL execution to fail
        mock_model = sample_patch_directory._hgit_instance._HGit__repo.model
        mock_model.execute_query.side_effect = Exception("SQL error")
        
        with pytest.raises(SchemaPatchesError, match="SQL error"):
            sample_patch_directory.apply_all_files()
    
    def test_apply_all_files_with_python_error(self, sample_patch_directory):
        """Should handle Python execution errors with rollback"""
        # Mock subprocess to fail for Python files
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = Exception("Python execution failed")
            
            with pytest.raises(SchemaPatchesError, match="Python execution failed"):
                sample_patch_directory.apply_all_files()
    
    def test_apply_single_file_sql(self, sample_patch_directory):
        """Should execute single SQL file successfully"""
        sql_file = PatchFile(
            "01_test.sql",
            Path("/fake/path"),
            "sql",
            1,
            "CREATE TABLE test (id INT);"
        )
        
        result = sample_patch_directory.apply_single_file(sql_file)
        
        assert result['success'] is True
        assert 'affected_rows' in result
        assert 'execution_time' in result
    
    def test_apply_single_file_python(self, sample_patch_directory):
        """Should execute single Python file successfully"""
        python_file = PatchFile(
            "02_test.py",
            Path("/fake/path"),
            "py",
            2,
            "print('Hello from patch')"
        )
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "Hello from patch"
            
            result = sample_patch_directory.apply_single_file(python_file)
            
            assert result['success'] is True
            assert result['return_code'] == 0
    
    def test_execute_sql_file_success(self, sample_patch_directory):
        """Should execute SQL file using halfORM model"""
        sql_file = PatchFile(
            "test.sql",
            Path("/fake/path"),
            "sql",
            1,
            "CREATE INDEX test_idx ON users(email);"
        )
        
        result = sample_patch_directory.execute_sql_file(sql_file)
        
        assert result['success'] is True
        assert 'affected_rows' in result
        assert 'execution_time' in result
    
    def test_execute_sql_file_with_error(self, sample_patch_directory):
        """Should handle SQL execution errors"""
        sql_file = PatchFile(
            "bad.sql",
            Path("/fake/path"),
            "sql",
            1,
            "INVALID SQL SYNTAX"
        )
        
        # Mock SQL execution failure
        mock_model = sample_patch_directory._hgit_instance._HGit__repo.model
        mock_model.execute_query.side_effect = Exception("SQL syntax error")
        
        with pytest.raises(SchemaPatchesError, match="SQL syntax error"):
            sample_patch_directory.execute_sql_file(sql_file)
    
    def test_execute_python_file_success(self, sample_patch_directory):
        """Should execute Python file using subprocess"""
        python_file = PatchFile(
            "test.py",
            Path("/fake/path"),
            "py",
            1,
            "print('Test execution')"
        )
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "Test execution"
            mock_run.return_value.stderr = ""
            
            result = sample_patch_directory.execute_python_file(python_file)
            
            assert result['success'] is True
            assert result['return_code'] == 0
            assert result['stdout'] == "Test execution"
    
    def test_execute_python_file_with_error(self, sample_patch_directory):
        """Should handle Python execution errors"""
        python_file = PatchFile(
            "bad.py",
            Path("/fake/path"),
            "py",
            1,
            "raise Exception('Test error')"
        )
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 1
            mock_run.return_value.stderr = "Exception: Test error"
            
            with pytest.raises(SchemaPatchesError, match="Test error"):
                sample_patch_directory.execute_python_file(python_file)


class TestPatchDirectorySyntaxValidation:
    """Test syntax validation for SQL and Python files"""
    
    def test_validate_sql_syntax_valid(self, sample_patch_directory):
        """Should validate correct SQL syntax"""
        valid_sql = """
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT NOW()
        );
        """
        
        is_valid = sample_patch_directory.validate_sql_syntax(valid_sql)
        assert is_valid is True
    
    def test_validate_sql_syntax_invalid(self, sample_patch_directory):
        """Should detect invalid SQL syntax"""
        invalid_sql = "CREATE TABLE INVALID SYNTAX WITHOUT PROPER"
        
        with pytest.raises(PatchValidationError, match="SQL syntax"):
            sample_patch_directory.validate_sql_syntax(invalid_sql)
    
    def test_validate_python_syntax_valid(self, sample_patch_directory):
        """Should validate correct Python syntax"""
        valid_python = """
def migrate_data():
    print("Starting migration")
    for i in range(10):
        print(f"Processing item {i}")
    return True

if __name__ == "__main__":
    migrate_data()
        """
        
        is_valid = sample_patch_directory.validate_python_syntax(valid_python)
        assert is_valid is True
    
    def test_validate_python_syntax_invalid(self, sample_patch_directory):
        """Should detect invalid Python syntax"""
        invalid_python = """
def invalid_function(
    print("unclosed parenthesis"
    return True
        """
        
        with pytest.raises(PatchValidationError, match="Python syntax"):
            sample_patch_directory.validate_python_syntax(invalid_python)


class TestPatchDirectoryDependencies:
    """Test dependency management"""
    
    def test_get_dependencies_from_comments(self, temp_schema_patches_dir, mock_hgit):
        """Should extract dependencies from file comments"""
        temp_dir, schema_patches_dir = temp_schema_patches_dir
        
        patch_dir_path = os.path.join(schema_patches_dir, '456-deps')
        os.makedirs(patch_dir_path)
        
        # Create file with dependency comments
        sql_with_deps = """
        -- DEPENDS: 123-security, 234-users
        -- REQUIRES: users_table, security_roles
        CREATE INDEX idx_secure_users ON users(email) WHERE active = true;
        """
        
        sql_file = os.path.join(patch_dir_path, '01_secure_index.sql')
        with open(sql_file, 'w') as f:
            f.write(sql_with_deps)
        
        mock_hgit._HGit__repo.base_dir = temp_dir
        patch_dir = PatchDirectory('456-deps', mock_hgit, Path(temp_dir))
        
        dependencies = patch_dir.get_dependencies()
        
        expected_deps = ['123-security', '234-users', 'users_table', 'security_roles']
        assert all(dep in dependencies for dep in expected_deps)
    
    def test_get_dependencies_empty(self, sample_patch_directory):
        """Should return empty list when no dependencies"""
        dependencies = sample_patch_directory.get_dependencies()
        assert isinstance(dependencies, list)
        assert len(dependencies) == 0


class TestPatchDirectoryRollback:
    """Test rollback functionality"""
    
    def test_create_rollback_point(self, sample_patch_directory):
        """Should create database rollback point"""
        rollback_id = sample_patch_directory.create_rollback_point()
        
        assert rollback_id is not None
        assert isinstance(rollback_id, str)
        assert len(rollback_id) > 0
    
    def test_rollback_to_point_success(self, sample_patch_directory):
        """Should rollback to specified point successfully"""
        rollback_id = sample_patch_directory.create_rollback_point()
        
        success = sample_patch_directory.rollback_to_point(rollback_id)
        assert success is True
    
    def test_rollback_to_point_invalid_id(self, sample_patch_directory):
        """Should handle invalid rollback point ID"""
        with pytest.raises(SchemaPatchesError, match="Invalid rollback point"):
            sample_patch_directory.rollback_to_point("invalid-id")
    
    def test_rollback_all_success(self, sample_patch_directory):
        """Should perform complete rollback successfully"""
        success = sample_patch_directory.rollback_all()
        assert success is True
    
    def test_rollback_all_failure(self, sample_patch_directory):
        """Should handle rollback failures"""
        # Mock rollback to fail
        with patch.object(sample_patch_directory, 'rollback_to_point', side_effect=Exception("Rollback failed")):
            with pytest.raises(SchemaPatchesError, match="Rollback failed"):
                sample_patch_directory.rollback_all()


class TestPatchDirectoryInformation:
    """Test information and metadata methods"""
    
    def test_get_patch_info(self, sample_patch_directory):
        """Should return comprehensive patch information"""
        info = sample_patch_directory.get_patch_info()
        
        assert info['patch_id'] == '456-performance'
        assert info['file_count'] == 4  # 3 SQL + 1 Python
        assert info['sql_files'] == 3
        assert info['python_files'] == 1
        assert 'total_size' in info
        assert info['total_size'] > 0
    
    def test_get_execution_summary_not_executed(self, sample_patch_directory):
        """Should return empty summary when not executed"""
        summary = sample_patch_directory.get_execution_summary()
        
        assert summary['files_executed'] == 0
        assert summary['total_time'] == 0
        assert summary['success_rate'] == 0.0
    
    def test_get_execution_summary_after_execution(self, sample_patch_directory):
        """Should return summary after execution"""
        # Execute patches first
        sample_patch_directory.apply_all_files()
        
        summary = sample_patch_directory.get_execution_summary()
        
        assert summary['files_executed'] == 4
        assert summary['total_time'] > 0
        assert summary['success_rate'] == 100.0


class TestPatchDirectoryResourceManagement:
    """Test resource cleanup and management"""
    
    def test_cleanup_resources(self, sample_patch_directory):
        """Should clean up resources without errors"""
        # Should not raise any exceptions
        sample_patch_directory.cleanup_resources()
        
        # Verify cleanup was performed (implementation specific)
        # This will need to be tested based on actual implementation
    
    def test_cleanup_resources_after_error(self, sample_patch_directory):
        """Should clean up resources even after execution errors"""
        # Mock execution to fail
        with patch.object(sample_patch_directory, 'apply_all_files', side_effect=Exception("Test error")):
            try:
                sample_patch_directory.apply_all_files()
            except:
                pass  # Expected to fail
        
        # Cleanup should still work
        sample_patch_directory.cleanup_resources()


class TestPatchDirectoryStringRepresentation:
    """Test string representation methods"""
    
    def test_str_representation(self, sample_patch_directory):
        """Should provide readable string representation"""
        str_repr = str(sample_patch_directory)
        
        assert "PatchDirectory" in str_repr
        assert "456-performance" in str_repr
        assert "files" in str_repr
    
    def test_repr_representation(self, sample_patch_directory):
        """Should provide detailed representation for debugging"""
        repr_str = repr(sample_patch_directory)
        
        assert "PatchDirectory" in repr_str
        assert "456-performance" in repr_str
        # Should contain more detail than __str__
        assert len(repr_str) >= len(str(sample_patch_directory))


class TestPatchDirectoryPrivateHelpers:
    """Test private helper methods"""
    
    def test_extract_sequence_number_valid(self, sample_patch_directory):
        """Should extract sequence number from valid filenames"""
        test_cases = [
            ("00_prerequisites.sql", 0),
            ("01_create_table.sql", 1),
            ("10_final_step.py", 10),
            ("99_cleanup.sql", 99)
        ]
        
        for filename, expected_sequence in test_cases:
            sequence = sample_patch_directory._extract_sequence_number(filename)
            assert sequence == expected_sequence
    
    def test_extract_sequence_number_invalid(self, sample_patch_directory):
        """Should raise error for invalid filename formats"""
        invalid_filenames = [
            "no_prefix.sql",
            "create_table.sql", 
            "1_missing_zero.sql",
            "_missing_number.sql",
            "abc_not_number.sql"
        ]
        
        for filename in invalid_filenames:
            with pytest.raises(PatchValidationError):
                sample_patch_directory._extract_sequence_number(filename)
    
    def test_validate_filename_format_valid(self, sample_patch_directory):
        """Should validate correct filename formats"""
        valid_filenames = [
            "00_prerequisites.sql",
            "01_create_tables.sql",
            "02_populate_data.py",
            "10_final_migration.sql",
            "99_cleanup_temp_tables.py"
        ]
        
        for filename in valid_filenames:
            is_valid = sample_patch_directory._validate_filename_format(filename)
            assert is_valid is True
    
    def test_validate_filename_format_invalid(self, sample_patch_directory):
        """Should reject incorrect filename formats"""
        invalid_filenames = [
            "create_table.sql",  # No sequence prefix
            "1_missing_zero.sql",  # Single digit sequence
            "abc_not_number.sql",  # Non-numeric prefix
            "01_test.txt",  # Wrong extension
            "01_.sql",  # Missing description
            "_01_reverse.sql"  # Wrong order
        ]
        
        for filename in invalid_filenames:
            is_valid = sample_patch_directory._validate_filename_format(filename)
            assert is_valid is False
    
    def test_setup_python_environment(self, sample_patch_directory):
        """Should setup proper Python execution environment"""
        env = sample_patch_directory._setup_python_environment()
        
        assert isinstance(env, dict)
        assert 'PYTHONPATH' in env
        # Should include repository base directory in PYTHONPATH
        assert sample_patch_directory._hgit_instance._HGit__repo.base_dir in env['PYTHONPATH']
    
    def test_parse_sql_statements_single(self, sample_patch_directory):
        """Should parse single SQL statement"""
        sql_content = "CREATE TABLE users (id SERIAL PRIMARY KEY);"
        
        statements = sample_patch_directory._parse_sql_statements(sql_content)
        
        assert len(statements) == 1
        assert statements[0].strip() == "CREATE TABLE users (id SERIAL PRIMARY KEY)"
    
    def test_parse_sql_statements_multiple(self, sample_patch_directory):
        """Should parse multiple SQL statements"""
        sql_content = """
        CREATE TABLE users (id SERIAL PRIMARY KEY);
        INSERT INTO users (id) VALUES (1);
        CREATE INDEX idx_users_id ON users(id);
        """
        
        statements = sample_patch_directory._parse_sql_statements(sql_content)
        
        assert len(statements) == 3
        assert "CREATE TABLE" in statements[0]
        assert "INSERT INTO" in statements[1] 
        assert "CREATE INDEX" in statements[2]
    
    def test_parse_sql_statements_with_comments(self, sample_patch_directory):
        """Should handle SQL comments properly"""
        sql_content = """
        -- This creates the users table
        CREATE TABLE users (id SERIAL PRIMARY KEY);
        /* Multi-line comment
           with additional info */
        INSERT INTO users (id) VALUES (1);
        """
        
        statements = sample_patch_directory._parse_sql_statements(sql_content)
        
        # Should have 2 executable statements (excluding comments)
        assert len(statements) == 2


class TestPatchDirectoryEdgeCases:
    """Test edge cases and error conditions"""
    
    def test_large_patch_directory(self, temp_schema_patches_dir, mock_hgit):
        """Should handle directory with many files"""
        temp_dir, schema_patches_dir = temp_schema_patches_dir
        
        # Create patch directory with many files
        patch_dir_path = os.path.join(schema_patches_dir, '999-large')
        os.makedirs(patch_dir_path)
        
        # Create 50 files
        for i in range(50):
            filename = f"{i:02d}_step_{i}.sql"
            file_path = os.path.join(patch_dir_path, filename)
            with open(file_path, 'w') as f:
                f.write(f"SELECT {i};")
        
        mock_hgit._HGit__repo.base_dir = temp_dir
        patch_dir = PatchDirectory('999-large', mock_hgit, Path(temp_dir))
        
        files = patch_dir.scan_files()
        assert len(files) == 50
        
        # Verify they're in correct order
        sequences = [f.sequence for f in patch_dir.get_execution_order()]
        assert sequences == list(range(50))
    
    def test_patch_directory_permissions(self, temp_schema_patches_dir, mock_hgit):
        """Should handle permission errors gracefully"""
        temp_dir, schema_patches_dir = temp_schema_patches_dir
        
        # Create patch directory
        patch_dir_path = os.path.join(schema_patches_dir, '999-perms')
        os.makedirs(patch_dir_path)
        
        # Create file and remove read permissions
        file_path = os.path.join(patch_dir_path, '01_test.sql')
        with open(file_path, 'w') as f:
            f.write("SELECT 1;")
        
        # Remove read permissions
        os.chmod(file_path, 0o000)
        
        try:
            mock_hgit._HGit__repo.base_dir = temp_dir
            patch_dir = PatchDirectory('999-perms', mock_hgit, Path(temp_dir))
            
            with pytest.raises(PatchValidationError, match="permission"):
                patch_dir.validate_structure()
        
        finally:
            # Restore permissions for cleanup
            os.chmod(file_path, 0o644)
    
    def test_patch_directory_concurrent_access(self, sample_patch_directory):
        """Should handle concurrent access attempts"""
        # This test would need threading for real concurrency testing
        # For now, test that multiple operations don't interfere
        
        info1 = sample_patch_directory.get_patch_info()
        files1 = sample_patch_directory.scan_files()
        info2 = sample_patch_directory.get_patch_info()
        files2 = sample_patch_directory.scan_files()
        
        # Results should be consistent
        assert info1 == info2
        assert len(files1) == len(files2)
    
    def test_patch_directory_unicode_filenames(self, temp_schema_patches_dir, mock_hgit):
        """Should handle Unicode characters in filenames properly"""
        temp_dir, schema_patches_dir = temp_schema_patches_dir
        
        patch_dir_path = os.path.join(schema_patches_dir, '999-unicode')
        os.makedirs(patch_dir_path)
        
        # Create files with Unicode characters
        unicode_files = {
            '01_测试_test.sql': 'SELECT 1;',
            '02_émigration.py': 'print("migration")',
            '03_файл.sql': 'SELECT 3;'
        }
        
        for filename, content in unicode_files.items():
            file_path = os.path.join(patch_dir_path, filename)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
        
        mock_hgit._HGit__repo.base_dir = temp_dir
        patch_dir = PatchDirectory('999-unicode', mock_hgit, Path(temp_dir))
        
        files = patch_dir.scan_files()
        assert len(files) == 3
        
        # Verify Unicode names are preserved
        filenames = [f.name for f in files]
        assert '01_测试_test.sql' in filenames
        assert '02_émigration.py' in filenames
        assert '03_файл.sql' in filenames


class TestPatchDirectoryIntegration:
    """Integration tests with GitTagManager and halfORM"""
    
    def test_integration_with_git_tag_manager(self, sample_patch_directory):
        """Should integrate properly with GitTagManager workflow"""
        # Mock GitTagManager creating a tag
        patch_tag = Mock()
        patch_tag.message = "456-performance"
        patch_tag.name = "dev-patch-1.3.2-performance"
        
        # PatchDirectory should be able to use the tag message
        assert sample_patch_directory._patch_id == "456-performance"
        
        # Should validate the referenced directory exists
        is_valid = sample_patch_directory.validate_structure()
        assert is_valid is True
    
    def test_integration_with_halfORM_model(self, sample_patch_directory):
        """Should integrate properly with halfORM model"""
        # Mock halfORM model interactions
        mock_model = sample_patch_directory._hgit_instance._HGit__repo.model
        
        # Should be able to execute SQL through the model
        sql_file = PatchFile(
            "test.sql",
            Path("/fake"),
            "sql", 
            1,
            "CREATE TABLE integration_test (id INT);"
        )
        
        result = sample_patch_directory.execute_sql_file(sql_file)
        
        # Verify model was called
        mock_model.execute_query.assert_called()
        assert result['success'] is True
    
    def test_full_workflow_simulation(self, sample_patch_directory):
        """Should complete full patch application workflow"""
        # Simulate complete workflow:
        # 1. Validate structure
        # 2. Check applicability
        # 3. Create rollback point
        # 4. Apply all files
        # 5. Get execution summary
        # 6. Clean up resources
        
        # Step 1: Validate
        is_valid = sample_patch_directory.validate_structure()
        assert is_valid is True
        
        # Step 2: Check applicability
        is_applicable = sample_patch_directory.is_applicable()
        assert is_applicable is True
        
        # Step 3: Create rollback point
        rollback_id = sample_patch_directory.create_rollback_point()
        assert rollback_id is not None
        
        # Step 4: Apply files
        result = sample_patch_directory.apply_all_files()
        assert result['success'] is True
        
        # Step 5: Get summary
        summary = sample_patch_directory.get_execution_summary()
        assert summary['files_executed'] > 0
        
        # Step 6: Cleanup
        sample_patch_directory.cleanup_resources()


class TestPatchDirectoryPerformance:
    """Performance and scalability tests"""
    
    def test_performance_many_small_files(self, temp_schema_patches_dir, mock_hgit):
        """Should handle many small files efficiently"""
        temp_dir, schema_patches_dir = temp_schema_patches_dir
        
        patch_dir_path = os.path.join(schema_patches_dir, '999-perf')
        os.makedirs(patch_dir_path)
        
        # Create 100 small files
        for i in range(100):
            filename = f"{i:02d}_small_operation_{i}.sql"
            file_path = os.path.join(patch_dir_path, filename)
            with open(file_path, 'w') as f:
                f.write(f"INSERT INTO test_table VALUES ({i});")
        
        mock_hgit._HGit__repo.base_dir = temp_dir
        patch_dir = PatchDirectory('999-perf', mock_hgit, Path(temp_dir))
        
        # Operations should complete in reasonable time
        import time
        
        start_time = time.time()
        files = patch_dir.scan_files()
        scan_time = time.time() - start_time
        
        start_time = time.time()
        ordered_files = patch_dir.get_execution_order()
        order_time = time.time() - start_time
        
        # Should process 100 files quickly
        assert len(files) == 100
        assert len(ordered_files) == 100
        assert scan_time < 1.0  # Less than 1 second
        assert order_time < 0.5  # Less than 0.5 seconds
    
    def test_memory_usage_large_files(self, temp_schema_patches_dir, mock_hgit):
        """Should handle large files without excessive memory usage"""
        temp_dir, schema_patches_dir = temp_schema_patches_dir
        
        patch_dir_path = os.path.join(schema_patches_dir, '999-large')
        os.makedirs(patch_dir_path)
        
        # Create one large file
        large_content = "SELECT 1;\n" * 10000  # ~100KB file
        file_path = os.path.join(patch_dir_path, '01_large_migration.sql')
        with open(file_path, 'w') as f:
            f.write(large_content)
        
        mock_hgit._HGit__repo.base_dir = temp_dir
        patch_dir = PatchDirectory('999-large', mock_hgit, Path(temp_dir))
        
        # Should scan without loading all content into memory
        files = patch_dir.scan_files()
        assert len(files) == 1
        
        # Content should be loaded on demand
        patch_file = files[0]
        assert patch_file.content is None  # Not loaded yet
        
        content = patch_file.load_content()
        assert len(content) > 90000  # Verify large content was loaded


# Test configuration and utilities
class TestConfiguration:
    """Test configuration and utilities for the test suite"""
    
    def test_temp_directory_cleanup(self, temp_schema_patches_dir):
        """Verify temporary directories are created and cleaned up properly"""
        temp_dir, schema_patches_dir = temp_schema_patches_dir
        
        # Directories should exist during test
        assert os.path.exists(temp_dir)
        assert os.path.exists(schema_patches_dir)
        
        # Test can create files
        test_file = os.path.join(schema_patches_dir, 'test.txt')
        with open(test_file, 'w') as f:
            f.write('test')
        
        assert os.path.exists(test_file)
    
    def test_mock_hgit_configuration(self, mock_hgit):
        """Verify mock HGit instance is properly configured"""
        assert hasattr(mock_hgit, '_HGit__repo')
        assert hasattr(mock_hgit._HGit__repo, 'base_dir')
        assert hasattr(mock_hgit._HGit__repo, 'model')
        
        # Model should have execute_query method
        assert hasattr(mock_hgit._HGit__repo.model, 'execute_query')
        
        # Should be callable
        result = mock_hgit._HGit__repo.model.execute_query("SELECT 1")
        assert 'affected_rows' in result


if __name__ == "__main__":
    # Run tests with verbose output and stop on first failure
    pytest.main([__file__, "-v", "-x", "--tb=short"])
