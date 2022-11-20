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

from half_orm_packager.utils import Hop

HOP = Hop()

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

HOP.add_commands(main)

if __name__ == '__main__':
    main({}, None)
