"""
Tests for migration 1.0.0a33: metadata-X.Y.Z.sql -> data-X.Y.Z.sql backfill.

Covers half_orm_dev/migrations/1/0/0/a33/00_metadata_to_data_sql.py, which
regenerates model/data-{version}.sql for a project's current published
version when only the old model/metadata-{version}.sql exists - preventing
silent data loss (including half_orm_meta.hop_release) for any project
upgrading past the metadata->data rename.
"""

import importlib.util
import pytest
from pathlib import Path
from unittest.mock import Mock

from half_orm_dev.repo import Repo


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "half_orm_dev" / "migrations" / "1" / "0" / "0" / "a33"
    / "00_metadata_to_data_sql.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("metadata_to_data_sql", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def migration():
    return _load_migration()


@pytest.fixture
def mock_repo(tmp_path):
    model_dir = tmp_path / ".hop" / "model"
    model_dir.mkdir(parents=True)

    repo = Mock()
    repo.base_dir = str(tmp_path)
    repo.model_dir = str(model_dir)
    repo._deduce_data_path = Repo._deduce_data_path.__get__(repo, type(repo))
    repo.database._generate_data_sql = Mock(
        side_effect=lambda version, mdir: (mdir / f"data-{version}.sql").write_text("-- generated")
    )
    repo.stage_maintenance_file = Mock()

    return repo, model_dir


class TestMetadataToDataSqlMigration:
    def test_backfills_data_file_from_metadata(self, migration, mock_repo):
        repo, model_dir = mock_repo
        (model_dir / "schema-1.2.3.sql").write_text("-- schema")
        (model_dir / "schema.sql").symlink_to("schema-1.2.3.sql")
        (model_dir / "metadata-1.2.3.sql").write_text("-- old metadata")

        result = migration.migrate(repo)

        assert (model_dir / "data-1.2.3.sql").exists()
        repo.database._generate_data_sql.assert_called_once_with("1.2.3", model_dir)
        repo.stage_maintenance_file.assert_called_once_with(
            str(Path(".hop/model/data-1.2.3.sql"))
        )
        assert result['sync_files'] == [str(Path(".hop/model/data-1.2.3.sql"))]

    def test_noop_when_data_file_already_exists(self, migration, mock_repo):
        repo, model_dir = mock_repo
        (model_dir / "schema-1.2.3.sql").write_text("-- schema")
        (model_dir / "schema.sql").symlink_to("schema-1.2.3.sql")
        (model_dir / "metadata-1.2.3.sql").write_text("-- old metadata")
        (model_dir / "data-1.2.3.sql").write_text("-- already backfilled")

        result = migration.migrate(repo)

        repo.database._generate_data_sql.assert_not_called()
        assert result == {}

    def test_noop_when_no_old_metadata_to_backfill_from(self, migration, mock_repo):
        """A from-scratch project on the new mechanism has nothing to backfill."""
        repo, model_dir = mock_repo
        (model_dir / "schema-1.2.3.sql").write_text("-- schema")
        (model_dir / "schema.sql").symlink_to("schema-1.2.3.sql")
        # No metadata-1.2.3.sql

        result = migration.migrate(repo)

        repo.database._generate_data_sql.assert_not_called()
        assert result == {}

    def test_noop_when_schema_sql_missing(self, migration, mock_repo):
        repo, model_dir = mock_repo
        # No schema.sql at all

        result = migration.migrate(repo)

        repo.database._generate_data_sql.assert_not_called()
        assert result == {}

    def test_noop_when_schema_sql_is_not_a_versioned_symlink(self, migration, mock_repo):
        repo, model_dir = mock_repo
        (model_dir / "schema.sql").write_text("-- regular file, not a symlink")

        result = migration.migrate(repo)

        repo.database._generate_data_sql.assert_not_called()
        assert result == {}
