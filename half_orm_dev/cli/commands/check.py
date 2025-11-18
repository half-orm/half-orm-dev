"""
Check command - Verify and update project configuration.

Checks project health and updates components as needed:
  - Git hooks (pre-commit)
  - Configuration files
  - Template files
  - Clean up stale branches
"""

import click
from half_orm_dev.repo import Repo
from half_orm import utils


@click.command()
@click.option(
    '--prune-branches', '-p',
    is_flag=True,
    help='Also clean up local branches that no longer exist on remote'
)
@click.option(
    '--dry-run',
    is_flag=True,
    help='Show what would be done without making changes'
)
@click.option(
    '--verbose', '-v',
    is_flag=True,
    help='Show detailed information'
)
def check(prune_branches: bool, dry_run: bool, verbose: bool) -> None:
    """
    Verify and update project configuration.

    Checks project health and updates components as needed. This command
    is also run automatically at the start of other commands.

    Checks performed:
      • Git hooks are up to date (pre-commit)
      • Repository is properly configured
      • Optionally: Clean up stale local branches

    Examples:
        # Basic check and update
        half_orm dev check

        # Check and clean up stale branches
        half_orm dev check --prune-branches

        # Preview what would be done
        half_orm dev check --dry-run
    """
    try:
        repo = Repo()

        # Perform check (delegates to Repo)
        result = repo.check_and_update(
            prune_branches=prune_branches,
            dry_run=dry_run,
            silent=False  # Show messages
        )

        # Display results
        _display_check_results(result, dry_run, prune_branches, verbose)

    except Exception as e:
        click.echo(utils.Color.red(f"❌ Error: {e}"), err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        raise click.Abort()


def _display_check_results(result: dict, dry_run: bool, prune_branches: bool, verbose: bool):
    """Display check results to user."""
    # Hooks
    hooks = result.get('hooks', {})
    if hooks.get('installed'):
        if hooks['action'] == 'updated':
            click.echo(f"✓ {utils.Color.green('Pre-commit hook updated')}")
        elif hooks['action'] == 'installed':
            click.echo(f"✓ {utils.Color.green('Pre-commit hook installed')}")
    elif verbose:
        click.echo(f"✓ {utils.Color.green('Pre-commit hook up to date')}")

    # Branches
    if prune_branches:
        branches = result.get('branches', {})
        deleted = branches.get('deleted', [])

        if deleted:
            if dry_run:
                click.echo(f"○ {utils.Color.yellow(f'Would delete {len(deleted)} stale branch(es)')}")
            else:
                click.echo(f"✓ {utils.Color.green(f'Deleted {len(deleted)} stale branch(es)')}")

            if verbose:
                for branch in deleted[:10]:
                    symbol = "○" if dry_run else "✓"
                    click.echo(f"  {symbol} {branch}")
                if len(deleted) > 10:
                    click.echo(f"  ... and {len(deleted) - 10} more")
        elif verbose:
            click.echo(f"✓ {utils.Color.green('No stale branches')}")

        if branches.get('errors'):
            click.echo(f"⚠ {utils.Color.yellow('Some errors occurred during cleanup')}")
            if verbose:
                for branch, error in branches['errors'][:3]:
                    click.echo(f"  {branch}: {error}")
