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
    '--dry-run',
    is_flag=True,
    help='Show what would be done without making changes'
)
@click.option(
    '--verbose', '-v',
    is_flag=True,
    help='Show detailed information'
)
def check(dry_run: bool, verbose: bool) -> None:
    """
    Verify and update project configuration.

    Checks project health and updates components as needed. This command
    is also run automatically at the start of other commands.

    Checks performed:
      • Git hooks are up to date (pre-commit)
      • Repository is properly configured
      • Detect and prompt to clean up stale local branches

    Examples:
        # Basic check and update
        half_orm dev check

        # Preview what would be done
        half_orm dev check --dry-run
    """
    try:
        repo = Repo()

        # Perform check (delegates to Repo)
        result = repo.check_and_update(
            dry_run=dry_run,
            silent=False  # Show messages
        )

        # Display results
        _display_check_results(repo, result, dry_run, verbose)

    except Exception as e:
        click.echo(utils.Color.red(f"❌ Error: {e}"), err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        raise click.Abort()


def _display_check_results(repo, result: dict, dry_run: bool, verbose: bool):
    """Display check results to user."""
    # Version check - display first and potentially interrupt
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
            # Critical update notice - display prominently at the top
            click.echo()
            click.echo(f"{'='*70}")
            click.echo(f"⚠️  {utils.Color.bold('UPDATE AVAILABLE')} ⚠️")
            click.echo(f"{'='*70}")
            click.echo(f"Current version: {utils.Color.bold(current)}")
            click.echo(f"Latest version:  {utils.Color.green(utils.Color.bold(latest))}")
            click.echo()
            click.echo(f"To update, run: {utils.Color.bold('pip install --upgrade half_orm_dev')}")
            click.echo(f"{'='*70}")
            click.echo()

            # Prompt user to update now
            if click.confirm("Do you want to interrupt and update now?", default=False):
                click.echo(f"\nℹ️  Please run the following command:")
                click.echo(f"   {utils.Color.bold('pip install --upgrade half_orm_dev')}")
                click.echo()
                raise click.Abort()

            click.echo()
        elif current:
            click.echo(f"✓ {utils.Color.green(f'half_orm_dev: {current} (latest)')}")
            click.echo()

    # Production version
    production_version = result.get('production_version')
    if production_version:
        click.echo(f"📦 {utils.Color.bold('Production version:')} {utils.Color.green(production_version)}")
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

    # Stale branches detection and cleanup
    stale_branches = result.get('stale_branches', {})
    candidates = stale_branches.get('candidates', [])

    if candidates:
        click.echo()
        if dry_run:
            click.echo(f"⚠️  {utils.Color.bold(f'Found {len(candidates)} stale local branch(es)')} (no longer on remote):")
            for branch in candidates[:10]:
                click.echo(f"  ○ {branch}")
            if len(candidates) > 10:
                click.echo(f"  ... and {len(candidates) - 10} more")
            click.echo(f"\n  Run without --dry-run to be prompted for deletion")
        else:
            # Show stale branches and prompt for deletion
            click.echo(f"⚠️  {utils.Color.bold(f'Found {len(candidates)} stale local branch(es)')} (no longer on remote):")
            for branch in candidates[:10]:
                click.echo(f"  • {branch}")
            if len(candidates) > 10:
                click.echo(f"  ... and {len(candidates) - 10} more")
            click.echo()

            # Prompt for confirmation
            if click.confirm(f"Delete these {len(candidates)} branch(es)?", default=False):
                # Get repo instance and actually delete the branches
                deleted = []
                errors = []
                try:
                    delete_result = repo.hgit.prune_local_branches(
                        pattern="ho-*",
                        dry_run=False,
                        exclude_current=True
                    )
                    deleted = delete_result.get('deleted', [])
                    errors = delete_result.get('errors', [])

                    if deleted:
                        click.echo(f"\n✓ {utils.Color.green(f'Deleted {len(deleted)} stale branch(es)')}")
                        if verbose:
                            for branch in deleted[:10]:
                                click.echo(f"  ✓ {branch}")
                            if len(deleted) > 10:
                                click.echo(f"  ... and {len(deleted) - 10} more")

                    if errors:
                        click.echo(f"\n⚠ {utils.Color.red('Some errors occurred during cleanup')}")
                        if verbose:
                            for branch, error in errors[:3]:
                                click.echo(f"  {branch}: {error}")
                except Exception as e:
                    click.echo(utils.Color.red(f"\n❌ Error deleting branches: {e}"), err=True)


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
        metadata = info.get('metadata', {})

        # Check if release branch exists
        release_branch_name = f"ho-release/{version}"
        release_branch_info = next((b for b in release_branches if b['name'] == release_branch_name), None)

        # Release header with status
        release_status = ""
        if release_branch_info:
            sync_status = release_branch_info.get('sync_status', 'unknown')
            ahead = release_branch_info.get('ahead', 0)
            behind = release_branch_info.get('behind', 0)
            exists_on_remote = release_branch_info.get('exists_on_remote', False)

            if not exists_on_remote:
                release_status = f" {utils.Color.bold('⚠️ local only - remote deleted')}"
            elif sync_status == 'remote_only':
                release_status = f" {utils.Color.blue('☁️ on remote only')}"
            elif sync_status == 'synced':
                release_status = f" {utils.Color.green('✓ synced')}"
            elif sync_status == 'ahead':
                release_status = f" {utils.Color.blue(f'↑ {ahead} ahead')}"
            elif sync_status == 'behind':
                release_status = f" {utils.Color.blue(f'↓ {behind} behind')}"
            elif sync_status == 'diverged':
                release_status = f" {utils.Color.red(f'⚠ diverged (↑{ahead} ↓{behind})')}"
        else:
            # Release files exist but no branch at all
            release_status = f" {utils.Color.red('⚠️ branch not found')}"

        click.echo(f"\n🚧 {utils.Color.bold(f'Release {version}')} (ho-release/{version}):{release_status}")

        # Show staged patches
        if staged:
            click.echo(f"\n  {utils.Color.bold('Stage')} ({len(staged)} integrated):")
            for patch_id in staged:
                click.echo(f"    • {patch_id} {utils.Color.green('✓')}")

        # Show candidate patches with sync status
        needs_sync = []  # Track patches that need synchronization
        rebased_commits = metadata.get('rebased_commits', {})

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

                    # Check if this patch was rebased and needs sync
                    expected_sha = rebased_commits.get(patch_id)
                    if expected_sha:
                        # Get local SHA (first 8 chars to match expected format)
                        import git
                        try:
                            repo = git.Repo('.')
                            if branch_name in [b.name for b in repo.branches]:
                                local_sha = repo.branches[branch_name].commit.hexsha[:8]
                                if local_sha != expected_sha:
                                    needs_sync.append(patch_id)
                                    status = utils.Color.red(f"⚠️ NEEDS SYNC (rebased to {expected_sha}, local: {local_sha})")
                                else:
                                    status = utils.Color.green(f"✓ synced (rebased: {expected_sha})")
                            else:
                                # Branch doesn't exist locally but was rebased
                                needs_sync.append(patch_id)
                                status = utils.Color.red(f"⚠️ NEEDS CHECKOUT (rebased: {expected_sha})")
                        except Exception:
                            status = utils.Color.blue("? (cannot check SHA)")
                    else:
                        # Normal sync status (not rebased)
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
                            status = utils.Color.bold("⚠️ local only (remote deleted or not pushed - run: git branch -d " + branch_name + ")")
                        else:
                            status = "?"

                    click.echo(f"    • {patch_id} - {status}")
                else:
                    # Branch doesn't exist anywhere
                    click.echo(f"    • {patch_id} {utils.Color.red('⚠ branch not found')}")

        # Show migration sync warning if needed
        if needs_sync:
            click.echo(f"\n  {utils.Color.bold(utils.Color.red('⚠️  MIGRATION DETECTED:'))}")
            click.echo(f"    {len(needs_sync)} patch(es) were rebased during promotion to production")
            click.echo(f"    You must sync your local branches:")
            click.echo()
            for patch_id in needs_sync:
                click.echo(f"      git checkout ho-patch/{patch_id}")
                click.echo(f"      git fetch origin")
                click.echo(f"      git reset --hard origin/ho-patch/{patch_id}")
                click.echo()

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
