"""
New command - Creates a new hop project
"""

import click
from half_orm_dev.repo import Repo


@click.command()
@click.argument('package_name')
@click.option('-d', '--devel', is_flag=True, help="Development mode")
def new(package_name, devel=False):
    """Creates a new hop project named <package_name>."""
    repo = Repo()
    repo.init(package_name, devel)
