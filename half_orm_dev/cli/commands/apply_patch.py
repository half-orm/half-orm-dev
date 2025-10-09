"""
Apply-patch command implementation.

Thin CLI layer that delegates to PatchManager for business logic.
Automatically detects patch from current ho-patch/* branch.
"""

import click
from half_orm_dev.repo import Repo
from half_orm_dev.patch_manager import PatchManagerError


@click.command('apply-patch')
def apply_patch() -> None:
    """
    Apply current patch files to database.

    Must be run from ho-patch/PATCH_ID branch. Automatically detects
    patch from current branch name and executes complete workflow:
    database restoration, patch application, and code generation.

    This command has no parameters - patch detection is automatic from
    the current Git branch. All business logic is delegated to
    PatchManager.apply_patch_complete_workflow().

    Workflow:
        1. Validate current branch is ho-patch/*
        2. Extract patch_id from branch name
        3. Restore database from model/schema.sql
        4. Apply patch SQL/Python files in lexicographic order
        5. Generate halfORM Python code via modules.py
        6. Display detailed report with next steps

    Branch Requirements:
        - Must be on ho-patch/PATCH_ID branch
        - Branch name format: ho-patch/456 or ho-patch/456-description
        - Corresponding Patches/PATCH_ID/ directory must exist

    Examples:
        On branch ho-patch/456-user-auth:
        $ half_orm dev apply-patch

        Output:
        ✓ Current branch: ho-patch/456-user-auth
        ✓ Detected patch: 456-user-auth
        ✓ Database restored from model/schema.sql
        ✓ Applied 2 patch files:
          • 01_create_users.sql
          • 02_add_indexes.sql
        ✓ Generated 3 Python files:
          • mydb/mydb/public/user.py
          • mydb/mydb/public/user_session.py
          • tests/mydb/public/test_user.py

        📝 Next steps:
          1. Review generated code in mydb/mydb/
          2. Implement business logic stubs
          3. Run: half_orm dev test
          4. Commit: git add mydb/ tests/ && git commit

    Error Cases:
        Not on ho-patch branch:
        $ half_orm dev apply-patch
        Error: Must be on ho-patch/* branch to apply patch
        Current branch: ho-prod

        Patch directory not found:
        $ half_orm dev apply-patch
        Error: Patch directory not found: Patches/456-user-auth/
        Branch: ho-patch/456-user-auth

        Database restoration fails:
        $ half_orm dev apply-patch
        Error: Database restoration failed: model/schema.sql not found

    Raises:
        click.ClickException: If not on ho-patch/* branch
        click.ClickException: If patch directory not found
        click.ClickException: If workflow execution fails
        click.ClickException: If any validation fails

    Notes:
        - Automatically handles database rollback on failure
        - Safe to run multiple times (idempotent via restore)
        - All patch files must be in Patches/PATCH_ID/ directory
        - Generated code auto-committed with [ho] prefix
        - Requires database connection configured via init-database
    """
    try:
        # Get repository instance
        repo = Repo()

        # Get current branch
        current_branch = repo.hgit.current_branch()

        # Validate branch is ho-patch/*
        if not current_branch.startswith('ho-patch/'):
            raise click.ClickException(
                f"Must be on ho-patch/* branch to apply patch.\n"
                f"Current branch: {current_branch}\n\n"
                f"Create a patch first: half_orm dev create-patch <patch_id>"
            )

        # Extract patch_id from branch name (remove 'ho-patch/' prefix)
        patch_id = current_branch[len('ho-patch/'):]

        # Display detection info
        click.echo(f"✓ Current branch: {current_branch}")
        click.echo(f"✓ Detected patch: {patch_id}")
        click.echo()

        # Execute complete workflow via PatchManager
        result = repo.patch_manager.apply_patch_complete_workflow(patch_id)

        # Display success report
        click.echo("✓ Database restored from model/schema.sql")
        click.echo()
        applied_files = result.get('applied_release_files', []) + result.get('applied_current_files', [])
        # Display applied files
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
        click.echo("  3. Run: half_orm dev test")
        click.echo("  4. Commit: git add . && git commit -m 'Implement business logic'")
        click.echo()

    except PatchManagerError as e:
        raise click.ClickException(str(e))
    except Exception as e:
        raise click.ClickException(f"Unexpected error: {e}")
