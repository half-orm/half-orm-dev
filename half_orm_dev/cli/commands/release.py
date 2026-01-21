"""
Release command group - Unified release management.

Groups all release-related commands under 'half_orm dev release':
- release create: Prepare next release stage file
- release promote: Promote stage to rc or production
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
        1. half_orm dev release create <level>
        2. half_orm dev patch create <patch_id>
        3. git checkout ho-patch/<patch_id> && half_orm dev patch merge
        4. half_orm dev release promote rc
        5. half_orm dev release promote prod
    """
    pass


@release.command('create')
@click.argument(
    'level',
    type=click.Choice(['patch', 'minor', 'major'], case_sensitive=False)
)
def release_create(level: str) -> None:
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
        $ half_orm dev release create patch

        Prepare minor release (production 1.3.5 → 1.4.0):
        $ half_orm dev release create minor

        Prepare major release (production 1.3.5 → 2.0.0):
        $ half_orm dev release create major

    \b
    Next steps after release create:
        • Create patches: half_orm dev patch create <patch_id>
        • Add to release: half_orm dev patch merge <patch_id>
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
        result = release_mgr.create_release(level)

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
        click.echo(f"  2. Create patches: {utils.Color.bold(f'half_orm dev patch create <patch_id>')}")
        click.echo(f"  3. Merge patches:  {utils.Color.bold('git checkout ho-patch/<patch_id> && half_orm dev patch merge')}")
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
        • Start next cycle: half_orm dev release create patch

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
            click.echo(f"  • If fixes needed: {utils.Color.bold('half_orm dev patch create <patch_id>')}")
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
            click.echo(f"  • If more fixes needed: {utils.Color.bold('half_orm dev patch create <patch_id>')}")
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
            click.echo(f"  • Start next cycle: {utils.Color.bold('half_orm dev release create minor')}")

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
        • Create patches: half_orm dev patch create <patch_id>
        • Merge patches: From ho-patch/<patch_id> branch, run: half_orm dev patch merge
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
        click.echo(f"  • Create patches: {utils.Color.bold('half_orm dev patch create <patch_id>')}")
        click.echo(f"  • Merge patches: {utils.Color.bold('git checkout ho-patch/<patch_id> && half_orm dev patch merge')}")
        click.echo(f"  • Promote hotfix: {utils.Color.bold('half_orm dev release promote hotfix')}")
        click.echo()
        click.echo(f"ℹ️  You are now on {utils.Color.bold(result['branch'])} - patches will be merged here")
        click.echo()

    except ReleaseManagerError as e:
        raise click.ClickException(str(e))


@release.command('apply')
@click.option(
    '--skip-tests',
    is_flag=True,
    help='Skip running pytest after applying patches'
)
def release_apply(skip_tests: bool) -> None:
    """
    Apply all patches for integration testing.

    Restores the database from production schema and applies ALL patches
    (candidates + staged) to test the complete release integration.
    Optionally runs pytest to validate the release.

    Unlike 'patch apply' which only applies validated (staged) patches,
    this command applies ALL patches including candidates that haven't
    passed individual validation yet. This enables testing the complete
    release before promotion.

    \b
    Workflow:
        1. Validate on release branch (ho-release/X.Y.Z)
        2. Restore database from model/schema.sql
        3. Apply all RC patches (if any)
        4. Apply ALL TOML patches (candidates + staged)
        5. Generate Python code
        6. Run pytest (unless --skip-tests)

    \b
    Requirements:
        - Must be on ho-release/X.Y.Z branch
        - Development release must exist

    \b
    Examples:
        Apply all patches and run tests:
        $ half_orm dev release apply

        Apply patches without running tests:
        $ half_orm dev release apply --skip-tests

    \b
    Output:
        ✓ Applied 5 patches for version 1.3.6
        ✓ Tests passed (42 tests)

        Or on failure:
        ✗ Tests failed
        <test output>
    """
    try:
        # Get repository instance
        repo = Repo()
        release_mgr = repo.release_manager

        # Display context
        click.echo("🔄 Applying all release patches for integration testing...")
        click.echo()

        # Apply release
        result = release_mgr.apply_release(run_tests=not skip_tests)

        # Display results
        version = result['version']
        patches = result['patches_applied']
        candidates = result.get('candidates_merged', [])
        patch_count = len(patches)

        click.echo(f"✓ {utils.Color.green('Patches applied successfully!')}")
        click.echo()
        click.echo(f"  Version:  {utils.Color.bold(version)}")
        click.echo(f"  Patches:  {utils.Color.bold(str(patch_count))}")
        if candidates:
            click.echo(f"  Candidates merged: {utils.Color.bold(str(len(candidates)))}")
        click.echo()

        # Show candidates merged (simulated merges)
        if candidates:
            click.echo("  Candidate branches merged (simulated):")
            for patch_id in candidates:
                click.echo(f"    • ho-patch/{patch_id}")
            click.echo()

        # Show patches applied
        if patches:
            click.echo("  Applied patches (SQL):")
            for patch_id in patches:
                click.echo(f"    • {patch_id}")
            click.echo()

        # Show test results
        if skip_tests:
            click.echo(f"⚠️  {utils.Color.bold('Tests skipped')} (--skip-tests flag)")
        elif result['tests_passed'] is None:
            click.echo(f"⚠️  {utils.Color.bold('Tests not run')} (pytest not found)")
        elif result['tests_passed']:
            click.echo(f"✓ {utils.Color.green('Tests passed!')}")
        else:
            click.echo(f"✗ {utils.Color.red('Tests failed!')}")
            click.echo()
            click.echo("Test output:")
            click.echo(result['test_output'])
            sys.exit(1)

        click.echo()
        click.echo("📝 Next steps:")
        if result['tests_passed'] or result['tests_passed'] is None:
            click.echo(f"  • Promote to RC: {utils.Color.bold('half_orm dev release promote rc')}")
        else:
            click.echo(f"  • Fix failing tests")
            click.echo(f"  • Re-run: {utils.Color.bold('half_orm dev release apply')}")

    except ReleaseManagerError as e:
        click.echo(f"❌ {utils.Color.red('Release apply failed:')}", err=True)
        click.echo(f"   {str(e)}", err=True)
        sys.exit(1)
