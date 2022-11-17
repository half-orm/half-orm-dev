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

from half_orm_packager.utils import get_connection_file_name, set_config_file, Hop, read_template, write_file
from half_orm_packager.patch import Patch
from half_orm_packager.test import tests
from half_orm_packager.update import update_modules
from half_orm_packager.hgit import HGit

PWD = os.path.abspath(os.path.curdir)

@click.group(invoke_without_command=True)
@click.pass_context
@click.option('-v', '--verbose', is_flag=True)
def main(ctx, verbose):
    """
    Generates/Synchronises/Patches a python package from a PostgreSQL database
    """
    if HOP.model and ctx.invoked_subcommand is None:
        click.echo('halfORM packager')
        HOP.status(verbose)
    elif not HOP.model and ctx.invoked_subcommand != 'new':
        sys.stderr.write(
            "You're not in a hop package directory.\n"
            "Try hop new <package directory> or change directory.\n")
        sys.exit()

    sys.path.insert(0, '.')

@click.command()
@click.argument('package_name')
def new(package_name):
    """ Creates a new hop project named <package_name>.

    It adds to your database a patch system (by creating the relations:
    * half_orm_meta.hop_release
    * half_orm_meta.hop_release_issue
    and the views
    * "half_orm_meta.view".hop_last_release
    * "half_orm_meta.view".hop_penultimate_release
    """
    # click.echo(f'hop new {package_name}')
    # on cherche un fichier de conf .hop/config dans l'arbre.
    conf_file, _, _ = get_connection_file_name('.', PWD)
    if conf_file is not None:
        sys.stderr.write("ERROR! Can't run hop new in a hop project.\n")
        sys.exit(1)
    model = set_config_file(HOP, package_name)

    HOP.init_package(package_name)
    HOP.what_next()
    print(f"\nPlease go to {PWD}/{package_name}")


@click.command()
@click.option('-f', '--force', is_flag=True, help="Don't check if git repo is clean.")
@click.option('-r', '--revert', is_flag=True, help="Revert to the previous release.")
@click.option('-p', '--prepare', type=click.Choice(['patch', 'minor', 'major']), help="Prepare next patch.")
# @click.argument('branch_from', required=False)
#TODO @click.option('-c', '--commit', is_flag=True, help="Commit the patch to the hop_main branch")
def patch(force, revert, prepare, branch_from=None):
    """ Applies the next patch.
    """
    # print('branch from', branch_from)
    if prepare:
        Patch(HOP).prep_next_release(prepare)
    elif revert:
        Patch(HOP).revert()
    else:
        Patch(HOP).patch(force, revert)

    sys.exit()


@click.command()
# @click.option('-d', '--dry-run', is_flag=True, help='Do nothing')
# @click.option('-l', '--loop', is_flag=True, help='Run every patches to apply')
def upgrade():
    """Apply one or many patches.

    switches to hop_main, pulls should check the tags
    """
    Patch(HOP).patch()

@click.command()
def test():
    """ Tests some common pitfalls.
    """
    if tests(HOP.model, HOP.package_name):
        click.echo('Tests OK')
    else:
        click.echo('Tests failed')

HOP = Hop(PWD)
if not HOP.model:
    main.add_command(new)
elif not HOP.production:
    # commands only available in dev
    main.add_command(patch)
    main.add_command(test)
    # main.add_command(update)
else:
    # in prod
    main.add_command(upgrade)

if __name__ == '__main__':
    main({}, None)
