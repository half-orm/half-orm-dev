#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CLI extension integration for half-orm-dev

Provides the halfORM development tools through the unified half_orm CLI interface.
Generates/Patches/Synchronizes a hop Python package with a PostgreSQL database.
"""

import sys
import click
from half_orm.cli_utils import create_and_register_extension

# Import existing halfORM_dev functionality
from half_orm_dev.repo import Repo
from half_orm import utils

class Hop:
    """Sets the options available to the hop command"""
    __available_cmds = []
    __command = None
    
    def __init__(self):
        self.__repo: Repo = Repo()
        if not self.repo_checked:
            Hop.__available_cmds = ['new']
        else:
            if not self.__repo.devel:
                # Sync-only mode
                Hop.__available_cmds = ['sync-package']
            else:
                # Full mode - check environment
                if self.__repo.production:
                    Hop.__available_cmds = ['upgrade', 'restore']
                else:
                    Hop.__available_cmds = ['prepare', 'apply', 'release', 'undo']
    
    @property
    def repo_checked(self):
        """Returns whether we are in a repo or not."""
        return self.__repo.checked

    @property
    def model(self):
        """Returns the model (half_orm.model.Model) associated to the repo."""
        return self.__repo.model

    @property
    def state(self):
        """Returns the state of the repo."""
        return self.__repo.state

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
    
    # Create hop instance to determine available commands
    hop = Hop()
    
    @create_and_register_extension(main_group, sys.modules[__name__])
    def dev():
        """halfORM development tools - project management, patches, and database synchronization"""
        pass
    
    # Define all possible commands
    @click.command()
    @click.argument('package_name')
    @click.option('-d', '--devel', is_flag=True, help="Development mode")
    def new(package_name, devel=False):
        """Creates a new hop project named <package_name>."""
        hop._Hop__repo.init(package_name, devel)

    @click.command()
    @click.option(
        '-l', '--level',
        type=click.Choice(['patch', 'minor', 'major']), help="Release level.")
    @click.option('-m', '--message', type=str, help="The git commit message")
    def prepare(level, message=None):
        """Prepares the next release."""
        hop._Hop__command = 'prepare'
        hop._Hop__repo.prepare_release(level, message)
        sys.exit()

    @click.command()
    def apply():
        """Apply the current release."""
        hop._Hop__command = 'apply'
        hop._Hop__repo.apply_release()

    @click.command()
    @click.option(
        '-d', '--database-only', is_flag=True,
        help='Restore the database to the previous release.')
    def undo(database_only):
        """Undo the last release."""
        hop._Hop__command = 'undo'
        hop._Hop__repo.undo_release(database_only)

    @click.command()
    def upgrade():
        """Apply one or many patches.
        
        Switches to hop_main, pulls should check the tags.
        """
        hop._Hop__command = 'upgrade_prod'
        hop._Hop__repo.upgrade_prod()

    @click.command()
    @click.argument('release')
    def restore(release):
        """Restore to release."""
        hop._Hop__repo.restore(release)

    @click.command()
    @click.option('-p', '--push', is_flag=True, help='Push git repo to origin')
    def release(push=False):
        """Commit and optionally push the current release."""
        hop._Hop__repo.commit_release(push)

    @click.command()
    def sync_package():
        """Synchronize the Python package with the database model."""
        hop._Hop__repo.sync_package()

    # Map command names to command functions
    all_commands = {
        'new': new,
        'prepare': prepare,
        'apply': apply,
        'undo': undo,
        'release': release,
        'sync-package': sync_package,
        'upgrade': upgrade,
        'restore': restore
    }
    
    # 🎯 COMPORTEMENT ADAPTATIF RESTAURÉ
    # Only add commands that are available in the current context
    for cmd_name in hop._Hop__available_cmds:
        if cmd_name in all_commands:
            dev.add_command(all_commands[cmd_name])
    
    # Add callback to show state when no subcommand (like original hop)
    original_callback = dev.callback
    
    @click.pass_context
    def enhanced_callback(ctx, *args, **kwargs):
        if ctx.invoked_subcommand is None:
            # Show repo state when no subcommand is provided
            if hop.repo_checked:
                click.echo(hop.state)
            else:
                click.echo(hop.state)
                click.echo("\nNot in a hop repository.")
                click.echo(f"Try {utils.Color.bold('half_orm dev new [--devel] <package_name>')} or change directory.\n")
        else:
            # Call original callback if there is one
            if original_callback:
                return original_callback(*args, **kwargs)
    
    dev.callback = enhanced_callback