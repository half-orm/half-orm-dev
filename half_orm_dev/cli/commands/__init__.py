"""
Commands module for half-orm-dev CLI

Provides all individual command implementations.
REFACTORED in v0.16.0 - Git-centric patch workflow
"""

# ✅ New Git-centric commands (stubs for now)
from .init_database import init_database
from .init_project import init_project
from .create_patch import create_patch
from .todo import apply_patch
from .todo import add_to_release
from .todo import promote_to_rc
from .todo import promote_to_prod
from .todo import deploy_to_prod
from .todo import create_hotfix
from .todo import rollback

# ♻️ Adapted existing commands
from .todo import apply          # Adapted for new architecture
from .todo import sync_package    # Unchanged
from .todo import upgrade      # Adapted for production workflow
from .todo import restore      # Adapted for new architecture

# Registry of all available commands - Git-centric architecture
ALL_COMMANDS = {
    # 🚧 Core workflow (stubs)
    'init-database': init_database,
    'init-project': init_project,
    'create-patch': create_patch,
    'apply-patch': apply_patch,
    'add-to-release': add_to_release,

    # 🚧 Release management (stubs)
    'promote-to-rc': promote_to_rc,
    'promote-to-prod': promote_to_prod,
    'deploy-to-prod': deploy_to_prod,

    # 🚧 Emergency workflow (stubs)
    'create-hotfix': create_hotfix,
    'rollback': rollback,

    # ♻️ Adapted commands
    'apply': apply,              # Will be adapted
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
    'add_to_release',
    'promote_to_rc',
    'promote_to_prod', 
    'deploy_to_prod',
    'create_hotfix',
    'rollback',
    # Adapted commands
    'apply',
    'sync_package',
    'upgrade', 
    'restore',
    'ALL_COMMANDS'
]