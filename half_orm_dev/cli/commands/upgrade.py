"""
Upgrade command - Apply releases sequentially to production database.

Equivalent to 'apt upgrade' - applies available releases incrementally
to existing production database without data destruction.
"""

import click
from half_orm_dev.repo import Repo
from half_orm_dev.release_manager import ReleaseManagerError
from half_orm import utils


@click.command()
@click.option(
    '--to-release', '-t',
    type=str,
    default=None,
    help='Stop at specific version (e.g., 1.3.7). Default: choose interactively'
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
@click.option(
    '--yes', '-y',
    is_flag=True,
    help='Skip confirmation prompt'
)
def upgrade(to_release, dry_run, force, skip_backup, yes):
    """
    Apply releases sequentially to production database.

    Fetches available releases, lets you choose a target version interactively,
    then upgrades the production database incrementally without data destruction.
    Creates automatic backup before any changes.

    Examples:
        # Interactive: choose target from list
        half_orm dev upgrade

        # Upgrade to specific version (no prompt)
        half_orm dev upgrade --to-release=1.3.7

        # Simulate upgrade (no changes, no prompt)
        half_orm dev upgrade --dry-run

        # Apply all without confirmation
        half_orm dev upgrade --yes
    """
    try:
        repo = Repo()

        # === Fetch and display available releases ===
        click.echo("🔄 Fetching available releases...\n")
        update_info = repo.release_manager.update_production()

        current = update_info['current_version']
        click.echo(f"Current version: {utils.Color.bold(current)}")

        if not update_info['has_updates']:
            click.echo(f"\n✓ {utils.Color.green('Production is already at latest version.')}")
            return

        available = update_info['available_releases']
        upgrade_path = update_info['upgrade_path']
        latest = upgrade_path[-1]

        click.echo(f"\nAvailable releases:")
        for rel in available:
            patch_count = len(rel['patches'])
            patches_label = f"{patch_count} patch{'es' if patch_count != 1 else ''}"
            click.echo(f"  • {utils.Color.bold(rel['version'])}  ({patches_label})")

        # === Determine target version ===
        if to_release is None and not dry_run:
            path_str = " → ".join([current] + upgrade_path)
            click.echo(f"\nUpgrade path: {path_str}\n")

            raw = click.prompt(
                "Target version",
                default=latest,
            ).strip()

            if raw not in upgrade_path:
                click.echo(
                    f"\n❌ '{raw}' is not in the upgrade path.\n"
                    f"   Available: {', '.join(upgrade_path)}",
                    err=True,
                )
                raise click.Abort()
            to_release = raw if raw != latest else None  # None means "all"

        # === Confirmation (unless --dry-run or --yes) ===
        if not dry_run and not yes:
            apply_path = upgrade_path
            if to_release:
                apply_path = upgrade_path[:upgrade_path.index(to_release) + 1]

            click.echo(f"\nWill apply: {utils.Color.bold(' → '.join(apply_path))}")
            if not skip_backup:
                click.echo("Will create backup before starting.")

            if not click.confirm("\nProceed?", default=True):
                click.echo("\nUpgrade cancelled.")
                return

        click.echo()

        # === Run upgrade (pass pre-fetched update_info to avoid double git fetch) ===
        result = repo.release_manager.upgrade_production(
            to_version=to_release,
            dry_run=dry_run,
            force_backup=force,
            skip_backup=skip_backup,
            update_info=update_info,
        )

        _display_upgrade_results(result)

    except ReleaseManagerError as e:
        click.echo(f"\n❌ {utils.Color.red('Upgrade failed:')}")
        click.echo(f"   {str(e)}\n")
        raise click.Abort()


def _display_upgrade_results(result):
    """Format and display upgrade results."""
    if result.get('dry_run'):
        click.echo(f"{utils.Color.bold('DRY RUN')} - Simulation only, no changes made\n")

        current = result['current_version']
        click.echo(f"Current version: {utils.Color.bold(current)}")

        if not result.get('releases_would_apply'):
            click.echo(f"\n✓ {utils.Color.green('Already at latest version')}")
            return

        click.echo(f"\nWould create backup: {utils.Color.bold(result.get('backup_would_be_created', ''))}")
        click.echo(f"\nWould apply releases:")
        for version in result['releases_would_apply']:
            patches = result['patches_would_apply'][version]
            click.echo(f"  → {utils.Color.bold(version)} - {len(patches)} patches")
            for patch_id in patches:
                click.echo(f"      • {patch_id}")

        final = result['final_version']
        click.echo(f"\nWould upgrade: {current} → {utils.Color.green(final)}")
        click.echo(f"\n{utils.Color.bold('To apply this upgrade, run without --dry-run')}")
        return

    current = result['current_version']

    if result.get('backup_created'):
        click.echo(f"✓ Backup created: {utils.Color.bold(result['backup_created'])}")
    elif result.get('snapshot_used'):
        click.echo(f"✓ Snapshot created: {utils.Color.bold(result['snapshot_used'])}")
    elif result.get('releases_applied'):
        click.echo(f"⚠️  {utils.Color.bold('No backup created (--skip-backup used)')}")

    if not result['releases_applied']:
        click.echo(f"\n✓ {utils.Color.green('Production already at latest version')}")
        return

    click.echo(f"\n{utils.Color.green('Applied releases:')}")
    for version in result['releases_applied']:
        patches = result['patches_applied'][version]
        if patches:
            click.echo(f"  ✓ {utils.Color.bold(version)} - {len(patches)} patches")
            for patch_id in patches:
                click.echo(f"      • {patch_id}")
        else:
            click.echo(f"  ✓ {utils.Color.bold(version)} - (empty release)")

    final = result['final_version']
    click.echo(f"\n{utils.Color.green('✓ Upgrade complete!')}")
    click.echo(f"   {current} → {utils.Color.bold(utils.Color.green(final))}")

    if result.get('target_version'):
        click.echo(f"\n📝 Partial upgrade to {result['target_version']} complete.")
        click.echo(f"   To upgrade further, run: half_orm dev upgrade")
    else:
        click.echo(f"\n📝 Production is now at latest version.")

    if result.get('backup_created'):
        click.echo(f"\n💡 To rollback if needed:")
        click.echo(f"   psql -d {result.get('db_name', 'DATABASE')} -f {result['backup_created']}")
