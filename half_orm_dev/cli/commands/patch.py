"""
Patch command group - Unified patch development and management.

Groups all patch-related commands under 'half_orm dev patch':
- patch create: Create new patch branch and directory
- patch apply: Apply current patch files to database
- patch merge: Add patch to stage release with validation
- patch detach: Detach a candidate patch from its release

Replaces legacy commands:
- create-patch → patch create
- apply-patch → patch apply
- add-to-release → patch merge
"""

import click
from pathlib import Path
from typing import Optional

from half_orm_dev.repo import Repo
from half_orm_dev.patch_manager import PatchManagerError
from half_orm_dev.release_manager import ReleaseManagerError
from half_orm import utils


@click.group()
def patch():
    """
    Patch development and management commands.

    Create, apply, and integrate patches into releases with this
    unified command group.

    \b
    Common workflow:
        1. half_orm dev patch create <patch_id>
        2. half_orm dev patch apply
        3. half_orm dev patch merge
    """
    pass


@patch.command('create')
@click.argument('patch_id', type=str)
@click.option(
    '--description', '-d',
    type=str,
    default=None,
    help='Optional description for the patch'
)
@click.option(
    '--before',
    type=str,
    default=None,
    help='Insert patch before this patch ID in the application order'
)
def patch_create(patch_id: str, description: Optional[str] = None, before: Optional[str] = None) -> None:
    """
    Create new patch branch and directory structure.

    Creates a new ho-patch/PATCH_ID branch from ho-prod and sets up the
    corresponding Patches/PATCH_ID/ directory structure for schema changes.

    This command must be run from the ho-prod branch. All business logic
    is delegated to PatchManager.

    \b
    Args:
        patch_id: Patch identifier (e.g., "456" or "456-user-authentication")
        description: Optional description to include in patch README
        before: Optional patch ID to insert before in application order

    \b
    Examples:
        Create patch with numeric ID:
        $ half_orm dev patch create 456

        Create patch with full ID and description:
        $ half_orm dev patch create 456-user-auth -d "Add user authentication"

        Insert patch before another patch (to control application order):
        $ half_orm dev patch create 457-hotfix --before 456-user-auth

    \b
    Raises:
        click.ClickException: If validation fails or creation errors occur
    """
    try:
        # Get repository instance
        repo = Repo()

        # Delegate to PatchManager
        result = repo.patch_manager.create_patch(patch_id, description, before=before)

        # Display success message
        click.echo(f"✓ Created patch branch: {utils.Color.bold(result['branch_name'])}")
        click.echo(f"✓ Created patch directory: {utils.Color.bold(str(result['patch_dir']))}")
        click.echo(f"✓ Added to candidates: {utils.Color.bold(result['version'] + '-candidates.txt')}")
        click.echo(f"✓ Switched to branch: {utils.Color.bold(result['on_branch'])}")
        click.echo()
        click.echo("📝 Next steps:")
        click.echo(f"  1. Add SQL/Python files to {result['patch_dir']}/")
        click.echo(f"  2. Run: {utils.Color.bold('half_orm dev patch apply')}")
        click.echo("  3. Test your changes")
        click.echo(f"  4. Run: {utils.Color.bold('half_orm dev patch merge')} (when ready to integrate)")

    except PatchManagerError as e:
        raise click.ClickException(str(e))


