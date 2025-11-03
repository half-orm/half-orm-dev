"""
Clone command - Clone existing half_orm_dev project from Git repository

Clones a Git repository, checks out ho-prod branch, sets up local database,
and restores schema to production version.
"""

import click
from pathlib import Path
from half_orm_dev.repo import Repo, RepoError


@click.command('clone')
@click.argument('git_origin')
@click.option('--database-name', default=None, help='Custom local database name (default: use project name)')
@click.option('--dest-dir', default=None, help='Destination directory name (default: infer from git URL)')
@click.option('--production', is_flag=True, help='Production mode (default: False)')
@click.option('--no-create-db', is_flag=True, help='Skip database creation (database must exist)')
def clone(git_origin, database_name, dest_dir, production, no_create_db):
    """
    Clone existing half_orm_dev project and setup local database.

    Clones a Git repository, checks out the ho-prod branch, creates/configures
    the local database, and restores the schema to production version.

    ARGUMENTS:
        git_origin: Git repository URL (HTTPS, SSH, file://)

    WORKFLOW:
        1. Clone repository from git_origin
        2. Checkout ho-prod branch
        3. Create .hop/alt_config if --database-name provided
        4. Setup database (create + metadata if needed)
        5. Restore database from model/schema.sql

    EXAMPLES:
        # Basic clone (prompts for database connection params)
        half_orm dev clone https://github.com/user/project.git

        # Clone with custom database name
        half_orm dev clone https://github.com/user/project.git --database-name my_local_db

        # Clone to specific directory
        half_orm dev clone https://github.com/user/project.git --dest-dir my_project

        # Production mode (database must already exist)
        half_orm dev clone https://github.com/user/project.git --production --no-create-db

    NOTES:
        - Changes current directory to cloned project
        - Interactive prompts for missing connection parameters
        - Requires model/schema.sql in repository for schema restoration
    """
    try:
        click.echo(f"🔄 Cloning half_orm project from {git_origin}...")
        click.echo()

        # Execute clone
        Repo.clone_repo(
            git_origin=git_origin,
            database_name=database_name,
            dest_dir=dest_dir,
            production=production,
            create_db=not no_create_db
        )

        # Determine project name for success message
        if dest_dir:
            project_name = dest_dir
        else:
            project_name = git_origin.rstrip('/').split('/')[-1]
            if project_name.endswith('.git'):
                project_name = project_name[:-4]

        click.echo()
        click.echo(f"✅ Project '{project_name}' cloned and configured successfully!")
        click.echo(f"   📁 Project directory: {Path.cwd()}")
        click.echo(f"   🗄️  Database restored to production version")
        click.echo()
        click.echo(f"Next steps:")
        click.echo(f"  • cd {project_name}")
        click.echo(f"  • half_orm dev create-patch <patch_id>  # Start developing")
        click.echo()

    except FileExistsError as e:
        click.echo(f"❌ Error: {e}", err=True)
        click.echo(f"   Remove the existing directory or choose a different destination.", err=True)
        raise click.Abort()

    except RepoError as e:
        click.echo(f"❌ Clone failed: {e}", err=True)
        click.echo()
        click.echo(f"Common issues:")
        click.echo(f"  • Invalid or inaccessible Git URL")
        click.echo(f"  • Missing 'ho-prod' branch in repository")
        click.echo(f"  • Database connection or permission issues")
        click.echo(f"  • Missing model/schema.sql in repository")
        raise click.Abort()

    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        raise click.Abort()
