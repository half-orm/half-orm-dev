"""
Migrate command - Apply repository migrations after half_orm_dev upgrade.

This command runs pending migrations when the installed half_orm_dev version
is newer than the repository's hop_version in .hop/config.
"""

import click
from half_orm_dev.repo import Repo, RepoError
from half_orm_dev.migration_manager import (
    MigrationManager, HALF_ORM_BREAKING_CHANGES_URL)
from half_orm import utils


def announce_breaking_changes(repo, config_version: str, installed_version: str) -> bool:
    """Say what a migration breaks, before it is confirmed.

    Two kinds of breaking change, shown differently:

    * half-orm's, when its major version changes: what the application's
      code must change. They are documented on half-orm's site, so a link
      is enough -- migrating happens on a development machine.
    * half_orm_dev's: what the migration about to run does to the
      repository. Shown in full, since that is what is being confirmed.

    Returns:
        True when there was something to announce, and the migration calls
        for an explicit "yes" rather than a y/n.
    """
    mgr = MigrationManager(repo)
    major_change = mgr.half_orm_major_change(config_version, installed_version)
    notes = mgr.get_breaking_changes(config_version, installed_version)

    if major_change:
        from_major, to_major = major_change
        click.echo(utils.Color.bold(
            f"⚠️  half-orm {from_major}.x → {to_major}.x: a major release, "
            "which may require changes to your code."))
        click.echo("   Read what changed, and what to write instead, before going on:")
        click.echo(f"   {HALF_ORM_BREAKING_CHANGES_URL.format(major=to_major)}")
        click.echo()

    if notes:
        width = 70
        label = 'half-orm-dev'
        lines = ['━' * width, "  ⚠️  BREAKING CHANGES", '━' * width]
        for note in notes:
            lines.append(
                f"\n  ━━━ {label} {installed_version} "
                f"{'━' * max(0, width - len(label) - len(installed_version) - 7)}")
            lines.extend(f"  {line}" for line in note['content'].splitlines())
        lines.append(f"\n{'━' * width}")
        click.echo_via_pager('\n'.join(lines) + '\n')

    return bool(major_change or notes)


def confirm_breaking_migration() -> bool:
    "Ask for the explicit \"yes\" a breaking migration calls for."
    click.echo("Type \"yes\" to confirm you have read the breaking changes and want to proceed.")
    answer = click.prompt("Proceed?", default="no")
    return answer.strip().lower() == "yes"


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
        config_version = repo.config.hop_version

        # Migration needed (comparison > 0)
        click.echo(f"⚠️  {utils.Color.bold('Migration needed:')}")
        click.echo(f"  half_orm_dev {config_version} → {installed_version}")

        # Check current branch
        current_branch = repo.hgit.branch if repo.hgit else 'unknown'
        click.echo(f"  Current branch: {current_branch}")
        click.echo()

        # Check for breaking changes between current and target version
        if announce_breaking_changes(repo, config_version, installed_version):
            confirmed = confirm_breaking_migration()
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
