"""
Tests for Database.setup_database() classmethod

Comprehensive unit tests covering:
- Parameter collection from CLI options vs interactive prompts  
- Database creation with create_db flag
- Metadata installation with add_metadata flag
- Configuration file saving to HALFORM_CONF_DIR
- Error handling for connection, creation, and metadata installation
- Direct Database functionality without DbConn dependency
"""

import pytest
import os
import unittest.mock
from unittest.mock import Mock, patch, MagicMock, call
from configparser import ConfigParser
from psycopg2 import OperationalError

from half_orm_dev.database import Database


class TestDatabaseSetup:
    """Test Database.setup_database() classmethod functionality."""

    @pytest.fixture
    def basic_connection_options(self):
        """Basic connection parameters for testing."""
        return {
            'host': 'localhost',
            'port': 5432,
            'user': 'testuser',
            'password': 'testpass',
            'production': False
        }

    @pytest.fixture  
    def production_connection_options(self):
        """Production connection parameters."""
        return {
            'host': 'prod.db.com',
            'port': 5432,
            'user': 'produser', 
            'password': 'prodpass',
            'production': True
        }

    @pytest.fixture
    def minimal_connection_options(self):
        """Minimal connection options requiring prompts."""
        return {
            'host': 'localhost',
            'port': 5432,
            'user': None,  # Should prompt
            'password': None,  # Should prompt  
            'production': False
        }

    @patch('half_orm_dev.database.Model')
    def test_setup_database_with_all_parameters(self, mock_model, basic_connection_options):
        """Test setup_database with complete CLI parameters - no prompts needed."""
        # Setup mocks
        mock_model_instance = Mock()
        mock_model.return_value = mock_model_instance

        # Call method (should not prompt for anything)
        Database.setup_database(
            database_name="test_db",
            connection_options=basic_connection_options,
            create_db=False,
            add_metadata=False
        )

        # Verify Model was created
        mock_model.assert_called_once_with("test_db")

    @patch('half_orm_dev.database.Database._collect_connection_params')
    @patch('half_orm_dev.database.Model')
    def test_setup_database_with_missing_parameters_prompts(self, mock_model, mock_collect_params, minimal_connection_options):
        """Test setup_database prompts for missing parameters."""
        # Setup mocks
        mock_collect_params.return_value = {
            'host': 'localhost',
            'port': 5432,
            'user': 'prompted_user',
            'password': 'prompted_pass',
            'production': False
        }
        mock_model_instance = Mock()
        mock_model.return_value = mock_model_instance

        # Call method (should prompt for missing user/password)
        Database.setup_database(
            database_name="test_db",
            connection_options=minimal_connection_options,
            create_db=False,
            add_metadata=False
        )

        # Verify prompting was called
        mock_collect_params.assert_called_once_with("test_db", minimal_connection_options)

    @patch('half_orm_dev.database.Database._save_configuration')
    @patch('half_orm_dev.database.Model')
    def test_setup_database_saves_configuration(self, mock_model, mock_save_config, basic_connection_options):
        """Test configuration file is saved to HALFORM_CONF_DIR."""
        mock_save_config.return_value = "/path/to/config/test_db"
        mock_model_instance = Mock()
        mock_model.return_value = mock_model_instance

        Database.setup_database(
            database_name="test_db",
            connection_options=basic_connection_options,
            create_db=False,
            add_metadata=False
        )

        # Verify configuration was saved
        mock_save_config.assert_called_once_with("test_db", basic_connection_options)

    @patch('half_orm_dev.database.Database._save_configuration')
    @patch('half_orm_dev.database.Model')
    def test_setup_database_registers_initial_release(self, mock_model, mock_save_config, basic_connection_options):
        """Test initial release 0.0.0 registration when metadata is installed."""
        mock_save_config.return_value = "/path/to/config/test_db"
        mock_model_instance = Mock()
        mock_model.return_value = mock_model_instance

        # Mock relation class for release registration
        mock_release_class = Mock()
        mock_model_instance.get_relation_class.return_value = mock_release_class
        mock_release_instance = Mock()
        mock_release_class.return_value = mock_release_instance

        Database.setup_database(
            database_name="test_db",
            connection_options=basic_connection_options,
            create_db=True,
            add_metadata=True
        )

        # Should register initial release 0.0.0
        # This will be implemented similar to existing register_release method
        expected_calls = [
            call('half_orm_meta.hop_release'),
            # May have other calls for metadata checking
        ]
        mock_model_instance.get_relation_class.assert_has_calls(expected_calls, any_order=True)

    @patch('half_orm_dev.database.Database._save_configuration')
    @patch('half_orm_dev.database.Model')
    def test_setup_database_connection_error(self, mock_model, mock_save_config, basic_connection_options):
        """Test handling of database connection errors."""
        mock_save_config.return_value = "/path/to/config/unreachable_db"

        # Model initialization should fail
        mock_model.side_effect = OperationalError("Connection failed")

        with pytest.raises(OperationalError):
            Database.setup_database(
                database_name="unreachable_db",
                connection_options=basic_connection_options,
                create_db=False,  # Don't try to create
                add_metadata=False
            )

    @patch('half_orm_dev.database.Database._execute_pg_command')
    @patch('half_orm_dev.database.Database._save_configuration')
    @patch('half_orm_dev.database.Model')  
    def test_setup_database_creation_error(self, mock_model, mock_save_config, mock_execute_pg, basic_connection_options):
        """Test handling of database creation errors."""
        mock_save_config.return_value = "/path/to/config/creation_fail_db"

        # First Model call fails (no database), createdb fails, second Model call still fails
        mock_model.side_effect = [OperationalError("database does not exist"), OperationalError("still no database")]
        mock_execute_pg.side_effect = Exception("createdb failed")

        with pytest.raises(Exception):
            Database.setup_database(
                database_name="creation_fail_db", 
                connection_options=basic_connection_options,
                create_db=True,
                add_metadata=False
            )

    @pytest.mark.skip(reason="Error handling for metadata installation not implemented yet")
    @patch('half_orm_dev.database.Database._execute_pg_command')
    @patch('half_orm_dev.database.Database._save_configuration')
    @patch('half_orm_dev.database.Model')
    def test_setup_database_metadata_installation_error(self, mock_model, mock_save_config, mock_execute_pg, basic_connection_options):
        """Test handling of metadata installation errors."""
        mock_save_config.return_value = "/path/to/config/metadata_fail_db"
        mock_model_instance = Mock()
        mock_model.return_value = mock_model_instance

        # Metadata installation command fails
        mock_execute_pg.side_effect = Exception("Could not install metadata")

        with pytest.raises(Exception):
            Database.setup_database(
                database_name="metadata_fail_db",
                connection_options=basic_connection_options,
                create_db=False,
                add_metadata=True
            )

    def test_setup_database_parameter_validation(self):
        """Test parameter validation for setup_database."""
        # Test database name validation
        with pytest.raises(ValueError, match="Database name cannot be None"):
            Database.setup_database(
                database_name=None,  # None name  
                connection_options={},
                create_db=False,
                add_metadata=False
            )

        with pytest.raises(ValueError, match="Database name cannot be empty"):
            Database.setup_database(
                database_name="",  # Empty name
                connection_options={},
                create_db=False,
                add_metadata=False
            )

        with pytest.raises(ValueError, match="Database name cannot be empty"):
            Database.setup_database(
                database_name="   ",  # Whitespace only
                connection_options={},
                create_db=False,
                add_metadata=False
            )

        with pytest.raises(ValueError, match="must be a string"):
            Database.setup_database(
                database_name=123,  # Not a string
                connection_options={},
                create_db=False,
                add_metadata=False
            )

        with pytest.raises(ValueError, match="contains invalid characters"):
            Database.setup_database(
                database_name="db@name!",  # Invalid characters
                connection_options={},
                create_db=False,
                add_metadata=False
            )

        with pytest.raises(ValueError, match="cannot start with a digit"):
            Database.setup_database(
                database_name="9database",  # Starts with digit
                connection_options={},
                create_db=False,
                add_metadata=False
            )

    def test_setup_database_invalid_connection_options(self):
        """Test handling of invalid connection options."""
        with pytest.raises(TypeError, match="Connection options cannot be None"):
            Database.setup_database(
                database_name="test_db",
                connection_options=None,
                create_db=False,
                add_metadata=False
            )

        with pytest.raises(TypeError, match="must be a dictionary"):
            Database.setup_database(
                database_name="test_db", 
                connection_options="not_a_dict",
                create_db=False,
                add_metadata=False
            )

        with pytest.raises(ValueError, match="Unexpected connection options"):
            Database.setup_database(
                database_name="test_db",
                connection_options={'host': 'localhost', 'invalid_key': 'value'},
                create_db=False,
                add_metadata=False
            )

        with pytest.raises(ValueError, match="Port must be an integer between 1 and 65535"):
            Database.setup_database(
                database_name="test_db",
                connection_options={'port': 70000},  # Invalid port
                create_db=False,
                add_metadata=False
            )

        with pytest.raises(ValueError, match="Port must be an integer between 1 and 65535"):
            Database.setup_database(
                database_name="test_db", 
                connection_options={'port': -1},  # Negative port
                create_db=False,
                add_metadata=False
            )

        with pytest.raises(ValueError, match="Production flag must be boolean"):
            Database.setup_database(
                database_name="test_db",
                connection_options={'production': 'true'},  # String instead of bool
                create_db=False,
                add_metadata=False
            )

    @pytest.mark.skip(reason="Database creation and metadata installation not implemented yet")
    @patch('half_orm_dev.database.Database._save_configuration')
    @patch('half_orm_dev.database.Model')
    def test_setup_database_both_create_and_add_metadata(self, mock_model, mock_save_config, basic_connection_options):
        """Test setup_database with both create_db=True and add_metadata=True."""
        mock_save_config.return_value = "/path/to/config/full_setup_db"
        
        # First Model fails (no DB), then succeeds after creation
        mock_model.side_effect = [OperationalError("database does not exist"), Mock()]

        Database.setup_database(
            database_name="full_setup_db",
            connection_options=basic_connection_options,
            create_db=True,
            add_metadata=True
        )

        # Should call Model twice: once to check, once after creation
        assert mock_model.call_count == 2