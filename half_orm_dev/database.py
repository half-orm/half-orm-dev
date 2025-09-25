"""Provides the Database class
"""

import os
import subprocess
import sys

from psycopg2 import OperationalError
from half_orm.model import Model
from half_orm.model_errors import UnknownRelation
from half_orm import utils
from half_orm_dev.db_conn import DbConn
from .utils import HOP_PATH


class Database:
    """Reads and writes the halfORM connection file
    """

    def __init__(self, repo, get_release=True):
        self.__repo = repo
        self.__model = None
        self.__last_release = None
        self.__connection_params: DbConn = DbConn(self.__repo.name)
        if self.__repo.name:
            try:
                self.__model = Model(self.__repo.name)
                self.__init(self.__repo.name, get_release)
            except OperationalError as err:
                if not self.__repo.new:
                    utils.error(err, 1)

    def __call__(self, name):
        return self.__class__(self.__repo)

    def __init(self, name, get_release=True):
        self.__name = name
        self.__connection_params = DbConn(name)
        if get_release and self.__repo.devel:
            self.__last_release = self.last_release

    @property
    def last_release(self):
        "Returns the last release"
        self.__last_release = next(
            self.__model.get_relation_class('half_orm_meta.view.hop_last_release')().ho_select())
        return self.__last_release

    @property
    def last_release_s(self):
        "Returns the string representation of the last release X.Y.Z"
        return '{major}.{minor}.{patch}'.format(**self.last_release)

    @property
    def model(self):
        "The model (halfORM) of the database"
        return self.__model

    @property
    def state(self):
        "The state (str) of the database"
        res = ['[Database]']
        res.append(f'- name: {self.__name}')
        res.append(f'- user: {self.__connection_params.user}')
        res.append(f'- host: {self.__connection_params.host}')
        res.append(f'- port: {self.__connection_params.port}')
        prod = utils.Color.blue(
            True) if self.__connection_params.production else False
        res.append(f'- production: {prod}')
        if self.__repo.devel:
            res.append(f'- last release: {self.last_release_s}')
        return '\n'.join(res)

    @property
    def production(self):
        "Returns wether the database is tagged in production or not."
        return self.__connection_params.production

    def init(self, name):
        """Called when creating a new repo.
        Tries to read the connection parameters and then connect to
        the database.
        """
        try:
            self.__init(name, get_release=False)
        except FileNotFoundError:
            pass
        return self.__init_db()

    def __init_db(self):
        """Tries to connect to the database. If unsuccessful, creates the
        database end initializes it with half_orm_meta.
        """
        try:
            self.__model = Model(self.__name)
        except OperationalError:
            sys.stderr.write(f"The database '{self.__name}' does not exist.\n")
            create = input('Do you want to create it (Y/n): ') or "y"
            if create.upper() == 'Y':
                self.execute_pg_command('createdb')
            else:
                utils.error(
                    f'Aborting! Please remove {self.__name} directory.\n', exit_code=1)
        self.__model = Model(self.__name)
        if self.__repo.devel:
            try:
                self.__model.get_relation_class('half_orm_meta.hop_release')
            except UnknownRelation:
                hop_init_sql_file = os.path.join(
                    HOP_PATH, 'patches', 'sql', 'half_orm_meta.sql')
                self.execute_pg_command(
                    'psql', '-f', hop_init_sql_file, stdout=subprocess.DEVNULL)
                self.__model.reconnect(reload=True)
                self.__last_release = self.register_release(
                    major=0, minor=0, patch=0, changelog='Initial release')
        return self(self.__name)

    @property
    def execute_pg_command(self):
        "Helper: execute a postgresql command"
        return self.__connection_params.execute_pg_command

    def register_release(self, major, minor, patch, changelog):
        "Register the release into half_orm_meta.hop_release"
        return self.__model.get_relation_class('half_orm_meta.hop_release')(
            major=major, minor=minor, patch=patch, changelog=changelog
        ).ho_insert()

    @classmethod
    def setup_database(cls, database_name, connection_options, create_db=False, add_metadata=False):
        """
        Configure database connection and install half-orm metadata schemas.

        Replaces the interactive __init_db() method with a non-interactive version
        that accepts connection parameters from CLI options or prompts for missing ones.

        Args:
            database_name (str): PostgreSQL database name
            connection_options (dict): Connection parameters from CLI
                - host (str): PostgreSQL host (default: localhost)
                - port (int): PostgreSQL port (default: 5432)  
                - user (str): Database user (default: $USER)
                - password (str): Database password (prompts if None)
                - production (bool): Production environment flag
            create_db (bool): Create database if it doesn't exist
            add_metadata (bool): Add half_orm_meta schemas to existing database

        Returns:
            None: Configuration saved to $HALFORM_CONF_DIR/<database_name> (or /etc/half_orm/<database_name>)

        Raises:
            DatabaseConnectionError: If connection to PostgreSQL fails
            DatabaseCreationError: If database creation fails
            MetadataInstallationError: If metadata schema installation fails

        Process Flow:
            1. Parameter Collection: Use provided options or prompt for missing ones
            2. Connection Test: Verify PostgreSQL connection with provided credentials  
            3. Database Setup: Create database if create_db=True, or connect to existing
            4. Metadata Installation: Add half_orm_meta and half_orm_meta.view schemas
            5. Configuration Save: Store connection parameters in $HALFORM_CONF_DIR/<database_name> or /etc/half_orm/<database_name>
            6. Initial Release: Register version 0.0.0 in metadata

        Examples:
            # Create new database with metadata
            Database.setup_database(
                database_name="my_blog_db",
                connection_options={'host': 'localhost', 'user': 'dev', 'password': 'secret'},
                create_db=True,
                add_metadata=True
            )

            # Add metadata to existing database  
            Database.setup_database(
                database_name="legacy_db", 
                connection_options={'host': 'prod.db.com', 'user': 'admin'},
                create_db=False,
                add_metadata=True  
            )

            # Interactive prompts for missing parameters
            Database.setup_database(
                database_name="dev_db",
                connection_options={'host': 'localhost'},  # Missing user/password -> prompts
                create_db=True
            )
        """
        # TODO: Implementation in TDD Phase 3
        # This method will replace the interactive logic from __init_db()
        # and provide non-interactive database setup with CLI parameters

        # Step 1: Validate input parameters
        cls._validate_parameters(database_name, connection_options)

        # TODO: Other steps to be implemented
        pass

    @classmethod
    def _validate_parameters(cls, database_name, connection_options):
        """
        Validate input parameters for database setup.

        Args:
            database_name (str): PostgreSQL database name
            connection_options (dict): Connection parameters from CLI

        Raises:
            ValueError: If database_name is invalid
            TypeError: If connection_options is not a dict

        Returns:
            None: Parameters are valid

        Examples:
            # Valid parameters
            Database._validate_parameters("my_db", {'host': 'localhost'})

            # Invalid database name
            Database._validate_parameters("", {})  # Raises ValueError
            Database._validate_parameters(None, {})  # Raises ValueError

            # Invalid connection options
            Database._validate_parameters("my_db", None)  # Raises TypeError
        """
        # Validate database_name
        if database_name is None:
            raise ValueError("Database name cannot be None")

        if not isinstance(database_name, str):
            raise ValueError(f"Database name must be a string, got {type(database_name).__name__}")

        if database_name.strip() == "":
            raise ValueError("Database name cannot be empty")

        # Basic name format validation (PostgreSQL identifier rules)
        database_name = database_name.strip()
        if not database_name.replace('_', '').replace('-', '').isalnum():
            raise ValueError(f"Database name '{database_name}' contains invalid characters. Use only letters, numbers, underscore, and hyphen.")

        if database_name[0].isdigit():
            raise ValueError(f"Database name '{database_name}' cannot start with a digit")

        # Validate connection_options
        if connection_options is None:
            raise TypeError("Connection options cannot be None")

        if not isinstance(connection_options, dict):
            raise TypeError(f"Connection options must be a dictionary, got {type(connection_options).__name__}")

        # Expected option keys (some may be None/missing for interactive prompts)
        expected_keys = {'host', 'port', 'user', 'password', 'production'}
        provided_keys = set(connection_options.keys())

        # Check for unexpected keys
        unexpected_keys = provided_keys - expected_keys
        if unexpected_keys:
            raise ValueError(f"Unexpected connection options: {sorted(unexpected_keys)}. Expected: {sorted(expected_keys)}")

        # Validate port if provided
        if 'port' in connection_options and connection_options['port'] is not None:
            port = connection_options['port']
            if not isinstance(port, int) or port <= 0 or port > 65535:
                raise ValueError(f"Port must be an integer between 1 and 65535, got {port}")

        # Validate production flag if provided  
        if 'production' in connection_options and connection_options['production'] is not None:
            production = connection_options['production']
            if not isinstance(production, bool):
                raise ValueError(f"Production flag must be boolean, got {type(production).__name__}")