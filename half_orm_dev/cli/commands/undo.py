"""
Undo command - Undo the last release
"""

import click
from half_orm_dev.repo import Repo


@click.command()
@click.option(
    '-d', '--database-only', is_flag=True,
    help='Restore the database to the previous release.'
)
def undo(database_only):
    """Undo the last release."""
    repo = Repo()
    repo.undo_release(database_only)
