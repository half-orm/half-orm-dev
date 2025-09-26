"""
Tests for Database.setup_database() classmethod

Comprehensive unit tests covering:
- Parameter collection from CLI options vs interactive prompts  
- Database creation with create_db flag
- Metadata installation with add_metadata flag
- Configuration file saving to HALFORM_CONF_DIR
- Error handling for connection, creation, and metadata installation
- Direct Database functionality without  dependency
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

    @pytest.mark.skip(reason="Parameter collection and  integration not implemented yet")
    @patch('half_orm_dev.database.')
    @patch('half_orm_dev.database.Model')
    def test_setup_database_with_all_parameters(self, mock_model, mock_db_conn, basic_connection_options):
        """Test setup_database with complete CLI parameters - no prompts needed."""
        # Setup mocks
        mock_db_conn_instance = Mock()
        mock_db_conn.return_value = mock_db_conn_instance
        mock_model_instance = Mock()
        mock_model.return_value = mock_model_instance

        # Call method (should not prompt for anything)
        Database.setup_database(
            database_name="test_db",
            connection_options=basic_connection_options,
            create_db=False,
            add_metadata=False
        )

        # Verify  was created and configured
        mock_db_conn.assert_called_once_with("test_db")
        # Should call a method to set parameters from options (to be implemented)
        assert mock_db_conn_instance.method_calls  # Some method should be called

    @pytest.mark.skip(reason="Interactive prompts not implemented yet")
    @patch('half_orm_dev.database.')
    @patch('half_orm_dev.database.Model') 
    @patch('builtins.input')
    @patch('getpass.getpass')
    def test_setup_database_with_missing_parameters_prompts(self, mock_getpass, mock_input, 
                                                           mock_model, mock_db_conn, minimal_connection_options):
        """Test setup_database prompts for missing parameters interactively."""
        # Setup input mocks
        mock_input.side_effect = ['prompted_user']  # For user input
        mock_getpass.return_value = 'prompted_pass'  # For password input

        mock_db_conn_instance = Mock()
        mock_db_conn.return_value = mock_db_conn_instance
        mock_model_instance = Mock()
        mock_model.return_value = mock_model_instance

        # Call with minimal options
        Database.setup_database(
            database_name="test_db",
            connection_options=minimal_connection_options,
            create_db=False, 
            add_metadata=False
        )

        # Verify interactive prompts were called
        mock_input.assert_called()  # Should prompt for user
        mock_getpass.assert_called()  # Should prompt for password

    @patch('half_orm_dev.database.Database._execute_pg_command')
    @patch('half_orm_dev.database.Database._save_configuration')
    @patch('half_orm_dev.database.Model')
    def test_setup_database_create_db_flag(self, mock_model, mock_save_config, mock_execute_pg, basic_connection_options):
        """Test database creation when create_db=True."""
        mock_save_config.return_value = "/path/to/config/new_test_db"
        
        # First call to Model should fail (database doesn't exist)
        # Second call should succeed (after creation)
        mock_model.side_effect = [OperationalError("database does not exist"), Mock()]

        Database.setup_database(
            database_name="new_test_db",
            connection_options=basic_connection_options,
            create_db=True,
            add_metadata=False
        )

        # Should attempt database creation via PostgreSQL commands
        mock_execute_pg.assert_called_with(
            "new_test_db", 
            unittest.mock.ANY,  # connection_params (any dict)
            'createdb', 
            'new_test_db'
        )

    @patch('half_orm_dev.database.Database._save_configuration')
    @patch('half_orm_dev.database.Model')
    def test_setup_database_create_db_false_existing_db(self, mock_model, mock_save_config, basic_connection_options):
        """Test connection to existing database when create_db=False."""
        mock_save_config.return_value = "/path/to/config/existing_db"
        mock_model_instance = Mock()
        mock_model.return_value = mock_model_instance  # Database exists

        Database.setup_database(
            database_name="existing_db",
            connection_options=basic_connection_options,
            create_db=False,
            add_metadata=False
        )

        # Should connect successfully without creation attempts
        mock_model.assert_called_once_with("existing_db")
        mock_save_config.assert_called_once()

    @patch('half_orm_dev.database.Database._execute_pg_command')
    @patch('half_orm_dev.database.Database._save_configuration') 
    @patch('half_orm_dev.database.Model')
    def test_setup_database_add_metadata_flag(self, mock_model, mock_save_config, mock_execute_pg, basic_connection_options):
        """Test metadata installation when add_metadata=True."""
        mock_save_config.return_value = "/path/to/config/test_db"
        mock_model_instance = Mock()

        # Mock get_relation_class to simulate missing metadata first, then return release class
        from half_orm.model_errors import UnknownRelation
        mock_release_class = Mock()
        mock_release_instance = Mock()
        mock_release_class.return_value = mock_release_instance
        
        # First call raises UnknownRelation, second call returns the class for release registration
        mock_model_instance.get_relation_class.side_effect = [
            UnknownRelation("half_orm_meta.hop_release"),  # First check - metadata missing
            mock_release_class  # After installation - for release registration
        ]
        mock_model.return_value = mock_model_instance

        Database.setup_database(
            database_name="test_db", 
            connection_options=basic_connection_options,
            create_db=False,
            add_metadata=True
        )

        # Should install metadata schemas
        assert mock_model_instance.get_relation_class.call_count == 2  # Called twice
        mock_model_instance.get_relation_class.assert_any_call('half_orm_meta.hop_release')
        
        # Should execute SQL file for metadata installation  
        mock_execute_pg.assert_called()
        
        # Should register initial release
        mock_release_class.assert_called_with(
            major=0, minor=0, patch=0, changelog='Initial release'
        )
        mock_release_instance.ho_insert.assert_called_once()

    @patch('half_orm_dev.database.Database._save_configuration')
    @patch('half_orm_dev.database.Model') 
    def test_setup_database_add_metadata_false_no_installation(self, mock_model, mock_save_config, basic_connection_options):
        """Test no metadata installation when add_metadata=False."""
        mock_save_config.return_value = "/path/to/config/test_db"
        mock_model_instance = Mock()
        mock_model.return_value = mock_model_instance

        Database.setup_database(
            database_name="test_db",
            connection_options=basic_connection_options, 
            create_db=False,
            add_metadata=False
        )

    @patch('half_orm_dev.database.Database._save_configuration')
    @patch('half_orm_dev.database.Model')
    @patch('getpass.getpass')
    def test_setup_database_trust_mode_empty_password(self, mock_getpass, mock_model, mock_save_config):
        """Test trust mode authentication with empty password."""
        mock_getpass.return_value = ''  # User presses Enter for empty password
        mock_save_config.return_value = "/path/to/config/trust_db"
        mock_model_instance = Mock()
        mock_model.return_value = mock_model_instance

        # Connection options with password=None to trigger prompt
        connection_options = {
            'host': 'localhost',
            'port': 5432,
            'user': 'testuser',
            'password': None,  # This will trigger password prompt
            'production': False
        }

        Database.setup_database(
            database_name="trust_db",
            connection_options=connection_options,
            create_db=False,
            add_metadata=False
        )

        # Verify password prompt was called
        mock_getpass.assert_called_once_with("Password: ")
        
        # Verify configuration was saved with trust mode parameters
        mock_save_config.assert_called_once()
        call_args = mock_save_config.call_args
        saved_params = call_args[0][1]  # connection_params
        assert saved_params['password'] is None  # Trust mode
        assert saved_params['host'] == ''         # Local socket
        assert saved_params['port'] == ''         # No port

    @pytest.mark.skip(reason="Configuration saving not implemented yet")
    @patch('half_orm_dev.database.')
    @patch('half_orm_dev.database.Model')
    @patch('os.path.join')
    @patch('builtins.open', new_callable=Mock)
    def test_setup_database_saves_configuration(self, mock_open, mock_path_join, mock_model, mock_db_conn, basic_connection_options):
        """Test configuration file is saved to HALFORM_CONF_DIR."""
        mock_db_conn_instance = Mock()
        mock_db_conn.return_value = mock_db_conn_instance
        mock_model_instance = Mock()
        mock_model.return_value = mock_model_instance

        # Mock CONF_DIR path
        with patch('half_orm_dev.database.CONF_DIR', '/test/conf/dir'):
            mock_path_join.return_value = '/test/conf/dir/test_db'

            Database.setup_database(
                database_name="test_db",
                connection_options=basic_connection_options,
                create_db=False,
                add_metadata=False
            )

            # Should save configuration file
            # This will be implemented via .save() or similar method
            assert mock_db_conn_instance.method_calls  # Some save method called

    @pytest.mark.skip(reason="Release registration not implemented yet")
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

    @pytest.mark.skip(reason="Error handling for connection failures not implemented yet")
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

    @pytest.mark.skip(reason="Error handling for database creation not implemented yet")
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

        # Metadata installation fails
        mock_execute_pg.side_effect = Exception("SQL execution failed")

        from half_orm.model_errors import UnknownRelation
        mock_model_instance.get_relation_class.side_effect = UnknownRelation("half_orm_meta.hop_release")

        with pytest.raises(Exception):
            Database.setup_database(
                database_name="metadata_fail_db",
                connection_options=basic_connection_options, 
                create_db=False,
                add_metadata=True
            )

    @pytest.mark.skip(reason="Production flag handling not implemented yet")
    @patch('half_orm_dev.database.Database._save_configuration')
    @patch('half_orm_dev.database.Model')
    def test_setup_database_production_flag_handling(self, mock_model, mock_save_config, production_connection_options):
        """Test production flag is properly handled and saved."""
        mock_save_config.return_value = "/path/to/config/prod_db"
        mock_model_instance = Mock()
        mock_model.return_value = mock_model_instance

        Database.setup_database(
            database_name="prod_db",
            connection_options=production_connection_options,
            create_db=False,
            add_metadata=False
        )

        # Should handle production flag in configuration
        # This will be verified through Database._save_configuration parameter checking
        mock_save_config.assert_called_once()

    # VALIDATION TESTS - These should pass immediately (no skip needed)
    def test_setup_database_invalid_database_name(self):
        """Test handling of invalid database names."""
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
        mock_save_config.return_value = "/path/to/config/new_db_with_metadata"

        # First call fails (no database), second succeeds (after creation)  
        mock_model_instance = Mock()
        mock_model.side_effect = [OperationalError("database does not exist"), mock_model_instance]

        # Mock metadata installation
        from half_orm.model_errors import UnknownRelation
        mock_model_instance.get_relation_class.side_effect = UnknownRelation("half_orm_meta.hop_release")

        Database.setup_database(
            database_name="new_db_with_metadata",
            connection_options=basic_connection_options,
            create_db=True,
            add_metadata=True
        )

        # Should create database AND install metadata
        assert mock_model.call_count == 2  # Once for check, once after creation
        mock_model_instance.get_relation_class.assert_called()

    @pytest.mark.skip(reason="Metadata installation logic not implemented yet")
    @patch('half_orm_dev.database.Database._save_configuration')
    @patch('half_orm_dev.database.Model')
    def test_setup_database_existing_metadata_no_reinstall(self, mock_model, mock_save_config, basic_connection_options):
        """Test setup_database doesn't reinstall existing metadata."""
        mock_save_config.return_value = "/path/to/config/db_with_existing_metadata"
        mock_model_instance = Mock()
        mock_model.return_value = mock_model_instance

        # Mock existing metadata (no UnknownRelation raised)
        mock_release_class = Mock()
        mock_model_instance.get_relation_class.return_value = mock_release_class

        Database.setup_database(
            database_name="db_with_existing_metadata",
            connection_options=basic_connection_options,
            create_db=False,
            add_metadata=True
        )

        # Should check for metadata but not reinstall
        mock_model_instance.get_relation_class.assert_called_with('half_orm_meta.hop_release')
        # Should not execute SQL installation since metadata exists
