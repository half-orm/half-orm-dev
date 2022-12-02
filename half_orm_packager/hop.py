#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# pylint: disable=invalid-name, protected-access

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

import os
import subprocess
import sys

import click
import psycopg2

from half_orm.model import Model, CONF_DIR
from half_orm.model_errors import MissingConfigFile
from half_orm_packager.globals import HOP_PATH
from half_orm_packager.repo import Repo

class Hop:
    __available_cmds = []
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
        return bool(self.__repo.name)

    @property
    def model(self):
        return self.__repo.model

    @property
    def status(self):
        return(self.__repo.status)

    def add_commands(self, main):
        @click.command()
        @click.argument('package_name')
        def new(package_name):
            """ Creates a new hop project named <package_name>.
            """
            self.command = 'new'
            self.__repo.init(package_name)


        @click.command()
        @click.option('-f', '--force', is_flag=True, help="Don't check if git repo is clean.")
        @click.option('-r', '--revert', is_flag=True, help="Revert to the previous release.")
        @click.option('-p', '--prepare', type=click.Choice(['patch', 'minor', 'major']), help="Prepare next patch.")
        # @click.argument('branch_from', required=False)
        #TODO @click.option('-c', '--commit', is_flag=True, help="Commit the patch to the hop_main branch")
        def patch(force, revert, prepare, branch_from=None):
            """ Applies the next patch.
            """
            print('XXX WIP')
            self.command = 'patch'
            self.__repo.patch()
            sys.exit(1)
            # print('branch from', branch_from)
            if prepare:
                Patch(self).prep_next_release(prepare)
            elif revert:
                Patch(self).revert()
            else:
                Patch(self).patch(force, revert)

            sys.exit()


        @click.command()
        # @click.option('-d', '--dry-run', is_flag=True, help='Do nothing')
        # @click.option('-l', '--loop', is_flag=True, help='Run every patches to apply')
        def upgrade():
            """Apply one or many patches.

            switches to hop_main, pulls should check the tags
            """
            self.command = 'upgrade'
            Patch(self).patch()

        @click.command()
        def test():
            """ Tests some common pitfalls.
            """
            if tests(self.model, self.package_name):
                click.echo('Tests OK')
            else:
                click.echo('Tests failed')

        CMDS = {
            'new': new,
            'patch': patch,
            'upgrade': upgrade,
        }

        for cmd in self.__available_cmds:
            main.add_command(CMDS[cmd])


hop = Hop()

@click.group(invoke_without_command=True)
@click.pass_context
@click.option('-v', '--verbose', is_flag=True)
def main(ctx, verbose):
    """
    Generates/Synchronises/Patches a python package from a PostgreSQL database
    """
    if hop.is_repo and ctx.invoked_subcommand is None:
        click.echo(hop.status)
    elif not hop.model and ctx.invoked_subcommand != 'new':
        sys.stderr.write(
            "You're not in a hop repository.\n"
            "Try `hop new <package name>` or change directory.\n")
        sys.exit()

hop.add_commands(main)

if __name__ == '__main__':
    main({}, None)
