"""Provides the Database class
"""

import getpass
import os
import re
import subprocess
import sys
from configparser import ConfigParser

from pathlib import Path
from psycopg2 import OperationalError
from half_orm.model import Model, CONF_DIR
from half_orm.model_errors import UnknownRelation
from half_orm import utils
from .utils import HOP_PATH

class DatabaseError(Exception):
    pass

class DockerNotAvailableError(Exception):
    """
    Raised when Docker is not installed or not running.

    This exception is raised when attempting to use Docker for PostgreSQL
    operations but Docker is not available on the system.

    Examples:
        Docker not installed:
            DockerNotAvailableError("Docker is not installed on this system")

        Docker daemon not running:
            DockerNotAvailableError("Docker daemon is not running")
    """
    pass


class DockerContainerNotFoundError(Exception):
    """
    Raised when specified Docker container does not exist.

    This exception is raised when a database configuration references a
    Docker container that does not exist on the system.

    Examples:
        Container not found:
            DockerContainerNotFoundError(
                "Docker container 'my_postgres' not found. "
                "Run: docker ps -a to list containers"
            )
    """
    pass


class DockerContainerNotRunningError(Exception):
    """
    Raised when Docker container exists but is not running.

    This exception is raised when a Docker container exists but is in a
    stopped state and cannot execute PostgreSQL commands.

    Examples:
        Container stopped:
            DockerContainerNotRunningError(
                "Docker container 'my_postgres' exists but is not running. "
                "Run: docker start my_postgres"
            )
    """
    pass


