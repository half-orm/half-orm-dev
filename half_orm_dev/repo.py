"""The pkg_conf module provides the Repo class.
"""

import os
import sys
from configparser import ConfigParser
from typing import Optional
from psycopg2 import OperationalError
import half_orm
from half_orm import utils
from half_orm_dev.database import Database
from half_orm_dev.hgit import HGit
from half_orm_dev import modules
from half_orm.model import Model
from half_orm_dev.patch import Patch
from half_orm_dev.changelog import Changelog
from half_orm_dev.patch_manager import PatchManager, PatchManagerError

from .utils import TEMPLATE_DIRS, hop_version

class Config:
    """
    """
    __name: Optional[str] = None
    __git_origin: str = ''
    __devel: bool = False
    __hop_version: Optional[str] = None
    def __init__(self, base_dir, **kwargs):
        Config.__file = os.path.join(base_dir, '.hop', 'config')
        self.__name = kwargs.get('name')
        self.__devel = kwargs.get('devel', False)
        if os.path.exists(self.__file):
            sys.path.insert(0, base_dir)
            self.read()

    def read(self):
        "Sets __name and __hop_version"
        config = ConfigParser()
        config.read(self.__file)
        self.__name = config['halfORM']['package_name']
        self.__hop_version = config['halfORM'].get('hop_version', '')
        self.__git_origin = config['halfORM'].get('git_origin', '')
        self.__devel = config['halfORM'].getboolean('devel', False)

    def write(self):
        "Helper: write file in utf8"
        config = ConfigParser()
        self.__hop_version = hop_version()
        data = {
            'config_file': self.__name,
            'package_name': self.__name,
            'hop_version': self.__hop_version,
            'git_origin': self.__git_origin,
            'devel': self.__devel
        }
        config['halfORM'] = data
        with open(Config.__file, 'w', encoding='utf-8') as configfile:
            config.write(configfile)

    @property
    def name(self):
        return self.__name
    @name.setter
    def name(self, name):
        self.__name = name

    @property
    def git_origin(self):
        return self.__git_origin
    @git_origin.setter
    def git_origin(self, origin):
        "Sets the git origin and register it in .hop/config"
        self.__git_origin = origin
        self.write()

    @property
    def hop_version(self):
        return self.__hop_version
    @hop_version.setter
    def hop_version(self, version):
        self.__hop_version = version
        self.write()

    @property
    def devel(self):
        return self.__devel
    @devel.setter
    def devel(self, devel):
        self.__devel = devel

