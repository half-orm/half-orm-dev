"""
Init-project command - Creates a new hop project with Git-centric architecture

Replaces legacy 'new' command with ho-prod/ho-patch workflow.
"""

import click
import os
from pathlib import Path
from half_orm_dev.repo import Repo
from half_orm import utils


@click.command()
@click.argument('database_name')
@click.option(
    '--template',
    type=click.Choice(['basic', 'api', 'web']),
    default='basic',
    help="Project template to use"
)
def init_project(database_name, full=False, template='basic'):
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
    
    Examples:
    \b
        half_orm dev init-project myapp
        half_orm dev init-project myapp
    
    Git-centric workflow:
    \b
        ho-prod (main branch) + ho-patch/patch-name (patch development)
        Patches/patch-name/ (schema files)
        releases/X.Y.Z-stage.txt → rc → production
    """
    # Validation préliminaire
    if not database_name or not database_name.strip():
        raise click.BadParameter("Database name cannot be empty")
    
    database_name = database_name.strip()
    project_dir = Path.cwd() / database_name
    
    # Vérifier que le répertoire n'existe pas déjà
    if project_dir.exists():
        raise click.ClickException(f"Directory '{database_name}' already exists!")
    
    click.echo(f"🚀 Initializing halfORM project '{database_name}' with Git-centric architecture...")
    
    try:
        # Créer nouveau repo avec architecture Git-centric
        repo = Repo()
        repo.init_git_centric_project(
            package_name=database_name
        )
        
        click.echo()
        click.echo(f"✅ Project '{database_name}' initialized successfully!")
        
        if repo.devel:
            click.echo()
            click.echo(utils.Color.green("🔧 Full development mode enabled:"))
            click.echo("  • Git repository with ho-prod main branch")
            click.echo("  • Patches/ directory for schema management")
            click.echo("  • halfORM metadata tables (version 0.0.0)")
            click.echo("  • PatchManager integration available")
            click.echo("  • releases/ directory for release management")
            
            click.echo()
            click.echo(utils.Color.bold("🚀 Next steps:"))
            click.echo(f"  cd {database_name}")
            click.echo("  half_orm dev create-patch 001-initial-schema")
            click.echo("  # Edit files in Patches/001-initial-schema/")
            click.echo("  half_orm dev apply-patch")
            click.echo("  half_orm dev add-to-release 001-initial-schema")
        else:
            click.echo()
            click.echo(utils.Color.blue("📦 Sync-only mode:"))
            click.echo("  • Package structure generated from existing database")
            click.echo("  • Database connection configured")
            click.echo("  • No patch management (read-only)")
            
            click.echo()
            click.echo(utils.Color.bold("🔄 Next steps:"))
            click.echo(f"  cd {database_name}")
            click.echo("  half_orm dev sync-package  # Update from database")
    
    except Exception as e:
        # Nettoyage en cas d'erreur
        if project_dir.exists():
            try:
                import shutil
                shutil.rmtree(project_dir)
                click.echo(f"❌ Cleaned up partial project directory: {project_dir}")
            except Exception:
                pass
        
        # Re-lever l'exception avec contexte
        raise click.ClickException(f"Failed to initialize project: {e}")