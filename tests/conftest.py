"""
Shared pytest fixtures for half_orm_dev tests.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock
from half_orm_dev.database import Database


@pytest.fixture
def temp_repo():
    """
    Create temporary directory structure for testing.
    """
    temp_dir = tempfile.mkdtemp()
    patches_dir = Path(temp_dir) / "Patches"
    patches_dir.mkdir()

    repo = Mock()
    repo.base_dir = temp_dir
    repo.devel = True
    repo.name = "test_database"
    repo.git_origin = "https://github.com/test/repo.git"

    # Create default HGit mock with tag methods
    mock_hgit = Mock()
    mock_hgit.fetch_tags = Mock()
    mock_hgit.tag_exists = Mock(return_value=False)
    mock_hgit.create_tag = Mock()
    mock_hgit.push_tag = Mock()
    repo.hgit = mock_hgit

    yield repo, temp_dir, patches_dir

    shutil.rmtree(temp_dir)


@pytest.fixture
def patch_manager(temp_repo):
    """
    Create PatchManager instance with temporary repo.

    The repo.hgit already has default tag mocks configured in temp_repo fixture.
    Tests can override repo.hgit if needed, but should use mock_hgit_complete fixture.
    """
    from half_orm_dev.patch_manager import PatchManager

    repo, temp_dir, patches_dir = temp_repo
    patch_mgr = PatchManager(repo)
    return patch_mgr, repo, temp_dir, patches_dir


@pytest.fixture
def mock_hgit_complete():
    """
    Create complete HGit mock with all necessary methods for patch creation.

    Use this fixture when you need to replace repo.hgit in tests to ensure
    all required methods are mocked properly.

    Returns:
        Mock: Configured HGit mock with:
            - branch: Current branch name
            - repos_is_clean(): Returns True
            - has_remote(): Returns True
            - fetch_from_origin(): Fetch all references from remote
            - checkout(): Branch checkout
            - fetch_tags(): Tag fetching
            - tag_exists(): Returns False (tag doesn't exist)
            - create_tag(): Tag creation
            - push_tag(): Tag push
            - push_branch(): Branch push (for reservation)

    Example:
        def test_something(self, patch_manager, mock_hgit_complete):
            patch_mgr, repo, temp_dir, patches_dir = patch_manager

            # Use complete mock instead of creating new one
            mock_hgit_complete.branch = "ho-prod"
            repo.hgit = mock_hgit_complete

            result = patch_mgr.create_patch("456-test")
    """
    mock_hgit = Mock()

    # Branch context
    mock_hgit.branch = "ho-prod"

    # Repository state
    mock_hgit.repos_is_clean = Mock(return_value=True)
    mock_hgit.has_remote = Mock(return_value=True)

    # Remote synchronization
    mock_hgit.fetch_from_origin = Mock()

    # Branch operations
    mock_hgit.checkout = Mock()
    mock_hgit.push_branch = Mock()

    # Tag operations (for patch number reservation)
    mock_hgit.fetch_tags = Mock()
    mock_hgit.tag_exists = Mock(return_value=False)  # By default, tag doesn't exist
    mock_hgit.create_tag = Mock()
    mock_hgit.push_tag = Mock()
    mock_hgit.delete_local_branch = Mock()
    mock_hgit.delete_local_tag = Mock()

    return mock_hgit


@pytest.fixture
def sample_patch_files():
    """
    Provide sample patch file contents for testing.
    """
    return {
        '01_create_table.sql': 'CREATE TABLE users (id SERIAL PRIMARY KEY);',
        '02_add_indexes.sql': 'CREATE INDEX idx_users_id ON users(id);',
        'migrate.py': 'print("Running migration")',
        'cleanup.py': 'print("Cleanup complete")',
    }


@pytest.fixture
def mock_database():
    """
    Mock database connection for testing.

    Provides a mock database connection object that can be used
    to test SQL execution without requiring a real database.

    Returns:
        Mock: Mock database connection with execute_query method
    """
    mock_db = Mock()
    mock_db.execute_query = Mock()
    mock_db.execute = Mock()
    mock_db.cursor = Mock()

    return mock_db

@pytest.fixture
def mock_database_for_schema_generation():
    """
    Create complete Database mock for _generate_schema_sql() testing.

    Provides a mock with all necessary attributes and methods for schema
    generation tests, including mangled private attributes.

    Returns:
        Mock: Configured Database mock with:
            - _Database__name: Database name (mangled private attribute)
            - _collect_connection_params(): Returns connection parameters
            - _get_connection_params(): Returns connection parameters
            - _execute_pg_command(): Mock for pg_dump execution

    Example:
        def test_something(self, mock_database_for_schema_generation, tmp_path):
            database = mock_database_for_schema_generation
            model_dir = tmp_path / "model"
            model_dir.mkdir()

            result = Database._generate_schema_sql(database, "1.0.0", model_dir)
    """
    mock_db = Mock(spec=Database)

    # Set mangled private attribute for database name
    mock_db._Database__name = "test_db"

    # Mock connection parameter methods
    connection_params = {
        'user': 'test_user',
        'password': 'test_pass',
        'host': 'localhost',
        'port': 5432,
        'production': False
    }

    mock_db._collect_connection_params = Mock(return_value=connection_params)
    mock_db._get_connection_params = Mock(return_value=connection_params)

    # Mock pg_dump execution
    mock_db._execute_pg_command = Mock()

    return mock_db