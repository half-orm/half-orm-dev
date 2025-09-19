"""
Sync command - Synchronize the Python package with the database model
"""

import click
from half_orm_dev.repo import Repo


@click.command()
def sync_package():
    """Synchronize the Python package with the database model."""
    repo = Repo()
    repo.sync_package()
