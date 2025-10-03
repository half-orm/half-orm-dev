"""
Prepare command - Prepares the next release
"""

import sys
import click
from half_orm_dev.repo import Repo


@click.command()
@click.option(
    '-l', '--level',
    type=click.Choice(['patch', 'minor', 'major']),
    help="Release level."
)
@click.option('-m', '--message', type=str, help="The git commit message")
def prepare(level, message=None):
    """Prepares the next release."""
    repo = Repo()
    repo.prepare_release(level, message)
    sys.exit()
