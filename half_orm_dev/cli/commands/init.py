"""
Init command - Initialize new half_orm_dev project (unified workflow)

Orchestrates database setup and project creation in a single command.
This is a convenience wrapper around the existing init-database and init-project logic.
"""

import click
from pathlib import Path
from half_orm import utils
from half_orm.model import Model
from half_orm_dev.database import Database
from half_orm_dev.repo import Repo


class DatabaseExistsWithMetadataError(Exception):
    """Raised when database already has metadata (existing project)."""
    pass


class ProjectDirectoryExistsError(Exception):
    """Raised when project directory already exists."""
    pass


@click.command('init')
@click.argument('project_name')
@click.option('--host', default='localhost', help='PostgreSQL host (default: localhost)')
@click.option('--port', default=5432, type=int, help='PostgreSQL port (default: 5432)')
@click.option('--user', default=None, help='Database user (default: $USER)')
@click.option('--password', default=None, help='Database password (prompts if missing)')
@click.option('--git-origin', default=None, help='Git remote origin URL (prompts if missing)')
@click.option('--production', is_flag=True, help='Mark as production environment (default: False)')
@click.option('--force-sync-only', is_flag=True, help='Skip metadata installation, force sync-only mode')
@click.option('--create-db', is_flag=False, default=True)
@click.option('--docker', default='', help='Docker container name for PostgreSQL')
def init(project_name, host, port, user, password, git_origin, production, force_sync_only, create_db, docker):
    """
    Initialize a new half_orm_dev project with database and code structure.

    Creates both database (with metadata) and project structure in a single command.

    \b
    ARGUMENTS:
        project_name: Name of the project (= database name = Python package name)

    \b
    WORKFLOW:
        1. Check if database exists and has metadata
        2. Create/configure database with half_orm_dev metadata
        3. Create project directory structure with Git repository
        4. Generate Python package from database schema

    \b
    EXAMPLES:
        # Create new project with new database (interactive)
        half_orm dev init my_blog

        # Create with explicit connection parameters
        half_orm dev init my_blog --host=localhost --user=dev --git-origin=https://github.com/user/my_blog.git

        # Force sync-only mode (no metadata, limited functionality)
        half_orm dev init legacy_project --force-sync-only

    \b
    PROJECT STRUCTURE CREATED:
        my_blog/
        ├── .git/              (ho-prod branch)
        ├── .hop/config        (project configuration)
        ├── Patches/           (schema patches)
        ├── releases/          (release management)
        ├── model/             (schema snapshots)
        ├── backups/           (database backups)
        ├── my_blog/           (Python package)
        ├── tests/             (test directory)
        ├── README.md
        ├── .gitignore
        └── pyproject.toml

    \b
    MODES:
        - Full development mode (default): Database with half_orm_dev metadata
          → Enables: create-patch, apply-patch, prepare-release, etc.

        - Sync-only mode (--force-sync-only or user declines metadata):
          → Only enables: sync-package (code generation from schema)
          → Limited functionality, no patch management

    \b
    ERROR CASES:
        - Database exists with metadata:
          → Error: "Use 'half_orm dev clone <git-url>' to work on existing project"

        - Project directory already exists:
          → Error: "Directory already exists, choose a different name"
    """
    try:
        database_name = project_name
        package_name = project_name

        click.echo(f"🚀 Initializing half_orm project '{project_name}'...")
        click.echo()

        # ============================================================
        # STEP 1: PRE-FLIGHT CHECKS
        # ============================================================

        # Check 1: Project directory must not exist
        project_dir = Path.cwd() / project_name
        if project_dir.exists():
            raise ProjectDirectoryExistsError(
                f"Directory '{project_name}' already exists in current directory.\n"
                f"Choose a different project name or remove the existing directory."
            )

        # Prepare connection options (will be used by both check and setup)
        connection_options = {
            'host': host,
            'port': port,
            'user': user,
            'password': password,
            'production': production,
            'docker_container': docker
        }

        # Check 2: Database status (exists? has metadata?)
        click.echo(f"🔍 Checking database status...")
        db_exists, has_metadata = _check_database_status(
            database_name, connection_options
        )

        # Check 3: Existing project detection
        if has_metadata:
            raise DatabaseExistsWithMetadataError(
                f"Database '{database_name}' already has half_orm_dev metadata (existing project).\n"
                f"To work on this project, use: half_orm dev clone <git-url>"
            )

        # ============================================================
        # STEP 2: DATABASE SETUP
        # ============================================================

        # Determine metadata installation strategy
        install_metadata = True
        create_db = not db_exists

        if db_exists:
            # Database exists without metadata
            click.echo(f"ℹ️  Database '{database_name}' exists without half_orm_dev metadata.")

            if force_sync_only:
                install_metadata = False
                click.echo("⚠️  Sync-only mode forced: metadata installation skipped.")
            else:
                # Interactive prompt
                install_metadata = click.confirm(
                    "Install half_orm_dev metadata for full development mode?",
                    default=True
                )
                if not install_metadata:
                    click.echo("⚠️  Continuing in sync-only mode (limited functionality).")

            click.echo()

        # Execute database setup (reuses existing Database.setup_database)
        click.echo(f"🗄️  Setting up database '{database_name}'...")
        Database.setup_database(
            database_name=database_name,
            connection_options=connection_options,
            create_db=create_db,
            add_metadata=install_metadata
        )

        click.echo(f"✅ Database '{database_name}' configured successfully.")
        click.echo()

        # ============================================================
        # STEP 3: PROJECT STRUCTURE CREATION
        # ============================================================

        # Prompt for git_origin if not provided
        if not git_origin:
            git_origin = _prompt_for_git_origin(project_name)

        click.echo(f"📁 Creating project structure...")

        # Now safe to instantiate Repo (database is configured)
        repo = Repo()
        repo.init_git_centric_project(
            package_name=package_name,
            git_origin=git_origin
        )

        # ============================================================
        # STEP 4: SUCCESS MESSAGE
        # ============================================================

        click.echo()
        click.echo(f"✅ Project '{project_name}' initialized successfully!")
        click.echo()
        click.echo("📂 Project structure:")
        click.echo(f"   {project_name}/")
        click.echo(f"   ├── .git/              (ho-prod branch)")
        click.echo(f"   ├── .hop/config")
        click.echo(f"   ├── Patches/")
        click.echo(f"   ├── releases/")
        click.echo(f"   ├── model/")
        click.echo(f"   ├── {package_name}/    (Python package)")
        click.echo(f"   └── tests/")
        click.echo()
        click.echo("🚀 Next steps:")
        click.echo(f"   cd {project_name}/")

        if install_metadata:
            click.echo("   half_orm dev create-patch <patch-name>  # Start developing")
        else:
            click.echo("   half_orm dev sync-package              # Sync Python code with schema")
            click.echo()
            click.echo("   ⚠️  Note: Sync-only mode has limited functionality.")
            click.echo("      To enable full development mode later, you'll need to:")
            click.echo("      1. Install metadata manually in the database")
            click.echo("      2. Reconfigure the project")

    except DatabaseExistsWithMetadataError as e:
        click.echo()
        utils.error(str(e), exit_code=1)

    except ProjectDirectoryExistsError as e:
        click.echo()
        utils.error(str(e), exit_code=1)

    except Exception as e:
        click.echo()
        utils.error(f"Project initialization failed: {e}", exit_code=1)


