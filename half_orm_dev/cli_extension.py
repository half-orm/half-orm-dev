#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CLI extension integration for half-orm-dev

Provides the halfORM development tools through the unified half_orm CLI interface.
Ultra-simplified Git-centric patch management for database schema evolution.
"""

import sys
from half_orm.cli_utils import create_and_register_extension

# Import existing halfORM_dev functionality
from half_orm_dev.repo import Repo

# Import half-orm-dev CLI modules
from half_orm_dev.cli.status import add_status_commands
from half_orm_dev.cli.new import add_new_commands
from half_orm_dev.cli.create_patch import add_create_patch_commands


class HalfOrmDev:
    """
    Simple context holder for half-orm-dev commands.
    
    Provides repository context to CLI commands following the 
    ultra-simplified Git-centric workflow architecture.
    """
    
    def __init__(self):
        """Initialize with current repository context."""
        self._repo: Repo = Repo()
    
    @property
    def repo_checked(self):
        """Returns whether we are in a repo or not."""
        return self._repo.checked

    @property
    def model(self):
        """Returns the model (half_orm.model.Model) associated to the repo."""
        return self._repo.model

    @property
    def state(self):
        """Returns the state of the repo."""
        return self._repo.state


def add_commands(main_group):
    """
    Required entry point for halfORM extensions.
    
    Args:
        main_group: The main Click group for the half_orm command
    """
    
    # Create half-orm-dev instance to determine available commands
    dev_instance = HalfOrmDev()
    
    @create_and_register_extension(main_group, sys.modules[__name__])
    def dev():
        """halfORM development tools - Git-centric patch management and database synchronization"""
        pass
    
    # ==================== ADD MODULAR CLI COMMANDS ====================
    
    # Each module handles its own registration logic
    add_status_commands(dev, dev_instance)  # Always available + default behavior
    add_new_commands(dev, dev_instance)     # Conditional registration in module
    add_create_patch_commands(dev, dev_instance)  # Conditional registration in module