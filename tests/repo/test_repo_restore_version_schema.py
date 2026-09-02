"""
Tests for Repo.restore_database_from_version_schema().

Focused on restoring the database to the exact published snapshot of a
past version (model/schema-X.Y.Z.sql + model/data-X.Y.Z.sql), as opposed
to restore_database_from_schema() which always targets whatever
model/schema.sql currently points to.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, call

from half_orm_dev.repo import Repo, RepoError


@pytest.fixture
def mock_version_restore_environment(temp_repo):
    """
    Setup a temp_repo with a versioned model/ directory
    (schema-X.Y.Z.sql, data-X.Y.Z.sql), and bind the real
    restore_database_from_version_schema method onto the mocked repo.
    """
    repo, temp_dir, patches_dir = temp_repo

    model_dir = Path(temp_dir) / ".hop" / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    repo.model_dir = str(model_dir)

    repo.restore_database_from_version_schema = (
        Repo.restore_database_from_version_schema.__get__(repo, type(repo))
    )

    mock_model = Mock()
    mock_model.desc = Mock(return_value=[])
    mock_model.execute_query = Mock()
    mock_model.reconnect = Mock()
    repo.model = mock_model

    mock_execute = Mock()
    repo.database.execute_pg_command = mock_execute

    return repo, model_dir, mock_model, mock_execute


class TestRestoreDatabaseFromVersionSchema:
    def test_missing_schema_file_raises(self, mock_version_restore_environment):
        repo, model_dir, mock_model, mock_execute = mock_version_restore_environment

        with pytest.raises(RepoError, match="schema-0.3.5.sql"):
            repo.restore_database_from_version_schema("0.3.5")

        mock_execute.assert_not_called()

    def test_restores_exact_version_not_current_schema(self, mock_version_restore_environment):
        """
        The whole point of this method: given schema-0.3.13.sql AND
        schema-0.3.5.sql both present, asking for "0.3.5" must load
        schema-0.3.5.sql - never silently fall back to a newer version.
        """
        repo, model_dir, mock_model, mock_execute = mock_version_restore_environment

        (model_dir / "schema-0.3.13.sql").write_text("-- current prod schema")
        (model_dir / "schema-0.3.5.sql").write_text("-- old schema")

        with patch.object(repo, '_reset_database_schemas') as mock_reset:
            repo.restore_database_from_version_schema("0.3.5")

            mock_reset.assert_called_once()
            expected = call('psql', '-d', 'test_database', '-f',
                             str(model_dir / "schema-0.3.5.sql"))
            assert expected in mock_execute.call_args_list
            not_expected = call('psql', '-d', 'test_database', '-f',
                                 str(model_dir / "schema-0.3.13.sql"))
            assert not_expected not in mock_execute.call_args_list
            mock_model.reconnect.assert_called_once_with(reload=True)

    def test_loads_matching_data_file(self, mock_version_restore_environment):
        repo, model_dir, mock_model, mock_execute = mock_version_restore_environment

        (model_dir / "schema-0.3.5.sql").write_text("-- schema")
        (model_dir / "data-0.3.5.sql").write_text("-- data")

        with patch.object(repo, '_reset_database_schemas'):
            repo.restore_database_from_version_schema("0.3.5")

            expected = call('psql', '-d', 'test_database', '-f',
                             str(model_dir / "data-0.3.5.sql"))
            assert expected in mock_execute.call_args_list

    def test_missing_data_file_is_not_an_error(self, mock_version_restore_environment):
        repo, model_dir, mock_model, mock_execute = mock_version_restore_environment

        (model_dir / "schema-0.3.5.sql").write_text("-- schema")

        with patch.object(repo, '_reset_database_schemas'):
            repo.restore_database_from_version_schema("0.3.5")  # no raise

    def test_does_not_load_unrelated_version_data_file(self, mock_version_restore_environment):
        """A data-X.Y.Z.sql for a different version must never be picked up."""
        repo, model_dir, mock_model, mock_execute = mock_version_restore_environment

        (model_dir / "schema-0.3.5.sql").write_text("-- schema")
        (model_dir / "data-0.3.13.sql").write_text("-- unrelated version data")

        with patch.object(repo, '_reset_database_schemas'):
            repo.restore_database_from_version_schema("0.3.5")

            not_expected = call('psql', '-d', 'test_database', '-f',
                                 str(model_dir / "data-0.3.13.sql"))
            assert not_expected not in mock_execute.call_args_list

    def test_psql_failure_raises_repo_error(self, mock_version_restore_environment):
        repo, model_dir, mock_model, mock_execute = mock_version_restore_environment

        (model_dir / "schema-0.3.5.sql").write_text("-- schema")
        mock_execute.side_effect = Exception("psql exploded")

        with patch.object(repo, '_reset_database_schemas'):
            with pytest.raises(RepoError, match="Failed to load schema"):
                repo.restore_database_from_version_schema("0.3.5")
