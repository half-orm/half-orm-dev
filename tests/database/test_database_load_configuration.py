"""
Comprehensive unit tests for Database._load_configuration() method.

This module tests the complete replacement of  functionality
with integrated Database._load_configuration() method.
"""

import os
import tempfile
import pytest
from configparser import ConfigParser
from unittest.mock import patch, mock_open
from pathlib import Path

from half_orm_dev.database import Database


class TestLoadConfiguration:
    """Test Database._load_configuration() method replacing  logic."""

    @pytest.fixture
    def temp_config_dir(self):
        """Create temporary configuration directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def mock_conf_dir(self, temp_config_dir):
        """Mock CONF_DIR to point to temporary directory."""
        with patch('half_orm.model.CONF_DIR', temp_config_dir):
            yield temp_config_dir

    def create_config_file(self, config_dir, database_name, config_data):
        """Helper to create configuration file with given data."""
        config = ConfigParser()
        config.read_dict(config_data)

        config_file = os.path.join(config_dir, database_name)
        with open(config_file, 'w') as f:
            config.write(f)

        return config_file

    def test_load_configuration_complete_config(self, mock_conf_dir):
        """Test loading complete configuration with all parameters."""
        database_name = "production_db"
        config_data = {
            'database': {
                'name': database_name,
                'user': 'app_user',
                'password': 'secret123',
                'host': 'db.company.com',
                'port': '5432',
                'production': 'True'
            }
        }

        self.create_config_file(mock_conf_dir, database_name, config_data)

        result = Database._load_configuration(database_name)

        expected = {
            'name': database_name,
            'user': 'app_user',
            'password': 'secret123',
            'host': 'db.company.com',
            'port': 5432,
            'production': True
        }
        assert result == expected

    def test_load_configuration_minimal_trust_mode(self, mock_conf_dir):
        """Test loading minimal configuration (trust mode - name only)."""
        database_name = "local_dev"
        config_data = {
            'database': {
                'name': database_name
            }
        }

        self.create_config_file(mock_conf_dir, database_name, config_data)

        with patch.dict(os.environ, {'USER': 'developer'}):
            result = Database._load_configuration(database_name)

        expected = {
            'name': database_name,
            'user': 'developer',
            'password': '',
            'host': '',
            'port': 5432,
            'production': False
        }
        assert result == expected

    def test_load_configuration_partial_config_with_defaults(self, mock_conf_dir):
        """Test loading partial configuration with some defaults applied."""
        database_name = "dev_db"
        config_data = {
            'database': {
                'name': database_name,
                'user': 'dev_user',
                'host': 'localhost'
                # Missing: password, port, production
            }
        }

        self.create_config_file(mock_conf_dir, database_name, config_data)

        result = Database._load_configuration(database_name)

        expected = {
            'name': database_name,
            'user': 'dev_user',
            'password': '',
            'host': 'localhost',
            'port': 5432,
            'production': False
        }
        assert result == expected

    def test_load_configuration_nonexistent_file(self, mock_conf_dir):
        """Test loading configuration for non-existent database."""
        result = Database._load_configuration("unknown_database")
        assert result is None

    def test_load_configuration_empty_password_trust_mode(self, mock_conf_dir):
        """Test configuration with empty password (trust authentication)."""
        database_name = "trust_db"
        config_data = {
            'database': {
                'name': database_name,
                'user': 'trust_user',
                'password': '',  # Explicit empty password
                'host': '',      # Unix socket
                'port': ''       # Default port
            }
        }

        self.create_config_file(mock_conf_dir, database_name, config_data)

        result = Database._load_configuration(database_name)

        expected = {
            'name': database_name,
            'user': 'trust_user',
            'password': '',
            'host': '',
            'port': 5432,  # Should convert empty string to default int
            'production': False
        }
        assert result == expected

    def test_load_configuration_production_flag_variations(self, mock_conf_dir):
        """Test various production flag formats (True/False/true/false)."""
        test_cases = [
            ('True', True),
            ('true', True),
            ('TRUE', True),
            ('False', False),
            ('false', False),
            ('FALSE', False),
            ('1', True),
            ('0', False)
        ]

        for prod_value, expected_bool in test_cases:
            database_name = f"test_prod_{prod_value.lower()}"
            config_data = {
                'database': {
                    'name': database_name,
                    'production': prod_value
                }
            }

            self.create_config_file(mock_conf_dir, database_name, config_data)

            with patch.dict(os.environ, {'USER': 'test_user'}):
                result = Database._load_configuration(database_name)

            assert result['production'] == expected_bool, f"Failed for production='{prod_value}'"

    def test_load_configuration_port_parsing(self, mock_conf_dir):
        """Test port number parsing from string to int."""
        database_name = "port_test"
        config_data = {
            'database': {
                'name': database_name,
                'port': '3306'  # MySQL port as string
            }
        }

        self.create_config_file(mock_conf_dir, database_name, config_data)

        with patch.dict(os.environ, {'USER': 'test_user'}):
            result = Database._load_configuration(database_name)

        assert result['port'] == 3306
        assert isinstance(result['port'], int)

    def test_load_configuration_missing_user_env_fallback(self, mock_conf_dir):
        """Test fallback to USER environment variable when user not in config."""
        database_name = "env_user_test"
        config_data = {
            'database': {
                'name': database_name,
                'host': 'localhost'
            }
        }

        self.create_config_file(mock_conf_dir, database_name, config_data)

        with patch.dict(os.environ, {'USER': 'system_user'}):
            result = Database._load_configuration(database_name)

        assert result['user'] == 'system_user'

    def test_load_configuration_file_permission_error(self, mock_conf_dir):
        """Test handling of permission errors when reading config file."""
        database_name = "permission_test"
        config_data = {
            'database': {
                'name': database_name
            }
        }

        config_file = self.create_config_file(mock_conf_dir, database_name, config_data)

        # Make file unreadable
        os.chmod(config_file, 0o000)

        try:
            with pytest.raises(PermissionError):
                Database._load_configuration(database_name)
        finally:
            # Restore permissions for cleanup
            os.chmod(config_file, 0o644)

    def test_load_configuration_invalid_config_format(self, mock_conf_dir):
        """Test handling of invalid configuration file format."""
        database_name = "invalid_config"
        config_file = os.path.join(mock_conf_dir, database_name)

        # Create invalid config file
        with open(config_file, 'w') as f:
            f.write("This is not a valid config file\nNo sections here!")

        with pytest.raises(ValueError, match="Configuration file format is invalid"):
            Database._load_configuration(database_name)

    def test_load_configuration_missing_database_section(self, mock_conf_dir):
        """Test handling of config file missing [database] section."""
        database_name = "missing_section"
        config_file = os.path.join(mock_conf_dir, database_name)

        # Create config with wrong section name
        with open(config_file, 'w') as f:
            f.write("[wrong_section]\nname=test\n")

        with pytest.raises(ValueError, match="Configuration file format is invalid"):
            Database._load_configuration(database_name)

    def test_load_configuration_nonexistent_conf_dir(self):
        """Test handling when CONF_DIR doesn't exist."""
        with patch('half_orm.model.CONF_DIR', '/nonexistent/directory'):
            with pytest.raises(FileNotFoundError):
                Database._load_configuration("any_database")

    def test_load_configuration_dbconn_compatibility(self, mock_conf_dir):
        """Test full compatibility with existing  configuration files."""
        # Simulate exact format created by
        database_name = "dbconn_compat"

        # Create config exactly as .set_params() would
        config = ConfigParser()
        config.add_section('database')
        config.set('database', 'name', database_name)
        config.set('database', 'user', 'dbconn_user')
        config.set('database', 'password', 'dbconn_pass')
        config.set('database', 'host', 'dbconn_host')
        config.set('database', 'port', '5433')
        config.set('database', 'production', 'False')

        config_file = os.path.join(mock_conf_dir, database_name)
        with open(config_file, 'w') as f:
            config.write(f)

        result = Database._load_configuration(database_name)

        # Should match exactly what  would provide
        expected = {
            'name': database_name,
            'user': 'dbconn_user',
            'password': 'dbconn_pass',
            'host': 'dbconn_host',
            'port': 5433,
            'production': False
        }
        assert result == expected

    def test_load_configuration_return_type_consistency(self, mock_conf_dir):
        """Test that return types are consistent (int for port, bool for production)."""
        database_name = "type_test"
        config_data = {
            'database': {
                'name': database_name,
                'port': '5432',
                'production': 'True'
            }
        }

        self.create_config_file(mock_conf_dir, database_name, config_data)

        with patch.dict(os.environ, {'USER': 'test_user'}):
            result = Database._load_configuration(database_name)

        # Verify types are standardized
        assert isinstance(result['name'], str)
        assert isinstance(result['user'], str)
        assert isinstance(result['password'], str)
        assert isinstance(result['host'], str)
        assert isinstance(result['port'], int)
        assert isinstance(result['production'], bool)
