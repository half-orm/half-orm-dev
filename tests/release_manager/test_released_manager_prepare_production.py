"""
Tests for ReleaseManager.prepare_release() - Production version reading.

Focused on testing:
- Reading version from model/schema.sql symlink
- Error handling for missing files
- First project scenario (0.0.0)
- Version calculation from production

NOTE: These tests use mock_release_manager_with_hgit (NOT with_production)
because they need to test the REAL _get_production_version() behavior.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock

from half_orm_dev.release_manager import ReleaseManager, ReleaseManagerError, ReleaseFileError


class TestPrepareReleaseProductionVersion:
    """Test production version reading and usage."""

    def test_reads_from_schema_symlink(self, mock_release_manager_with_hgit):
        """Test reads production version from model/schema.sql symlink."""
        release_mgr, mock_repo, mock_hgit, tmp_path = mock_release_manager_with_hgit

        # Create model/ with production schema 1.3.5
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        schema_file = model_dir / "schema-1.3.5.sql"
        schema_file.write_text("-- Schema 1.3.5")
        schema_symlink = model_dir / "schema.sql"
        schema_symlink.symlink_to("schema-1.3.5.sql")

        # Mock database
        mock_database = Mock()
        mock_database.last_release_s = "1.3.5"
        mock_repo.database = mock_database

        result = release_mgr.prepare_release('patch')

        # Should calculate from production version 1.3.5
        assert result['previous_version'] == '1.3.5'
        assert result['version'] == '1.3.6'

    def test_calculates_minor_from_production(self, mock_release_manager_with_hgit):
        """Test minor increment calculated from production version."""
        release_mgr, mock_repo, mock_hgit, tmp_path = mock_release_manager_with_hgit

        # Setup production 1.3.5
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        schema_file = model_dir / "schema-1.3.5.sql"
        schema_file.write_text("-- Schema")
        (model_dir / "schema.sql").symlink_to("schema-1.3.5.sql")

        mock_database = Mock()
        mock_database.last_release_s = "1.3.5"
        mock_repo.database = mock_database

        result = release_mgr.prepare_release('minor')

        assert result['previous_version'] == '1.3.5'
        assert result['version'] == '1.4.0'

    def test_calculates_major_from_production(self, mock_release_manager_with_hgit):
        """Test major increment calculated from production version."""
        release_mgr, mock_repo, mock_hgit, tmp_path = mock_release_manager_with_hgit

        # Setup production 1.3.5
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        schema_file = model_dir / "schema-1.3.5.sql"
        schema_file.write_text("-- Schema")
        (model_dir / "schema.sql").symlink_to("schema-1.3.5.sql")

        mock_database = Mock()
        mock_database.last_release_s = "1.3.5"
        mock_repo.database = mock_database

        result = release_mgr.prepare_release('major')

        assert result['previous_version'] == '1.3.5'
        assert result['version'] == '2.0.0'

    def test_schema_symlink_missing_raises_error(self, mock_release_manager_with_hgit):
        """Test error when model/schema.sql doesn't exist."""
        release_mgr, mock_repo, mock_hgit, tmp_path = mock_release_manager_with_hgit

        # model/ directory exists but no schema.sql
        model_dir = tmp_path / "model"
        model_dir.mkdir()

        with pytest.raises(ReleaseFileError, match="schema.sql.*not found|Production schema"):
            release_mgr.prepare_release('patch')

    def test_model_directory_missing_raises_error(self, mock_release_manager_with_hgit):
        """Test error when model/ directory doesn't exist."""
        release_mgr, mock_repo, mock_hgit, tmp_path = mock_release_manager_with_hgit

        # No model/ directory
        with pytest.raises(ReleaseFileError, match="Model directory not found"):
            release_mgr.prepare_release('patch')

    def test_first_project_from_0_0_0_patch(self, mock_release_manager_with_hgit):
        """Test first patch release from 0.0.0 (after init-database)."""
        release_mgr, mock_repo, mock_hgit, tmp_path = mock_release_manager_with_hgit

        # Create model/ with schema-0.0.0.sql
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        schema_file = model_dir / "schema-0.0.0.sql"
        schema_file.write_text("-- Initial schema")
        schema_symlink = model_dir / "schema.sql"
        schema_symlink.symlink_to("schema-0.0.0.sql")

        mock_database = Mock()
        mock_database.last_release_s = "0.0.0"
        mock_repo.database = mock_database

        result = release_mgr.prepare_release('patch')

        # Should create 0.0.1-stage.txt from 0.0.0
        assert result['previous_version'] == '0.0.0'
        assert result['version'] == '0.0.1'

        # Verify stage file created
        stage_file = tmp_path / "releases" / "0.0.1-stage.txt"
        assert stage_file.exists()

    def test_first_project_from_0_0_0_minor(self, mock_release_manager_with_hgit):
        """Test first minor release from 0.0.0."""
        release_mgr, mock_repo, mock_hgit, tmp_path = mock_release_manager_with_hgit

        model_dir = tmp_path / "model"
        model_dir.mkdir()
        schema_file = model_dir / "schema-0.0.0.sql"
        schema_file.write_text("-- Initial schema")
        schema_symlink = model_dir / "schema.sql"
        schema_symlink.symlink_to("schema-0.0.0.sql")

        mock_database = Mock()
        mock_database.last_release_s = "0.0.0"
        mock_repo.database = mock_database

        result = release_mgr.prepare_release('minor')

        assert result['previous_version'] == '0.0.0'
        assert result['version'] == '0.1.0'

    def test_first_project_from_0_0_0_major(self, mock_release_manager_with_hgit):
        """Test first major release from 0.0.0."""
        release_mgr, mock_repo, mock_hgit, tmp_path = mock_release_manager_with_hgit

        model_dir = tmp_path / "model"
        model_dir.mkdir()
        schema_file = model_dir / "schema-0.0.0.sql"
        schema_file.write_text("-- Initial schema")
        schema_symlink = model_dir / "schema.sql"
        schema_symlink.symlink_to("schema-0.0.0.sql")

        mock_database = Mock()
        mock_database.last_release_s = "0.0.0"
        mock_repo.database = mock_database

        result = release_mgr.prepare_release('major')

        assert result['previous_version'] == '0.0.0'
        assert result['version'] == '1.0.0'

    def test_symlink_points_to_invalid_version_format(self, mock_release_manager_with_hgit):
        """Test error when symlink points to file with invalid version format."""
        release_mgr, mock_repo, mock_hgit, tmp_path = mock_release_manager_with_hgit

        model_dir = tmp_path / "model"
        model_dir.mkdir()

        # Create file with invalid version format
        invalid_file = model_dir / "schema-invalid.sql"
        invalid_file.write_text("-- Schema")
        schema_symlink = model_dir / "schema.sql"
        schema_symlink.symlink_to("schema-invalid.sql")

        with pytest.raises(ReleaseFileError, match="Invalid schema symlink target format"):
            release_mgr.prepare_release('patch')

    def test_symlink_is_broken(self, mock_release_manager_with_hgit):
        """Test error when symlink points to non-existent file."""
        release_mgr, mock_repo, mock_hgit, tmp_path = mock_release_manager_with_hgit

        model_dir = tmp_path / "model"
        model_dir.mkdir()

        # Create broken symlink
        schema_symlink = model_dir / "schema.sql"
        schema_symlink.symlink_to("schema-nonexistent.sql")  # Doesn't exist

        # Broken symlink: exists() returns False
        with pytest.raises(ReleaseFileError, match="Production schema file not found"):
            release_mgr.prepare_release('patch')
