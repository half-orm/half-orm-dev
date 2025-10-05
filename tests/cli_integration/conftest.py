"""
Integration test fixtures for CLI commands.

Provides session-scoped fixtures for testing CLI commands with real PostgreSQL databases.
No Python version skipping (unlike tests/cli/conftest.py).

These fixtures create real databases, directories, and run actual CLI commands
for end-to-end integration testing.
"""

import os
import pytest
import subprocess
from pathlib import Path


@pytest.fixture(scope="session")
def ensure_postgres():
    """
    Ensure PostgreSQL is available for integration tests.

    Checks that PostgreSQL command-line tools (createdb, dropdb, psql) are
    available in the system PATH.

    Raises:
        pytest.fail: If PostgreSQL tools are not available

    Example:
        def test_something(ensure_postgres):
            # PostgreSQL is guaranteed to be available here
            subprocess.run(['createdb', 'my_test_db'], check=True)
    """
    try:
        subprocess.run(
            ['createdb', '--version'],
            check=True,
            capture_output=True,
            text=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.fail(
            "PostgreSQL is required for integration tests. "
            "Install PostgreSQL or skip integration tests with: pytest -m 'not integration'"
        )


@pytest.fixture(scope="session")
def isolated_config_session(tmp_path_factory):
    """
    Session-wide isolated HALFORM_CONF_DIR.

    Creates a temporary .half_orm directory and sets HALFORM_CONF_DIR
    environment variable for the entire test session. This ensures that
    integration tests don't interfere with the user's actual half_orm
    configuration.

    Args:
        tmp_path_factory: pytest's session-scoped temporary directory factory

    Yields:
        Path: Path to isolated config directory (~/.half_orm equivalent)

    Example:
        def test_config(isolated_config_session):
            config_file = isolated_config_session / "my_db"
            # Write test configuration without affecting user's real config
    """
    config_dir = tmp_path_factory.mktemp("config") / ".half_orm"
    config_dir.mkdir()

    # Set environment variable for entire session
    original_conf_dir = os.environ.get('HALFORM_CONF_DIR')
    os.environ['HALFORM_CONF_DIR'] = str(config_dir)

    yield config_dir

    # Restore original environment (if it existed)
    if original_conf_dir:
        os.environ['HALFORM_CONF_DIR'] = original_conf_dir
    else:
        os.environ.pop('HALFORM_CONF_DIR', None)


@pytest.fixture(scope="session")
def clean_database(ensure_postgres, isolated_config_session):
    """
    Clean PostgreSQL database WITHOUT half-orm metadata.

    Creates a real PostgreSQL database for testing sync-only mode
    (init-project without metadata). The database is empty except for
    PostgreSQL system catalogs.

    Args:
        ensure_postgres: Ensures PostgreSQL is available
        isolated_config_session: Isolated config directory

    Yields:
        tuple: (database_name: str, config_dir: Path)

    Cleanup:
        Drops database after test session completes

    Example:
        def test_sync_mode(clean_database):
            db_name, config_dir = clean_database
            # Database exists but has no half-orm metadata
            # Perfect for testing sync-only mode
    """
    db_name = f"hop_test_sync_{os.getpid()}"

    # Create database
    result = subprocess.run(
        ['createdb', db_name],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        pytest.fail(f"Failed to create database {db_name}: {result.stderr}")

    yield db_name, isolated_config_session

    # Cleanup: drop database
    subprocess.run(
        ['dropdb', '--if-exists', db_name],
        capture_output=True,
        check=False
    )


@pytest.fixture(scope="session")
def database_name_for_creation(isolated_config_session):
    """
    Database name for testing init-database --create-db.

    Provides a database name for tests that need to test database creation
    itself (via init-database --create-db). Does NOT create the database
    beforehand - tests will create it.

    Args:
        isolated_config_session: Isolated config directory

    Yields:
        tuple: (database_name: str, config_dir: Path)

    Cleanup:
        Drops database if it was created by tests

    Example:
        def test_create_db(database_name_for_creation):
            db_name, config_dir = database_name_for_creation
            # Database does NOT exist yet
            # Test can call: half_orm dev init-database db_name --create-db
    """
    db_name = f"hop_test_create_{os.getpid()}"

    yield db_name, isolated_config_session

    # Cleanup: drop database if tests created it
    subprocess.run(
        ['dropdb', '--if-exists', db_name],
        capture_output=True,
        check=False
    )
