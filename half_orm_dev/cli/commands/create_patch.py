"""
Create-patch command implementation.

Thin CLI layer that delegates to PatchManager for business logic.
"""

import click
from typing import Optional

from half_orm_dev.repo import Repo
from half_orm_dev.patch_manager import PatchManagerError


@click.command('create-patch')
@click.argument('patch_id', type=str)
@click.option(
    '--description', '-d',
    type=str,
    default=None,
    help='Optional description for the patch'
)
def create_patch(patch_id: str, description: Optional[str] = None) -> None:
    """
    Create new patch branch and directory structure.

    Creates a new ho-patch/PATCH_ID branch from ho-prod and sets up the
    corresponding Patches/PATCH_ID/ directory structure for schema changes.

    This command must be run from the ho-prod branch. All business logic
    is delegated to PatchManager.

    Args:
        patch_id: Patch identifier (e.g., "456" or "456-user-authentication")
        description: Optional description to include in patch README

    Examples:
        Create patch with numeric ID:
        $ half_orm dev create-patch "456"

        Create patch with full ID and description:
        $ half_orm dev create-patch "456-user-auth" --description "Add user authentication"

    Raises:
        click.ClickException: If validation fails or creation errors occur
    """
    try:
        # Get repository instance
        repo = Repo()

        # Delegate to PatchManager
        result = repo.patch_manager.create_patch(patch_id, description)

        # Display success message
        click.echo(f"✓ Created patch branch: {result['branch_name']}")
        click.echo(f"✓ Created patch directory: {result['patch_dir']}")
        click.echo(f"✓ Switched to branch: {result['on_branch']}")
        click.echo()
        click.echo("Next steps:")
        click.echo(f"  1. Add SQL/Python files to {result['patch_dir']}/")
        click.echo("  2. Run: half_orm dev apply-patch")
        click.echo("  3. Test your changes")
        click.echo("  4. Run: half_orm dev add-to-release")

    except PatchManagerError as e:
        raise click.ClickException(str(e))
