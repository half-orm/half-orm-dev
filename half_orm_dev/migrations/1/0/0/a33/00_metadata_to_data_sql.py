"""
Migration 1.0.0a33 — metadata-X.Y.Z.sql -> data-X.Y.Z.sql

_generate_schema_sql() now writes an unrestricted pg_dump --data-only
snapshot (half_orm_meta bookkeeping + all application data) to
model/data-{version}.sql, replacing the old model/metadata-{version}.sql
(half_orm_meta tables only). restore_database_from_schema() and
restore_database_from_version_schema() look for data-{version}.sql, not
metadata-{version}.sql.

Without this migration, any project upgrading past this version would
have a schema.sql pointing at a version with only the old
metadata-{version}.sql on disk - a fresh clone/restore at that version
would silently load structure with no data at all (including no
half_orm_meta.hop_release row, breaking Repo() initialization).

This backfills model/data-{version}.sql for the project's *current*
published version (whatever model/schema.sql is symlinked to) by dumping
it fresh from the live database - which is, by construction, at exactly
that version. Older, already-superseded metadata-X.Y.Z.sql files are left
untouched (harmless, simply no longer read); backfilling those would
require rebuilding a database at each historical version, which is out of
scope for an automatic migration.
"""

from pathlib import Path


def get_description():
    return "Backfill data-X.Y.Z.sql (replaces metadata-X.Y.Z.sql) for the current version"


def migrate(repo):
    model_dir = Path(repo.model_dir)
    schema_path = model_dir / "schema.sql"

    if not schema_path.exists():
        return {}

    data_path, version = repo._deduce_data_path(schema_path)
    if data_path is None:
        # schema.sql isn't a versioned symlink - nothing to deduce/backfill
        return {}

    if data_path.exists():
        # Already backfilled (e.g. a release was cut after this migration
        # shipped, which generates data-X.Y.Z.sql on its own)
        return {}

    old_metadata_path = model_dir / f"metadata-{version}.sql"
    if not old_metadata_path.exists():
        # Nothing to backfill from - a from-scratch project already using
        # the new mechanism, or one that never had metadata files
        return {}

    repo.database._generate_data_sql(version, model_dir)

    relative_path = data_path.relative_to(repo.base_dir)
    repo.stage_maintenance_file(str(relative_path))

    return {'sync_files': [str(relative_path)]}
