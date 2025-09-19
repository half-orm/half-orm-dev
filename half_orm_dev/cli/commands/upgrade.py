"""
Upgrade command - Apply one or many patches in production
"""

import click
from half_orm_dev.repo import Repo


@click.command()
def upgrade():
    """Apply one or many patches.
    
    Switches to hop_main, pulls should check the tags.
    """
    repo = Repo()
    repo.upgrade_prod()
