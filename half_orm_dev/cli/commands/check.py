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
    # Version check
    version_info = result.get('version')
    if version_info:
        current = version_info.get('current_version')
        latest = version_info.get('latest_version')
        update_available = version_info.get('update_available', False)
        error = version_info.get('error')

        if error:
            if verbose:
                click.echo(f"ℹ {utils.Color.blue(f'Version check: {error}')}")
        elif update_available and latest:
            click.echo(f"⚠ {utils.Color.bold(f'half_orm_dev: {current}')} {utils.Color.bold(f'(update available: {latest})')}")
            click.echo(f"  Run: {utils.Color.bold('pip install --upgrade half_orm_dev')}")
            click.echo()
        elif current:
            click.echo(f"✓ {utils.Color.green(f'half_orm_dev: {current} (latest)')}")
            click.echo()

    # Hooks
    hooks = result.get('hooks', {})
    if hooks.get('installed'):
        if hooks['action'] == 'updated':
            click.echo(f"✓ {utils.Color.green('Pre-commit hook updated')}")
        elif hooks['action'] == 'installed':
            click.echo(f"✓ {utils.Color.green('Pre-commit hook installed')}")
    elif verbose:
        click.echo(f"✓ {utils.Color.green('Pre-commit hook up to date')}")

    # Active branches
    active = result.get('active_branches', {})
    patch_branches = active.get('patch_branches', [])
    release_branches = active.get('release_branches', [])

    # Show current branch
    current = active.get('current_branch')
    if current:
        click.echo(f"\n📍 {utils.Color.bold('Current branch:')} {current}")

    # Show releases with candidates and staged patches
    releases_info = result.get('releases_info', {})
    if releases_info:
        _display_releases_with_patches(releases_info, patch_branches, release_branches, verbose)
    elif verbose:
        click.echo(f"\n📦 {utils.Color.bold('Active releases:')} None")

    # Show standalone patch branches (not in candidates/stage)
    standalone_patches = [b for b in patch_branches
                         if not _is_patch_in_releases(b['name'], releases_info)]
    if standalone_patches:
        click.echo(f"\n🔧 {utils.Color.bold('Standalone patch branches')} ({len(standalone_patches)}):")
        for branch_info in standalone_patches:
            _display_branch_info(branch_info, verbose)

    # Show stale release branches (exist locally but not in stage)
    stale_release = [b for b in release_branches if not b.get('in_stage_file', False)]
    if stale_release and verbose:
        click.echo(f"\n⚠️  {utils.Color.blue('Stale release branches')} ({len(stale_release)}):")
        for branch_info in stale_release[:5]:
            click.echo(f"  • {branch_info['name']}")
            if not branch_info['exists_on_remote']:
                click.echo(f"    {utils.Color.red('⚠ Not on remote - can be deleted')}")
        if len(stale_release) > 5:
            click.echo(f"  ... and {len(stale_release) - 5} more")

    # Prune results
    if prune_branches:
        branches = result.get('branches', {})
        deleted = branches.get('deleted', [])

        if deleted:
            click.echo()
            if dry_run:
                click.echo(f"○ {utils.Color.blue(f'Would delete {len(deleted)} stale branch(es)')}")
            else:
                click.echo(f"✓ {utils.Color.green(f'Deleted {len(deleted)} stale branch(es)')}")

            if verbose:
                for branch in deleted[:10]:
                    symbol = "○" if dry_run else "✓"
                    click.echo(f"  {symbol} {branch}")
                if len(deleted) > 10:
                    click.echo(f"  ... and {len(deleted) - 10} more")

        if branches.get('errors'):
            click.echo(f"⚠ {utils.Color.red('Some errors occurred during cleanup')}")
            if verbose:
                for branch, error in branches['errors'][:3]:
                    click.echo(f"  {branch}: {error}")


def _display_release_branches_grouped(branches: list, verbose: bool):
    """Display release branches grouped by version and sorted by order."""
    from collections import defaultdict

    # Group branches by version
    by_version = defaultdict(list)
    for branch_info in branches:
        name = branch_info['name']
        # Extract version from ho-release/{version}/{patch_id}
        parts = name.split('/')
        if len(parts) >= 3 and parts[0] == 'ho-release':
            version = parts[1]
            patch_id = '/'.join(parts[2:])  # Handle patch IDs with slashes
            by_version[version].append((patch_id, branch_info))

    # Display each version group
    for version in sorted(by_version.keys()):
        patches = by_version[version]

        # Sort patches by their order in the stage file
        patches_sorted = sorted(patches, key=lambda x: x[1].get('order', 999))

        click.echo(f"\n  {utils.Color.bold(f'Release {version}')} ({len(patches)} patch{'es' if len(patches) > 1 else ''}):")
        for patch_id, branch_info in patches_sorted:
            _display_branch_info(branch_info, verbose, indent="    ", show_patch_id_only=True)


