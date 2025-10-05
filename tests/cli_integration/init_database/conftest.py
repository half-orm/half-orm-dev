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
def initialized_database(setup_halftest_user, ensure_postgres, isolated_config_session):
    """
    Database WITH half-orm metadata installed.

    Creates a real PostgreSQL database and installs half-orm-dev metadata
    by running the actual CLI command: half_orm dev init-database

    This fixture is the foundation for testing development mode (repo.devel = True).

    Process:
        1. Create database config in tests/.config/
        2. Run: half_orm dev init-database <db_name> --create-db (via CLI)
        3. HALFORM_CONF_DIR already set by isolated_config_session
        4. Verify metadata installation
        5. Return Model instance + database info

    Args:
        setup_halftest_user: Ensures halftest user exists
        ensure_postgres: Ensures PostgreSQL is available
        isolated_config_session: Config directory pointing to tests/.config/

    Yields:
        tuple: (model: Model, db_name: str, config_dir: Path)
            - model: halfORM Model instance connected to database
            - db_name: Database name
            - config_dir: Path to config directory (tests/.config/)

    Cleanup:
        Drops database after test session completes

    Example:
        def test_metadata_installed(initialized_database):
            model, db_name, config_dir = initialized_database
            # Database has half_orm_meta schema installed
            # Can test init-project in development mode
    """
    db_name = f"hop_test_devel_{os.getpid()}"

    # Create config file for this database in tests/.config/
    from configparser import ConfigParser
    config = ConfigParser()
    config['database'] = {
        'name': db_name,
        'user': 'halftest',
        'password': 'halftest',
        'host': 'localhost',
        'port': '5432',
        'production': 'False'
    }
    config_file = isolated_config_session / db_name
    with open(config_file, 'w') as f:
        config.write(f)

    # Install database + metadata via CLI (--create-db creates the DB)
    result = subprocess.run([
        'half_orm', 'dev', 'init-database', db_name,
        '--create-db',
        '--user', 'halftest',
        '--password', 'halftest',
        '--host', 'localhost',
        '--port', '5432'
    ], capture_output=True, text=True)

    if result.returncode != 0:
        # Cleanup config file before failing
        config_file.unlink(missing_ok=True)
        pytest.fail(
            f"Failed to initialize database {db_name}:\n"
            f"STDOUT: {result.stdout}\n"
            f"STDERR: {result.stderr}"
        )

    # Create Model instance to verify and provide to tests
    try:
        model = Model(db_name)
    except Exception as e:
        # Cleanup database and config before failing
        subprocess.run(
            ['dropdb', '-U', 'halftest', '-h', 'localhost', '--if-exists', db_name],
            check=False,
            env={**os.environ, 'PGPASSWORD': 'halftest'}
        )
        config_file.unlink(missing_ok=True)
        pytest.fail(f"Failed to create Model for {db_name}: {e}")

    yield model, db_name, isolated_config_session

    # Cleanup: disconnect Model and drop database
    try:
        model.disconnect()
    except Exception:
        pass  # Ignore disconnect errors

    # Use --force to terminate active connections (PostgreSQL 13+)
    subprocess.run(
        ['dropdb', '-U', 'halftest', '-h', 'localhost', '--force', '--if-exists', db_name],
        capture_output=True,
        check=False,
        env={**os.environ, 'PGPASSWORD': 'halftest'}
    )
    config_file.unlink(missing_ok=True)
