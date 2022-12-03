#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Generates/Patches/Synchronizes a hop Python package with a PostgreSQL database
using the `hop` command.

Initiate a new project and repository with the `hop new <project_name>` command.
The <project_name> directory should not exist when using this command.

In the <project name> directory generated, the hop command helps you patch your
model, keep your Python synced with the PostgreSQL model, test your Python code and
deal with CI.

TODO:
On the 'devel' or any private branch hop applies patches if any, runs tests.
On the 'main' or 'master' branch, hop checks that your git repo is in sync with
the remote origin, synchronizes with devel branch if needed and tags your git
history with the last release applied.
"""

import sys

import click

from half_orm_packager.repo import Repo

class Hop:
    "Sets the options available to the hop command"
    __available_cmds = []
    __command = None
    def __init__(self):
        self.__repo: Repo = Repo()
        if not self.is_repo:
            Hop.__available_cmds = ['new']
        else:
            if not self.__repo.production:
                Hop.__available_cmds = ['patch']
            else:
                Hop.__available_cmds = ['upgrade']

    @property
    def is_repo(self):
        "Returns wether we are in a repo or not."
        return bool(self.__repo.name)

    @property
    def model(self):
        "Returns the model (half_orm.model.Model) associated to the repo."
        return self.__repo.model

    @property
    def status(self):
        "Returns the status of the repo."
        return self.__repo.status

    @property
    def command(self):
        "The command invoked (click)"
        return self.__command

    def add_commands(self, click_main):
        "Adds the commands to the main click group."
        @click.command()
        @click.argument('package_name')
        def new(package_name):
            """ Creates a new hop project named <package_name>.
            """
            self.__repo.new(package_name)


        @click.command()
        @click.option('-f', '--force', is_flag=True, help="Don't check if git repo is clean.")
        @click.option('-r', '--revert', is_flag=True, help="Revert to the previous release.")
        @click.option(
            '-p', '--prepare',
            type=click.Choice(['patch', 'minor', 'major']), help="Prepare next patch.")
        def patch(force, revert, prepare):
            """ Applies the next patch.
            """
            self.__command = 'patch'
            self.__repo.patch(force, revert, prepare)
            sys.exit()

        @click.command()
        # @click.option('-d', '--dry-run', is_flag=True, help='Do nothing')
        # @click.option('-l', '--loop', is_flag=True, help='Run every patches to apply')
        def upgrade():
            """Apply one or many patches.

            switches to hop_main, pulls should check the tags
            """
            self.__command = 'upgrade'
            self.__repo.patch(branch_from='hop_main')

        @click.command()
        def test():
            pass

        cmds = {
            'new': new,
            'patch': patch,
            'upgrade': upgrade,
            'test': test
        }

        for cmd in self.__available_cmds:
            click_main.add_command(cmds[cmd])


hop = Hop()

@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx):
    """
    Generates/Synchronises/Patches a python package from a PostgreSQL database
    """
    if hop.is_repo and ctx.invoked_subcommand is None:
        click.echo(hop.status)
    elif not hop.is_repo and ctx.invoked_subcommand != 'new':
        sys.stderr.write(
            "You're not in a hop repository.\n"
            "Try `hop new <package name>` or change directory.\n")
        sys.exit()

hop.add_commands(main)

if __name__ == '__main__':
    main({})
