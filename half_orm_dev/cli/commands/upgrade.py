"""
Upgrade command - Apply releases sequentially to production database.

Equivalent to 'apt upgrade' - applies available releases incrementally
to existing production database without data destruction.
"""

import click
from pathlib import Path
from half_orm_dev.repo import Repo
from half_orm_dev.release_manager import ReleaseManagerError
from half_orm import utils


@click.command()
@click.option(
    '--to-release', '-t',
    type=str,
    default=None,
    help='Stop at specific version (e.g., 1.3.7). Default: upgrade to latest'
)
@click.option(
    '--dry-run', '-d',
    is_flag=True,
    help='Simulate upgrade without making changes'
)
@click.option(
    '--force',
    is_flag=True,
    help='Overwrite existing backup without confirmation'
)
@click.option(
    '--skip-backup',
    is_flag=True,
    help='Skip backup creation (DANGEROUS - for testing only)'
)
def upgrade(to_release, dry_run, force, skip_backup):
    """
    Apply releases sequentially to production database.

    Upgrades production database by applying releases incrementally
    to existing data. NEVER destroys or recreates the database.
    Creates automatic backup before any changes.

    CRITICAL: This command works on EXISTING production database.
    It does NOT use restore operations that would destroy data.

    Must be run from ho-prod branch.

    Workflow:
        1. CREATE BACKUP (backups/{version}.sql) - FIRST ACTION
        2. Validate environment (ho-prod branch, clean repo)
        3. Apply releases sequentially on existing database
        4. Update database version after each release

    Examples:
        # Upgrade to latest (all available releases)
        half_orm dev upgrade

        # Upgrade to specific version
        half_orm dev upgrade --to-release=1.3.7

        # Simulate upgrade (no changes)
        half_orm dev upgrade --dry-run

        # Force overwrite existing backup
        half_orm dev upgrade --force

    Options:
        --to-release=VERSION  Stop at specific version
        --dry-run            Simulate without changes
        --force              Overwrite existing backup
        --skip-backup        Skip backup (DANGEROUS)

    Requires:
        - Current branch: ho-prod
        - Repository: clean (no uncommitted changes)
        - Permissions: Database write access
    """
    try:
        # Get repository instance
        repo = Repo()

        # Delegate to ReleaseManager
        click.echo("🔄 Starting production upgrade...\n")

        result = repo.release_manager.upgrade_production(
            to_version=to_release,
            dry_run=dry_run,
            force_backup=force,
            skip_backup=skip_backup
        )

        # Display results
        _display_upgrade_results(result)

    except ReleaseManagerError as e:
        click.echo(f"\n❌ {utils.Color.red('Upgrade failed:')}")
        click.echo(f"   {str(e)}\n")
        raise click.Abort()


def _display_upgrade_results(result):
    """
    Format and display upgrade results to user.

    Args:
        result: Dict from ReleaseManager.upgrade_production()
    """
    # === DRY RUN MODE ===
    if result.get('dry_run'):
        click.echo(f"{utils.Color.bold('DRY RUN')} - Simulation only, no changes made\n")

        current = result['current_version']
        click.echo(f"Current version: {utils.Color.bold(current)}")

        if not result['releases_would_apply']:
            click.echo(f"\n✓ {utils.Color.green('Already at latest version')}")
            return

        # Show what would happen
        click.echo(f"\nWould create backup: {utils.Color.bold(result['backup_would_be_created'])}")

        click.echo(f"\nWould apply releases:")
        for version in result['releases_would_apply']:
            patches = result['patches_would_apply'][version]
            patch_count = len(patches)
            click.echo(f"  → {utils.Color.bold(version)} - {patch_count} patches")
            for patch_id in patches:
                click.echo(f"      • {patch_id}")

        final = result['final_version']
        click.echo(f"\nWould upgrade: {current} → {utils.Color.green(final)}")

        click.echo(f"\n{utils.Color.bold('To apply this upgrade, run without --dry-run')}")
        return

    # === ACTUAL UPGRADE ===

    current = result['current_version']

    # Backup confirmation
    if result['backup_created']:
        backup_path = result['backup_created']
        click.echo(f"✓ Backup created: {utils.Color.bold(backup_path)}")
    elif result.get('message') and 'already at latest' in result['message'].lower():
        # Up to date scenario
        pass
    else:
        click.echo(f"⚠️  {utils.Color.bold('No backup created (--skip-backup used)')}")

    click.echo(f"\nCurrent version: {utils.Color.bold(current)}")

    # Check if already up to date
    if not result['releases_applied']:
        click.echo(f"\n✓ {utils.Color.green('Production already at latest version')}")
        return

    # Show applied releases
    click.echo(f"\n{utils.Color.green('Applied releases:')}")

    for version in result['releases_applied']:
        patches = result['patches_applied'][version]
        patch_count = len(patches)

        if patch_count == 0:
            click.echo(f"  ✓ {utils.Color.bold(version)} - (empty release)")
        else:
            click.echo(f"  ✓ {utils.Color.bold(version)} - {patch_count} patches")
            for patch_id in patches:
                click.echo(f"      • {patch_id}")

    # Final status
    final = result['final_version']
    click.echo(f"\n{utils.Color.green('✓ Upgrade complete!')}")
    click.echo(f"   {current} → {utils.Color.bold(utils.Color.green(final))}")

    # Next steps
    if result['target_version']:
        # Partial upgrade
        click.echo(f"\n📝 Partial upgrade to {result['target_version']} complete.")
        click.echo(f"   To upgrade further, run: half_orm dev upgrade")
    else:
        # Full upgrade
        click.echo(f"\n📝 Production is now at latest version.")

    # Rollback information
    if result['backup_created']:
        backup_path = result['backup_created']
        click.echo(f"\n💡 To rollback if needed:")
        click.echo(f"   psql -d {result.get('db_name', 'DATABASE')} -f {backup_path}")
