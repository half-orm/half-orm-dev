"""
Migrate command - Apply repository migrations after half_orm_dev upgrade.

This command runs pending migrations when the installed half_orm_dev version
is newer than the repository's hop_version in .hop/config.
"""

import click
from half_orm_dev.repo import Repo, RepoError
from half_orm_dev.migration_manager import MigrationManager
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

    \b
    Process:
      1. Detects version mismatch between installed half_orm_dev and repository
      2. Applies any migration scripts for intermediate versions
      3. Updates hop_version in .hop/config
      4. Creates migration commit on ho-prod
      5. Syncs .hop/ directory to all active branches

    \b
    Examples:
        # After upgrading half_orm_dev
        $ pip install --upgrade half_orm_dev
        $ half_orm dev migrate
        ⚠️  Migration needed: half_orm_dev 0.17.2 → 0.18.0
          Current branch: ho-prod

    \b
          Running migrations...
          ✓ Applied migration: 0.17.2 → 0.18.0
          ✓ Updated .hop/config: hop_version = 0.18.0
          ✓ Synced .hop/ to active branches

    \b
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

        # Migration needed (comparison > 0)
        click.echo(f"⚠️  {utils.Color.bold('Migration needed:')}")
        click.echo(f"  half_orm_dev {config_version} → {installed_version}")

        # Check current branch
        current_branch = repo.hgit.branch if repo.hgit else 'unknown'
        click.echo(f"  Current branch: {current_branch}")
        click.echo()

        # Check for breaking changes between current and target version
        mgr = MigrationManager(repo)
        breaking_changes = mgr.get_breaking_changes(config_version, installed_version)

        needs_explicit_confirm = False
        if breaking_changes:
            import importlib.metadata
            try:
                half_orm_installed = importlib.metadata.version('half-orm')
            except importlib.metadata.PackageNotFoundError:
                half_orm_installed = None

            width = 70
            lines = []
            lines.append('━' * width)
            lines.append(f"  ⚠️  BREAKING CHANGES")
            lines.append('━' * width)
            for bc in breaking_changes:
                if bc['component'] == 'hop':
                    label = 'half-orm-dev'
                    display_version = installed_version
                else:
                    label = 'half-orm'
                    display_version = half_orm_installed or bc['version']
                lines.append(f"\n  ━━━ {label} {display_version} {'━' * max(0, width - len(label) - len(display_version) - 7)}")
                for line in bc['content'].splitlines():
                    lines.append(f"  {line}")
            lines.append(f"\n{'━' * width}")
            click.echo_via_pager('\n'.join(lines) + '\n')
            needs_explicit_confirm = True

        # Run migrations
        if needs_explicit_confirm:
            click.echo("Type \"yes\" to confirm you have read the breaking changes and want to proceed.")
            answer = click.prompt("Proceed?", default="no")
            confirmed = answer.strip().lower() == "yes"
        else:
            confirmed = click.confirm("Do you want to proceed?", default=False)

        if not confirmed:
            click.echo()
            click.echo("If you want to revert half_orm_dev run:")
            click.echo(f"  pip install half-orm-dev=={config_version}")
        else:
            try:
                click.echo("  Running migrations...")
                result = repo.run_migrations_if_needed(silent=False)

                if result['migration_run']:
                    click.echo(f"\n✓ {utils.Color.green('Migration completed successfully')}")
                    click.echo(f"  Updated .hop/config: hop_version = {installed_version}")

                    if verbose and result.get('errors'):
                        click.echo(f"\n⚠️  Warnings during migration:")
                        for error in result['errors']:
                            click.echo(f"  • {error}")

                    click.echo(f"\n✓ Synced .hop/ to active branches")

                    deleted = result.get('orphaned_staged_deleted', [])
                    if deleted:
                        click.echo(f"✓ Deleted {len(deleted)} orphaned ho-staged branch(es)")
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
