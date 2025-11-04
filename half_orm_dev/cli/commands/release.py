"""
Release command group - Unified release management.

Groups all release-related commands under 'half_orm dev release':
- release new: Prepare next release stage file
- release promote: Promote stage to rc or production

Replaces legacy commands:
- prepare-release → release new
- promote-to → release promote
"""

import click
import sys
from typing import Optional

from half_orm_dev.repo import Repo
from half_orm_dev.release_manager import (
    ReleaseManagerError,
    ReleaseFileError,
    ReleaseVersionError
)
from half_orm import utils


@click.group()
def release():
    """
    Release management commands.

    Prepare, promote, and deploy releases with this unified command group.

    \b
    Common workflow:
        1. half_orm dev release new <level>
        2. half_orm dev patch add <patch_id>
        3. half_orm dev release promote rc
        4. half_orm dev release promote prod
    """
    pass


@release.command('new')
@click.argument(
    'level',
    type=click.Choice(['patch', 'minor', 'major'], case_sensitive=False)
)
def release_new(level: str) -> None:
    """
    Prepare next release stage file.

    Creates releases/X.Y.Z-stage.txt based on production version and
    semantic versioning increment level.

    \b
    LEVEL: Version increment type (patch, minor, or major)

    \b
    Semantic versioning rules:
    • patch: Bug fixes, minor changes (1.3.5 → 1.3.6)
    • minor: New features, backward compatible (1.3.5 → 1.4.0)
    • major: Breaking changes (1.3.5 → 2.0.0)

    \b
    Workflow:
    1. Read production version from model/schema.sql
    2. Calculate next version (patch/minor/major)
    3. Create releases/X.Y.Z-stage.txt
    4. Commit and push to reserve version globally

    \b
    Requirements:
    • Must be on ho-prod branch
    • Repository must be clean (no uncommitted changes)
    • Must be synced with origin/ho-prod

    \b
    Examples:
        Prepare patch release (production 1.3.5 → 1.3.6):
        $ half_orm dev release new patch

        Prepare minor release (production 1.3.5 → 1.4.0):
        $ half_orm dev release new minor

        Prepare major release (production 1.3.5 → 2.0.0):
        $ half_orm dev release new major

    \b
    Next steps after release new:
        • Create patches: half_orm dev patch new <patch_id>
        • Add to release: half_orm dev patch add <patch_id>
        • Promote to RC: half_orm dev release promote rc
    """
    # Normalize level to lowercase
    level = level.lower()

    try:
        # Get Repo singleton
        repo = Repo()

        # Get ReleaseManager
        release_mgr = repo.release_manager

        click.echo(f"Preparing {level} release...")
        click.echo()

        # Prepare release
        result = release_mgr.prepare_release(level)

        # Extract result info
        version = result['version']
        stage_file = result['file']
        previous_version = result['previous_version']

        # Success message
        click.echo(f"✅ {utils.Color.bold('Release prepared successfully!')}")
        click.echo()
        click.echo(f"  Previous version: {utils.Color.bold(previous_version)}")
        click.echo(f"  New version:      {utils.Color.bold(version)}")
        click.echo(f"  Stage file:       {utils.Color.bold(stage_file)}")
        click.echo()
        click.echo(f"📝 Next steps:")
        click.echo(f"  1. Create patches: {utils.Color.bold(f'half_orm dev patch new <patch_id>')}")
        click.echo(f"  2. Add to release: {utils.Color.bold(f'half_orm dev patch add <patch_id>')}")
        click.echo(f"  3. Promote to RC:  {utils.Color.bold('half_orm dev release promote rc')}")
        click.echo()

    except ReleaseManagerError as e:
        # Handle validation errors (branch, clean, sync, etc.)
        click.echo(f"❌ {utils.Color.red('Release preparation failed:')}", err=True)
        click.echo(f"   {str(e)}", err=True)
        sys.exit(1)

    except ReleaseFileError as e:
        # Handle file errors (missing schema, stage exists, etc.)
        click.echo(f"❌ {utils.Color.red('File error:')}", err=True)
        click.echo(f"   {str(e)}", err=True)
        sys.exit(1)

    except ReleaseVersionError as e:
        # Handle version errors (invalid format, calculation, etc.)
        click.echo(f"❌ {utils.Color.red('Version error:')}", err=True)
        click.echo(f"   {str(e)}", err=True)
        sys.exit(1)


