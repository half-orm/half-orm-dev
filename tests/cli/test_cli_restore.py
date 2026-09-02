"""
Tests for the `restore` CLI command.

Covers the file-resolution order the command must apply:
1. .hop/model/release-RELEASE.sql  -> restore_database_from_release_schema
2. .hop/model/schema-RELEASE.sql   -> restore_database_from_version_schema
3. neither exists                  -> clean failure, no restoration attempted
"""

import tempfile
import shutil
from pathlib import Path

import pytest
from unittest.mock import MagicMock, patch
from click.testing import CliRunner

from half_orm_dev.cli.commands.restore import restore


@pytest.fixture
def model_dir():
    temp_dir = tempfile.mkdtemp()
    model_dir = Path(temp_dir) / ".hop" / "model"
    model_dir.mkdir(parents=True)
    yield model_dir
    shutil.rmtree(temp_dir)


def _mock_repo(model_dir):
    mock_repo = MagicMock()
    mock_repo.model_dir = str(model_dir)
    mock_repo.get_release_schema_path.side_effect = (
        lambda version: model_dir / f"release-{version}.sql"
    )
    return mock_repo


def _invoke(release, mock_repo):
    runner = CliRunner()
    with patch('half_orm_dev.cli.commands.restore.Repo', return_value=mock_repo):
        return runner.invoke(restore, [release], catch_exceptions=False)


class TestRestorePrefersReleaseSchema:
    def test_uses_release_schema_when_present(self, model_dir):
        (model_dir / "release-0.17.1.sql").write_text("-- in-dev release schema")
        mock_repo = _mock_repo(model_dir)

        result = _invoke("0.17.1", mock_repo)

        assert result.exit_code == 0
        mock_repo.restore_database_from_release_schema.assert_called_once_with("0.17.1")
        mock_repo.restore_database_from_version_schema.assert_not_called()


class TestRestoreFallsBackToVersionSchema:
    def test_uses_version_schema_when_no_release_schema(self, model_dir):
        (model_dir / "schema-0.3.5.sql").write_text("-- published snapshot")
        mock_repo = _mock_repo(model_dir)

        result = _invoke("0.3.5", mock_repo)

        assert result.exit_code == 0
        mock_repo.restore_database_from_version_schema.assert_called_once_with("0.3.5")
        mock_repo.restore_database_from_release_schema.assert_not_called()


class TestRestoreUnknownVersion:
    def test_fails_cleanly_without_restoring_anything(self, model_dir):
        mock_repo = _mock_repo(model_dir)

        result = _invoke("9.9.9", mock_repo)

        assert result.exit_code != 0
        mock_repo.restore_database_from_release_schema.assert_not_called()
        mock_repo.restore_database_from_version_schema.assert_not_called()

    def test_does_not_silently_load_current_prod_schema(self, model_dir):
        """
        Regression guard: requesting a version with no matching file must
        never silently succeed against a different (e.g. current prod)
        schema - that was the original bug.
        """
        (model_dir / "schema-9.9.8.sql").write_text("-- unrelated version")
        mock_repo = _mock_repo(model_dir)

        result = _invoke("9.9.9", mock_repo)

        assert result.exit_code != 0
        mock_repo.restore_database_from_version_schema.assert_not_called()
