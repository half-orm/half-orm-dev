"""
Rollback command - Restore production to a previous version.

Restores the database from a stored snapshot and checks out the
corresponding immutable ho-prod-X.Y.Z branch.
"""

import click
from half_orm_dev.repo import Repo
from half_orm_dev.release_manager import ReleaseManagerError
from half_orm import utils


@click.command()
@click.option(
    '--to-version', '-t',
    type=str,
    default=None,
    help='Target version (default: previous version)'
)
@click.option(
    '--yes', '-y',
    is_flag=True,
    help='Skip confirmation prompt'
)
def rollback(to_version: str, yes: bool) -> None:
    """
    Rollback production to a previous version.

    Restores the database from the snapshot created before the last upgrade
    and checks out the corresponding ho-prod-X.Y.Z branch.

    Requirements:
      • Must be on a ho-prod-X.Y.Z branch
      • Snapshot must exist for the target version

    \b
    Examples:
        # Rollback to previous version (default)
        half_orm dev rollback

        # Rollback to a specific version
        half_orm dev rollback --to-version 0.2.23
    """
    try:
        repo = Repo()
        mgr = repo.release_manager

        current_version = repo.database.last_release_s
        available = mgr._list_rollback_versions()

        if not available:
            click.echo(utils.Color.red("❌ No snapshots available for rollback."), err=True)
            raise click.Abort()

        # Resolve default target
        target = to_version
        if target is None:
            from packaging.version import Version
            candidates = [v for v in available if Version(v) < Version(current_version)]
            target = max(candidates, key=lambda v: Version(v)) if candidates else None
            if target is None:
                click.echo(
                    utils.Color.red(f"❌ No previous version available for {current_version}."),
                    err=True
                )
                raise click.Abort()

        # Display options
        click.echo(f"Current version:  {utils.Color.bold(current_version)}")
        click.echo(f"\nAvailable rollback versions:")
        for v in available:
            marker = f"  {utils.Color.bold('← default')}" if v == target else ""
            click.echo(f"  • {utils.Color.bold(v)}{marker}")

        click.echo(f"\nWill rollback: {current_version} → {utils.Color.bold(target)}")
        click.echo(f"⚠️  This will REPLACE the current database with snapshot ho-prod-{target}.")

        if not yes:
            if not click.confirm("\nProceed?", default=False):
                click.echo("Cancelled.")
                return

        click.echo("\nRolling back...")
        result = mgr.rollback_production(to_version=target)

        click.echo(
            f"\n✓ {utils.Color.green('Rollback complete:')} "
            f"{result['from_version']} → {utils.Color.bold(result['to_version'])}"
        )
        click.echo(f"  Branch:   {result['branch']}")
        click.echo(f"  Snapshot: {result['snapshot']}")
        click.echo(
            f"\n💡 The snapshot {result['snapshot']} is still available.\n"
            f"   To re-upgrade: half_orm dev upgrade"
        )

    except ReleaseManagerError as e:
        click.echo(utils.Color.red(f"\n❌ {e}"), err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(utils.Color.red(f"\n❌ Unexpected error: {e}"), err=True)
        raise click.Abort()
