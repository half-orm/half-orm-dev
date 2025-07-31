#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CLI extension integration for half-orm-dev

Provides the halfORM development tools through the unified half_orm CLI interface.
Ultra-simplified Git-centric patch management for database schema evolution.

Current commands: new, status, create-patch
Other commands will be implemented in separate CLI modules.
"""

import sys
import click
from half_orm.cli_utils import create_and_register_extension

# Import existing halfORM_dev functionality
from half_orm_dev.repo import Repo
from half_orm import utils

# Import half-orm-dev CLI modules
from half_orm_dev.cli.status import add_status_commands
from half_orm_dev.cli.new import add_new_commands
from half_orm_dev.cli.create_patch import add_create_patch_commands


class HalfOrmDev:
    """
    Sets the options available to the half_orm dev command.
    
    Provides adaptive CLI behavior based on repository context and branch state
    following the ultra-simplified Git-centric workflow architecture.
    """
    
    def __init__(self):
        """Initialize with current repository context."""
        self._repo: Repo = Repo()
        self.__available_cmds = self._determine_available_commands()
        self.__command = None
    
    def _determine_available_commands(self) -> list:
        """
        Determine available commands based on repository state and branch context.
        
        Simplified logic for initial implementation:
        - No repo: ['new', 'status']  
        - Valid repo: ['status', 'create-patch']
        
        Returns:
            list: Available command names for current context
        """
        # Status is always available (adaptive behavior)
        base_commands = ['status']
        
        if not self.repo_checked:
            return ['new'] + base_commands
        
        # Valid repo - add create-patch if in development mode
        if self._repo.devel:
            return ['create-patch'] + base_commands
        else:
            # Sync-only mode - just status for now
            return base_commands
    
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

    @property
    def command(self):
        """The command invoked (click)"""
        return self.__command


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
    
    # Add status commands (always available)
    add_new_commands(dev, dev_instance)
    add_status_commands(dev, dev_instance)
    
    # Add create-patch commands (when available)
    if 'create-patch' in dev_instance._HalfOrmDev__available_cmds:
        add_create_patch_commands(dev, dev_instance)
    
    # ==================== DEFAULT BEHAVIOR (NO SUBCOMMAND) ====================
    
    original_callback = dev.callback
    
    @click.pass_context
    def enhanced_callback(ctx, *args, **kwargs):
        """Enhanced callback with repository state display."""
        if ctx.invoked_subcommand is None:
            # Show repo state when no subcommand is provided
            if dev_instance.repo_checked:
                click.echo(dev_instance.state)
                
                # Show available commands based on context
                click.echo(f"\n📋 Available commands:")
                for cmd_name in sorted(dev_instance._HalfOrmDev__available_cmds):
                    if cmd_name in all_commands:
                        cmd_obj = all_commands[cmd_name]
                        help_text = getattr(cmd_obj, 'help', '') or getattr(cmd_obj, '__doc__', '').split('\n')[0]
                        click.echo(f"   {utils.Color.bold(cmd_name)}: {help_text}")
                    elif cmd_name == 'status':
                        click.echo(f"   {utils.Color.bold('status')}: Show repository and development status")
                    elif cmd_name == 'create-patch':
                        click.echo(f"   {utils.Color.bold('create-patch')}: Create new patch branch and directory")
                
                # Show context info
                if dev_instance._HalfOrmDev__repo.devel:
                    click.echo(f"\n🔧 Development mode enabled - full half-orm-dev workflow available")
                else:
                    click.echo(f"\n📋 Limited mode - use 'half_orm dev new <name> --full' for development features")
                
            else:
                click.echo(dev_instance.state)
                click.echo("\n❌ Not in a half-orm-dev repository.")
                click.echo(f"Try {utils.Color.bold('half_orm dev new <package_name> --full')} to get started.\n")
        else:
            # Call original callback if there is one
            if original_callback:
                return original_callback(*args, **kwargs)
    
    dev.callback = enhanced_callback