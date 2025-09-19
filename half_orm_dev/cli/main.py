"""
Main CLI module - Creates and configures the CLI group
"""

import click
from half_orm_dev.repo import Repo
from half_orm import utils
from .commands import ALL_COMMANDS


class Hop:
    """Sets the options available to the hop command"""
    
    def __init__(self):
        self.__repo: Repo = Repo()  # Utilise le singleton
        self.__available_cmds = self._determine_available_commands()
    
    def _determine_available_commands(self):
        """Determine which commands are available based on context"""
        if not self.repo_checked:
            return ['new']
        else:
            if not self.__repo.devel:
                # Sync-only mode
                return ['sync-package']
            else:
                # Full mode - check environment
                if self.__repo.production:
                    return ['upgrade', 'restore']
                else:
                    return ['prepare', 'apply', 'release', 'undo']
    
    @property
    def repo_checked(self):
        """Returns whether we are in a repo or not."""
        return self.__repo.checked

    @property
    def state(self):
        """Returns the state of the repo."""
        return self.__repo.state
    
    @property
    def available_commands(self):
        """Returns the list of available commands."""
        return self.__available_cmds


def create_cli_group():
    """
    Creates and returns the CLI group with appropriate commands.
    
    Returns:
        click.Group: Configured CLI group
    """
    hop = Hop()
    
    @click.group(invoke_without_command=True)
    @click.pass_context
    def dev(ctx):
        """halfORM development tools - project management, patches, and database synchronization"""
        if ctx.invoked_subcommand is None:
            # Show repo state when no subcommand is provided
            if hop.repo_checked:
                click.echo(hop.state)
            else:
                click.echo(hop.state)
                click.echo("\nNot in a hop repository.")
                click.echo(f"Try {utils.Color.bold('half_orm dev new [--devel] <package_name>')} or change directory.\n")
    
    # Add only available commands to the group
    for cmd_name in hop.available_commands:
        if cmd_name in ALL_COMMANDS:
            dev.add_command(ALL_COMMANDS[cmd_name])
    
    return dev
