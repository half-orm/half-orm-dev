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
from .update import update
from .upgrade import upgrade
from .check import check
from .todo import apply_release
from .todo import rollback

# ♻️ Adapted existing commands
from .todo import sync_package    # Unchanged
from .todo import restore      # Adapted for new architecture

# Registry of all available commands - Git-centric architecture
ALL_COMMANDS = {
    # Core workflow
    'init': init,
    'clone': clone,
    'patch': patch,
    'release': release,
    'update': update,          # Adapted for production
    'upgrade': upgrade,          # Adapted for production
    'check': check,            # Project health check and updates
    # 🚧 (stubs)
    'apply_release': apply_release,

    # 🚧 Emergency workflow (stubs)
    'rollback': rollback,

    # ♻️ Adapted commands
    'sync-package': sync_package, # Unchanged
    'restore': restore,          # Adapted
}

__all__ = [
    # New commands
    'init',
    'clone',
    'patch',
    'release',
    'upgrade',
    'check',
    'rollback',
    # Adapted commands
    'sync_package',
    'ALL_COMMANDS'
]