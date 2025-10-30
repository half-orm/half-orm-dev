"""
Update command - Fetch and list available production releases.

Equivalent to 'apt update' - read-only operation that shows
available releases without making any changes.
"""

import click
from half_orm_dev.repo import Repo


@click.command()
def update():
    """
    Fetch and list available production releases.

    Synchronizes with origin (git fetch --tags) and displays available
    releases for production upgrade. Makes NO modifications to database
    or repository.

    By default, shows only production releases (v1.3.6, v1.4.0).
    Use --allow-rc to include release candidates (v1.3.6-rc1).

    Examples:
        # List production releases only
        half_orm dev update

        # Include RC releases
        half_orm dev update --allow-rc
    """
    repo = Repo()

    # Direct access to ReleaseManager (KISS principle)
    result = repo.release_manager.update_production()

    # Format and display results
    _display_update_results(result)


def _display_update_results(result):
    """
    Format and display update results to user.

    Args:
        result: Dict from ReleaseManager.update_production()
    """
    click.echo("\nFetching releases from origin... ✓\n")

    current = result['current_version']
    click.echo(f"Current production version: {current}")

    if not result['has_updates']:
        click.echo("\n✓ Production is up to date. No upgrades available.")
        return

    click.echo("\nAvailable releases for upgrade:")
    for rel in result['available_releases']:
        rel_type = rel['type'].upper() if rel['type'] != 'production' else ''
        type_label = f" ({rel_type})" if rel_type else ""
        patch_count = len(rel['patches'])
        click.echo(f"  → {rel['version']}{type_label} - {patch_count} patches")

    if result['upgrade_path']:
        click.echo("\nUpgrade path (sequential):")
        path_str = " → ".join([current] + result['upgrade_path'])
        click.echo(f"  {path_str}")

    click.echo("\nTo upgrade:")
    click.echo("  half_orm dev upgrade                     (apply all)")
    if result['upgrade_path']:
        first_version = result['upgrade_path'][0]
        click.echo(f"  half_orm dev upgrade --to-release={first_version}  (apply specific)")
    click.echo("  half_orm dev upgrade --dry-run           (simulate)")