def _display_branch_info(branch_info: dict, verbose: bool, indent: str = "  ", show_patch_id_only: bool = False):
    """Display information about a single branch.

    Args:
        branch_info: Branch information dict
        verbose: Show verbose output
        indent: Indentation prefix
        show_patch_id_only: If True, show only patch_id instead of full branch name
    """
    name = branch_info['name']
    is_current = branch_info.get('is_current', False)
    exists_on_remote = branch_info.get('exists_on_remote', False)
    sync_status = branch_info.get('sync_status', 'unknown')
    ahead = branch_info.get('ahead', 0)
    behind = branch_info.get('behind', 0)

    # Extract display name
    if show_patch_id_only:
        # Extract patch_id from ho-release/{version}/{patch_id}
        parts = name.split('/')
        if len(parts) >= 3:
            display_name = '/'.join(parts[2:])
        else:
            display_name = name
    else:
        display_name = name

    # Symbol for current branch
    marker = "→ " if is_current else ""

    # Status symbol and text
    if not exists_on_remote:
        status = utils.Color.red("⚠ no remote")
    elif sync_status == 'synced':
        status = utils.Color.green("✓ synced")
    elif sync_status == 'ahead':
        status = utils.Color.blue(f"↑ {ahead} ahead")
    elif sync_status == 'behind':
        status = utils.Color.blue(f"↓ {behind} behind")
    elif sync_status == 'diverged':
        status = utils.Color.red(f"⚠ diverged (↑{ahead} ↓{behind})")
    else:
        status = "?"

    click.echo(f"{indent}{marker}• {display_name} - {status}")


def _display_releases_with_patches(releases_info: dict, patch_branches: list, release_branches: list, verbose: bool):
    """Display releases grouped by version with candidates and staged patches.

    Args:
        releases_info: Dict of {version: {candidates: [], staged: [], ...}}
        patch_branches: List of patch branch info dicts
        release_branches: List of release branch info dicts
        verbose: Show verbose output
    """
    # Sort versions
    sorted_versions = sorted(releases_info.keys(), key=lambda v: [int(x) for x in v.split('.')])

    for version in sorted_versions:
        info = releases_info[version]
        candidates = info.get('candidates', [])
        staged = info.get('staged', [])

        # Check if release branch exists
        release_branch_name = f"ho-release/{version}"
        release_branch_info = next((b for b in release_branches if b['name'] == release_branch_name), None)

        # Release header with status
        release_status = ""
        if release_branch_info:
            if not release_branch_info.get('exists_on_remote', False) and release_branch_info.get('exists_locally', False):
                release_status = f" {utils.Color.yellow('⚠️ local only - remote deleted')}"
            elif release_branch_info.get('sync_status') == 'remote_only':
                release_status = f" {utils.Color.blue('☁️ on remote only')}"
        else:
            # Release files exist but no branch at all
            release_status = f" {utils.Color.red('⚠️ branch not found')}"

        click.echo(f"\n📦 {utils.Color.bold(f'Release {version}')} (ho-release/{version}):{release_status}")

        # Show staged patches
        if staged:
            click.echo(f"\n  {utils.Color.bold('Stage')} ({len(staged)} integrated):")
            for patch_id in staged:
                click.echo(f"    • {patch_id} {utils.Color.green('✓')}")

        # Show candidate patches with sync status
        if candidates:
            click.echo(f"\n  {utils.Color.bold('Candidates')} ({len(candidates)} in development):")
            for patch_id in candidates:
                # Find branch info for this patch
                branch_name = f"ho-patch/{patch_id}"
                branch_info = next((b for b in patch_branches if b['name'] == branch_name), None)

                if branch_info:
                    sync_status = branch_info.get('sync_status', 'unknown')
                    behind = branch_info.get('behind', 0)
                    ahead = branch_info.get('ahead', 0)

                    if sync_status == 'synced':
                        status = utils.Color.green("✓ synced")
                    elif sync_status == 'remote_only':
                        status = utils.Color.blue("☁️ on remote only (run: git checkout -b ho-patch/" + patch_id + " origin/ho-patch/" + patch_id + ")")
                    elif sync_status == 'behind':
                        status = utils.Color.blue(f"⚠️ {behind} commits behind")
                    elif sync_status == 'ahead':
                        status = utils.Color.blue(f"↑ {ahead} ahead")
                    elif sync_status == 'diverged':
                        status = utils.Color.red(f"⚠ diverged (↑{ahead} ↓{behind})")
                    elif sync_status == 'no_remote':
                        status = utils.Color.yellow("⚠️ local only (remote deleted or not pushed - run: git branch -d " + branch_name + ")")
                    else:
                        status = "?"

                    click.echo(f"    • {patch_id} - {status}")
                else:
                    # Branch doesn't exist anywhere
                    click.echo(f"    • {patch_id} {utils.Color.red('⚠ branch not found')}")

        if not staged and not candidates:
            click.echo(f"    {utils.Color.blue('(empty - no patches yet)')}")


def _is_patch_in_releases(branch_name: str, releases_info: dict) -> bool:
    """Check if a patch branch is referenced in any release candidates or stage.

    Args:
        branch_name: Branch name (e.g., "ho-patch/42-feature-x")
        releases_info: Dict of release information

    Returns:
        True if patch is in any candidates or staged list
    """
    # Extract patch_id from branch name
    if not branch_name.startswith('ho-patch/'):
        return False

    patch_id = branch_name.replace('ho-patch/', '')

    for info in releases_info.values():
        if patch_id in info.get('candidates', []):
            return True
        if patch_id in info.get('staged', []):
            return True

    return False
