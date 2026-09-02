"""
Restore command - Restore the development database to a given release.
"""

from pathlib import Path

import click
from half_orm_dev.repo import Repo, RepoError
from half_orm import utils


@click.command()
@click.argument('release')
def restore(release: str) -> None:
    """
    Restore the database to the state of RELEASE.

    Drops all user schemas and reloads them, picking the most precise
    snapshot available for RELEASE:

    \b
    1. .hop/model/release-RELEASE.sql   (production + patches staged
       for that release, still in development)
    2. .hop/model/schema-RELEASE.sql    (published snapshot of that
       exact released version)

    Fails with an error, rather than silently loading a different
    version, if neither file exists.

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

        release_schema_path = repo.get_release_schema_path(release)
        schema_path = Path(repo.model_dir) / f"schema-{release}.sql"

        if release_schema_path.exists():
            repo.restore_database_from_release_schema(release)
        elif schema_path.exists():
            repo.restore_database_from_version_schema(release)
        else:
            raise RepoError(
                f"No schema found for release '{release}': neither "
                f"{release_schema_path.name} nor {schema_path.name} "
                f"exists in {repo.model_dir}."
            )

        click.echo(f"✓ {utils.Color.green('Database restored to')} {utils.Color.bold(release)}")
    except RepoError as e:
        click.echo(utils.Color.red(f"\n❌ {e}"), err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(utils.Color.red(f"\n❌ Unexpected error: {e}"), err=True)
        raise click.Abort()
