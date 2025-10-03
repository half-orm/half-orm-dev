"""
Comprehensive unit tests for Database._get_connection_params() method.

This module tests the instance method that provides unified access to connection
parameters during the migration from DbConn to integrated Database functionality.
"""

import os
import pytest
from unittest.mock import Mock, patch, call
from pathlib import Path

from half_orm_dev.database import Database


class TestGetConnectionParams:
    """Test Database._get_connection_params() instance method."""

    @pytest.fixture
    def mock_repo(self):
        """Create mock repository for Database instances."""
        repo = Mock()
        repo.name = "test_database"
        repo.new = False
        repo.devel = True
        return repo

    @pytest.fixture
    def database_instance(self, mock_repo):
        """Create Database instance for testing."""
        # Mock Model to avoid database connection during tests
        with patch('half_orm_dev.database.Model'):
            db = Database(mock_repo, get_release=False)
            return db

    def test_get_connection_params_with_existing_config(self, database_instance):
        """Test getting connection params when configuration file exists."""
        complete_config = {
            'name': 'test_database',
            'user': 'test_user',
            'password': 'test_pass',
            'host': 'localhost',
            'port': 5432,
            'production': False
        }

        with patch.object(Database, '_load_configuration', return_value=complete_config) as mock_load:
            result = database_instance._get_connection_params()

        assert result == complete_config
        mock_load.assert_called_once_with('test_database')

    def test_get_connection_params_no_config_file(self, database_instance):
        """Test getting connection params when no configuration file exists."""
        with patch.object(Database, '_load_configuration', return_value=None) as mock_load:
            result = database_instance._get_connection_params()

        # Should return defaults when no config exists
        expected_defaults = {
            'name': 'test_database',
            'user': os.environ.get('USER', ''),
            'password': '',
            'host': '',
            'port': 5432,
            'production': False
        }
        assert result == expected_defaults
        mock_load.assert_called_once_with('test_database')

    def test_get_connection_params_handles_permission_error(self, database_instance):
        """Test graceful handling of PermissionError from _load_configuration."""
        with patch.object(Database, '_load_configuration', side_effect=PermissionError("Access denied")):
            result = database_instance._get_connection_params()

        # Should return defaults instead of raising exception
        expected_defaults = {
            'name': 'test_database',
            'user': os.environ.get('USER', ''),
            'password': '',
            'host': '',
            'port': 5432,
            'production': False
        }
        assert result == expected_defaults

    def test_get_connection_params_handles_file_not_found_error(self, database_instance):
        """Test graceful handling of FileNotFoundError from _load_configuration."""
        with patch.object(Database, '_load_configuration', side_effect=FileNotFoundError("Config dir missing")):
            result = database_instance._get_connection_params()

        # Should return defaults instead of raising exception
        expected_defaults = {
            'name': 'test_database',
            'user': os.environ.get('USER', ''),
            'password': '',
            'host': '',
            'port': 5432,
            'production': False
        }
        assert result == expected_defaults

    def test_get_connection_params_handles_value_error(self, database_instance):
        """Test graceful handling of ValueError from _load_configuration."""
        with patch.object(Database, '_load_configuration', side_effect=ValueError("Invalid config format")):
            result = database_instance._get_connection_params()

        # Should return defaults instead of raising exception
        expected_defaults = {
            'name': 'test_database',
            'user': os.environ.get('USER', ''),
            'password': '',
            'host': '',
            'port': 5432,
            'production': False
        }
        assert result == expected_defaults

    def test_get_connection_params_trust_mode_config(self, database_instance):
        """Test getting connection params with trust mode (minimal) configuration."""
        trust_config = {
            'name': 'test_database',
            'user': 'trust_user',
            'password': '',
            'host': '',
            'port': 5432,
            'production': False
        }

        with patch.object(Database, '_load_configuration', return_value=trust_config):
            result = database_instance._get_connection_params()

        assert result == trust_config
        assert result['password'] == ''  # Empty password for trust mode
        assert result['host'] == ''      # Unix socket

    def test_get_connection_params_production_config(self, database_instance):
        """Test getting connection params for production configuration."""
        production_config = {
            'name': 'test_database',
            'user': 'prod_user',
            'password': 'secure_pass',
            'host': 'prod.db.com',
            'port': 5432,
            'production': True
        }

        with patch.object(Database, '_load_configuration', return_value=production_config):
            result = database_instance._get_connection_params()

        assert result == production_config
        assert result['production'] is True
        assert result['host'] == 'prod.db.com'

    def test_get_connection_params_custom_port(self, database_instance):
        """Test getting connection params with custom port configuration."""
        custom_port_config = {
            'name': 'test_database',
            'user': 'db_user',
            'password': 'db_pass',
            'host': 'localhost',
            'port': 3306,  # MySQL port
            'production': False
        }

        with patch.object(Database, '_load_configuration', return_value=custom_port_config):
            result = database_instance._get_connection_params()

        assert result == custom_port_config
        assert result['port'] == 3306
        assert isinstance(result['port'], int)

    def test_get_connection_params_dbconn_compatibility(self, database_instance):
        """Test that _get_connection_params provides same data as DbConn properties."""
        # Simulate exact configuration that DbConn would provide
        dbconn_equivalent = {
            'name': 'test_database',
            'user': 'dbconn_user',
            'password': 'dbconn_password',
            'host': 'dbconn_host',
            'port': 5433,
            'production': False
        }

        with patch.object(Database, '_load_configuration', return_value=dbconn_equivalent):
            result = database_instance._get_connection_params()

        # Verify each property matches what DbConn would return
        assert result['user'] == 'dbconn_user'      # replaces self.__connection_params.user
        assert result['host'] == 'dbconn_host'      # replaces self.__connection_params.host
        assert result['port'] == 5433               # replaces self.__connection_params.port
        assert result['production'] is False        # replaces self.__connection_params.production
        assert result['password'] == 'dbconn_password'

    def test_get_connection_params_different_database_names(self):
        """Test _get_connection_params with different database names."""
        # Create instances with different database names
        repo1 = Mock()
        repo1.name = "database_one"
        repo1.new = False
        repo1.devel = True

        repo2 = Mock()
        repo2.name = "database_two"
        repo2.new = False
        repo2.devel = True

        config1 = {
            'name': 'database_one',
            'user': 'user1',
            'password': 'pass1',
            'host': 'host1',
            'port': 5432,
            'production': False
        }

        config2 = {
            'name': 'database_two',
            'user': 'user2',
            'password': 'pass2',
            'host': 'host2',
            'port': 5433,
            'production': True
        }

        with patch('half_orm_dev.database.Model'):
            db1 = Database(repo1, get_release=False)
            db2 = Database(repo2, get_release=False)

        with patch.object(Database, '_load_configuration', side_effect=[config1, config2])as mock_load:
            result1 = db1._get_connection_params()
            result2 = db2._get_connection_params()

        # Each instance should get its own configuration
        assert result1 == config1
        assert result2 == config2

        # Verify correct database names were used
        expected_calls = [call('database_one'), call('database_two')]
        mock_load.assert_has_calls(expected_calls)

    def test_get_connection_params_default_user_fallback(self, database_instance):
        """Test USER environment variable fallback in default configuration."""
        with patch.object(Database, '_load_configuration', return_value=None):
            with patch.dict(os.environ, {'USER': 'env_test_user'}):
                result = database_instance._get_connection_params()

        assert result['user'] == 'env_test_user'

        # Clear cache to test different environment
        database_instance._Database__connection_params_cache = None

        # Test when USER env var is not set
        with patch.object(Database, '_load_configuration', return_value=None):
            with patch.dict(os.environ, {}, clear=True):
                result = database_instance._get_connection_params()

        assert result['user'] == ''  # Empty string when USER not available

    def test_get_connection_params_return_type_consistency(self, database_instance):
        """Test that return types are always consistent."""
        config = {
            'name': 'test_database',
            'user': 'test_user',
            'password': 'test_pass',
            'host': 'localhost',
            'port': 5432,
            'production': True
        }

        with patch.object(Database, '_load_configuration', return_value=config):
            result = database_instance._get_connection_params()

        # Verify all types are correct and consistent
        assert isinstance(result['name'], str)
        assert isinstance(result['user'], str)
        assert isinstance(result['password'], str)
        assert isinstance(result['host'], str)
        assert isinstance(result['port'], int)
        assert isinstance(result['production'], bool)
