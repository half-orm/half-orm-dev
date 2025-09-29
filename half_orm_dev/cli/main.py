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
        """
        Determine which commands are available based on context.
        """
        if not self.repo_checked:
            # Outside hop repository
            return ['init-database']
        else:
            # Inside hop repository - nothing for now
            # TODO: Add more commands as we implement them
            # Will eventually have: create-patch, apply-patch, add-to-release, etc.
            return []

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
        """halfORM development tools - Git-centric patch management and database synchronization"""
        if ctx.invoked_subcommand is None:
            # Show repo state when no subcommand is provided
            if hop.repo_checked:
                click.echo(hop.state)
                click.echo("\n⚠️  Other commands to implement Git-centric architecture...")
            else:
                click.echo(hop.state)
                click.echo("\nNot in a hop repository.")
                click.echo(f"Try {utils.Color.bold('half_orm dev init-project <package_name>')} to create a new project.\n")

    # Add only available commands to the group
    for cmd_name in hop.available_commands:
        if cmd_name in ALL_COMMANDS:
            dev.add_command(ALL_COMMANDS[cmd_name])

    return dev