"""
Recover command - Complete or clean up an interrupted sync operation.
"""

import sys
import click
from half_orm_dev.repo import Repo
from half_orm import utils


@click.command()
def recover() -> None:
    """Complete or clean up a sync interrupted by a crash or network failure.

    Reads .git/hop-sync-lock to verify ownership of the interrupted operation,
    then either pushes branches whose sync commit completed (Phase 2 finish)
    or restores clean state for branches interrupted mid-commit (Phase 1 cleanup).
    Releases the distributed lock when done.
    """
    repo = Repo()
    result = repo.recover()

    if result['errors'] and not result['pushed_branches'] and not result['cleaned_branches']:
        for error in result['errors']:
            click.echo(utils.Color.red(f"Error: {error}"), err=True)
        sys.exit(1)

    if result['lock_tag']:
        click.echo(f"Recovering from interrupted sync (lock: {result['lock_tag']})")

    if result['pushed_branches']:
        for branch in result['pushed_branches']:
            click.echo(f"  Pushed:   {branch}")

    if result['cleaned_branches']:
        for branch in result['cleaned_branches']:
            click.echo(f"  Cleaned:  {branch}")

    if not result['pushed_branches'] and not result['cleaned_branches']:
        click.echo("Nothing to recover — lock released.")

    if result['errors']:
        for error in result['errors']:
            click.echo(utils.Color.yellow(f"Warning: {error}"), err=True)

    click.echo(utils.Color.green("Recovery complete."))