@patch.command('apply')
@click.option(
    '--from-dump',
    type=click.Path(exists=True, dir_okay=False, resolve_path=True),
    help='Restore from pg_dump SQL file instead of schema.sql. '
         'Useful for testing with production data.'
)
def patch_apply(from_dump: Optional[str]) -> None:
    """
    Apply current patch files to database.

    Must be run from ho-patch/PATCH_ID branch. Automatically detects
    patch from current branch name and executes complete workflow:
    database restoration, patch application, and code generation.

    Patch detection is automatic from the current Git branch.
    All business logic is delegated to PatchManager.apply_patch_complete_workflow().

    \b
    Workflow:
        1. Validate current branch is ho-patch/*
        2. Extract patch_id from branch name
        3. Restore database from model/schema.sql (or --from-dump file)
        4. Apply patch SQL/Python files in lexicographic order
        5. Generate halfORM Python code via modules.py
        6. Display detailed report with next steps

    \b
    Branch Requirements:
        - Must be on ho-patch/PATCH_ID branch
        - Branch name format: ho-patch/456 or ho-patch/456-description
        - Corresponding Patches/PATCH_ID/ directory must exist

    \b
    Examples:
        # Standard workflow (restore from schema.sql):
        $ half_orm dev patch apply

        # Using production dump for realistic data:
        $ half_orm dev patch apply --from-dump /path/to/prod_dump.sql

    \b
    Output:
        ✓ Current branch: ho-patch/456-user-auth
        ✓ Detected patch: 456-user-auth
        ✓ Database restored from model/schema.sql
        ✓ Applied 2 patch file(s):
            • 01_create_users.sql
            • 02_add_indexes.sql
        ✓ Generated 3 Python file(s):
            • mydb/mydb/public/user.py
            • mydb/mydb/public/user_session.py
            • tests/mydb/public/test_user.py

    \b
    📝 Next steps:
        1. Review generated code in mydb/mydb/
        2. Implement business logic stubs
        3. Run: half_orm dev test
        4. Commit: git add . && git commit -m 'Implement business logic'

    \b
    Raises:
        click.ClickException: If branch validation fails or application errors occur
    """
    try:
        # Get repository instance
        repo = Repo()

        # Get current branch
        current_branch = repo.hgit.branch

        # Validate branch format
        if not current_branch.startswith('ho-patch/'):
            raise click.ClickException(
                f"Must be on ho-patch/* branch. Current branch: {current_branch}\n"
                f"Use: half_orm dev patch create <patch_id>"
            )

        # Extract patch_id from branch name
        patch_id = current_branch.replace('ho-patch/', '')

        # Display current context
        click.echo(f"✓ Current branch: {utils.Color.bold(current_branch)}")
        click.echo(f"✓ Detected patch: {utils.Color.bold(patch_id)}")
        if from_dump:
            click.echo(f"✓ Using dump file: {utils.Color.bold(from_dump)}")
        click.echo()

        # Delegate to PatchManager
        click.echo("Applying patch...")
        dump_path = Path(from_dump) if from_dump else None
        result = repo.patch_manager.apply_patch_complete_workflow(patch_id, from_dump=dump_path)

        # Display success
        click.echo(f"✓ {utils.Color.green('Patch applied successfully!')}")
        if result.get('used_dump'):
            click.echo(f"✓ Database restored from dump file")
        else:
            click.echo(f"✓ Database restored from model/schema.sql")
        click.echo()

        # Display applied files
        applied_files = result.get('applied_release_files', []) + result.get('applied_current_files', [])
        if applied_files:
            click.echo(f"✓ Applied {len(applied_files)} patch file(s):")
            for filename in applied_files:
                click.echo(f"  • {filename}")
            click.echo()
        else:
            click.echo("ℹ No patch files to apply (empty patch)")
            click.echo()

        # Display generated files
        if result['generated_files']:
            click.echo(f"✓ Generated {len(result['generated_files'])} Python file(s):")
            for filepath in result['generated_files']:
                click.echo(f"  • {filepath}")
            click.echo()
        else:
            click.echo("ℹ No Python files generated (no schema changes)")
            click.echo()

        # Display next steps
        click.echo("📝 Next steps:")
        click.echo("  1. Review generated code")
        click.echo("  2. Implement business logic stubs")
        click.echo(f"  3. Run: {utils.Color.bold('half_orm dev test')}")
        click.echo(f"""  4. Commit: {utils.Color.bold('git add . && git commit -m "Implement business logic"')}""")
        click.echo()

    except PatchManagerError as e:
        raise click.ClickException(str(e))


