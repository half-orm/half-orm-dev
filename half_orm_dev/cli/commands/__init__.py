"""
Commands module for half-orm-dev CLI

Provides all individual command implementations.
REFACTORED in v0.16.0 - Git-centric patch workflow
"""

# ✅ New Git-centric commands (stubs for now)
from .init import init
from .clone import clone
from .patch import patch
from .release import release
from .upgrade import upgrade
from .check import check
from .set_git_origin import set_git_origin
from .migrate import migrate
from .revert_migration import revert_migration
from .rollback import rollback
from .recover import recover
from .restore import restore
from .todo import apply_release

# ♻️ Adapted existing commands
from .todo import sync_package    # Unchanged

# Registry of all available commands - Git-centric architecture
ALL_COMMANDS = {
    # Core workflow
    'init': init,
    'clone': clone,
    'patch': patch,
    'release': release,
    'upgrade': upgrade,          # Adapted for production
    'check': check,            # Project health check and updates
    'set-git-origin': set_git_origin,  # Update git remote origin URL
    'migrate': migrate,        # Repository migration after upgrade
    'revert-migration': revert_migration,  # Revert last migration
    # 🚧 (stubs)
    'apply_release': apply_release,

    # 🚧 Emergency workflow (stubs)
    'rollback': rollback,
    'recover': recover,
    'restore': restore,

    # ♻️ Adapted commands
    'sync-package': sync_package, # Unchanged
}

__all__ = [
    # New commands
    'init',
    'clone',
    'patch',
    'release',
    'upgrade',
    'check',
    'migrate',
    'rollback',
    'recover',
    'restore',
    # Adapted commands
    'sync_package',
    'ALL_COMMANDS'
]