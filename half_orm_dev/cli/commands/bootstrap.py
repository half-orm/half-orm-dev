"""
Bootstrap command - Execute data initialization scripts.

Runs bootstrap scripts from the bootstrap/ directory to initialize
application data after database setup.
"""

import click
from half_orm_dev.repo import Repo
from half_orm_dev.bootstrap_manager import BootstrapManager, BootstrapManagerError
from half_orm import utils


@click.command()
@click.option(
    '--dry-run',
    is_flag=True,
    help='Show what would be executed without executing'
)
@click.option(
    '--force',
    is_flag=True,
    help='Re-execute all files (ignore tracking)'
)
@click.option(
    '--verbose', '-v',
    is_flag=True,
    help='Show detailed information'
)
def bootstrap(dry_run: bool, force: bool, verbose: bool) -> None:
    """
    Execute bootstrap scripts to initialize application data.

    Bootstrap scripts are SQL and Python files in the bootstrap/ directory
    that initialize application data after the database schema is created.

    Files are named: <number>-<patch_id>-<version>.<ext>
    Example: 1-init-users-0.1.0.sql, 2-seed-config-0.1.0.py

    Scripts are executed in numeric order and tracked in the database
    to ensure each script is executed only once.

    EXAMPLES:
        # Execute pending bootstrap scripts
        half_orm dev bootstrap

        # Preview what would be executed
        half_orm dev bootstrap --dry-run

        # Re-execute all scripts (ignore tracking)
        half_orm dev bootstrap --force

    NOTES:
        - SQL files are executed via halfORM
        - Python files are executed as subprocesses
        - Execution is tracked in half_orm_meta.bootstrap table
        - Use --force to re-execute previously run scripts
    """
    try:
        repo = Repo()
        bootstrap_mgr = BootstrapManager(repo)

        # Check if bootstrap directory exists
        if not bootstrap_mgr.bootstrap_dir.exists():
            click.echo(f"ℹ️  No bootstrap directory found at {bootstrap_mgr.bootstrap_dir}")
            click.echo(f"   Create bootstrap/ directory with data scripts to use this command.")
            return

        # Get files info
        all_files = bootstrap_mgr.get_bootstrap_files()
        if not all_files:
            click.echo(f"ℹ️  No bootstrap files found in {bootstrap_mgr.bootstrap_dir}")
            return

        # Display header
        if dry_run:
            click.echo(f"🔍 {utils.Color.bold('Dry run mode')} - showing what would be executed")
            click.echo()

        if force:
            click.echo(f"⚠️  {utils.Color.bold('Force mode')} - re-executing all files")
            click.echo()

        # Run bootstrap
        result = bootstrap_mgr.run_bootstrap(dry_run=dry_run, force=force)

        # Display results
        _display_results(result, dry_run, verbose)

    except BootstrapManagerError as e:
        click.echo(utils.Color.red(f"❌ Bootstrap error: {e}"), err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(utils.Color.red(f"❌ Error: {e}"), err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        raise click.Abort()


def _display_results(result: dict, dry_run: bool, verbose: bool) -> None:
    """Display bootstrap execution results."""
    executed = result.get('executed', [])
    skipped = result.get('skipped', [])
    errors = result.get('errors', [])

    # Display executed files
    if executed:
        verb = "Would execute" if dry_run else "Executed"
        click.echo(f"✓ {utils.Color.green(f'{verb} {len(executed)} file(s):')}")
        for filename in executed:
            click.echo(f"  • {filename}")
        click.echo()

    # Display skipped files (already executed)
    if skipped and verbose:
        click.echo(f"ℹ️  {utils.Color.blue(f'Skipped {len(skipped)} already executed file(s):')}")
        for filename in skipped:
            click.echo(f"  • {filename}")
        click.echo()
    elif skipped and not verbose:
        click.echo(f"ℹ️  Skipped {len(skipped)} already executed file(s) (use -v to see list)")
        click.echo()

    # Display errors
    if errors:
        click.echo(utils.Color.red(f"❌ {len(errors)} error(s) occurred:"))
        for filename, error_msg in errors:
            click.echo(f"  • {filename}: {error_msg}")
        click.echo()

    # Summary
    if not executed and not errors:
        if skipped:
            click.echo(f"✓ {utils.Color.green('All bootstrap files have already been executed.')}")
        else:
            click.echo(f"ℹ️  No bootstrap files to execute.")
    elif not errors and not dry_run:
        click.echo(f"✓ {utils.Color.green('Bootstrap completed successfully.')}")
