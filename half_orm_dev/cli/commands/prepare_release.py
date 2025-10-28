"""
Prepare-release command - Prepares the next release stage file

Creates releases/X.Y.Z-stage.txt based on production version and increment level.
Part of Git-centric release workflow (stage → rc → production).
"""

import click
import sys
from half_orm_dev.repo import Repo
from half_orm_dev.release_manager import (
    ReleaseManagerError,
    ReleaseFileError,
    ReleaseVersionError
)
from half_orm import utils


@click.command()
@click.argument(
    'level',
    type=click.Choice(['patch', 'minor', 'major'], case_sensitive=False)
)
def prepare_release(level):
    """
    Prepare next release stage file.

    Creates releases/X.Y.Z-stage.txt based on production version and
    semantic versioning increment level.

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
        # Prepare patch release (production 1.3.5 → 1.3.6)
        half_orm dev prepare-release patch

        # Prepare minor release (production 1.3.5 → 1.4.0)
        half_orm dev prepare-release minor

        # Prepare major release (production 1.3.5 → 2.0.0)
        half_orm dev prepare-release major

    \b
    Next steps after prepare-release:
        • Create patches: half_orm dev create-patch <patch_id>
        • Add to release: half_orm dev add-to-release <patch_id>
        • Promote to RC: half_orm dev promote-to rc
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
        click.echo(f"  1. Create patches: {utils.Color.bold(f'half_orm dev create-patch <patch_id>')}")
        click.echo(f"  2. Add to release: {utils.Color.bold(f'half_orm dev add-to-release <patch_id>')}")
        click.echo(f"  3. Promote to RC:  {utils.Color.bold('half_orm dev promote-to rc')}")
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
