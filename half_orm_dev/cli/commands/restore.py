"""
Restore command - Restore the development database to a given release.
"""

from pathlib import Path

import click
from half_orm_dev.repo import Repo, RepoError
from half_orm_dev.release_manager import ReleaseManagerError
from half_orm import utils


@click.command()
@click.argument('release')
def restore(release: str) -> None:
    """
    Restore the database to the state of RELEASE.

    Drops all user schemas and reloads them, picking the most precise
    source available for RELEASE:

    \b
    1. .hop/model/schema-RELEASE.sql + data-RELEASE.sql (published
       snapshot of that exact released version)
    2. otherwise, for a release still in preparation: the production
       baseline replayed with the validated patches of every release in
       preparation up to RELEASE (patch -> minor -> major)

    Fails with an error, rather than silently loading a different
    version, if RELEASE is neither published nor in preparation.

    \b
    Examples:
        # Restore to a release currently in development
        half_orm dev restore 0.17.1

        # Restore to an already-published version
        half_orm dev restore 0.3.5
    """
    try:
        repo = Repo()
        click.echo(f"Restoring database to release {utils.Color.bold(release)}...")

        schema_path = Path(repo.model_dir) / f"schema-{release}.sql"

        if schema_path.exists():
            repo.restore_database_from_version_schema(release)
        else:
            repo.release_manager.restore_to_release(release)

        click.echo(f"✓ {utils.Color.green('Database restored to')} {utils.Color.bold(release)}")
    except (RepoError, ReleaseManagerError) as e:
        click.echo(utils.Color.red(f"\n❌ {e}"), err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(utils.Color.red(f"\n❌ Unexpected error: {e}"), err=True)
        raise click.Abort()
