"""
Apply command - Apply the current release
"""

import click
from half_orm_dev.repo import Repo


@click.command()
def apply():
    """Apply the current release."""
    repo = Repo()
    repo.apply_release()