class Repo:
    """Reads and writes the hop repo conf file.

    Implements Singleton pattern to ensure only one instance per base directory.
    """

    # Singleton storage: base_dir -> instance
    _instances = {}

    # Instance variables
    __new = False
    __checked: bool = False
    __base_dir: Optional[str] = None
    __config: Optional[Config] = None
    database: Optional[Database] = None
    hgit: Optional[HGit] = None
    _patch_directory: Optional[PatchManager] = None

    def __new__(cls):
        """Singleton implementation based on current working directory"""
        # Find the base directory for this context
        base_dir = cls._find_base_dir()

        # Return existing instance if it exists for this base_dir
        if base_dir in cls._instances:
            return cls._instances[base_dir]

        # Create new instance
        instance = super().__new__(cls)
        cls._instances[base_dir] = instance
        return instance

    def __init__(self):
        # Only initialize once per instance
        if hasattr(self, '_initialized'):
            return

        self._initialized = True
        self.__check()

    @classmethod
    def _find_base_dir(cls):
        """Find the base directory for the current context (same logic as __check)"""
        base_dir = os.path.abspath(os.path.curdir)
        while base_dir:
            conf_file = os.path.join(base_dir, '.hop', 'config')
            if os.path.exists(conf_file):
                return base_dir
            par_dir = os.path.split(base_dir)[0]
            if par_dir == base_dir:
                break
            base_dir = par_dir
        return os.path.abspath(os.path.curdir)  # fallback to current dir

    @classmethod
    def clear_instances(cls):
        """Clear all singleton instances - useful for testing or cleanup"""
        for instance in cls._instances.values():
            if instance.database and instance.database.model:
                try:
                    instance.database.model.disconnect()
                except:
                    pass
        cls._instances.clear()

    @property
    def new(self):
        "Returns if the repo is being created or not."
        return Repo.__new

    @property
    def checked(self):
        "Returns if the Repo is OK."
        return self.__checked

    @property
    def production(self):
        "Returns the production status of the database"
        return self.database.production

    @property
    def model(self):
        "Returns the Model (halfORM) of the database"
        return self.database.model

    def __check(self):
        """Searches the hop configuration file for the package.
        This method is called when no hop config file is provided.
        Returns True if we are in a repo, False otherwise.
        """
        base_dir = os.path.abspath(os.path.curdir)
        while base_dir:
            if self.__set_base_dir(base_dir):
                self.database = Database(self)
                if self.devel:
                    self.hgit = HGit(self)
                    current_branch = self.hgit.branch
                    self.changelog = Changelog(self)
                    # only check if the branch is clean
                    if self.hgit.repos_is_clean():
                        self.hgit.check_rebase_hop_main(current_branch)
                self.__checked = True
            par_dir = os.path.split(base_dir)[0]
            if par_dir == base_dir:
                break
            base_dir = par_dir

    def __set_base_dir(self, base_dir):
        conf_file = os.path.join(base_dir, '.hop', 'config')
        if os.path.exists(conf_file):
            self.__base_dir = base_dir
            self.__config = Config(base_dir)
            return True
        return False

    @property
    def base_dir(self):
        "Returns the base dir of the repository"
        return self.__base_dir

    @property
    def name(self):
        "Returns the name of the package"
        return self.__config and self.__config.name or None

    @property
    def git_origin(self):
        "Returns the git origin registered in .hop/config"
        return self.__config.git_origin
    @git_origin.setter
    def git_origin(self, origin):
        self.__config.git_origin = origin

    def __hop_version_mismatch(self):
        """Returns a boolean indicating if current hop version is different from
        the last hop version used with this repository.
        """
        return hop_version() != self.__config.hop_version

    @property
    def devel(self):
        return self.__config.devel

    @property
    def state(self):
        "Returns the state (str) of the repository."
        res = [f'hop version: {utils.Color.bold(hop_version())}']
        res += [f'half-orm version: {utils.Color.bold(half_orm.__version__)}\n']
        if self.__config:
            hop_version_display = utils.Color.red(self.__config.hop_version) if \
                self.__hop_version_mismatch() else \
                utils.Color.green(self.__config.hop_version)
            res += [
                '[Hop repository]',
                f'- base directory: {self.__base_dir}',
                f'- package name: {self.__config.name}',
                f'- hop version: {hop_version_display}'
            ]
            res.append(self.database.state)
            res.append(str(self.hgit))
            res.append(Patch(self).state)
        return '\n'.join(res)

    def init(self, package_name, devel):
        "Create a new hop repository"
        Repo.__new = True
        cur_dir = os.path.abspath(os.path.curdir)
        self.__base_dir = os.path.join(cur_dir, package_name)
        self.__config = Config(self.__base_dir, name=package_name, devel=devel)
        self.database = Database(self, get_release=False).init(self.__config.name)
        print(f"Installing new hop repo in {self.__base_dir}.")

        if not os.path.exists(self.__base_dir):
            os.makedirs(self.__base_dir)
        else:
            utils.error(f"ERROR! The path '{self.__base_dir}' already exists!\n", exit_code=1)
        readme = utils.read(os.path.join(TEMPLATE_DIRS, 'README'))
        setup_template = utils.read(os.path.join(TEMPLATE_DIRS, 'setup.py'))
        git_ignore = utils.read(os.path.join(TEMPLATE_DIRS, '.gitignore'))
        pipfile = utils.read(os.path.join(TEMPLATE_DIRS, 'Pipfile'))

        setup = setup_template.format(
                dbname=self.__config.name,
                package_name=self.__config.name,
                half_orm_version=half_orm.__version__)
        utils.write(os.path.join(self.__base_dir, 'setup.py'), setup)

        pipfile = pipfile.format(
                half_orm_version=half_orm.__version__,
                hop_version=hop_version())
        utils.write(os.path.join(self.__base_dir, 'Pipfile'), pipfile)

        os.mkdir(os.path.join(self.__base_dir, '.hop'))
        self.__config.write()
        modules.generate(self)

        readme = readme.format(
            hop_version=hop_version(), dbname=self.__config.name, package_name=self.__config.name)
        utils.write(os.path.join(self.__base_dir, 'README.md'), readme)
        utils.write(os.path.join(self.__base_dir, '.gitignore'), git_ignore)
        self.hgit = HGit().init(self.__base_dir)

        print(f"\nThe hop project '{self.__config.name}' has been created.")
        print(self.state)

    def sync_package(self):
        Patch(self).sync_package()

    def upgrade_prod(self):
        "Upgrade (production)"
        Patch(self).upgrade_prod()

    def restore(self, release):
        "Restore package and database to release (production/devel)"
        Patch(self).restore(release)

    def prepare_release(self, level, message=None):
        "Prepare a new release (devel)"
        Patch(self).prep_release(level, message)

    def apply_release(self):
        "Apply the current release (devel)"
        Patch(self).apply(self.hgit.current_release, force=True)

    def undo_release(self, database_only=False):
        "Undo the current release (devel)"
        Patch(self).undo(database_only=database_only)

    def commit_release(self, push):
        "Release a 'release' (devel)"
        Patch(self).release(push)

    @property
    def patch_manager(self) -> PatchManager:
        """
        Get PatchManager instance for patch-centric operations.

        Provides access to Patches/ directory management including:
        - Creating patch directories with minimal README templates
        - Validating patch structure following KISS principles  
        - Applying SQL and Python files in lexicographic order
        - Listing and managing existing patches

        Lazy initialization ensures PatchManager is only created when needed
        and cached for subsequent accesses.

        Returns:
            PatchManager: Instance for managing Patches/ operations

        Raises:
            PatchManagerError: If repository not in development mode
            RuntimeError: If repository not properly initialized

        Examples:
            # Create new patch directory
            repo.patch_manager.create_patch_directory("456-user-auth")

            # Apply patch files using repo's model
            applied = repo.patch_manager.apply_patch_files("456-user-auth", repo.model)

            # List all existing patches
            patches = repo.patch_manager.list_all_patches()

            # Get detailed patch structure analysis
            structure = repo.patch_manager.get_patch_structure("456-user-auth")
            if structure.is_valid:
                print(f"Patch has {len(structure.files)} executable files")
        """
        # Validate repository is properly initialized
        if not self.__checked:
            raise RuntimeError(
                "Repository not initialized. PatchManager requires valid repository context."
            )

        # Validate development mode requirement
        if not self.devel:
            raise PatchManagerError(
                "PatchManager operations require development mode. "
                "Enable development mode in repository configuration."
            )

        # Lazy initialization with caching
        if self._patch_directory is None:
            try:
                self._patch_directory = PatchManager(self)
            except Exception as e:
                raise PatchManagerError(
                    f"Failed to initialize PatchManager: {e}"
                ) from e

        return self._patch_directory

    def clear_patch_directory_cache(self) -> None:
        """
        Clear cached PatchManager instance.

        Forces re-initialization of PatchManager on next access.
        Useful for testing or when repository configuration changes.

        Examples:
            # Clear cache after configuration change
            repo.clear_patch_directory_cache()

            # Next access will create fresh instance
            new_patch_dir = repo.patch_manager
        """
        self._patch_directory = None

    def has_patch_directory_support(self) -> bool:
        """
        Check if repository supports PatchManager operations.

        Validates that repository is in development mode and properly
        initialized without actually creating PatchManager instance.

        Returns:
            bool: True if PatchManager operations are supported

        Examples:
            if repo.has_patch_directory_support():
                patches = repo.patch_manager.list_all_patches()
            else:
                print("Repository not in development mode")
        """
        return self.__checked and self.devel

    def init_git_centric_project(self, package_name):
        """
        Create a new half-orm-dev project with Git-centric architecture.

        Replaces legacy init() method with updated workflow:
        - Database must be pre-configured via init-database command
        - Automatic mode detection (metadata present → devel=True)
        - Git-centric structure: ho-prod branch, Patches/, releases/
        - Modern Python packaging (keeping current templates for now)

        Args:
            package_name (str): Name of the project/package to create

        Returns:
            None: Project directory created and initialized

        Raises:
            ValueError: If package_name is invalid
            FileExistsError: If project directory already exists
            DatabaseNotConfiguredError: If database not configured via init-database
            DatabaseConnectionError: If cannot connect to configured database

        Process Flow:
            1. Validate package_name format
            2. Check database configuration exists (~/.half_orm/<package_name>)
            3. Connect to database and detect mode (metadata → devel=True)
            4. Create project directory structure
            5. Generate configuration files (.hop/config)
            6. Create Git-centric directories (Patches/, releases/)
            7. Generate Python package structure
            8. Initialize Git repository with ho-prod branch
            9. Generate template files (README, .gitignore, setup.py, Pipfile)

        Git-centric Architecture:
            - Main branch: ho-prod (replaces hop_main)
            - Patch branches: ho-patch/<patch-name>
            - Directory structure: Patches/<patch-name>/ for schema files
            - Release management: releases/X.Y.Z-stage.txt workflow

        Mode Detection:
            - Full development mode: Database has half_orm_meta schemas
            - Sync-only mode: Database lacks metadata (read-only package sync)

        Examples:
            # After database configuration
            repo = Repo()
            repo.init_git_centric_project("my_blog")
            # → Creates my_blog/ with full development mode if metadata present

            # Sync-only mode (no metadata in database)
            repo.init_git_centric_project("legacy_app")
            # → Creates legacy_app/ in sync-only mode (no patch management)

        Migration Notes:
            - Replaces Repo.init(package_name, devel) from legacy workflow
            - Database creation moved to separate init-database command
            - Mode detection replaces explicit --devel flag
            - Git branch naming updated (hop_main → ho-prod)
        """
        # Step 1: Validate package name
        self._validate_package_name(package_name)

        # Step 2: Check database configuration exists
        self._verify_database_configured(package_name)

        # Step 3: Connect to database and detect mode
        devel_mode = self._detect_development_mode(package_name)

        # Step 4: Setup project directory
        self._create_project_directory(package_name)

        # Step 5: Initialize configuration
        self._initialize_configuration(package_name, devel_mode)

        # Step 6: Create Git-centric directories
        self._create_git_centric_structure()

        # Step 7: Generate Python package
        self._generate_python_package()

        # Step 8: Initialize Git repository with ho-prod branch
        self._initialize_git_repository()

        # Step 9: Generate template files
        self._generate_template_files()


    def _validate_package_name(self, package_name):
        """
        Validate package name follows Python package naming conventions.

        Args:
            package_name (str): Package name to validate

        Raises:
            ValueError: If package name is invalid

        Rules:
            - Not None or empty
            - Valid Python identifier (letters, numbers, underscore)
            - Cannot start with digit
            - Recommended: lowercase with underscores

        Examples:
            _validate_package_name("my_blog")      # Valid
            _validate_package_name("my-blog")      # Valid (converted to my_blog)
            _validate_package_name("9invalid")     # Raises ValueError
            _validate_package_name("my blog")      # Raises ValueError
        """
        import keyword

        # Check for None
        if package_name is None:
            raise ValueError("Package name cannot be None")

        # Check type
        if not isinstance(package_name, str):
            raise ValueError(f"Package name must be a string, got {type(package_name).__name__}")

        # Check for empty string
        if not package_name or not package_name.strip():
            raise ValueError("Package name cannot be empty")

        # Clean the name
        package_name = package_name.strip()

        # Convert hyphens to underscores (common convention)
        normalized_name = package_name.replace('-', '_')

        # Check if starts with digit
        if normalized_name[0].isdigit():
            raise ValueError(f"Package name '{package_name}' cannot start with a digit")

        # Check for valid Python identifier characters
        # Allow only letters, numbers, and underscores
        if not normalized_name.replace('_', '').isalnum():
            raise ValueError(
                f"Package name '{package_name}' contains invalid characters. "
                "Use only letters, numbers, underscore, and hyphen."
            )

        # Check for Python reserved keywords
        if keyword.iskeyword(normalized_name):
            raise ValueError(
                f"Package name '{package_name}' is a Python reserved keyword"
            )

        # Store normalized name for later use
        return normalized_name


    def _verify_database_configured(self, package_name):
        """
        Verify database is configured via init-database command.

        Checks that database configuration file exists and is accessible.
        Does NOT create the database - assumes init-database was run first.

        Args:
            package_name (str): Database name to verify

        Raises:
            DatabaseNotConfiguredError: If configuration file doesn't exist
            DatabaseConnectionError: If cannot connect to configured database

        Process:
            1. Check ~/.half_orm/<package_name> exists
            2. Attempt connection to verify database is accessible
            3. Store connection for later use

        Examples:
            # Database configured
            _verify_database_configured("my_blog")  # Success

            # Database not configured
            _verify_database_configured("unconfigured_db")
            # Raises: DatabaseNotConfiguredError with helpful message
        """
        # Try to load database configuration
        config = Database._load_configuration(package_name)

        if config is None:
            raise ValueError(
                f"Database '{package_name}' is not configured.\n"
                f"Please run: half_orm dev init-database {package_name} [OPTIONS]\n"
                f"See 'half_orm dev init-database --help' for more information."
            )

        # Try to connect to verify database is accessible
        try:
            model = Model(package_name)
            # Store model for later use
            return model
        except OperationalError as e:
            raise OperationalError(
                f"Cannot connect to database '{package_name}'.\n"
                f"Database may not exist or connection parameters may be incorrect.\n"
                f"Original error: {e}"
            )

    def _detect_development_mode(self, package_name):
        """
        Detect development mode based on metadata presence in database.

        Automatically determines if full development mode (with patch management)
        or sync-only mode based on half_orm_meta schemas presence.

        Args:
            package_name (str): Database name to check

        Returns:
            bool: True if metadata present (full mode), False if sync-only

        Detection Logic:
            - Query database for half_orm_meta.hop_release table
            - Present → devel=True (full development mode)
            - Absent → devel=False (sync-only mode)

        Examples:
            # Database with metadata
            mode = _detect_development_mode("my_blog")
            assert mode is True  # Full development mode

            # Database without metadata
            mode = _detect_development_mode("legacy_db")
            assert mode is False  # Sync-only mode
        """
        from half_orm.model import Model

        # Check if we already have a Model instance (from _verify_database_configured)
        if hasattr(self, 'database') and self.database and hasattr(self.database, 'model'):
            model = self.database.model
        else:
            # Create new Model instance
            model = Model(package_name)

        # Check for metadata table presence
        return model.has_relation('half_orm_meta.hop_release')

    def _create_project_directory(self, package_name):
        """
        Create project root directory with validation.

        Args:
            package_name (str): Name for project directory

        Raises:
            FileExistsError: If directory already exists
            OSError: If directory creation fails

        Process:
            1. Build absolute path from current directory
            2. Check directory doesn't already exist
            3. Create directory
            4. Store path in self.__base_dir

        Examples:
            # Success case
            _create_project_directory("my_blog")
            # Creates: /current/path/my_blog/

            # Error case
            _create_project_directory("existing_dir")
            # Raises: FileExistsError
        """
        import os

        # Build absolute path
        cur_dir = os.path.abspath(os.path.curdir)
        project_path = os.path.join(cur_dir, package_name)

        # Check if directory already exists
        if os.path.exists(project_path):
            raise FileExistsError(
                f"Directory '{package_name}' already exists at {project_path}.\n"
                "Choose a different project name or remove the existing directory."
            )

        # Create directory
        try:
            os.makedirs(project_path)
        except PermissionError as e:
            raise PermissionError(
                f"Permission denied: Cannot create directory '{project_path}'.\n"
                f"Check your write permissions for the current directory."
            ) from e
        except OSError as e:
            raise OSError(
                f"Failed to create directory '{project_path}': {e}"
            ) from e

        # Store base directory path
        self._Repo__base_dir = project_path

        return project_path


    def _initialize_configuration(self, package_name, devel_mode):
        """
        Initialize .hop/config with project settings.

        Args:
            package_name (str): Package name for configuration
            devel_mode (bool): Development mode flag

        Process:
            1. Create .hop/ directory
            2. Create Config instance
            3. Write configuration file with:
            - package_name
            - hop_version
            - git_origin (empty initially)
            - devel (detected automatically)

        Configuration Format:
            [halfORM]
            package_name = my_blog
            hop_version = 0.16.0
            git_origin = 
            devel = True

        Examples:
            # Full development mode
            _initialize_configuration("my_blog", devel_mode=True)
            # Creates: .hop/config with devel=True

            # Sync-only mode
            _initialize_configuration("legacy_app", devel_mode=False)
            # Creates: .hop/config with devel=False
        """
        import os

        # Ensure .hop directory exists
        hop_dir = os.path.join(self.__base_dir, '.hop')
        os.makedirs(hop_dir, exist_ok=True)

        # Create Config instance
        self.__config = Config(self.__base_dir, name=package_name, devel=devel_mode)

        # Write configuration file
        self.__config.write()

    def _create_git_centric_structure(self):
        """
        Create Git-centric directory structure for patch management.

        Creates directories required for Git-centric workflow:
        - Patches/ for patch development
        - releases/ for release management
        - model/ for schema snapshots
        - backups/ for database backups

        Only created in development mode (devel=True).

        Directory Structure:
            Patches/
            ├── README.md          # Patch development guide
            releases/
            ├── README.md          # Release workflow guide
            model/
            backups/

        Examples:
            # Development mode
            _create_git_centric_structure()
            # Creates: Patches/, releases/, model/, backups/

            # Sync-only mode
            _create_git_centric_structure()
            # Skips creation (not needed for sync-only)
        """
        pass


    def _generate_python_package(self):
        """
        Generate Python package structure from database schema.

        Uses modules.generate() to create Python classes for database tables.
        Creates hierarchical package structure matching database schemas.

        Process:
            1. Call modules.generate(self)
            2. Generates: <package>/<package>/<schema>/<table>.py
            3. Creates __init__.py files for each level
            4. Generates base_test.py and sql_adapter.py

        Generated Structure:
            my_blog/
            └── my_blog/
                ├── __init__.py
                ├── base_test.py
                ├── sql_adapter.py
                └── public/
                    ├── __init__.py
                    ├── user.py
                    └── post.py

        Examples:
            _generate_python_package()
            # Generates complete package structure from database
        """
        pass


    def _initialize_git_repository(self):
        """
        Initialize Git repository with ho-prod main branch.

        Replaces hop_main branch naming with ho-prod for Git-centric workflow.

        Process:
            1. Initialize Git repository via HGit
            2. Create initial commit
            3. Set main branch to ho-prod
            4. Configure remote origin (if available)

        Branch Naming:
            - Main branch: ho-prod (replaces hop_main)
            - Patch branches: ho-patch/<patch-name>

        Examples:
            _initialize_git_repository()
            # Creates: .git/ with ho-prod branch
        """
        pass


    def _generate_template_files(self):
        """
        Generate template files for project configuration.

        Creates standard project files:
        - README.md: Project documentation
        - .gitignore: Git exclusions
        - setup.py: Python packaging (current template)
        - Pipfile: Dependencies (current template)

        Templates read from TEMPLATE_DIRS and formatted with project variables.

        Note: Future enhancement will migrate to pyproject.toml,
        but keeping current templates for initial implementation.

        Examples:
            _generate_template_files()
            # Creates: README.md, .gitignore, setup.py, Pipfile
        """
        pass
