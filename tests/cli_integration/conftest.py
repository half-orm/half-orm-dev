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
def setup_halftest_user():
    """
    Ensure PostgreSQL user 'halftest' exists with password 'halftest'.

    Creates the user only if it doesn't already exist (idempotent).
    User is created with SUPERUSER privileges for testing purposes.

    Requires:
        - PostgreSQL superuser access (typically 'postgres' user)
        - sudo privileges or running as postgres user

    Raises:
        pytest.skip: If unable to create user (not a hard failure)

    Example:
        def test_with_halftest(setup_halftest_user):
            # halftest user is guaranteed to exist
            # Can connect with user='halftest', password='halftest'
    """
    # Check if user already exists
    check_result = subprocess.run(
        ['sudo', '-u', 'postgres', 'psql', '-tAc',
         "SELECT 1 FROM pg_roles WHERE rolname='halftest'"],
        capture_output=True,
        text=True
    )

    # If user exists, nothing to do
    if check_result.returncode == 0 and '1' in check_result.stdout:
        return

    # Create user if it doesn't exist
    try:
        subprocess.run(
            ['sudo', '-u', 'postgres', 'psql', 'template1', '-c',
             "CREATE USER halftest WITH PASSWORD 'halftest' SUPERUSER"],
            check=True,
            capture_output=True,
            text=True
        )
    except subprocess.CalledProcessError as e:
        pytest.skip(
            f"Cannot create halftest user (requires postgres superuser access): {e.stderr}"
        )


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
def isolated_config_session():
    """
    Session-wide HALFORM_CONF_DIR pointing to tests/.config/ directory.

    Uses the existing tests/.config/ directory (same as CI) which contains
    the hop_test configuration file with halftest credentials.

    Sets HALFORM_CONF_DIR environment variable for the entire test session.

    Yields:
        Path: Path to tests/.config directory containing hop_test config

    Example:
        def test_config(isolated_config_session):
            config_file = isolated_config_session / "hop_test"
            # Uses existing test configuration
    """
    # Use tests/.config directory (same as CI)
    tests_root = Path(__file__).parent
    config_dir = tests_root / ".config"

    if not config_dir.exists():
        pytest.fail(f"Configuration directory {config_dir} doesn't exist")

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
def clean_database(setup_halftest_user, ensure_postgres, isolated_config_session):
    """
    Clean PostgreSQL database WITHOUT half-orm metadata.

    Creates a real PostgreSQL database for testing sync-only mode
    (init-project without metadata). Database is created with halftest
    user but WITHOUT installing half-orm metadata.

    Uses createdb command directly (not init-database) to create empty database.

    Args:
        setup_halftest_user: Ensures halftest user exists
        ensure_postgres: Ensures PostgreSQL is available
        isolated_config_session: Config directory with hop_test config

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

    # Create database directly (not via init-database, to avoid metadata)
    result = subprocess.run(
        ['createdb', '-U', 'halftest', '-h', 'localhost', db_name],
        capture_output=True,
        text=True,
        env={**os.environ, 'PGPASSWORD': 'halftest'}
    )
    if result.returncode != 0:
        pytest.fail(f"Failed to create database {db_name}: {result.stderr}")

    yield db_name, isolated_config_session

    # Cleanup: drop database with --force (PostgreSQL 13+)
    subprocess.run(
        ['dropdb', '-U', 'halftest', '-h', 'localhost', '--force', '--if-exists', db_name],
        capture_output=True,
        check=False,
        env={**os.environ, 'PGPASSWORD': 'halftest'}
    )


@pytest.fixture(scope="session")
def database_name_for_creation(setup_halftest_user, isolated_config_session):
    """
    Database name for testing init-database --create-db.

    Provides a database name for tests that need to test database creation
    itself (via init-database --create-db). Does NOT create the database
    beforehand - tests will create it.

    Uses halftest user (created by setup_halftest_user fixture).

    Args:
        setup_halftest_user: Ensures halftest user exists
        isolated_config_session: Config directory with hop_test config

    Yields:
        tuple: (database_name: str, config_dir: Path)

    Cleanup:
        Drops database AND config file if they were created by tests

    Example:
        def test_create_db(database_name_for_creation):
            db_name, config_dir = database_name_for_creation
            # Database does NOT exist yet
            # Test can call: half_orm dev init-database db_name --create-db
    """
    db_name = f"hop_test_create_{os.getpid()}"
    config_file = isolated_config_session / db_name

    yield db_name, isolated_config_session

    # Cleanup: drop database AND config file if tests created them
    subprocess.run(
        ['dropdb', '-U', 'halftest', '-h', 'localhost', '--force', '--if-exists', db_name],
        capture_output=True,
        check=False,
        env={**os.environ, 'PGPASSWORD': 'halftest'}
    )
    config_file.unlink(missing_ok=True)