@release.command('promote')
@click.argument('target', type=click.Choice(['rc', 'prod'], case_sensitive=False))
def release_promote(target: str) -> None:
    """
    Promote stage release to RC or production.

    Promotes the smallest stage release to RC (rc1, rc2, etc.) or promotes
    an RC to production. Merges archived patch code into ho-prod and
    manages branch cleanup. Must be run from ho-prod branch.

    \b
    TARGET: Either 'rc' or 'prod'
    • rc: Promotes stage to release candidate (with branch cleanup)
    • prod: Promotes RC to production release (generates schema dumps)

    \b
    Complete workflow for RC:
        1. Detect smallest stage release (sequential promotion)
        2. Validate single active RC rule
        3. Acquire distributed lock on ho-prod
        4. Merge archived patches code into ho-prod
        5. Rename stage file to RC file (git mv)
        6. Commit and push promotion
        7. Send rebase notifications to active branches
        8. Cleanup patch branches
        9. Release lock

    \b
    Complete workflow for Production:
        1. Detect latest RC file
        2. Validate sequential version rule
        3. Acquire distributed lock on ho-prod
        4. Restore database and apply all patches
        5. Generate schema-X.Y.Z.sql and metadata-X.Y.Z.sql
        6. Update schema.sql symlink
        7. Rename RC file to production file (git mv)
        8. Commit and push promotion
        9. Release lock

    \b
    Examples:
        Promote smallest stage release to RC:
        $ half_orm dev release promote rc

        Output:
        ✓ Promoted 1.3.5-stage → 1.3.5-rc1
        ✓ Merged 3 patches into ho-prod
        ✓ Deleted 3 patch branches
        ✓ Notified 2 active branches

        Promote RC to production:
        $ half_orm dev release promote prod

        Output:
        ✓ Promoted 1.3.5-rc1 → 1.3.5
        ✓ Generated schema-1.3.5.sql
        ✓ Generated metadata-1.3.5.sql
        ✓ Updated schema.sql → schema-1.3.5.sql

    \b
    Next steps after promote rc:
        • Test RC: Run integration tests
        • Fix issues: Create patches, add to new stage, promote again
        • Deploy: half_orm dev release promote prod

    \b
    Next steps after promote prod:
        • Tag release: git tag v1.3.5
        • Deploy to production: Use db upgrade on production servers
        • Start next cycle: half_orm dev release new patch

    \b
    Raises:
        click.ClickException: If validations fail or workflow errors occur
    """
    try:
        # Get repository instance
        repo = Repo()

        # Delegate to ReleaseManager
        click.echo(f"Promoting release to {target.upper()}...")
        click.echo()

        result = repo.release_manager.promote_to(target.lower())

        # Display success message
        click.echo(f"✓ {utils.Color.green('Success!')}")
        click.echo()

        # Target-specific output
        if target.lower() == 'rc':
            # RC promotion output
            click.echo(f"  Promoted:        {utils.Color.bold(result['from_file'])} → {utils.Color.bold(result['to_file'])}")
            patches = result.get('patches_merged')
            if patches:
                click.echo(f"  Patches merged:  {utils.Color.bold(str(len(patches)))} patch(es)")
            click.echo(f"  Branches cleaned: {utils.Color.bold(str(len(result['branches_deleted'])))} branch(es)")

            if result.get('notified_branches'):
                click.echo(f"  Notified:        {len(result['notified_branches'])} active branch(es)")

            click.echo()
            click.echo("📝 Next steps:")
            click.echo(f"  • Test RC thoroughly")
            click.echo(f"  • Fix issues: Create patch, add to new stage, promote again")
            click.echo(f"  • Deploy to production: {utils.Color.bold('half_orm dev release promote prod')}")

        else:
            # Production promotion output
            click.echo(f"  Promoted:        {utils.Color.bold(result['from_file'])} → {utils.Color.bold(result['to_file'])}")
            click.echo(f"  Version:         {utils.Color.bold(result['version'])}")

            if result.get('schema_file'):
                click.echo(f"  Schema:          {utils.Color.bold(result['schema_file'])}")
            if result.get('metadata_file'):
                click.echo(f"  Metadata:        {utils.Color.bold(result['metadata_file'])}")
            if result.get('symlink_updated'):
                click.echo(f"  Symlink:         schema.sql → {utils.Color.bold(result['schema_file'])}")

            click.echo()
            click.echo("📝 Next steps:")
            click.echo(f"""  • Tag release: {utils.Color.bold(f'git tag v{result["version"]}')}""")
            click.echo(f"  • Deploy to production servers: {utils.Color.bold('half_orm dev db upgrade')}")
            click.echo(f"  • Start next cycle: {utils.Color.bold('half_orm dev release new patch')}")

        click.echo()

    except ReleaseManagerError as e:
        raise click.ClickException(str(e))


@release.command('hotfix')
@click.argument('patch_id', type=str)
def release_hotfix(patch_id: str) -> None:
    """
    Create emergency hotfix release (NOT IMPLEMENTED YET).

    Creates a hotfix release that bypasses the normal stage → rc → prod
    workflow for critical production issues.

    \b
    Args:
        patch_id: Patch identifier for the hotfix

    \b
    Example:
        $ half_orm dev release hotfix critical-security-fix

    \b
    Status: 🚧 Not implemented - planned for future release
    """
    click.echo("🚧 Hotfix release creation not implemented yet")
    click.echo()
    click.echo("Planned workflow:")
    click.echo("  1. Create ho-patch/PATCH_ID from ho-prod")
    click.echo("  2. Create releases/X.Y.Z-hotfixN.txt")
    click.echo("  3. Emergency deployment workflow")
    click.echo()
    raise NotImplementedError("Hotfix release creation not yet implemented")


@release.command('apply')
@click.argument('version', type=str, required=False)
def release_apply(version: Optional[str] = None) -> None:
    """
    Test complete release before deployment (NOT IMPLEMENTED YET).

    Applies all patches from a release file to test the complete
    release workflow before production deployment.

    \b
    Args:
        version: Release version to test (e.g., "1.3.5-rc1")
                 If not provided, applies latest RC

    \b
    Examples:
        Test latest RC:
        $ half_orm dev release apply

        Test specific RC:
        $ half_orm dev release apply 1.3.5-rc1

        Test stage release:
        $ half_orm dev release apply 1.3.5-stage

    \b
    Status: 🚧 Not implemented - planned for future release
    """
    click.echo("🚧 Release testing not implemented yet")
    click.echo()
    click.echo("Planned workflow:")
    click.echo("  1. Restore database from model/schema.sql")
    click.echo("  2. Apply all patches from release file")
    click.echo("  3. Run comprehensive tests")
    click.echo("  4. Validate final state")
    click.echo()
    raise NotImplementedError("Release apply not yet implemented")