@patch.command('merge')
@click.option(
    '--force', '-f',
    is_flag=True,
    default=False,
    help='Skip confirmation prompt'
)
def patch_merge(force: bool) -> None:
    """
    Close patch by merging into release branch.

    Automatically detects patch from current branch (must be on ho-patch/PATCH_ID).
    Displays patch information and asks for confirmation before closing.

    Examples:
        Close patch (with confirmation):
        $ half_orm dev patch merge

        Close patch (skip confirmation):
        $ half_orm dev patch merge --force

    Raises:
        click.ClickException: If not on patch branch or validation fails
    """
    try:
        repo = Repo()

        # Get all patch information from PatchManager
        info = repo.patch_manager.get_patch_close_info()

        # Display context
        click.echo(f"Current branch: {utils.Color.bold(info['current_branch'])}")
        click.echo(f"Patch: {utils.Color.bold(info['patch_id'])}")
        click.echo()

        # Display README if exists
        if info['readme']:
            click.echo("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            click.echo(f"{utils.Color.bold('README.md:')}")
            click.echo(info['readme'])
            click.echo("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            click.echo()
        else:
            click.echo("ℹ No README.md found")
            click.echo()

        # Display files
        if info['files']:
            click.echo(f"{utils.Color.bold('Files:')}")
            for file_info in info['files']:
                file_type = ""
                if file_info['is_sql']:
                    file_type = " (SQL)"
                elif file_info['is_python']:
                    file_type = " (Python)"
                click.echo(f"  • {file_info['name']}{file_type}")
            click.echo()
        else:
            click.echo("ℹ No files in patch")
            click.echo()

        # Display synchronization status
        sync = info['sync_status']
        if sync['status'] == 'synced':
            click.echo(f"✓ {sync['message']}")
            click.echo()
        elif sync['status'] == 'behind':
            click.echo(f"⚠ {utils.Color.bold(sync['message'])}")
            if click.confirm("Pull updates from origin?", default=True):
                try:
                    repo.hgit.pull(info['current_branch'])
                    click.echo(f"✓ Pulled updates from origin/{info['current_branch']}")
                    click.echo()
                except Exception as e:
                    raise click.ClickException(f"Failed to pull updates: {e}")
            else:
                click.echo("Continuing without pulling updates...")
                click.echo()
        elif sync['status'] == 'diverged':
            click.echo(f"⚠ {utils.Color.bold(sync['message'])}")
            if not click.confirm("Continue anyway?", default=False):
                raise click.ClickException("Aborted due to diverged branch")
            click.echo()
        elif sync['status'] in ('ahead', 'no_remote', 'fetch_failed', 'check_failed'):
            click.echo(f"ℹ {sync['message']}")
            click.echo()

        # Show what will happen
        click.echo(f"{utils.Color.bold('⚠ This will:')}")
        for i, action in enumerate(info['actions'], 1):
            click.echo(f"  {i}. {action}")
        click.echo()

        # Ask for confirmation (unless --force)
        if not force:
            if not click.confirm(f"Close patch {info['patch_id']}?", default=False):
                click.echo("Cancelled.")
                return

        # Execute merge
        click.echo()
        click.echo("Merging patch...")
        result = repo.patch_manager.merge_patch()

        # Display success message
        click.echo(f"✓ {utils.Color.green('Patch closed successfully!')}")
        click.echo()
        click.echo(f"  Version:         {utils.Color.bold(result['version'])}")
        click.echo(f"  Patches file:    {utils.Color.bold(result['patches_file'])}")
        click.echo(f"  Merged into:     {utils.Color.bold(result['merged_into'])}")

        if result.get('notified_branches'):
            click.echo(f"  Notified:        {len(result['notified_branches'])} active branch(es)")

        click.echo()
        click.echo("📝 Next steps:")
        click.echo(f"""  • Other developers: {utils.Color.bold(f'git pull && git merge origin/{result["merged_into"]}')}""")
        click.echo(f"  • Continue development: {utils.Color.bold('half_orm dev patch create <next_patch_id>')}")
        click.echo(f"  • Promote to RC: {utils.Color.bold('half_orm dev release promote rc')}")
        click.echo()

    except PatchManagerError as e:
        raise click.ClickException(str(e))


@patch.command('detach')
@click.argument('patch_id', type=str, required=False)
@click.option('--force', '-f', is_flag=True, help='Skip confirmation prompt')
def patch_detach(patch_id: Optional[str], force: bool) -> None:
    """
    Detach a candidate patch from its release.

    Moves the patch to Patches/orphaned/ directory.
    The git branch is preserved for future reattachment.

    If PATCH_ID is not provided, uses the current branch's patch.

    Examples:
        Detach current patch (from ho-patch/* branch):
        $ half_orm dev patch detach

        Detach specific patch:
        $ half_orm dev patch detach 123-feature

        Detach without confirmation:
        $ half_orm dev patch detach --force
    """
    try:
        repo = Repo()

        # Auto-detect patch_id from current branch if not provided
        if not patch_id:
            branch = repo.hgit.branch
            if not branch.startswith('ho-patch/'):
                raise click.UsageError(
                    "Not on a patch branch. Provide PATCH_ID or checkout ho-patch/* branch."
                )
            patch_id = branch.replace('ho-patch/', '')

        # Get patch info for confirmation
        status_map = repo.patch_manager.get_patch_status_map()
        if patch_id not in status_map:
            click.echo(utils.Color.red(f"Patch '{patch_id}' not found"))
            raise click.Abort()

        patch_info = status_map[patch_id]
        version = patch_info.get('version', 'unknown')
        status = patch_info.get('status', 'unknown')

        # Check if patch can be detached
        if status == 'staged':
            click.echo(utils.Color.red(
                f"Cannot detach staged patch '{patch_id}'. "
                "Only candidate patches can be detached."
            ))
            raise click.Abort()

        if status == 'orphaned':
            click.echo(utils.Color.red(f"Patch '{patch_id}' is already orphaned."))
            raise click.Abort()

        # Confirmation
        if not force:
            click.echo(f"Detaching patch '{utils.Color.bold(patch_id)}' from release {utils.Color.bold(version)}")
            click.echo()
            click.echo("This will:")
            click.echo(f"  • Remove patch from {version}-patches.toml")
            click.echo(f"  • Move directory to Patches/orphaned/{patch_id}/")
            click.echo(f"  • Keep git branch ho-patch/{patch_id}")
            click.echo()
            if not click.confirm("Continue?", default=True):
                click.echo("Cancelled.")
                return

        # Execute detach
        result = repo.patch_manager.detach_patch(patch_id)

        click.echo()
        click.echo(utils.Color.green(f"✓ Patch '{patch_id}' detached from release {version}"))
        click.echo(f"  Directory moved to: {result['orphaned_path']}")
        click.echo(f"  Branch preserved: ho-patch/{patch_id}")
        click.echo()
        click.echo("To reattach later: half_orm dev release attach-patch <patch_id>")

    except PatchManagerError as e:
        click.echo(utils.Color.red(f"Error: {e}"), err=True)
        raise click.Abort()
