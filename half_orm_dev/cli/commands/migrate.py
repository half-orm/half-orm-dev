"""
Migrate command - Apply repository migrations after half_orm_dev upgrade.

This command runs pending migrations when the installed half_orm_dev version
is newer than the repository's hop_version in .hop/config.
"""

import click
from half_orm_dev.repo import Repo, RepoError
from half_orm import utils


@click.command()
@click.option(
    '--verbose', '-v',
    is_flag=True,
    help='Show detailed migration information'
)
def migrate(verbose: bool) -> None:
    """
    Apply repository migrations after half_orm_dev upgrade.

    This command updates the repository structure and configuration files
    when you upgrade to a newer version of half_orm_dev.

    Requirements:
      • Must be on ho-prod branch
      • Repository must be clean (no uncommitted changes)

    Process:
      1. Detects version mismatch between installed half_orm_dev and repository
      2. Applies any migration scripts for intermediate versions
      3. Updates hop_version in .hop/config
      4. Creates migration commit on ho-prod
      5. Syncs .hop/ directory to all active branches

    Examples:
        # After upgrading half_orm_dev
        $ pip install --upgrade half_orm_dev
        $ half_orm dev migrate
        ⚠️  Migration needed: half_orm_dev 0.17.2 → 0.18.0
          Current branch: ho-prod

          Running migrations...
          ✓ Applied migration: 0.17.2 → 0.18.0
          ✓ Updated .hop/config: hop_version = 0.18.0
          ✓ Synced .hop/ to active branches

        # View detailed migration info
        $ half_orm dev migrate --verbose
    """
    try:
        repo = Repo()

        # Check if we're in a repository
        if not repo.checked:
            click.echo(utils.Color.red("❌ Not in a hop repository"), err=True)
            raise click.Abort()

        # Get current versions
        from half_orm_dev.utils import hop_version
        installed_version = hop_version()
        config_version = repo._Repo__config.hop_version if hasattr(repo, '_Repo__config') else '0.0.0'

        # Check if migration is needed
        comparison = repo.compare_versions(installed_version, config_version)

        if comparison == 0:
            # Versions are equal - no migration needed
            click.echo(f"✓ {utils.Color.green('Repository is up to date')}")
            click.echo(f"  Repository version: {config_version}")
            click.echo(f"  Installed version:  {installed_version}")
            return

        elif comparison < 0:
            # Installed version is OLDER than repository version
            click.echo(f"⚠️  {utils.Color.red('Installed half_orm_dev is older than repository version')}", err=True)
            click.echo(f"\n  Repository version: {config_version}", err=True)
            click.echo(f"  Installed version:  {installed_version}", err=True)
            click.echo(f"\n  Please upgrade half_orm_dev:", err=True)
            click.echo(f"    pip install --upgrade half_orm_dev\n", err=True)
            raise click.Abort()

        # Migration needed (comparison > 0)
        click.echo(f"⚠️  {utils.Color.bold('Migration needed:')}")
        click.echo(f"  half_orm_dev {config_version} → {installed_version}")

        # Check current branch
        current_branch = repo.hgit.branch if repo.hgit else 'unknown'
        click.echo(f"  Current branch: {current_branch}")
        click.echo()

        # Run migrations
        click.echo(f"  Running migrations...")

        try:
            result = repo.run_migrations_if_needed(silent=False)

            if result['migration_run']:
                click.echo(f"\n✓ {utils.Color.green('Migration completed successfully')}")
                click.echo(f"  Updated .hop/config: hop_version = {installed_version}")

                if verbose and result.get('errors'):
                    click.echo(f"\n⚠️  Warnings during migration:")
                    for error in result['errors']:
                        click.echo(f"  • {error}")

                click.echo(f"\n✓ Synced .hop/ to active branches")
            else:
                click.echo(f"✓ {utils.Color.green('Repository is up to date')}")

        except RepoError as e:
            # Migration failed or branch check failed
            click.echo(utils.Color.red(f"\n❌ {e}"), err=True)
            raise click.Abort()

    except RepoError as e:
        click.echo(utils.Color.red(f"❌ Error: {e}"), err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(utils.Color.red(f"❌ Unexpected error: {e}"), err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        raise click.Abort()
