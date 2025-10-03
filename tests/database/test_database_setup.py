"""
Tests for Database.setup_database() classmethod - Updated for automatic metadata installation

Comprehensive unit tests covering:
- Automatic metadata installation when create_db=True (NEW BEHAVIOR)
- Parameter collection from CLI options vs interactive prompts
- Database creation with create_db flag
- Explicit metadata installation with add_metadata flag
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
    def test_setup_database_with_all_parameters_no_creation(self, mock_model, basic_connection_options):
        """Test setup_database with complete CLI parameters - existing database, no metadata."""
        # Setup mocks
        mock_model_instance = Mock()
        mock_model.return_value = mock_model_instance

        # Call method (should not prompt for anything, no database creation)
        Database.setup_database(
            database_name="test_db",
            connection_options=basic_connection_options,
            create_db=False,
            add_metadata=False
        )

        # Verify Model was created once (no database creation)
        mock_model.assert_called_once_with("test_db")

        # Verify no metadata installation attempted
        mock_model_instance.get_relation_class.assert_not_called()

    @patch('half_orm_dev.database.Database._execute_pg_command')
    @patch('half_orm_dev.database.Database._save_configuration')
    @patch('half_orm_dev.database.Model')
    def test_setup_database_create_db_auto_installs_metadata(self, mock_model, mock_save_config, mock_execute_pg, basic_connection_options):
        """Test NEW BEHAVIOR: create_db=True automatically installs metadata."""
        mock_save_config.return_value = "/path/to/config/new_db"

        # First Model fails (no DB), then succeeds after creation
        mock_model_instance = Mock()
        mock_model.side_effect = [OperationalError("database does not exist"), mock_model_instance]

        # Mock metadata installation - setup proper mock chain
        from half_orm.model_errors import UnknownRelation
        mock_release_class = Mock()
        mock_release_instance = Mock()
        mock_release_class.return_value = mock_release_instance

        # First call raises UnknownRelation (no metadata), second call returns release class
        def mock_get_relation_class(relation_name):
            if relation_name == 'half_orm_meta.hop_release':
                if mock_model_instance.get_relation_class.call_count == 1:
                    raise UnknownRelation("half_orm_meta.hop_release not found")
                else:
                    return mock_release_class
            return Mock()

        mock_model_instance.get_relation_class.side_effect = mock_get_relation_class

        Database.setup_database(
            database_name="new_db",
            connection_options=basic_connection_options,
            create_db=True,  # NEW: Should automatically install metadata
            add_metadata=False  # Explicit False, but should be overridden by create_db=True
        )

        # Should call Model twice: once to check, once after creation
        assert mock_model.call_count == 2

        # Should execute createdb command
        mock_execute_pg.assert_any_call("new_db", basic_connection_options, 'createdb', 'new_db')

        # Should execute psql command for metadata installation (automatic)
        mock_execute_pg.assert_any_call(
            "new_db", basic_connection_options, 'psql', '-d', 'new_db', '-f', unittest.mock.ANY
        )

        # Should register initial release 0.0.0
        mock_release_instance.ho_insert.assert_called_once()

    @patch('half_orm_dev.database.Database._execute_pg_command')
    @patch('half_orm_dev.database.Database._save_configuration')
    @patch('half_orm_dev.database.Model')
    def test_setup_database_existing_db_explicit_metadata(self, mock_model, mock_save_config, mock_execute_pg, basic_connection_options):
        """Test explicit metadata installation on existing database."""
        mock_save_config.return_value = "/path/to/config/existing_db"
        mock_model_instance = Mock()
        mock_model.return_value = mock_model_instance

        # Mock metadata installation for existing database
        from half_orm.model_errors import UnknownRelation
        mock_release_class = Mock()
        mock_release_instance = Mock()
        mock_release_class.return_value = mock_release_instance

        # First call raises UnknownRelation (no metadata), second call returns release class
        def mock_get_relation_class(relation_name):
            if relation_name == 'half_orm_meta.hop_release':
                if mock_model_instance.get_relation_class.call_count == 1:
                    raise UnknownRelation("half_orm_meta.hop_release not found")
                else:
                    return mock_release_class
            return Mock()

        mock_model_instance.get_relation_class.side_effect = mock_get_relation_class

        Database.setup_database(
            database_name="existing_db",
            connection_options=basic_connection_options,
            create_db=False,  # Existing database
            add_metadata=True  # Explicit metadata installation
        )

        # Should call Model only once (existing database)
        mock_model.assert_called_once_with("existing_db")

        # Should NOT execute createdb
        createdb_calls = [call for call in mock_execute_pg.call_args_list if 'createdb' in call[0]]
        assert len(createdb_calls) == 0

        # Should execute psql command for metadata installation
        mock_execute_pg.assert_called_once()
        psql_call = mock_execute_pg.call_args_list[0]
        assert 'psql' in psql_call[0]
        assert '-d' in psql_call[0]
        assert 'existing_db' in psql_call[0]

        # Should register initial release
        mock_release_instance.ho_insert.assert_called_once()

    @patch('half_orm_dev.database.Database._save_configuration')
    @patch('half_orm_dev.database.Model')
    def test_setup_database_existing_db_with_metadata_skip_installation(self, mock_model, mock_save_config, basic_connection_options):
        """Test skipping metadata installation when it already exists."""
        mock_save_config.return_value = "/path/to/config/metadata_exists_db"
        mock_model_instance = Mock()
        mock_model.return_value = mock_model_instance

        # Mock metadata already exists
        mock_release_class = Mock()
        mock_model_instance.get_relation_class.return_value = mock_release_class

        Database.setup_database(
            database_name="metadata_exists_db",
            connection_options=basic_connection_options,
            create_db=False,
            add_metadata=True  # Requested, but metadata already exists
        )

        # Should call Model once
        mock_model.assert_called_once_with("metadata_exists_db")

        # Should check for metadata existence
        mock_model_instance.get_relation_class.assert_called_once_with('half_orm_meta.hop_release')

        # Should NOT call ho_insert (no new release registration needed)
        mock_release_class.return_value.ho_insert.assert_not_called()

    @patch('half_orm_dev.database.Database._execute_pg_command')
    @patch('half_orm_dev.database.Database._save_configuration')
    @patch('half_orm_dev.database.Model')
    def test_setup_database_create_db_true_add_metadata_false_still_installs(self, mock_model, mock_save_config, mock_execute_pg, basic_connection_options):
        """Test precedence: create_db=True overrides add_metadata=False."""
        mock_save_config.return_value = "/path/to/config/precedence_db"

        # First Model fails (no DB), then succeeds after creation
        mock_model_instance = Mock()
        mock_model.side_effect = [OperationalError("database does not exist"), mock_model_instance]

        # Mock metadata installation
        from half_orm.model_errors import UnknownRelation
        mock_release_class = Mock()
        mock_release_instance = Mock()
        mock_release_class.return_value = mock_release_instance

        # Setup proper mock chain for get_relation_class
        def mock_get_relation_class(relation_name):
            if relation_name == 'half_orm_meta.hop_release':
                if mock_model_instance.get_relation_class.call_count == 1:
                    raise UnknownRelation("half_orm_meta.hop_release not found")
                else:
                    return mock_release_class
            return Mock()

        mock_model_instance.get_relation_class.side_effect = mock_get_relation_class

        Database.setup_database(
            database_name="precedence_db",
            connection_options=basic_connection_options,
            create_db=True,      # Should force metadata installation
            add_metadata=False   # Explicit False should be overridden
        )

        # Should still install metadata despite add_metadata=False
        assert mock_execute_pg.call_count >= 2  # createdb + psql for metadata

        # Verify createdb was called
        createdb_calls = [call for call in mock_execute_pg.call_args_list if 'createdb' in call[0]]
        assert len(createdb_calls) == 1

        # Verify psql was called
        psql_calls = [call for call in mock_execute_pg.call_args_list if 'psql' in call[0]]
        assert len(psql_calls) == 1

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

    # NEW TESTS for automatic metadata behavior

    @patch('half_orm_dev.database.Database._execute_pg_command')
    @patch('half_orm_dev.database.Database._save_configuration')
    @patch('half_orm_dev.database.Model')
    def test_setup_database_automatic_metadata_logic(self, mock_model, mock_save_config, mock_execute_pg, basic_connection_options):
        """Test the automatic metadata installation logic for new databases."""
        mock_save_config.return_value = "/path/to/config/auto_metadata_db"

        # Simulate database creation scenario
        mock_model_instance = Mock()
        mock_model.side_effect = [OperationalError("database does not exist"), mock_model_instance]

        # Mock metadata installation
        from half_orm.model_errors import UnknownRelation
        mock_release_class = Mock()
        mock_release_instance = Mock()
        mock_release_class.return_value = mock_release_instance

        # Setup proper mock chain for get_relation_class
        def mock_get_relation_class(relation_name):
            if relation_name == 'half_orm_meta.hop_release':
                if mock_model_instance.get_relation_class.call_count == 1:
                    raise UnknownRelation("half_orm_meta.hop_release not found")
                else:
                    return mock_release_class
            return Mock()

        mock_model_instance.get_relation_class.side_effect = mock_get_relation_class

        Database.setup_database(
            database_name="auto_metadata_db",
            connection_options=basic_connection_options,
            create_db=True,
            # add_metadata not specified - should default to False but be overridden
        )

        # Verify automatic metadata installation occurred
        psql_calls = [call for call in mock_execute_pg.call_args_list if 'psql' in call[0]]
        assert len(psql_calls) == 1, "Should have executed psql for metadata installation"

        # Verify correct SQL file path
        psql_call = psql_calls[0]
        assert '-f' in psql_call[0], "Should include -f flag for SQL file"
        sql_file_path = psql_call[0][psql_call[0].index('-f') + 1]
        assert 'half_orm_meta.sql' in sql_file_path, "Should reference half_orm_meta.sql file"

        # Verify initial release registration
        mock_release_instance.ho_insert.assert_called_once()

    @patch('half_orm_dev.database.Database._save_configuration')
    @patch('half_orm_dev.database.Model')
    def test_setup_database_no_metadata_for_existing_db_default(self, mock_model, mock_save_config, basic_connection_options):
        """Test that existing database without explicit add_metadata=True gets no metadata."""
        mock_save_config.return_value = "/path/to/config/existing_no_metadata"
        mock_model_instance = Mock()
        mock_model.return_value = mock_model_instance

        Database.setup_database(
            database_name="existing_no_metadata",
            connection_options=basic_connection_options,
            create_db=False,
            add_metadata=False  # Explicit False for existing database
        )

        # Should not attempt metadata installation
        mock_model_instance.get_relation_class.assert_not_called()
