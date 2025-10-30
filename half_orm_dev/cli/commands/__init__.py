"""
Commands module for half-orm-dev CLI

Provides all individual command implementations.
REFACTORED in v0.16.0 - Git-centric patch workflow
"""

# ✅ New Git-centric commands (stubs for now)
from .init_database import init_database
from .init_project import init_project
from .create_patch import create_patch
from .apply_patch import apply_patch
from .prepare_release import prepare_release
from .add_to_release import add_to_release
from .promote_to import promote_to
from .update import update
from .todo import apply_release
from .todo import deploy_to_prod
from .todo import create_hotfix
from .todo import rollback

# ♻️ Adapted existing commands
from .todo import sync_package    # Unchanged
from .todo import upgrade      # Adapted for production workflow
from .todo import restore      # Adapted for new architecture

# Registry of all available commands - Git-centric architecture
ALL_COMMANDS = {
    # Core workflow
    'init-database': init_database,
    'init-project': init_project,
    'create-patch': create_patch,
    'apply-patch': apply_patch,
    'prepare-release': prepare_release,
    'add-to-release': add_to_release,
    'promote-to': promote_to,
    'update': update,          # Adapted for production
    # 🚧 (stubs)
    'apply_release': apply_release,

    # 🚧 Release management (stubs)
    'deploy-to-prod': deploy_to_prod,

    # 🚧 Emergency workflow (stubs)
    'create-hotfix': create_hotfix,
    'rollback': rollback,

    # ♻️ Adapted commands
    'sync-package': sync_package, # Unchanged
    'upgrade': upgrade,          # Adapted for production
    'restore': restore,          # Adapted
}

__all__ = [
    # New commands
    'init_database',
    'init_project',
    'create_patch',
    'apply_patch',
    'prepare_release',
    'add_to_release',
    'apply_release',
    'promote_to',
    'promote_to_prod',
    'deploy_to_prod',
    'create_hotfix',
    'rollback',
    # Adapted commands
    'sync_package',
    'upgrade',
    'restore',
    'ALL_COMMANDS'
]