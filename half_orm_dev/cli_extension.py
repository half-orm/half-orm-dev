#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CLI extension integration for half-orm-dev

Provides the halfORM development tools through the unified half_orm CLI interface.
Generates/Patches/Synchronizes a hop Python package with a PostgreSQL database.
"""

import sys
from half_orm.cli_utils import create_and_register_extension
from .cli import create_cli_group


def add_commands(main_group):
    """
    Required entry point for halfORM extensions.

    Args:
        main_group: The main Click group for the half_orm command
    """

    # Create the dev CLI group with all commands
    dev_group = create_cli_group()

    # Register it as an extension
    @create_and_register_extension(main_group, sys.modules[__name__])
    def dev():
        """halfORM development tools - project management, patches, and database synchronization"""
        pass

    # Copy all commands from the created group to the registered extension
    for name, command in dev_group.commands.items():
        dev.add_command(command)

    # Copy the callback from the created group
    dev.callback = dev_group.callback