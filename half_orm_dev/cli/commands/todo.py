"""
TODO command - Placeholder for unimplemented Git-centric commands

Single function with multiple aliases for all commands to implement.
"""

import click


@click.command()
@click.pass_context
def todo(ctx):
    """
    Placeholder for unimplemented Git-centric commands.

    All legacy commands (prepare, undo, release, new) removed in v0.16.0.
    New patch-centric workflow commands not yet implemented.

    Target Git-centric architecture:
    - ho-prod + ho-patch/patch-name branches
    - Patches/patch-name/ directory structure
    - releases/X.Y.Z-stage.txt → rc → production workflow
    - PatchManager integration via repo.patch_manager
    - Single active development rule (one RC at a time)
    - Developer responsibility for conflict management
    """
    command_name = ctx.info_name

    # Map of command → description for helpful error messages
    command_descriptions = {
        # 🚧 New Git-centric commands
        'init-project': 'Initialize new project with ho-prod branch and Patches/ structure',
        'create-patch': 'Create ho-patch/patch-name branch with Patches/patch-name/ directory',
        'apply-patch': 'Apply current patch files using PatchManager.apply_patch_files()',
        'add-to-release': 'Add patch to releases/X.Y.Z-stage.txt and merge to ho-prod',
        'prepare-release': 'Create next releases/X.Y.Z-stage.txt file',
        'promote-to': "Promote stage → target ('rc', 'prod') with automatic branch cleanup",
        'update': 'Apply patches in production (adapt for Git-centric)',
        'upgrade': 'Apply patches in production (adapt for Git-centric)',

        # ♻️ Commands to implement
        'create-hotfix': 'Create emergency hotfix bypassing normal workflow',
        'rollback': 'Rollback database to previous version using backups/',
        'sync-package': 'Synchronize Python package with database model',
        'restore': 'Restore database to specific version (adapt for new backups)',
        'list-patches': 'List all patches in Patches/ directory',
        'status': 'Show development status with patch/release information',
        'apply-release': 'Apply next release',
    }

    description = command_descriptions.get(command_name, 'Git-centric command')

    raise NotImplementedError(
        f"Command '{command_name}' not implemented in v0.16.0\n"
        f"Description: {description}\n\n"
        f"Legacy commands removed - use new patch-centric workflow:\n"
        f"See docs/half_orm_dev.md for architecture details.\n"
        f"Current working: PatchManager (102 tests), HGit, Repo integration."
    )


# Create aliases for ALL commands (new + adapted)
# 🚧 New Git-centric commands
add_to_release = todo
apply_release = todo
create_hotfix = todo
rollback = todo
list_patches = todo
status = todo

# ♻️ Commands to adapt (also in todo for now)
sync_package = todo   # Keep functionality, adapt to new architecture
restore = todo        # Adapt for new backup/restore logic
