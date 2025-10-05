"""
Fixtures for init-database integration tests.

Provides fixtures for testing init-database command with real PostgreSQL databases
and half-orm metadata installation.
"""

import os
import pytest
import subprocess
from half_orm.model import Model


@pytest.fixture(scope="session")
def initialized_database(ensure_postgres, isolated_config_session):
    """
    Database WITH half-orm metadata installed.

    Creates a real PostgreSQL database and installs half-orm-dev metadata
    by running the actual CLI command: half_orm dev init-database

    This fixture is the foundation for testing development mode (repo.devel = True).

    Process:
        1. Create database via createdb
        2. Run: half_orm dev init-database <db_name> (with connection params)
        3. Verify metadata installation
        4. Return Model instance + database info

    Args:
        ensure_postgres: Ensures PostgreSQL is available
        isolated_config_session: Isolated config directory

    Yields:
        tuple: (model: Model, db_name: str, config_dir: Path)
            - model: halfORM Model instance connected to database
            - db_name: Database name
            - config_dir: Path to isolated config directory

    Cleanup:
        Drops database after test session completes

    Example:
        def test_metadata_installed(initialized_database):
            model, db_name, config_dir = initialized_database
            # Database has half_orm_meta schema installed
            # Can test init-project in development mode
    """
    db_name = f"hop_test_devel_{os.getpid()}"

    # Create database
    result = subprocess.run(
        ['createdb', db_name],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        pytest.fail(f"Failed to create database {db_name}: {result.stderr}")

    # Install half-orm metadata via CLI
    # Use environment USER and local trust connection (no password)
    user = os.environ.get('USER', 'postgres')

    result = subprocess.run([
        'half_orm', 'dev', 'init-database', db_name,
        '--user', user,
        '--host', 'localhost',
        '--port', '5432'
    ], capture_output=True, text=True, input='\n')  # Accept default password (empty)

    if result.returncode != 0:
        # Cleanup database before failing
        subprocess.run(['dropdb', '--if-exists', db_name], check=False)
        pytest.fail(
            f"Failed to initialize database {db_name}:\n"
            f"STDOUT: {result.stdout}\n"
            f"STDERR: {result.stderr}"
        )

    # Create Model instance to verify and provide to tests
    try:
        model = Model(db_name)
    except Exception as e:
        # Cleanup database before failing
        subprocess.run(['dropdb', '--if-exists', db_name], check=False)
        pytest.fail(f"Failed to create Model for {db_name}: {e}")

    yield model, db_name, isolated_config_session

    # Cleanup: drop database
    subprocess.run(
        ['dropdb', '--if-exists', db_name],
        capture_output=True,
        check=False
    )
