"""
Release command - Commit and optionally push the current release
"""

import click
from half_orm_dev.repo import Repo


@click.command()
@click.option('-p', '--push', is_flag=True, help='Push git repo to origin')
def release(push=False):
    """Commit and optionally push the current release."""
    repo = Repo()
    repo.commit_release(push)