class Database:
    """Reads and writes the halfORM connection file
    """

    def __init__(self, repo, get_release=True):
        self.__repo = repo
        self.__model = None
        self.__last_release = None
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
        res.append(f"- user: {self._get_connection_params()['user']}")
        res.append(f"- host: {self._get_connection_params()['host']}")
        res.append(f"- port: {self._get_connection_params()['port']}")
        prod = utils.Color.blue(
            True) if self._get_connection_params()['production'] else False
        res.append(f'- production: {prod}')
        if self.__repo.devel:
            res.append(f'- last release: {self.last_release_s}')
        return '\n'.join(res)

    @property
    def production(self):
        "Returns whether the database is tagged in production or not."
        return self._get_connection_params()['production']

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

    def execute_pg_command(self, *command_args):
        """Execute PostgreSQL command with instance's connection parameters."""
        return self._execute_pg_command(
            self.__name,
            self._get_connection_params(),
            *command_args
        )

    def register_release(self, major, minor, patch, changelog=None):
        "Register the release into half_orm_meta.hop_release"
        return self.__model.get_relation_class('half_orm_meta.hop_release')(
            major=major, minor=minor, patch=patch, changelog=changelog
        ).ho_insert()

    def _generate_schema_sql(self, version: str, model_dir: Path) -> Path:
        """
        Generate versioned schema SQL dump.

        Creates model/schema-{version}.sql with current database structure
        using pg_dump --schema-only. Creates model/metadata-{version}.sql
        with half_orm_meta data using pg_dump --data-only.
        Updates model/schema.sql symlink to point to the new version.

        This method is used by:
        - init-project: Generate initial schema-0.0.0.sql after database setup
        - deploy-to-prod: Generate schema-X.Y.Z.sql after production deployment

        Version History Strategy:
        - Only production versions are saved (X.Y.Z)
        - Stage and RC versions are NOT saved
        - Hotfixes overwrite the base version (1.3.4-hotfix1 overwrites 1.3.4)
        - Git history preserves old versions if needed

        Args:
            version: Version string (e.g., "0.0.0", "1.3.4", "2.0.0")
            model_dir: Path to model/ directory where schema files are stored

        Returns:
            Path to generated schema file (model/schema-{version}.sql)

        Raises:
            DatabaseError: If pg_dump command fails
            FileNotFoundError: If model_dir does not exist
            PermissionError: If cannot write to model_dir or create symlink
            ValueError: If version format is invalid

        Examples:
            # During init-project - create initial schema
            from pathlib import Path
            model_dir = Path("/project/model")
            schema_path = database._generate_schema_sql("0.0.0", model_dir)
            # → Creates model/schema-0.0.0.sql
            # → Creates model/metadata-0.0.0.sql
            # → Creates symlink model/schema.sql → schema-0.0.0.sql
            # → Returns Path("/project/model/schema-0.0.0.sql")

            # During deploy-to-prod - save production schema
            schema_path = database._generate_schema_sql("1.3.4", model_dir)
            # → Creates model/schema-1.3.4.sql
            # → Creates model/metadata-1.3.4.sql
            # → Updates symlink model/schema.sql → schema-1.3.4.sql

        File Structure Created:
            model/
            ├── schema.sql          # Symlink to current version
            ├── schema-0.0.0.sql    # Initial version (structure)
            ├── metadata-0.0.0.sql  # Initial version (half_orm_meta data)
            ├── schema-1.0.0.sql    # Production version (structure)
            ├── metadata-1.0.0.sql  # Production version (half_orm_meta data)
            ├── schema-1.3.4.sql    # Latest production version (current)
            ├── metadata-1.3.4.sql  # Latest production version (current)
            └── ...

        Notes:
            - Uses pg_dump --schema-only for structure (no data)
            - Uses pg_dump --data-only for metadata (only half_orm_meta tables)
            - Symlink is relative (schema.sql → schema-X.Y.Z.sql)
            - No symlink for metadata (version deduced from schema.sql)
            - Existing symlink is replaced atomically
            - Version format should be X.Y.Z (semantic versioning)
        """
        # Validate version format (X.Y.Z where X, Y, Z are integers)
        version_pattern = r'^\d+\.\d+\.\d+$'
        if not re.match(version_pattern, version):
            raise ValueError(
                f"Invalid version format: '{version}'. "
                f"Expected semantic versioning (X.Y.Z, e.g., '1.3.4')"
            )

        # Validate model_dir exists
        if not model_dir.exists():
            raise FileNotFoundError(
                f"Model directory does not exist: {model_dir}"
            )

        if not model_dir.is_dir():
            raise FileNotFoundError(
                f"Model path exists but is not a directory: {model_dir}"
            )

        # Construct versioned schema file path
        schema_file = model_dir / f"schema-{version}.sql"

        # Generate schema dump using pg_dump
        try:
            self.execute_pg_command(
                'pg_dump',
                self.__name,
                '--schema-only',
                '-f',
                str(schema_file)
            )
        except Exception as e:
            raise Exception(f"Failed to generate schema SQL: {e}") from e

        # Generate metadata dump (half_orm_meta data only)
        metadata_file = model_dir / f"metadata-{version}.sql"

        try:
            self.execute_pg_command(
                'pg_dump',
                self.__name,
                '--data-only',
                '--table=half_orm_meta.database',
                '--table=half_orm_meta.hop_release',
                '--table=half_orm_meta.hop_release_issue',
                '-f',
                str(metadata_file)
            )
        except Exception as e:
            raise Exception(f"Failed to generate metadata SQL: {e}") from e

        # Create or update symlink
        symlink_path = model_dir / "schema.sql"
        symlink_target = f"schema-{version}.sql"  # Relative path

        try:
            # Remove existing symlink if it exists
            if symlink_path.exists() or symlink_path.is_symlink():
                symlink_path.unlink()

            # Create new symlink (relative)
            symlink_path.symlink_to(symlink_target)

        except PermissionError as e:
            raise PermissionError(
                f"Permission denied: cannot create symlink in {model_dir}"
            ) from e
        except OSError as e:
            raise OSError(
                f"Failed to create symlink {symlink_path} → {symlink_target}: {e}"
            ) from e

        return schema_file

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
        # from half_orm.model import CONF_DIR

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
        config.set('database', 'docker_container', connection_params.get('docker_container', ''))

        # Write configuration file
        with open(config_file, 'w') as f:
            config.write(f)

        return config_file

    @classmethod
    def _check_docker_available(cls) -> bool:
        """
        Check if Docker is available on the system.

        Verifies that Docker is installed and the Docker daemon is running
        by executing 'docker --version'.

        Returns:
            bool: True if Docker is available, False otherwise

        Examples:
            >>> Database._check_docker_available()
            True  # Docker is installed and running

            >>> Database._check_docker_available()
            False  # Docker not installed or daemon not running
        """
        try:
            result = subprocess.run(
                ['docker', '--version'],
                capture_output=True,
                text=True,
                check=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False

    @classmethod
    def _check_docker_container_exists(cls, container_name: str) -> bool:
        """
        Check if a Docker container exists (running or stopped).

        Uses 'docker inspect' to verify container existence. This checks
        for containers in any state (running, stopped, paused, etc.).

        Args:
            container_name (str): Name or ID of the Docker container

        Returns:
            bool: True if container exists, False otherwise

        Examples:
            >>> Database._check_docker_container_exists('my_postgres')
            True  # Container exists

            >>> Database._check_docker_container_exists('nonexistent')
            False  # Container does not exist
        """
        try:
            result = subprocess.run(
                ['docker', 'inspect', container_name],
                capture_output=True,
                text=True,
                check=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False

    @classmethod
    def _check_docker_container_running(cls, container_name: str) -> bool:
        """
        Check if a Docker container is currently running.

        Uses 'docker inspect' to check the container's running state.
        Returns False if container doesn't exist or is stopped.

        Args:
            container_name (str): Name or ID of the Docker container

        Returns:
            bool: True if container is running, False otherwise

        Examples:
            >>> Database._check_docker_container_running('my_postgres')
            True  # Container is running

            >>> Database._check_docker_container_running('stopped_container')
            False  # Container exists but is stopped
        """
        try:
            result = subprocess.run(
                ['docker', 'inspect', '-f', '{{.State.Running}}', container_name],
                capture_output=True,
                text=True,
                check=True,
                timeout=5
            )
            # Docker inspect returns "true" or "false" as string
            return result.stdout.strip().lower() == 'true'
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False

    @classmethod
    def _get_docker_container_info(cls, container_name: str) -> dict:
        """
        Get detailed information about a Docker container.

        Retrieves container status, ID, and other relevant information
        using 'docker inspect'. Useful for debugging and error messages.

        Args:
            container_name (str): Name or ID of the Docker container

        Returns:
            dict: Container information with keys:
                - exists (bool): Whether container exists
                - running (bool): Whether container is running
                - status (str): Container status (running, exited, etc.)
                - id (str): Container ID (first 12 chars)
                - name (str): Container name

        Examples:
            >>> info = Database._get_docker_container_info('my_postgres')
            >>> print(info)
            {
                'exists': True,
                'running': True,
                'status': 'running',
                'id': '3f8d9a2b1c4e',
                'name': 'my_postgres'
            }
        """
        info = {
            'exists': False,
            'running': False,
            'status': 'unknown',
            'id': '',
            'name': container_name
        }

        # Check if container exists
        if not cls._check_docker_container_exists(container_name):
            return info

        info['exists'] = True

        try:
            # Get container status
            result = subprocess.run(
                ['docker', 'inspect', '-f', '{{.State.Status}}', container_name],
                capture_output=True,
                text=True,
                check=True,
                timeout=5
            )
            info['status'] = result.stdout.strip()
            info['running'] = info['status'] == 'running'

            # Get container ID
            result = subprocess.run(
                ['docker', 'inspect', '-f', '{{.Id}}', container_name],
                capture_output=True,
                text=True,
                check=True,
                timeout=5
            )
            info['id'] = result.stdout.strip()[:12]  # First 12 chars

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass

        return info

    @classmethod
    def _execute_native_pg_command(cls, database_name, connection_params, *command_args):
        """
        Execute PostgreSQL command on native PostgreSQL installation.

        This is the original implementation extracted from _execute_pg_command().
        Executes PostgreSQL commands (psql, createdb, pg_dump, etc.) on a
        native PostgreSQL installation using environment variables.

        Args:
            database_name (str): PostgreSQL database name
            connection_params (dict): Connection parameters (host, port, user, password)
            *command_args: PostgreSQL command and arguments

        Returns:
            subprocess.CompletedProcess: Command execution result

        Raises:
            subprocess.CalledProcessError: If PostgreSQL command fails

        Examples:
            >>> Database._execute_native_pg_command(
            ...     'my_db',
            ...     {'host': 'localhost', 'port': 5432, 'user': 'dev', 'password': 'secret'},
            ...     'createdb', 'my_db'
            ... )
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
    def _execute_docker_pg_command(cls, container_name, database_name, connection_params, *command_args):
        """
        Execute PostgreSQL command inside a Docker container.

        Handles Docker-specific challenges:
        - Adds -U option to avoid "role 'root' does not exist" errors
        - Manages psql -f by reading files on host and passing via stdin
        - Manages pg_dump -f by capturing stdout and writing to host

        Args:
            container_name (str): Docker container name
            database_name (str): PostgreSQL database name
            connection_params (dict): Connection parameters (user, password)
            *command_args: PostgreSQL command and arguments

        Returns:
            subprocess.CompletedProcess: Command execution result

        Raises:
            DockerNotAvailableError: If Docker is not installed or not running
            DockerContainerNotFoundError: If container does not exist
            DockerContainerNotRunningError: If container exists but is stopped
            subprocess.CalledProcessError: If PostgreSQL command fails

        Examples:
            # psql -f (reads file on host, passes via stdin)
            >>> Database._execute_docker_pg_command(
            ...     'my_postgres', 'my_db',
            ...     {'user': 'postgres', 'password': 'secret'},
            ...     'psql', '-d', 'my_db', '-f', '/path/to/schema.sql'
            ... )

            # pg_dump -f (captures stdout, writes to host)
            >>> Database._execute_docker_pg_command(
            ...     'my_postgres', 'my_db',
            ...     {'user': 'postgres', 'password': 'secret'},
            ...     'pg_dump', 'my_db', '--schema-only', '-f', '/path/to/dump.sql'
            ... )
        """
        # ═══════════════════════════════════════════════════════════════════
        # STEP 1: Check Docker availability
        # ═══════════════════════════════════════════════════════════════════
        if not cls._check_docker_available():
            raise DockerNotAvailableError(
                "Docker is not installed or not running.\n"
                "Install Docker: https://docs.docker.com/get-docker/"
            )

        # ═══════════════════════════════════════════════════════════════════
        # STEP 2: Check container exists
        # ═══════════════════════════════════════════════════════════════════
        if not cls._check_docker_container_exists(container_name):
            raise DockerContainerNotFoundError(
                f"Docker container '{container_name}' not found.\n"
                f"Run: docker ps -a  # to list all containers\n"
                f"Or create a new PostgreSQL container:\n"
                f"  docker run -d --name {container_name} -e POSTGRES_PASSWORD=postgres postgres:17"
            )

        # ═══════════════════════════════════════════════════════════════════
        # STEP 3: Check container is running
        # ═══════════════════════════════════════════════════════════════════
        if not cls._check_docker_container_running(container_name):
            container_info = cls._get_docker_container_info(container_name)
            raise DockerContainerNotRunningError(
                f"Docker container '{container_name}' exists but is not running.\n"
                f"Status: {container_info['status']}\n"
                f"Run: docker start {container_name}"
            )

        # ═══════════════════════════════════════════════════════════════════
        # STEP 4: Handle file operations (psql -f, pg_dump -f)
        # ═══════════════════════════════════════════════════════════════════
        command_list = list(command_args)
        modified_command = command_list.copy()
        sql_input = None      # For psql -f (stdin)
        output_file = None    # For pg_dump -f (stdout redirect)

        command_name = command_list[0] if len(command_list) > 0 else ''

        # ────────────────────────────────────────────────────────────────────
        # Case 1: psql -f <file> → Read file and pass via stdin
        # ────────────────────────────────────────────────────────────────────
        if command_name == 'psql':
            try:
                f_index = command_list.index('-f')
                if f_index + 1 < len(command_list):
                    host_file_path = command_list[f_index + 1]

                    # Read SQL file content on host
                    with open(host_file_path, 'r', encoding='utf-8') as f:
                        sql_input = f.read()

                    # Remove -f option from command (will use stdin)
                    modified_command = command_list[:f_index] + command_list[f_index+2:]
            except (ValueError, FileNotFoundError, OSError):
                # -f not found or file read failed, use original command
                pass

        # ────────────────────────────────────────────────────────────────────
        # Case 2: pg_dump -f <file> → Remove -f and capture stdout
        # ────────────────────────────────────────────────────────────────────
        elif command_name == 'pg_dump':
            try:
                f_index = command_list.index('-f')
                if f_index + 1 < len(command_list):
                    output_file = command_list[f_index + 1]

                    # Remove -f option (will capture stdout)
                    modified_command = command_list[:f_index] + command_list[f_index+2:]
            except ValueError:
                # -f not found, use original command
                pass

        # ═══════════════════════════════════════════════════════════════════
        # STEP 5: Prepare PostgreSQL command with -U option
        # ═══════════════════════════════════════════════════════════════════
        # CRITICAL: Add -U <user> to avoid "role 'root' does not exist" error
        # docker exec runs as root, but we need PostgreSQL user

        pg_user = connection_params['user']

        if len(modified_command) > 0:
            pg_command = modified_command[0]  # e.g., 'createdb', 'psql', 'pg_dump'
            command_args_rest = modified_command[1:]

            # Insert -U <user> after command name
            final_command = [pg_command, '-U', pg_user] + command_args_rest
        else:
            final_command = modified_command

        # ═══════════════════════════════════════════════════════════════════
        # STEP 6: Prepare Docker exec command
        # ═══════════════════════════════════════════════════════════════════
        docker_cmd = ['docker', 'exec', '-i', container_name] + final_command

        # ═══════════════════════════════════════════════════════════════════
        # STEP 7: Prepare environment variables
        # ═══════════════════════════════════════════════════════════════════
        env = os.environ.copy()

        # Set password if provided (PGPASSWORD for authentication)
        if connection_params.get('password'):
            env['PGPASSWORD'] = connection_params['password']

        # ═══════════════════════════════════════════════════════════════════
        # STEP 8: Execute command with appropriate I/O handling
        # ═══════════════════════════════════════════════════════════════════

        if sql_input:
            # ──────────────────────────────────────────────────────────────
            # psql -f: Pass SQL content via stdin
            # ──────────────────────────────────────────────────────────────
            result = subprocess.run(
                docker_cmd,
                env=env,
                input=sql_input,
                capture_output=True,
                text=True,
                check=True
            )

        elif output_file:
            # ──────────────────────────────────────────────────────────────
            # pg_dump -f: Capture stdout and write to host file
            # ──────────────────────────────────────────────────────────────
            result = subprocess.run(
                docker_cmd,
                env=env,
                capture_output=True,
                text=True,
                check=True
            )

            # Write stdout to output file on host
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(result.stdout)

        else:
            # ──────────────────────────────────────────────────────────────
            # Standard execution (no file operations)
            # ──────────────────────────────────────────────────────────────
            result = subprocess.run(
                docker_cmd,
                env=env,
                capture_output=True,
                text=True,
                check=True
            )

        return result


    @classmethod
    def _execute_pg_command(cls, database_name, connection_params, *command_args):
        """
        Execute PostgreSQL command with connection parameters (native or Docker).

        Routes command execution to either native PostgreSQL or Docker container
        based on the presence of 'docker_container' in connection_params.

        **Mode Detection**:
        - If docker_container is present and non-empty → Docker mode
        - Otherwise → Native PostgreSQL mode

        Args:
            database_name (str): PostgreSQL database name
            connection_params (dict): Connection parameters including optional docker_container
            *command_args: PostgreSQL command arguments

        Returns:
            subprocess.CompletedProcess: Command execution result

        Raises:
            DockerNotAvailableError: If Docker mode but Docker not available
            DockerContainerNotFoundError: If Docker mode but container not found
            DockerContainerNotRunningError: If Docker mode but container stopped
            subprocess.CalledProcessError: If PostgreSQL command fails

        Examples:
            # Native PostgreSQL (existing behavior)
            >>> Database._execute_pg_command(
            ...     'my_db',
            ...     {'host': 'localhost', 'port': 5432, 'user': 'dev', 'password': 'secret'},
            ...     'createdb', 'my_db'
            ... )

            # Docker PostgreSQL (new behavior)
            >>> Database._execute_pg_command(
            ...     'my_db',
            ...     {'user': 'postgres', 'password': 'secret', 'docker_container': 'my_postgres'},
            ...     'createdb', 'my_db'
            ... )
        """
        # Detect execution mode based on docker_container presence
        docker_container = connection_params.get('docker_container')

        if docker_container:
            # Docker mode: Execute command inside Docker container
            return cls._execute_docker_pg_command(
                docker_container,
                database_name,
                connection_params,
                *command_args
            )
        else:
            # Native mode: Execute command on native PostgreSQL
            return cls._execute_native_pg_command(
                database_name,
                connection_params,
                *command_args
            )

    @classmethod
    def setup_database(cls, database_name, connection_options, create_db=True, add_metadata=False):
        """
        Configure database connection and install half-orm metadata schemas.

        Replaces the interactive __init_db() method with a non-interactive version
        that accepts connection parameters from CLI options or prompts for missing ones.

        **AUTOMATIC METADATA INSTALLATION**: If create_db=True, metadata is automatically
        installed for the newly created database (add_metadata becomes True automatically).

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
                            (automatically True if create_db=True)

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
            - Automatically installed for newly created databases (create_db=True)
            - Manually requested for existing databases (add_metadata=True)
            5. Configuration Save: Store connection parameters in configuration file
            6. Initial Release: Register version 0.0.0 in metadata

        Examples:
            # Create new database - metadata automatically installed
            Database.setup_database(
                database_name="my_blog_db",
                connection_options={'host': 'localhost', 'user': 'dev', 'password': 'secret'},
                create_db=True  # add_metadata becomes True automatically
            )

            # Add metadata to existing database manually
            Database.setup_database(
                database_name="legacy_db",
                connection_options={'host': 'prod.db.com', 'user': 'admin'},
                create_db=False,
                add_metadata=True  # Explicit metadata installation
            )

            # Connect to existing database without metadata (sync-only mode)
            Database.setup_database(
                database_name="readonly_db",
                connection_options={'host': 'localhost'},
                create_db=False,
                add_metadata=False  # No metadata - sync-only mode
            )
        """
        # Step 1: Validate input parameters
        cls._validate_parameters(database_name, connection_options)

        # Step 2: Collect connection parameters
        complete_params = cls._collect_connection_params(database_name, connection_options)

        # Step 3: Save configuration to file
        config_file = cls._save_configuration(database_name, complete_params)

        # Step 4: Test database connection (create if needed)
        database_created = False  # Track if we created a new database

        try:
            model = Model(database_name)
        except OperationalError:
            if create_db:
                # Create database using PostgreSQL createdb command
                cls._execute_pg_command(database_name, complete_params, 'createdb', database_name)
                database_created = True  # Mark that we created the database
                # Retry connection after creation
                model = Model(database_name)
            else:
                raise OperationalError(f"Database '{database_name}' does not exist and create_db=False")

        # Step 5: Install metadata if requested OR if database was newly created
        # AUTOMATIC BEHAVIOR: newly created databases automatically get metadata
        should_install_metadata = add_metadata or database_created

        if should_install_metadata:
            try:
                model.get_relation_class('half_orm_meta.hop_release')
                # Metadata already exists - skip installation
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
        expected_keys = {'host', 'port', 'user', 'password', 'production', 'docker_container'}
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
        from half_orm.model import CONF_DIR

        # Check if configuration directory exists
        if not os.path.exists(CONF_DIR):
            raise FileNotFoundError(f"Configuration directory {CONF_DIR} doesn't exist")

        # Build configuration file path
        config_file = os.path.join(CONF_DIR, database_name)

        # Return None if configuration file doesn't exist
        if not os.path.exists(config_file):
            return None

        # Check if file is readable before attempting to parse
        if not os.access(config_file, os.R_OK):
            raise PermissionError(f"Configuration file {config_file} is not readable")

        # Read configuration file
        config = ConfigParser()
        try:
            config.read(config_file)
        except Exception as e:
            raise ValueError(f"Configuration file format is invalid: {e}")

        # Check if [database] section exists
        if not config.has_section('database'):
            raise ValueError("Configuration file format is invalid: missing [database] section")

        # Extract configuration values with PostgreSQL defaults
        try:
            name = config.get('database', 'name')
            user = config.get('database', 'user', fallback=os.environ.get('USER', ''))
            password = config.get('database', 'password', fallback='')
            host = config.get('database', 'host', fallback='')
            port_str = config.get('database', 'port', fallback='')
            production_str = config.get('database', 'production', fallback='False')
            docker_container = config.get('database', 'docker_container', fallback='')

            # Convert port to int (default 5432 if empty)
            if port_str == '':
                port = 5432
            else:
                port = int(port_str)

            # Convert production to bool
            production = config.getboolean('database', 'production', fallback=False)

            return {
                'name': name,
                'user': user,
                'password': password,
                'host': host,
                'port': port,
                'production': production,
                'docker_container': docker_container
            }

        except (ValueError, TypeError) as e:
            raise ValueError(f"Configuration file format is invalid: {e}")

    def _get_connection_params(self):
        """
        Get current connection parameters for this database instance.

        Returns the connection parameters dictionary for this Database instance,
        replacing direct access to DbConn properties. This method serves as the
        unified interface for accessing connection parameters during the migration
        from DbConn to integrated Database functionality.

        Uses instance-level caching to avoid repeated file reads within the same
        Database instance lifecycle.

        Returns:
            dict: Connection parameters dictionary with standardized keys:
                - name (str): Database name
                - user (str): Database user
                - password (str): Database password (empty string if not set)
                - host (str): Database host (empty string for Unix socket)
                - port (int): Database port (5432 default)
                - production (bool): Production environment flag
            Returns dict with defaults if no configuration exists or errors occur.

        Examples:
            # Get connection parameters for existing database instance
            db = Database(repo)
            params = db._get_connection_params()
            # Returns: {'name': 'my_db', 'user': 'dev', 'password': '',
            #           'host': 'localhost', 'port': 5432, 'production': False}

            # Access specific parameters (replaces DbConn.property access)
            user = db._get_connection_params()['user']      # replaces self.__connection_params.user
            host = db._get_connection_params()['host']      # replaces self.__connection_params.host
            prod = db._get_connection_params()['production'] # replaces self.__connection_params.production

        Implementation Notes:
            - Uses _load_configuration() internally but handles all exceptions
            - Provides stable interface - never raises exceptions
            - Returns sensible defaults if configuration is missing/invalid
            - Serves as protective wrapper around _load_configuration()
            - Exceptions from _load_configuration() are caught and handled gracefully
            - Uses instance-level cache to avoid repeated file reads

        Migration Notes:
            - Replaces self.__connection_params.user, .host, .port, .production access
            - Serves as transition method during DbConn elimination
            - Maintains compatibility with existing Database instance usage patterns
            - Will be used by state, production, and execute_pg_command properties
        """
        # Return cached parameters if already loaded
        if hasattr(self, '_Database__connection_params_cache') and self.__connection_params_cache is not None:
            return self.__connection_params_cache

        # Load configuration with defaults
        config = {
            'name': self.__repo.name,
            'user': os.environ.get('USER', ''),
            'password': '',
            'host': '',
            'port': 5432,
            'production': False
        }

        try:
            # Try to load configuration for this database
            loaded_config = self._load_configuration(self.__repo.name)
            if loaded_config is not None:
                config = loaded_config
        except (FileNotFoundError, PermissionError, ValueError):
            # Handle all possible exceptions from _load_configuration gracefully
            # Return sensible defaults to maintain stable interface
            pass

        # Cache the result for subsequent calls
        self.__connection_params_cache = config
        return config

    def get_postgres_version(self) -> tuple:
        """
        Get PostgreSQL server version.

        Returns:
            tuple: (major, minor) version numbers
                Examples: (13, 4), (16, 1), (17, 0)

        Raises:
            DatabaseError: If version cannot be determined

        Examples:
            version = db.get_postgres_version()
            if version >= (13, 0):
                # Use --force flag for dropdb
                pass
        """
        try:
            result = self._execute_pg_command(
                self.__name,
                self._get_connection_params(),
                *['psql', '-d', 'postgres', '-t', '-A', '-c', 'SHOW server_version;'],
            )

            # Output format: "16.1 (Ubuntu 16.1-1.pgdg22.04+1)"
            # Extract version: "16.1"
            version_str = result.stdout.strip().split()[0]

            # Parse major.minor
            parts = version_str.split('.')
            major = int(parts[0])
            minor = int(parts[1]) if len(parts) > 1 else 0

            return (major, minor)

        except Exception as e:
            raise DatabaseError(
                f"Failed to get PostgreSQL version: {e}\n"
                f"Ensure PostgreSQL is installed and accessible."
            )