"""
Shared pytest fixtures for half_orm_dev tests.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch
from half_orm_dev.database import Database
from half_orm_dev.repo import Repo


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
    repo.restore_database_from_schema = Repo.restore_database_from_schema.__get__(repo, type(repo))
    mock_get_version = Mock(return_value=(16, 1))
    repo.database.get_postgres_version = mock_get_version
    patch_mgr = PatchManager(repo)
    return patch_mgr, repo, temp_dir, patches_dir


@pytest.fixture
def mock_hgit_complete():
    """
    Create complete mock HGit for create_patch workflow tests.

    Provides all necessary mocks for successful patch creation workflow:
    - Branch validation (on ho-prod)
    - Repository clean check
    - Remote configuration check
    - Remote fetch operations
    - Branch synchronization check (NEW)
    - Tag availability check
    - Git operations (checkout, add, commit, tag, push)
    - Branch operations (create, delete, checkout)
    """
    mock_hgit = Mock()

    # Branch and repo state
    mock_hgit.branch = "ho-prod"
    mock_hgit.repos_is_clean.return_value = True
    mock_hgit.has_remote.return_value = True

    # NEW: Branch synchronization check
    # Returns (is_synced, status) tuple
    mock_hgit.is_branch_synced.return_value = (True, "synced")

    # Fetch operations
    mock_hgit.fetch_from_origin.return_value = None
    mock_hgit.fetch_tags.return_value = None

    # Tag operations
    mock_hgit.tag_exists.return_value = False  # No existing tags
    mock_hgit.create_tag.return_value = None
    mock_hgit.push_tag.return_value = None
    mock_hgit.delete_local_tag.return_value = None

    # Branch operations
    mock_hgit.checkout.return_value = None
    mock_hgit.delete_local_branch.return_value = None
    mock_hgit.push_branch.return_value = None

    # Git proxy methods
    mock_hgit.add.return_value = None
    mock_hgit.commit.return_value = None

    # Git repo access for reset operations
    mock_git_repo = Mock()
    mock_git_repo.git.reset.return_value = None
    mock_hgit._HGit__git_repo = mock_git_repo

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

"""
Additional fixtures for ReleaseManager tests.
Add these to tests/conftest.py
"""

@pytest.fixture
def mock_release_manager_basic(tmp_path):
    """
    Create basic ReleaseManager with minimal mocks.

    Provides:
    - ReleaseManager instance
    - Mock repo with base_dir
    - Temporary releases/ directory

    Returns:
        Tuple of (release_mgr, mock_repo, tmp_path)
    """
    from unittest.mock import Mock
    from half_orm_dev.release_manager import ReleaseManager

    mock_repo = Mock()
    mock_repo.base_dir = str(tmp_path)

    # Create releases/ directory
    releases_dir = tmp_path / "releases"
    releases_dir.mkdir()

    release_mgr = ReleaseManager(mock_repo)

    return release_mgr, mock_repo, tmp_path


@pytest.fixture
def mock_release_manager_with_hgit(mock_release_manager_basic):
    """
    Create ReleaseManager with fully mocked HGit.

    Provides:
    - ReleaseManager instance
    - Mock repo with HGit configured
    - HGit mocked for all Git operations
    - Default "happy path" configuration

    Returns:
        Tuple of (release_mgr, mock_repo, mock_hgit, tmp_path)
    """
    from unittest.mock import Mock

    release_mgr, mock_repo, tmp_path = mock_release_manager_basic

    # Mock HGit with all required methods
    mock_hgit = Mock()

    # Branch and repo state
    mock_hgit.branch = "ho-prod"
    mock_hgit.repos_is_clean.return_value = True

    # Fetch and sync
    mock_hgit.fetch_from_origin.return_value = None
    mock_hgit.is_branch_synced.return_value = (True, "synced")
    mock_hgit.pull.return_value = None

    # Git operations
    mock_hgit.add.return_value = None
    mock_hgit.commit.return_value = None
    mock_hgit.push.return_value = None

    mock_repo.hgit = mock_hgit

    return release_mgr, mock_repo, mock_hgit, tmp_path


@pytest.fixture
def mock_release_manager_with_production(mock_release_manager_with_hgit):
    """
    Create ReleaseManager with production version mocking.

    Provides:
    - Everything from mock_release_manager_with_hgit
    - Mock _get_production_version() to return "1.3.5"
    - Mock model/schema.sql symlink (for tests that directly test _get_production_version)
    - Default production version: 1.3.5

    Returns:
        Tuple of (release_mgr, mock_repo, mock_hgit, tmp_path, prod_version)
    """
    from unittest.mock import Mock, patch

    release_mgr, mock_repo, mock_hgit, tmp_path = mock_release_manager_with_hgit

    # Create model/ directory with schema files (for tests that test _get_production_version directly)
    model_dir = tmp_path / "model"
    model_dir.mkdir()

    # Create versioned schema file
    prod_version = "1.3.5"
    schema_file = model_dir / f"schema-{prod_version}.sql"
    schema_file.write_text("-- Schema version 1.3.5")

    # Create symlink schema.sql -> schema-1.3.5.sql
    schema_symlink = model_dir / "schema.sql"
    schema_symlink.symlink_to(f"schema-{prod_version}.sql")

    # Mock database last_release_s
    mock_database = Mock()
    mock_database.last_release_s = prod_version
    mock_repo.database = mock_database

    # CRITICAL: Mock _get_production_version() to avoid reading symlink in most tests
    # This allows tests to focus on workflow without setting up full file structure
    release_mgr._get_production_version = Mock(return_value=prod_version)

    return release_mgr, mock_repo, mock_hgit, tmp_path, prod_version


@pytest.fixture
def sample_release_files(tmp_path):
    """
    Create sample release files in releases/ directory.

    Creates:
    - releases/1.3.4.txt (production)
    - releases/1.3.5-rc2.txt (rc)
    - releases/1.4.0-stage.txt (stage)

    Returns:
        Tuple of (releases_dir, dict of created files)
    """
    releases_dir = tmp_path / "releases"
    releases_dir.mkdir()

    files = {
        '1.3.4.txt': '',
        '1.3.5-rc2.txt': '',
        '1.4.0-stage.txt': '',
    }

    for filename, content in files.items():
        (releases_dir / filename).write_text(content)

    return releases_dir, files