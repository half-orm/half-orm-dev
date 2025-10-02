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
@click.option(
    '--git-origin',
    default=None,
    help='Git remote origin URL (HTTPS, SSH, or Git protocol). '
         'If not provided, will prompt interactively.'
)
def init_project(package_name, git_origin):
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

        # Create project with explicit git origin
        half_orm dev init-project my_blog --git-origin=https://github.com/user/my_blog.git

        # Create project with interactive prompt for git origin
        half_orm dev init-project my_blog

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

    # Collect git_origin (from parameter or interactive prompt)
    if not git_origin:
        git_origin = _prompt_for_git_origin()

    click.echo(
        f"🚀 Initializing halfORM project '{package_name}' "
        "with Git-centric architecture..."
    )

    try:
        # Créer nouveau repo avec architecture Git-centric
        repo = Repo()
        repo.init_git_centric_project(
            package_name=package_name,
            git_origin=git_origin
        )

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
        # Errors from validation methods (package name, database not configured, git_origin, etc.)
        raise click.ClickException(str(e))
    except FileExistsError as e:
        # Directory already exists (should be caught above, but defensive)
        raise click.ClickException(str(e))
    except Exception as e:
        # Unexpected errors
        click.echo(f"\n❌ Error during project initialization: {e}", err=True)
        raise


def _prompt_for_git_origin():
    """
    Prompt user interactively for Git remote origin URL.

    Validates the URL and re-prompts if invalid. Strips whitespace
    from input.

    Returns:
        str: Valid Git origin URL

    Examples:
        git_origin = _prompt_for_git_origin()
        # User enters: https://github.com/user/repo.git
        # Returns: 'https://github.com/user/repo.git'
    """
    from half_orm_dev.repo import Repo

    while True:
        click.echo()
        git_origin = click.prompt(
            "Git remote origin URL",
            type=str
        ).strip()

        # Check if empty
        if not git_origin:
            click.echo("❌ Git origin URL cannot be empty. Please try again.")
            continue

        # Validate URL format
        try:
            # Use Repo's validation method
            repo = Repo()
            repo._validate_git_origin_url(git_origin)
            return git_origin
        except ValueError as e:
            click.echo(f"❌ {e}")
            click.echo("Please try again.")
            continue
