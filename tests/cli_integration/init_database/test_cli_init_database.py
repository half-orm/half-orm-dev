"""
Integration tests for init-database CLI command.

Tests the complete init-database workflow with real PostgreSQL databases:
- Database creation (--create-db)
- Metadata installation (half_orm_meta schema)
- Initial version registration (0.0.0)
- Configuration file creation

Uses half_orm.model.Model to verify metadata installation (same as half_orm_dev).
"""

import os
import pytest
import subprocess
from pathlib import Path
from configparser import ConfigParser
from half_orm.model import Model


@pytest.mark.integration
@pytest.mark.slow
class TestInitDatabaseMetadataInstallation:
    """Test metadata installation via init-database command."""

    def test_metadata_schema_exists(self, initialized_database):
        """Test that half_orm_meta schema is created."""
        model, db_name, config_dir = initialized_database

        # Verify half_orm_meta schema exists using Model
        # This checks if the relation exists in the model's relation cache
        assert model.has_relation('half_orm_meta.hop_release'), \
            "half_orm_meta.hop_release relation should exist"

    def test_hop_release_table_exists(self, initialized_database):
        """Test that hop_release table is created in half_orm_meta schema."""
        model, db_name, config_dir = initialized_database

        # Get relation class - will raise UnknownRelation if table doesn't exist
        try:
            release_class = model.get_relation_class('half_orm_meta.hop_release')
            assert release_class is not None
        except Exception as e:
            pytest.fail(f"hop_release table should exist: {e}")

    def test_initial_version_registered(self, initialized_database):
        """Test that initial version 0.0.0 is registered in hop_release."""
        model, db_name, config_dir = initialized_database

        # Get hop_release relation class (same as half_orm_dev uses)
        release_class = model.get_relation_class('half_orm_meta.hop_release')

        # Query all releases
        releases = list(release_class())

        assert len(releases) == 1, "Should have exactly one initial release"

        # Verify version components (hop_release uses major/minor/patch columns)
        release = releases[0]
        assert release['major'] == 0, "Initial major version should be 0"
        assert release['minor'] == 0, "Initial minor version should be 0"
        assert release['patch'] == 0, "Initial patch version should be 0"

    def test_configuration_file_created(self, initialized_database):
        """Test that configuration file is created in config directory."""
        model, db_name, config_dir = initialized_database

        # Check config file exists
        config_file = config_dir / db_name
        assert config_file.exists(), f"Config file should exist at {config_file}"

        # Parse and verify config content
        config = ConfigParser()
        config.read(config_file)

        assert config.has_section('database'), "Config should have [database] section"
        assert config.get('database', 'name') == db_name
        assert config.get('database', 'host') == 'localhost'
        assert config.get('database', 'port') == '5432'



@pytest.mark.integration
@pytest.mark.slow
class TestInitDatabaseWithCreateDB:
    """Test init-database with --create-db option."""

    def test_create_db_option_creates_database(self, database_name_for_creation, setup_halftest_user, ensure_postgres):
        """Test that --create-db option creates the database."""
        db_name, config_dir = database_name_for_creation

        # Verify database does NOT exist yet
        check_result = subprocess.run(
            ['psql', '-U', 'halftest', '-h', 'localhost', '-lqt'],
            capture_output=True,
            text=True,
            env={**os.environ, 'PGPASSWORD': 'halftest'}
        )
        assert db_name not in check_result.stdout, "Database should not exist before test"

        # Run init-database with --create-db (via CLI)
        # Provide input for any interactive prompts
        result = subprocess.run([
            'half_orm', 'dev', 'init-database', db_name,
            '--create-db',
            '--user', 'halftest',
            '--password', 'halftest',
            '--host', 'localhost',
            '--port', '5432'
        ], capture_output=True, text=True, input='\n')  # Accept defaults

        assert result.returncode == 0, f"init-database --create-db failed:\n{result.stderr}"

        # Verify database now exists
        check_result = subprocess.run(
            ['psql', '-U', 'halftest', '-h', 'localhost', '-lqt'],
            capture_output=True,
            text=True,
            env={**os.environ, 'PGPASSWORD': 'halftest'}
        )
        assert db_name in check_result.stdout, "Database should exist after --create-db"

        # Verify metadata is installed using half_orm Model
        model = Model(db_name)

        # Check metadata exists (same method as half_orm_dev)
        assert model.has_relation('half_orm_meta.hop_release'), \
            "Metadata should be installed"

        release_class = model.get_relation_class('half_orm_meta.hop_release')
        releases = list(release_class())

        assert len(releases) == 1
        assert releases[0]['major'] == 0
        assert releases[0]['minor'] == 0
        assert releases[0]['patch'] == 0

        # Cleanup: disconnect model (config and DB cleaned by fixture)
        model.disconnect()


@pytest.mark.integration
@pytest.mark.slow
class TestInitDatabaseProductionFlag:
    """Test init-database with --production flag."""

    def test_production_flag_in_configuration(self, database_name_for_creation, setup_halftest_user, ensure_postgres):
        """Test that --production flag is saved in configuration."""
        db_name, config_dir = database_name_for_creation
        config_file = config_dir / db_name

        # Run init-database with --production (via CLI)
        # Need to provide input for production confirmation prompt
        result = subprocess.run([
            'half_orm', 'dev', 'init-database', db_name,
            '--create-db',
            '--production',
            '--user', 'halftest',
            '--password', 'halftest',
            '--host', 'localhost',
            '--port', '5432'
        ], capture_output=True, text=True, input='\n')  # Accept default (True)

        assert result.returncode == 0, f"init-database --production failed:\n{result.stderr}"

        # Check configuration file
        assert config_file.exists()

        config = ConfigParser()
        config.read(config_file)

        # Verify production flag is True
        production_value = config.get('database', 'production', fallback='False')
        assert production_value.lower() in ['true', '1'], "Production flag should be True"

        # Cleanup: remove config file (database cleanup handled by fixture)
        config_file.unlink(missing_ok=True)