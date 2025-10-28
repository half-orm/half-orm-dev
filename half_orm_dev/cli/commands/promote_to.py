"""
Promote-to command implementation.

Thin CLI layer that delegates to ReleaseManager for business logic.
Promotes stage release to target ('rc' or 'prod') with code merge and branch cleanup.
"""

import click
import sys

from half_orm_dev.repo import Repo
from half_orm_dev.release_manager import ReleaseManagerError
from half_orm import utils


@click.command('promote-to')
@click.argument('target', type=click.Choice(['rc', 'prod'], case_sensitive=False))
def promote_to(target: str) -> None:
    """
    Promote stage release to release candidate.

    Promotes the smallest stage release to RC (rc1, rc2, etc.), merges all
    archived patch code into ho-prod, and deletes patch branches. Must be
    run from ho-prod branch.

    Complete workflow:
        1. Detect smallest stage release (sequential promotion)
        2. Validate single active RC rule
        3. Acquire distributed lock on ho-prod
        4. Merge archived patches code into ho-prod
        5. Rename stage file to RC file (git mv)
        6. Commit and push promotion
        7. Send rebase notifications to active branches
        8. Cleanup patch branches
        9. Release lock

    Examples:
        # Promote smallest stage release
        $ half_orm dev promote-to

        # Output:
        # ✓ Promoted 1.3.5-stage → 1.3.5-rc1
        # ✓ Merged 3 patches into ho-prod
        # ✓ Deleted 3 patch branches
        # ✓ Notified 2 active branches

    Raises:
        click.ClickException: If validations fail or workflow errors occur
    """
    try:
        # Get repository instance
        repo = Repo()

        # Delegate to ReleaseManager
        click.echo(f"Promoting stage release to {target.upper()}...")
        click.echo()

        result = repo.release_manager.promote_to(target.lower())

        # Display success message
        click.echo(f"✓ {utils.Color.green('Success!')}")
        click.echo()
        click.echo(f"Promoted: {utils.Color.bold(result['from_file'])} → {utils.Color.bold(result['to_file'])}")
        click.echo(f"Version: {utils.Color.bold(result['version'])}")
        if result.get('rc_number'):
            click.echo(f"RC number: {utils.Color.bold(str(result['rc_number']))}")
        click.echo()

        # Display merged patches
        if result['patches_merged']:
            click.echo(f"✓ Merged {len(result['patches_merged'])} patches into ho-prod:")
            for patch in result['patches_merged']:
                click.echo(f"  • {patch}")
            click.echo()
        else:
            click.echo("✓ No patches to merge (empty stage)")
            click.echo()

        # Display deleted branches
        if result['branches_deleted']:
            click.echo(f"✓ Deleted {len(result['branches_deleted'])} patch branches")
            click.echo()

        # Display notifications
        if result.get('notifications_sent'):
            click.echo(f"✓ Notified {len(result['notifications_sent'])} active patch branches:")
            for branch in result['notifications_sent']:
                click.echo(f"  • {branch}")
            click.echo()

        # Display commit info
        click.echo(f"Commit: {utils.Color.bold(result['commit_sha'][:8])}")
        click.echo(f"Lock: {result['lock_tag']}")
        click.echo()

        # Next steps
        click.echo(f"{utils.Color.bold('📝 Next steps:')}")
        click.echo(f"""  1. Test RC: {utils.Color.bold(f'half_orm dev apply-release {result["to_file"].replace(".txt", "")}')}""")
        click.echo(f"  2. If tests pass: {utils.Color.bold('half_orm dev promote-to prod')}")
        click.echo(f"  3. If issues found: Create fix patch and add to new RC")
        click.echo()

    except ReleaseManagerError as e:
        # Handle expected errors
        click.echo(f"❌ {utils.Color.red('Promotion failed:')}", err=True)
        click.echo(f"   {str(e)}", err=True)
        click.echo()

        # Provide helpful hints based on error type
        error_msg = str(e).lower()

        if "must be on ho-prod" in error_msg:
            click.echo("💡 Switch to ho-prod: git checkout ho-prod", err=True)
        elif "uncommitted changes" in error_msg:
            click.echo("💡 Commit or stash changes first", err=True)
        elif "no stage releases" in error_msg:
            click.echo("💡 Create a stage release: half_orm dev prepare-release", err=True)
        elif "rc" in error_msg and "must be deployed" in error_msg:
            click.echo("💡 Deploy existing RC to production first", err=True)
        elif "lock held" in error_msg or "lock" in error_msg:
            click.echo("💡 Another operation in progress, retry later", err=True)
        elif "merge conflict" in error_msg:
            click.echo("💡 Resolve conflicts manually and retry", err=True)
        elif "diverged" in error_msg:
            click.echo("💡 Resolve ho-prod divergence: git pull origin ho-prod", err=True)

        sys.exit(1)
