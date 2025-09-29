"""
Init-project command - Creates a new hop project with Git-centric architecture

Replaces legacy 'new' command with ho-prod/ho-patch workflow.
"""

import click
from pathlib import Path
from half_orm_dev.repo import Repo
from half_orm import utils


@click.command()
@click.argument('package_name')
def init_project(package_name):
    """
    Initialize a new halfORM project with Git-centric patch management.

    Creates a new project directory with Git-centric architecture:

    \b
    • Git repository with ho-prod main branch (replaces hop_main)
    • Version 0.0.0 evolutionary metadata base
    • Patches/ directory for schema patch management
    • Generated Python package structure
    • Database connection configuration
    • PatchManager integration

    The database must be configured first using 'init-database' command.
    Mode (full development vs sync-only) is auto-detected based on metadata presence.

    Examples:
    \b
        # Configure database first
        half_orm dev init-database my_blog_db --create-db

        # Then create project
        half_orm dev init-project my_blog

        # Project name must match configured database name

    Git-centric workflow:
    \b
        ho-prod (main branch) + ho-patch/patch-name (patch development)
        Patches/patch-name/ (schema files)
        releases/X.Y.Z-stage.txt → rc → production
    """
    # Validation préliminaire
    if not package_name or not package_name.strip():
        raise click.BadParameter("Package name cannot be empty")

    package_name = package_name.strip()
    project_dir = Path.cwd() / package_name

    # Vérifier que le répertoire n'existe pas déjà
    if project_dir.exists():
        raise click.ClickException(
            f"Directory '{package_name}' already exists in current directory!"
        )

    click.echo(
        f"🚀 Initializing halfORM project '{package_name}' "
        "with Git-centric architecture..."
    )

    try:
        # Créer nouveau repo avec architecture Git-centric
        repo = Repo()
        repo.init_git_centric_project(package_name=package_name)

        click.echo()
        click.echo(f"✅ Project '{package_name}' initialized successfully!")
        click.echo()
        click.echo("📁 Project structure created:")
        click.echo(f"   {package_name}/")
        click.echo("   ├── .git/              (ho-prod branch)")
        click.echo("   ├── .hop/config        (project configuration)")
        click.echo("   ├── Patches/           (patch development)")
        click.echo("   ├── releases/          (release management)")
        click.echo(f"   ├── {package_name}/    (Python package)")
        click.echo("   ├── model/             (database snapshots)")
        click.echo("   ├── backups/           (database backups)")
        click.echo("   └── README.md")
        click.echo()
        click.echo("🎯 Next steps:")
        click.echo(f"   cd {package_name}")
        click.echo("   half_orm dev create-patch <patch-name>")

    except ValueError as e:
        # Errors from validation methods (package name, database not configured, etc.)
        raise click.ClickException(str(e))
    except FileExistsError as e:
        # Directory already exists (should be caught above, but defensive)
        raise click.ClickException(str(e))
    except Exception as e:
        # Unexpected errors
        click.echo(f"\n❌ Error during project initialization: {e}", err=True)
        raise
