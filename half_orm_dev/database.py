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
    def _save_configuration(cls, database_name, connection_params):
        """
        Save connection parameters to configuration file.

        Args:
            database_name (str): PostgreSQL database name
            connection_params (dict): Complete connection parameters

        Returns:
            str: Path to saved configuration file

        Raises:
            OSError: If configuration directory is not writable
        """
        from configparser import ConfigParser
        from half_orm.model import CONF_DIR

        # Ensure configuration directory exists and is writable
        if not os.path.exists(CONF_DIR):
            os.makedirs(CONF_DIR, exist_ok=True)

        if not os.access(CONF_DIR, os.W_OK):
            raise OSError(f"Configuration directory {CONF_DIR} is not writable")

        # Create configuration file path
        config_file = os.path.join(CONF_DIR, database_name)

        # Create and populate configuration
        config = ConfigParser()
        config.add_section('database')
        config.set('database', 'name', database_name)
        config.set('database', 'user', connection_params['user'])
        config.set('database', 'password', connection_params['password'] or '')
        config.set('database', 'host', connection_params['host'])
        config.set('database', 'port', str(connection_params['port']))
        config.set('database', 'production', str(connection_params['production']))

        # Write configuration file
        with open(config_file, 'w') as f:
            config.write(f)

        return config_file

    @classmethod
    def _execute_pg_command(cls, database_name, connection_params, *command_args):
        """
        Execute PostgreSQL command with connection parameters.

        Args:
            database_name (str): PostgreSQL database name
            connection_params (dict): Connection parameters
            *command_args: PostgreSQL command arguments

        Returns:
            subprocess.CompletedProcess: Command execution result

        Raises:
            subprocess.CalledProcessError: If PostgreSQL command fails
        """
        # Prepare environment variables for PostgreSQL commands
        env = os.environ.copy()
        env['PGUSER'] = connection_params['user']
        env['PGHOST'] = connection_params['host']
        env['PGPORT'] = str(connection_params['port'])

        # Set password if provided (use PGPASSWORD environment variable)
        if connection_params.get('password'):
            env['PGPASSWORD'] = connection_params['password']

        # Execute PostgreSQL command
        result = subprocess.run(
            command_args,
            env=env,
            capture_output=True,
            text=True,
            check=True
        )

        return result

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
            str: Path to saved configuration file

        Raises:
            DatabaseConnectionError: If connection to PostgreSQL fails
            DatabaseCreationError: If database creation fails
            MetadataInstallationError: If metadata schema installation fails

        Process Flow:
            1. Parameter Collection: Use provided options or prompt for missing ones
            2. Connection Test: Verify PostgreSQL connection with provided credentials  
            3. Database Setup: Create database if create_db=True, or connect to existing
            4. Metadata Installation: Add half_orm_meta and half_orm_meta.view schemas
            5. Configuration Save: Store connection parameters in configuration file
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
        # Step 1: Validate input parameters
        cls._validate_parameters(database_name, connection_options)

        # Step 2: Collect connection parameters  
        complete_params = cls._collect_connection_params(database_name, connection_options)

        # Step 3: Save configuration to file
        config_file = cls._save_configuration(database_name, complete_params)

        # Step 4: Test database connection (create if needed)
        try:
            model = Model(database_name)
        except OperationalError:
            if create_db:
                # Create database using PostgreSQL createdb command
                cls._execute_pg_command(database_name, complete_params, 'createdb', database_name)
                # Retry connection after creation
                model = Model(database_name)
            else:
                raise OperationalError(f"Database '{database_name}' does not exist and create_db=False")

        # Step 5: Install metadata if requested
        if add_metadata:
            try:
                model.get_relation_class('half_orm_meta.hop_release')
                # Metadata already exists
            except UnknownRelation:
                # Install metadata schemas
                hop_init_sql_file = os.path.join(HOP_PATH, 'patches', 'sql', 'half_orm_meta.sql')
                cls._execute_pg_command(
                    database_name, 
                    complete_params, 
                    'psql', 
                    '-d', database_name,
                    '-f', hop_init_sql_file
                )
                model.reconnect(reload=True)

                # Register initial release 0.0.0
                release_class = model.get_relation_class('half_orm_meta.hop_release')
                release_class(
                    major=0, minor=0, patch=0, changelog='Initial release'
                ).ho_insert()

        return config_file

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

    @classmethod
    def _collect_connection_params(cls, database_name, connection_options):
        """
        Collect missing connection parameters interactively.

        Takes partial connection parameters from CLI options and prompts
        interactively for any missing or None values. Applies halfORM
        standard defaults where appropriate.

        Args:
            database_name (str): PostgreSQL database name for context
            connection_options (dict): Partial connection parameters from CLI
                - host (str|None): PostgreSQL host
                - port (int|None): PostgreSQL port  
                - user (str|None): Database user
                - password (str|None): Database password
                - production (bool|None): Production environment flag

        Returns:
            dict: Complete connection parameters ready for DbConn initialization
                - host (str): PostgreSQL host (default: 'localhost')
                - port (int): PostgreSQL port (default: 5432)
                - user (str): Database user (default: $USER env var)
                - password (str): Database password (prompted if None)
                - production (bool): Production flag (default: False)

        Raises:
            KeyboardInterrupt: If user cancels interactive prompts
            EOFError: If input stream is closed during prompts

        Interactive Behavior:
            - Only prompts for missing/None parameters
            - Shows current defaults in prompts: "Host (localhost): "
            - Uses getpass for secure password input
            - Allows empty input to accept defaults
            - Confirms production flag if True

        Examples:
            # Complete parameters provided - no prompts
            complete = Database._collect_connection_params(
                "my_db",
                {'host': 'localhost', 'port': 5432, 'user': 'dev', 'password': 'secret', 'production': False}
            )
            # Returns: same dict (no interaction needed)

            # Missing user and password - prompts interactively
            complete = Database._collect_connection_params(
                "my_db", 
                {'host': 'localhost', 'port': 5432, 'user': None, 'password': None, 'production': False}
            )
            # Prompts: "User (current_user): " and "Password: [hidden]"
            # Returns: {'host': 'localhost', 'port': 5432, 'user': 'prompted_user', 'password': 'prompted_pass', 'production': False}

            # Only host provided - prompts for missing with defaults
            complete = Database._collect_connection_params(
                "my_db",
                {'host': 'prod.db.com'}
            )
            # Prompts: "Port (5432): ", "User (current_user): ", "Password: "
            # Returns: complete dict with provided host and prompted/default values

            # Production flag confirmation
            complete = Database._collect_connection_params(
                "prod_db",
                {'host': 'prod.db.com', 'production': True}
            )
            # Prompts: "Production environment (True): " for confirmation
            # Returns: dict with confirmed production setting
        """
        import getpass
        import os

        # Create a copy to avoid modifying the original
        complete_params = connection_options.copy()

        # Interactive prompts for None values BEFORE applying defaults
        print(f"Connection parameters for database '{database_name}':")

        # Prompt for user if None
        if complete_params.get('user') is None:
            default_user = os.environ.get('USER', 'postgres')
            user_input = input(f"User ({default_user}): ").strip()
            complete_params['user'] = user_input if user_input else default_user

        # Prompt for password if None (always prompt - security requirement)
        if complete_params.get('password') is None:
            password_input = getpass.getpass("Password: ")
            if password_input == '':
                # Empty password - assume trust/ident authentication
                complete_params['password'] = None  # Explicitly None for trust mode
                complete_params['host'] = ''        # Local socket connection
                complete_params['port'] = ''        # No port for local socket
            else:
                complete_params['password'] = password_input

        # Prompt for host if None  
        if complete_params.get('host') is None:
            host_input = input("Host (localhost): ").strip()
            complete_params['host'] = host_input if host_input else 'localhost'

        # Prompt for port if None
        if complete_params.get('port') is None:
            port_input = input("Port (5432): ").strip()
            if port_input:
                try:
                    complete_params['port'] = int(port_input)
                except ValueError:
                    raise ValueError(f"Invalid port number: {port_input}")
            else:
                complete_params['port'] = 5432

        # Apply defaults for still missing parameters (no prompts needed)
        if complete_params.get('host') is None:
            complete_params['host'] = 'localhost'

        if complete_params.get('port') is None:
            complete_params['port'] = 5432

        if complete_params.get('user') is None:
            complete_params['user'] = os.environ.get('USER', 'postgres')

        if complete_params.get('production') is None:
            complete_params['production'] = False

        # Prompt for production confirmation if True (security measure)
        if complete_params.get('production') is True:
            prod_input = input(f"Production environment (True): ").strip().lower()
            if prod_input and prod_input not in ['true', 't', 'yes', 'y', '1']:
                complete_params['production'] = False

        return complete_params

    @classmethod
    def _load_configuration(cls, database_name):
        """
        Load existing database configuration file, replacing DbConn functionality.
        
        Reads halfORM configuration file and returns connection parameters as a dictionary.
        This method completely replaces DbConn.__init() logic, supporting both minimal
        configurations (PostgreSQL trust mode) and complete parameter sets.
        
        Args:
            database_name (str): Name of the database to load configuration for
            
        Returns:
            dict | None: Connection parameters dictionary with standardized keys:
                - name (str): Database name (always present)
                - user (str): Database user (defaults to $USER environment variable)  
                - password (str): Database password (empty string if not set)
                - host (str): Database host (empty string for Unix socket, 'localhost' otherwise)
                - port (int): Database port (5432 if not specified)
                - production (bool): Production environment flag (defaults to False)
            Returns None if configuration file doesn't exist.
            
        Raises:
            FileNotFoundError: If CONF_DIR doesn't exist or isn't accessible
            PermissionError: If configuration file exists but isn't readable  
            ValueError: If configuration file format is invalid or corrupted
            
        Examples:
            # Complete configuration file
            config = Database._load_configuration("production_db")
            # Returns: {'name': 'production_db', 'user': 'app_user', 'password': 'secret',
            #           'host': 'db.company.com', 'port': 5432, 'production': True}
            
            # Minimal trust mode configuration (only name=database_name)
            config = Database._load_configuration("local_dev")
            # Returns: {'name': 'local_dev', 'user': 'joel', 'password': '',  
            #           'host': '', 'port': 5432, 'production': False}
            
            # Non-existent configuration
            config = Database._load_configuration("unknown_db")
            # Returns: None
            
        Migration Notes:
            - Completely replaces DbConn.__init() and DbConn.__init logic
            - Maintains backward compatibility with existing config files
            - Standardizes return format (int for port, bool for production)
            - Integrates PostgreSQL trust mode defaults directly into Database class
            - Eliminates external DbConn dependency while preserving all functionality
        """
        pass
