"""
Patch command group - Unified patch development and management.

Groups all patch-related commands under 'half_orm dev patch':
- patch new: Create new patch branch and directory
- patch apply: Apply current patch files to database
- patch add: Add patch to stage release with validation

Replaces legacy commands:
- create-patch → patch new
- apply-patch → patch apply
- add-to-release → patch add
"""

import click
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
        1. half_orm dev patch new <patch_id>
        2. half_orm dev patch apply
        3. half_orm dev patch add <patch_id>
    """
    pass


@patch.command('new')
@click.argument('patch_id', type=str)
@click.option(
    '--description', '-d',
    type=str,
    default=None,
    help='Optional description for the patch'
)
def patch_new(patch_id: str, description: Optional[str] = None) -> None:
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

    \b
    Examples:
        Create patch with numeric ID:
        $ half_orm dev patch new 456

        Create patch with full ID and description:
        $ half_orm dev patch new 456-user-auth -d "Add user authentication"

    \b
    Raises:
        click.ClickException: If validation fails or creation errors occur
    """
    try:
        # Get repository instance
        repo = Repo()

        # Delegate to PatchManager
        result = repo.patch_manager.create_patch(patch_id, description)

        # Display success message
        click.echo(f"✓ Created patch branch: {utils.Color.bold(result['branch_name'])}")
        click.echo(f"✓ Created patch directory: {utils.Color.bold(str(result['patch_dir']))}")
        click.echo(f"✓ Switched to branch: {utils.Color.bold(result['on_branch'])}")
        click.echo()
        click.echo("📝 Next steps:")
        click.echo(f"  1. Add SQL/Python files to {result['patch_dir']}/")
        click.echo(f"  2. Run: {utils.Color.bold('half_orm dev patch apply')}")
        click.echo("  3. Test your changes")
        click.echo(f"  4. Run: {utils.Color.bold('half_orm dev patch add')} {patch_id}")

    except PatchManagerError as e:
        raise click.ClickException(str(e))


@patch.command('apply')
def patch_apply() -> None:
    """
    Apply current patch files to database.

    Must be run from ho-patch/PATCH_ID branch. Automatically detects
    patch from current branch name and executes complete workflow:
    database restoration, patch application, and code generation.

    This command has no parameters - patch detection is automatic from
    the current Git branch. All business logic is delegated to
    PatchManager.apply_patch_complete_workflow().

    \b
    Workflow:
        1. Validate current branch is ho-patch/*
        2. Extract patch_id from branch name
        3. Restore database from model/schema.sql
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
        On branch ho-patch/456-user-auth:
        $ half_orm dev patch apply

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
                f"Use: half_orm dev patch new <patch_id>"
            )

        # Extract patch_id from branch name
        patch_id = current_branch.replace('ho-patch/', '')

        # Display current context
        click.echo(f"✓ Current branch: {utils.Color.bold(current_branch)}")
        click.echo(f"✓ Detected patch: {utils.Color.bold(patch_id)}")
        click.echo()

        # Delegate to PatchManager
        click.echo("Applying patch...")
        result = repo.patch_manager.apply_patch_complete_workflow(patch_id)

        # Display success
        click.echo(f"✓ {utils.Color.green('Patch applied successfully!')}")
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


@patch.command('add')
@click.argument('patch_id', type=str)
@click.option(
    '--to-version', '-v',
    type=str,
    default=None,
    help='Target release version (required if multiple stage releases exist)'
)
def patch_add(patch_id: str, to_version: Optional[str] = None) -> None:
    """
    Add patch to stage release file with validation.

    Integrates developed patch into a stage release for deployment.
    Must be run from ho-prod branch. All business logic is delegated
    to ReleaseManager with distributed lock for safe concurrent operations.

    \b
    Complete workflow:
        1. Acquire exclusive lock on ho-prod (via Git tag)
        2. Create temporary validation branch
        3. Apply all release patches + current patch
        4. Run pytest validation tests
        5. If tests pass: integrate to ho-prod
        6. If tests fail: cleanup and exit with error
        7. Send resync notifications to other patch branches
        8. Archive patch branch to ho-release/{version}/ namespace
        9. Cleanup patch branch
        10. Release lock

    \b
    Args:
        patch_id: Patch identifier to add (e.g., "456-user-auth")
        to_version: Target release version (auto-detected if single stage exists)

    \b
    Branch Requirements:
        - Must be on ho-prod branch
        - Repository must be clean (no uncommitted changes)
        - Must be synced with origin/ho-prod
        - Patch branch ho-patch/PATCH_ID must exist
        - At least one stage release file must exist

    \b
    Examples:
        Add patch to auto-detected stage release:
        $ half_orm dev patch add 456-user-auth

        Add patch to specific version:
        $ half_orm dev patch add 456-user-auth --to-version 1.3.6

    \b
    Output:
        ✓ Detected stage release: 1.3.6-stage.txt
        ✓ Validated patch 456-user-auth
        ✓ All tests passed
        ✓ Integrated to ho-prod
        ✓ Archived branch: ho-release/1.3.6/456-user-auth
        ✓ Notified 2 active patch branches

        📝 Next steps:
          1. Other developers: git pull && git rebase ho-prod
          2. Continue development: half_orm dev patch new <next_patch_id>
          3. Promote to RC: half_orm dev release promote rc

    \b
    Raises:
        click.ClickException: If validation fails or integration errors occur
    """
    try:
        # Get repository instance
        repo = Repo()

        # Display context
        click.echo(f"Adding patch {utils.Color.bold(patch_id)} to stage release...")
        click.echo()

        # Delegate to ReleaseManager
        result = repo.release_manager.add_patch_to_release(patch_id, to_version)

        # Display success message
        click.echo(f"✓ {utils.Color.green('Patch added to release successfully!')}")
        click.echo()
        click.echo(f"  Stage file:      {utils.Color.bold(result['stage_file'])}")
        click.echo(f"  Patch added:     {utils.Color.bold(result['patch_id'])}")
        click.echo(f"  Tests passed:    {utils.Color.green('✓')}")
        click.echo(f"  Archived branch: {utils.Color.bold(result['archived_branch'])}")

        if result.get('notified_branches'):
            click.echo(f"  Notified:        {len(result['notified_branches'])} active branch(es)")

        click.echo()
        click.echo("📝 Next steps:")
        click.echo(f"  • Other developers: {utils.Color.bold('git pull && git rebase ho-prod')}")
        click.echo(f"  • Continue development: {utils.Color.bold('half_orm dev patch new <next_patch_id>')}")
        click.echo(f"  • Promote to RC: {utils.Color.bold('half_orm dev release promote rc')}")
        click.echo()

    except ReleaseManagerError as e:
        raise click.ClickException(str(e))
