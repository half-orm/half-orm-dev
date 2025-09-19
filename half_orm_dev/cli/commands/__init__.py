"""
Commands module for half-orm-dev CLI

Provides all individual command implementations.
"""

from .new import new
from .prepare import prepare
from .apply import apply
from .undo import undo
from .release import release
from .sync import sync_package
from .upgrade import upgrade
from .restore import restore

# Registry of all available commands
ALL_COMMANDS = {
    'new': new,
    'prepare': prepare,
    'apply': apply,
    'undo': undo,
    'release': release,
    'sync-package': sync_package,
    'upgrade': upgrade,
    'restore': restore,
}

__all__ = [
    'new',
    'prepare', 
    'apply',
    'undo',
    'release',
    'sync_package',
    'upgrade',
    'restore',
    'ALL_COMMANDS'
]