def _check_database_status(database_name, connection_options):
    """
    Check if database exists and has half_orm_dev metadata.

    Args:
        database_name (str): Name of the database to check
        connection_options (dict): Already collected connection parameters
            - host (str): PostgreSQL host
            - port (int): PostgreSQL port
            - user (str): Database user
            - password (str): Database password
            - production (bool): Production flag

    Returns:
        tuple: (db_exists: bool, has_metadata: bool)
            - (False, False): Database doesn't exist
            - (True, False): Database exists without metadata
            - (True, True): Database exists with metadata (existing project)

    Implementation:
        Attempts connection using Model. If successful, checks for
        half_orm_meta.hop_release table. Uses already-collected parameters
        to avoid re-prompting the user.
    """
    try:
        # Try to create Model instance
        # Model will attempt to read from ~/.half_orm/<database_name> config
        # If config doesn't exist yet, connection will fail and we return (False, False)
        model = Model(database_name)

        # Database exists and is accessible, check for metadata
        has_metadata = model.has_relation('half_orm_meta.hop_release')

        # Clean up
        model.disconnect()

        return (True, has_metadata)

    except Exception as e:
        # Database doesn't exist or not accessible yet
        # This is expected for new databases before setup_database runs
        error_msg = str(e).lower()
        if 'does not exist' in error_msg or 'database' in error_msg or 'connection' in error_msg:
            return (False, False)
        else:
            # Unexpected error, re-raise
            raise


def _prompt_for_git_origin(project_name):
    """
    Interactively prompt user for git origin URL.

    Args:
        project_name (str): Project name (used for suggestion)

    Returns:
        str: Git origin URL provided by user

    Prompts:
        "Git remote origin URL (e.g., https://github.com/user/my_blog.git): "

    Validation:
        - Must not be empty
        - Basic URL format check (starts with http/git/ssh)
    """
    click.echo("🔗 Git repository configuration:")
    click.echo(f"   Example: https://github.com/<user>/{project_name}.git")
    click.echo()

    while True:
        git_origin = click.prompt(
            "Git remote origin URL",
            type=str,
            default=""
        )

        # Validation
        if not git_origin or git_origin.strip() == "":
            click.echo("❌ Git origin URL cannot be empty. Please provide a valid URL.")
            continue

        git_origin = git_origin.strip()

        # Basic format validation
        valid_prefixes = ('http://', 'https://', 'git://', 'git@', 'ssh://')
        if not any(git_origin.startswith(prefix) for prefix in valid_prefixes):
            click.echo(
                "⚠️  Warning: Git URL should start with http://, https://, git://, git@, or ssh://\n"
                "   Example: https://github.com/user/repo.git"
            )
            if not click.confirm("Use this URL anyway?", default=False):
                continue

        return git_origin
