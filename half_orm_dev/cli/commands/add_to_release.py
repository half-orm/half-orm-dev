"""
Add-to-release command implementation.

Thin CLI layer that delegates to ReleaseManager for business logic.
Adds patch to stage release file with validation and distributed lock.
"""

import click
from typing import Optional

from half_orm_dev.repo import Repo
from half_orm_dev.release_manager import ReleaseManagerError


@click.command('add-to-release')
@click.argument('patch_id', type=str)
@click.option(
    '--to-version', '-v',
    type=str,
    default=None,
    help='Target release version (required if multiple stage releases exist)'
)
def add_to_release(patch_id: str, to_version: Optional[str] = None) -> None:
    """
    Add patch to stage release file with validation.

    Integrates developed patch into a stage release for deployment.
    Must be run from ho-prod branch. All business logic is delegated
    to ReleaseManager with distributed lock for safe concurrent operations.

    Complete workflow:
        1. Acquire exclusive lock on ho-prod (via Git tag)
        2. Create temporary validation branch
        3. Apply all release patches + current patch
        4. Run pytest validation tests
        5. If tests pass: integrate to ho-prod
        6. If tests fail: cleanup and exit with error
        7. Send resync notifications to other patch branches
        8. Archive patch branch to ho-release/{version}/ namespace
        9. Release lock (always, even on error)

    Args:
        patch_id: Patch identifier (e.g., "456-user-auth")
        to_version: Optional explicit version (e.g., "1.3.6")
                   Required if multiple stage releases exist
                   Auto-detected if only one stage exists

    Examples:
        Add patch to auto-detected stage (one stage exists):
        $ half_orm dev add-to-release "456-user-auth"

        Add patch to specific version (multiple stages):
        $ half_orm dev add-to-release "456-user-auth" --to-version="1.3.6"

        Using short option:
        $ half_orm dev add-to-release "456" -v "1.4.0"

    Raises:
        click.ClickException: If validations fail, tests fail, or lock cannot be acquired
    """
    try:
        # Get repository instance
        repo = Repo()

        # Delegate to ReleaseManager
        result = repo.release_manager.add_patch_to_release(patch_id, to_version)

        # Display success message
        click.echo(f"✓ Patch {result['patch_id']} added to release {result['target_version']}-stage")
        click.echo(f"✓ Tests passed on temporary validation branch")
        click.echo(f"✓ Committed to ho-prod: {result['commit_sha'][:8]}")
        click.echo(f"✓ Branch archived: {result['archived_branch']}")

        click.echo()
        click.echo(f"📦 Release {result['target_version']}-stage now contains:")
        for patch in result['patches_in_release']:
            marker = "→" if patch == patch_id else " "
            click.echo(f"  {marker} {patch}")

        click.echo()
        click.echo("Next steps:")
        click.echo(f"  1. Review integration: git show {result['commit_sha'][:8]}")
        click.echo(f"  2. Test release: half_orm dev apply-release {result['target_version']}-stage")
        click.echo(f"  3. Promote to RC: half_orm dev promote-to-rc")

    except ReleaseManagerError as e:
        raise click.ClickException(str(e))
    except Exception as e:
        raise click.ClickException(f"Unexpected error: {e}")
