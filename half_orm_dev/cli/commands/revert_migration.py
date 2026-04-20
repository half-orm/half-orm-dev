"""
revert-migration command - Revert the last migration.

Uses the annotated git tag ho-migration/<version> created during migration
to identify the exact commits to revert on each branch.

Not available after a production promotion (the tag is deleted at that point).
"""

import click
from half_orm_dev.repo import Repo, RepoError
from half_orm_dev.migration_manager import MigrationManagerError
from half_orm import utils


@click.command('revert-migration')
def revert_migration() -> None:
    """
    Revert the last migration applied by 'half_orm dev migrate'.

    Uses the annotated tag ho-migration/<version> to locate the exact
    commits and runs 'git revert --no-edit' on each affected branch.

    \b
    Constraints:
      • Must be on ho-prod branch
      • Not possible after a production promotion

    \b
    Multiple migrations:
      Call repeatedly to roll back a chain of migrations (LIFO order).
      Each call reverts the migration with the highest version number.
    """
    try:
        repo = Repo()

        if not repo.checked:
            click.echo(utils.Color.red("❌ Not in a hop repository"), err=True)
            raise click.Abort()

        repo.revert_migration()
        click.echo(f"✓ {utils.Color.green('Migration reverted successfully.')}")

    except (RepoError, MigrationManagerError) as e:
        click.echo(utils.Color.red(f"❌ {e}"), err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(utils.Color.red(f"❌ Unexpected error: {e}"), err=True)
        raise click.Abort()