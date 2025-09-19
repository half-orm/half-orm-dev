"""
Restore command - Restore to release
"""

import click
from half_orm_dev.repo import Repo


@click.command()
@click.argument('release')
def restore(release):
    """Restore to release."""
    repo = Repo()
    repo.restore(release)
