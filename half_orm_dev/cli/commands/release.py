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

        click.echo(f"Creating {level} release with integration branch...")
        click.echo()

        # Create new release with integration branch
        result = release_mgr.new_release(level)

        # Extract result info
        version = result['version']
        branch = result['branch']
        patches_file = result['patches_file']

        # Success message
        click.echo(f"✅ {utils.Color.bold('Release created successfully!')}")
        click.echo()
        click.echo(f"  Version:          {utils.Color.bold(version)}")
        click.echo(f"  Release branch:   {utils.Color.bold(branch)}")
        click.echo(f"  Patches file:     {utils.Color.bold(patches_file)}")
        click.echo()
        click.echo(f"📝 Next steps:")
        click.echo(f"  1. Switch to release branch: {utils.Color.bold(f'git checkout {branch}')}")
        click.echo(f"  2. Create patches: {utils.Color.bold(f'half_orm dev patch new <patch_id>')}")
        click.echo(f"  3. Close patches:  {utils.Color.bold(f'half_orm dev patch close <patch_id>')}")
        click.echo(f"  4. Promote to RC:  {utils.Color.bold('half_orm dev release promote rc')}")
        click.echo()
        click.echo(f"ℹ️  You are now on {utils.Color.bold(branch)} - patches will be merged here")
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
@click.argument('target', type=click.Choice(['rc', 'prod', 'hotfix'], case_sensitive=False))
def release_promote(target: str) -> None:
    """
    Promote stage release to RC, production, or hotfix.

    Promotes the smallest stage release to RC (rc1, rc2, etc.), promotes
    an RC to production, or promotes a hotfix to production. Merges code
    into ho-prod and manages branches.

    \b
    TARGET: Either 'rc', 'prod', or 'hotfix'
    • rc: Promotes stage to release candidate (from ho-release/X.Y.Z)
    • prod: Promotes RC to production release (generates schema dumps)
    • hotfix: Promotes hotfix to production (from ho-release/X.Y.Z)

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
        release_mgr = repo.release_manager

        # Delegate to ReleaseManager
        click.echo(f"Promoting release to {target.upper()}...")
        click.echo()

        # ReleaseManager auto-detects which version to promote
        if target.lower() == 'rc':
            result = release_mgr.promote_to_rc()
        elif target.lower() == 'hotfix':
            result = release_mgr.promote_to_hotfix()
        else:  # prod
            result = release_mgr.promote_to_prod()

        # Display success message
        click.echo(f"✓ {utils.Color.green('Success!')}")
        click.echo()

        # Target-specific output
        if target.lower() == 'rc':
            # RC promotion output
            click.echo(f"  Version:  {utils.Color.bold(result['version'])}")
            click.echo(f"  Tag:      {utils.Color.bold(result['tag'])}")
            click.echo(f"  Branch:   {utils.Color.bold(result['branch'])}")
            click.echo()
            click.echo("📝 Next steps:")
            click.echo(f"  • Test RC thoroughly")
            click.echo(f"  • If fixes needed: {utils.Color.bold('half_orm dev patch new <patch_id>')}")
            click.echo(f"  • Deploy to production: {utils.Color.bold('half_orm dev release promote prod')}")
            click.echo()
            click.echo(f"ℹ️  You are now on {utils.Color.bold(result['branch'])} - patches will be merged here")

        elif target.lower() == 'hotfix':
            # Hotfix promotion output
            click.echo(f"  Version:     {utils.Color.bold(result['version'])}")
            click.echo(f"  Hotfix tag:  {utils.Color.bold(result['hotfix_tag'])}")
            click.echo(f"  Branch:      {utils.Color.bold(result['branch'])}")
            click.echo()
            click.echo("📝 Next steps:")
            click.echo(f"  • Deploy hotfix to production servers")
            click.echo(f"  • Monitor for additional issues")
            click.echo(f"  • If more fixes needed: {utils.Color.bold('half_orm dev patch new <patch_id>')}")
            click.echo()
            click.echo(f"ℹ️  You are back on {utils.Color.bold(result['branch'])} - ready for more hotfixes if needed")

        else:
            # Production promotion output
            click.echo(f"  Version:          {utils.Color.bold(result['version'])}")
            click.echo(f"  Tag:              {utils.Color.bold(result['tag'])}")
            deleted = result.get('deleted_branches', [])
            if deleted:
                click.echo(f"  Branches deleted: {utils.Color.bold(str(len(deleted)))}")
            click.echo()
            click.echo("📝 Next steps:")
            click.echo(f"  • Deploy to production servers")
            click.echo(f"  • Start next cycle: {utils.Color.bold('half_orm dev release new minor')}")

        click.echo()

    except ReleaseManagerError as e:
        raise click.ClickException(str(e))


@release.command('hotfix')
@click.argument('version', type=str, required=False)
def release_hotfix(version: Optional[str] = None) -> None:
    """
    Reopen a production version for hotfix development.

    Recreates the ho-release/X.Y.Z branch from the production tag vX.Y.Z
    and creates empty candidates.txt and stage.txt files to enable
    emergency patches on a production version.

    \b
    Args:
        version: Production version to reopen (e.g., "1.3.5")
                If not provided, uses current production version from model/schema.sql

    \b
    Complete workflow:
        1. Detect production version (from model/schema.sql or parameter)
        2. Verify production tag vX.Y.Z exists
        3. Delete existing ho-release/X.Y.Z branch if exists
        4. Create branch from production tag
        5. Create empty X.Y.Z-candidates.txt file
        6. Create empty X.Y.Z-stage.txt file
        7. Commit and push
        8. Switch to branch

    \b
    Examples:
        Reopen current production version:
        $ half_orm dev release hotfix

        Output:
        ✓ Reopened version 1.3.5 for hotfix
          Branch:           ho-release/1.3.5
          Candidates file:  releases/1.3.5-candidates.txt
          Stage file:       releases/1.3.5-stage.txt

        Reopen specific version:
        $ half_orm dev release hotfix 1.3.4

    \b
    Next steps after hotfix:
        • Create patches: half_orm dev patch new <patch_id>
        • Close patches: half_orm dev patch close <patch_id>
        • Promote hotfix: half_orm dev release promote hotfix

    \b
    Raises:
        click.ClickException: If validation fails or reopening errors occur
    """
    try:
        # Get repository instance
        repo = Repo()

        # Display context
        if version:
            click.echo(f"⚠️  Version parameter is ignored - will reopen current production version")
        click.echo("Reopening current production version for hotfix...")
        click.echo()

        # Delegate to ReleaseManager (auto-detects version)
        result = repo.release_manager.reopen_for_hotfix()

        # Display success message
        click.echo(f"✓ {utils.Color.green('Version reopened for hotfix successfully!')}")
        click.echo()
        click.echo(f"  Version:          {utils.Color.bold(result['version'])}")
        click.echo(f"  Branch:           {utils.Color.bold(result['branch'])}")
        click.echo(f"  Patches file:     {utils.Color.bold(result['patches_file'])}")
        click.echo()
        click.echo("📝 Next steps:")
        click.echo(f"  • Create patches: {utils.Color.bold('half_orm dev patch new <patch_id>')}")
        click.echo(f"  • Close patches: {utils.Color.bold('half_orm dev patch close <patch_id>')}")
        click.echo(f"  • Promote hotfix: {utils.Color.bold('half_orm dev release promote hotfix')}")
        click.echo()
        click.echo(f"ℹ️  You are now on {utils.Color.bold(result['branch'])} - patches will be merged here")
        click.echo()

    except ReleaseManagerError as e:
        raise click.ClickException(str(e))


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
