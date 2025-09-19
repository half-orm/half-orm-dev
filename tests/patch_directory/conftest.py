"""
Fixtures communes pour tous les tests PatchDirectory.

Ce module fournit les fixtures pytest partagées entre tous les modules
de test pour PatchDirectory, incluant la configuration temporaire des 
répertoires et les données de test.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock


@pytest.fixture
def temp_repo():
    """
    Create temporary repository structure for testing.
    
    Creates a temporary directory with SchemaPatches/ subdirectory
    and a mock repository object with required attributes.
    
    Yields:
        tuple: (repo_mock, temp_dir_path, schema_patches_path)
        
    Cleanup:
        Automatically removes temporary directory after test completion
    """
    temp_dir = tempfile.mkdtemp()
    
    # Create basic repo structure
    schema_patches_dir = Path(temp_dir) / "SchemaPatches"
    schema_patches_dir.mkdir()
    
    # Mock repo object with required attributes
    repo = Mock()
    repo.base_dir = temp_dir
    repo.name = "test_db"
    repo.devel = True
    
    yield repo, temp_dir, schema_patches_dir
    
    # Cleanup - remove temporary directory
    shutil.rmtree(temp_dir)


@pytest.fixture
def patch_directory(temp_repo):
    """
    Create PatchDirectory instance with temporary repo.
    
    Provides a ready-to-use PatchDirectory instance for testing
    with all dependencies properly mocked.
    
    Args:
        temp_repo: Fixture providing temporary repository setup
        
    Returns:
        tuple: (patch_directory_instance, repo_mock, temp_dir, schema_patches_dir)
    """
    from half_orm_dev.patch_directory import PatchDirectory
    
    repo, temp_dir, schema_patches_dir = temp_repo
    patch_dir = PatchDirectory(repo)
    
    return patch_dir, repo, temp_dir, schema_patches_dir


@pytest.fixture
def sample_patch_files():
    """
    Sample patch files content for testing.
    
    Provides a dictionary of realistic patch files with different
    types (SQL, Python) and proper naming conventions for testing
    patch directory operations.
    
    Returns:
        dict: Mapping of filename -> file_content for test files
    """
    return {
        "01_create_users.sql": (
            "-- Create users table\n"
            "CREATE TABLE users (\n"
            "    id SERIAL PRIMARY KEY,\n"
            "    name VARCHAR(100) NOT NULL,\n"
            "    email VARCHAR(255) UNIQUE,\n"
            "    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n"
            ");"
        ),
        "02_add_indexes.sql": (
            "-- Add performance indexes\n"
            "CREATE INDEX idx_users_name ON users(name);\n"
            "CREATE INDEX idx_users_email ON users(email);\n"
            "CREATE INDEX idx_users_created_at ON users(created_at);"
        ),
        "03_update_permissions.py": (
            "#!/usr/bin/env python3\n"
            "# Update user permissions\n"
            "print('Updating user permissions...')\n"
            "# Business logic would go here\n"
            "print('Permissions updated successfully')"
        ),
        "04_seed_data.sql": (
            "-- Insert initial data\n"
            "INSERT INTO users (name, email) VALUES\n"
            "    ('Admin User', 'admin@example.com'),\n"
            "    ('Guest User', 'guest@example.com');"
        ),
        "README.md": (
            "# Test Patch\n\n"
            "This is a test patch for unit testing.\n\n"
            "## Purpose\n"
            "Testing patch directory functionality.\n\n"
            "## Files\n"
            "- 01_create_users.sql: Create users table\n"
            "- 02_add_indexes.sql: Add performance indexes\n"
            "- 03_update_permissions.py: Update permissions\n"
            "- 04_seed_data.sql: Insert initial data\n"
        )
    }


@pytest.fixture
def mock_database():
    """
    Mock database connection for testing.
    
    Provides a mock database connection object that can be used
    to test SQL execution without requiring a real database.
    
    Returns:
        Mock: Mock database connection with execute method
    """
    mock_db = Mock()
    mock_db.execute = Mock()
    mock_db.cursor = Mock()
    
    return mock_db


@pytest.fixture
def sample_invalid_files():
    """
    Sample invalid patch files for error testing.
    
    Provides files with various types of validation errors
    for testing error handling and validation logic.
    
    Returns:
        dict: Mapping of filename -> (content, expected_error_type)
    """
    return {
        "invalid.txt": (
            "This is not a SQL or Python file",
            "invalid_extension"
        ),
        "no_order_prefix.sql": (
            "SELECT 1;",
            "missing_order_prefix"  
        ),
        "1_single_digit.sql": (
            "SELECT 1;",
            "invalid_order_format"
        ),
        "abc_invalid_order.sql": (
            "SELECT 1;", 
            "invalid_order_format"
        ),
        "99_bad_sql.sql": (
            "INVALID SQL SYNTAX !!!",
            "sql_syntax_error"
        ),
        "98_bad_python.py": (
            "invalid python syntax !!!!",
            "python_syntax_error"
        )
    }


@pytest.fixture
def create_patch_with_files(temp_repo, sample_patch_files):
    """
    Factory fixture to create patch directories with files.
    
    Provides a function that can create patch directories
    with specified files for testing purposes.
    
    Args:
        temp_repo: Fixture providing temporary repository
        sample_patch_files: Fixture providing sample file content
        
    Returns:
        function: Factory function to create patches
    """
    repo, temp_dir, schema_patches_dir = temp_repo
    
    def _create_patch(patch_id, files=None, include_readme=True):
        """
        Create a patch directory with specified files.
        
        Args:
            patch_id: Patch identifier
            files: Dict of filename -> content (defaults to sample_patch_files)
            include_readme: Whether to include README.md
            
        Returns:
            Path: Path to created patch directory
        """
        if files is None:
            files = sample_patch_files
            
        patch_path = schema_patches_dir / patch_id
        patch_path.mkdir()
        
        for filename, content in files.items():
            if filename == "README.md" and not include_readme:
                continue
            (patch_path / filename).write_text(content)
            
        return patch_path
    
    return _create_patch


@pytest.fixture
def patch_validator_mock():
    """
    Mock PatchValidator for testing integration.
    
    Provides a mock PatchValidator that returns predictable
    validation results for testing PatchDirectory integration.
    
    Returns:
        Mock: Mock PatchValidator instance
    """
    from half_orm_dev.patch_validator import PatchInfo
    
    mock_validator = Mock()
    
    # Default behavior for valid patch IDs
    def mock_validate_patch_id(patch_id):
        if "-" in patch_id:
            parts = patch_id.split("-", 1)
            return PatchInfo(
                original_id=patch_id,
                normalized_id=patch_id,
                ticket_number=parts[0],
                description=parts[1],
                is_numeric_only=False
            )
        else:
            return PatchInfo(
                original_id=patch_id,
                normalized_id=patch_id,
                ticket_number=patch_id,
                description=None,
                is_numeric_only=True
            )
    
    mock_validator.validate_patch_id.side_effect = mock_validate_patch_id
    
    return mock_validator


# Configuration pytest globale pour ce module de test
pytest_plugins = []  # Pas de plugins additionnels nécessaires

def pytest_configure(config):
    """Configuration pytest pour les tests PatchDirectory."""
    # Ajouter des marqueurs personnalisés si nécessaire
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
