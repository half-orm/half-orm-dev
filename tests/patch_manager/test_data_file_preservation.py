"""
Tests for data file preservation feature (@HOP:data annotation).

Tests the new feature that allows marking SQL files with @HOP:data to
preserve reference data (DML) for from-scratch installations.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock
from half_orm_dev.patch_manager import PatchManager
from half_orm_dev.file_executor import is_bootstrap_file


@pytest.fixture
def patch_manager_with_data_files(tmp_path):
    """Create PatchManager with patches containing data files."""
    # Create Patches directory
    patches_dir = tmp_path / "Patches"
    patches_dir.mkdir()

    # Create releases directory for the new structure
    releases_dir = tmp_path / ".hop" / "releases"
    releases_dir.mkdir(parents=True)

    # Create mock repo
    mock_repo = Mock()
    mock_repo.base_dir = str(tmp_path)
    mock_repo.model_dir = str(tmp_path / ".hop" / "model")
    mock_repo.releases_dir = str(releases_dir)
    mock_repo.devel = True
    mock_repo.name = "test_database"

    # Create patch manager
    patch_mgr = PatchManager(mock_repo)

    return patch_mgr, tmp_path, patches_dir


class TestDataFileDetection:
    """Test detection of @HOP:data annotation in SQL files."""

    def test_is_bootstrap_file_with_data_annotation(self, patch_manager_with_data_files):
        """Test that file with @HOP:data annotation is detected."""
        patch_mgr, tmp_path, patches_dir = patch_manager_with_data_files

        # Create SQL file with @HOP:data annotation
        sql_file = tmp_path / "test.sql"
        sql_file.write_text("-- @HOP:data\nINSERT INTO roles VALUES (1, 'admin');")

        assert is_bootstrap_file(sql_file) is True

    def test_is_bootstrap_file_with_bootstrap_annotation(self, patch_manager_with_data_files):
        """Test that file with @HOP:bootstrap annotation is detected."""
        patch_mgr, tmp_path, patches_dir = patch_manager_with_data_files

        # Create SQL file with @HOP:bootstrap annotation
        sql_file = tmp_path / "test.sql"
        sql_file.write_text("-- @HOP:bootstrap\nINSERT INTO roles VALUES (1, 'admin');")

        assert is_bootstrap_file(sql_file) is True

    def test_is_bootstrap_file_without_annotation(self, patch_manager_with_data_files):
        """Test that file without @HOP:data annotation is not detected."""
        patch_mgr, tmp_path, patches_dir = patch_manager_with_data_files

        # Create SQL file without annotation
        sql_file = tmp_path / "test.sql"
        sql_file.write_text("CREATE TABLE users (id SERIAL PRIMARY KEY);")

        assert is_bootstrap_file(sql_file) is False

    def test_is_bootstrap_file_with_annotation_not_first_line(self, patch_manager_with_data_files):
        """Test that annotation must be on first line."""
        patch_mgr, tmp_path, patches_dir = patch_manager_with_data_files

        # Create SQL file with annotation on second line
        sql_file = tmp_path / "test.sql"
        sql_file.write_text("-- Comment\n-- @HOP:data\nINSERT INTO roles VALUES (1, 'admin');")

        assert is_bootstrap_file(sql_file) is False

    def test_is_bootstrap_file_missing_file(self, patch_manager_with_data_files):
        """Test that missing file returns False."""
        patch_mgr, tmp_path, patches_dir = patch_manager_with_data_files

        non_existent = tmp_path / "missing.sql"
        assert is_bootstrap_file(non_existent) is False

    def test_is_bootstrap_file_python_with_data(self, patch_manager_with_data_files):
        """Test that Python file with @HOP:data annotation is detected."""
        patch_mgr, tmp_path, patches_dir = patch_manager_with_data_files

        # Create Python file with @HOP:data annotation
        py_file = tmp_path / "test.py"
        py_file.write_text("# @HOP:data\nimport sys\nprint('data')")

        assert is_bootstrap_file(py_file) is True

    def test_is_bootstrap_file_python_with_bootstrap(self, patch_manager_with_data_files):
        """Test that Python file with @HOP:bootstrap annotation is detected."""
        patch_mgr, tmp_path, patches_dir = patch_manager_with_data_files

        # Create Python file with @HOP:bootstrap annotation
        py_file = tmp_path / "test.py"
        py_file.write_text("# @HOP:bootstrap\nimport sys\nprint('bootstrap')")

        assert is_bootstrap_file(py_file) is True

    def test_get_data_files_from_patch_with_data(self, patch_manager_with_data_files):
        """Test getting data files from a patch."""
        patch_mgr, tmp_path, patches_dir = patch_manager_with_data_files

        # Create patch directory
        patch_dir = patches_dir / "456-user-auth"
        patch_dir.mkdir()
        readme = patch_dir / "README.md"
        readme.write_text("# Patch 456")

        # Create data file
        data_file = patch_dir / "01_roles.sql"
        data_file.write_text("-- @HOP:data\nINSERT INTO roles (name) VALUES ('admin') ON CONFLICT DO NOTHING;")

        # Create non-data file
        schema_file = patch_dir / "02_users.sql"
        schema_file.write_text("CREATE TABLE users (id SERIAL PRIMARY KEY);")

        # Get data files
        data_files = patch_mgr._get_data_files_from_patch("456-user-auth")

        assert len(data_files) == 1
        assert data_files[0].name == "01_roles.sql"

    def test_get_data_files_from_patch_no_data(self, patch_manager_with_data_files):
        """Test getting data files from patch with no data files."""
        patch_mgr, tmp_path, patches_dir = patch_manager_with_data_files

        # Create patch directory
        patch_dir = patches_dir / "456-user-auth"
        patch_dir.mkdir()
        readme = patch_dir / "README.md"
        readme.write_text("# Patch 456")

        # Create only schema files
        schema_file = patch_dir / "01_users.sql"
        schema_file.write_text("CREATE TABLE users (id SERIAL PRIMARY KEY);")

        # Get data files
        data_files = patch_mgr._get_data_files_from_patch("456-user-auth")

        assert len(data_files) == 0

    def test_get_data_files_maintains_order(self, patch_manager_with_data_files):
        """Test that data files are returned in lexicographic order."""
        patch_mgr, tmp_path, patches_dir = patch_manager_with_data_files

        # Create patch directory
        patch_dir = patches_dir / "456-user-auth"
        patch_dir.mkdir()
        readme = patch_dir / "README.md"
        readme.write_text("# Patch 456")

        # Create multiple data files
        for i in [3, 1, 2]:
            data_file = patch_dir / f"0{i}_data.sql"
            data_file.write_text(f"-- @HOP:data\nINSERT INTO test VALUES ({i});")

        # Get data files
        data_files = patch_mgr._get_data_files_from_patch("456-user-auth")

        assert len(data_files) == 3
        assert data_files[0].name == "01_data.sql"
        assert data_files[1].name == "02_data.sql"
        assert data_files[2].name == "03_data.sql"


class TestDataFileIdempotencyValidation:
    """Test validation of idempotent SQL patterns."""

    def test_validate_idempotent_with_on_conflict(self, patch_manager_with_data_files):
        """Test that INSERT with ON CONFLICT is valid."""
        patch_mgr, tmp_path, patches_dir = patch_manager_with_data_files

        sql_file = tmp_path / "test.sql"
        sql_file.write_text(
            "-- @HOP:data\n"
            "INSERT INTO roles (name) VALUES ('admin') ON CONFLICT DO NOTHING;"
        )

        is_valid, warnings = patch_mgr._validate_data_file_idempotent(sql_file)

        assert is_valid is True
        assert len(warnings) == 0

    def test_validate_idempotent_with_delete_before_insert(self, patch_manager_with_data_files):
        """Test that DELETE before INSERT is valid."""
        patch_mgr, tmp_path, patches_dir = patch_manager_with_data_files

        sql_file = tmp_path / "test.sql"
        sql_file.write_text(
            "-- @HOP:data\n"
            "DELETE FROM roles WHERE name = 'admin';\n"
            "INSERT INTO roles (name) VALUES ('admin');"
        )

        is_valid, warnings = patch_mgr._validate_data_file_idempotent(sql_file)

        assert is_valid is True
        assert len(warnings) == 0

    def test_validate_idempotent_with_where_not_exists(self, patch_manager_with_data_files):
        """Test that INSERT with WHERE NOT EXISTS is valid."""
        patch_mgr, tmp_path, patches_dir = patch_manager_with_data_files

        sql_file = tmp_path / "test.sql"
        sql_file.write_text(
            "-- @HOP:data\n"
            "INSERT INTO roles (name) SELECT 'admin' WHERE NOT EXISTS (SELECT 1 FROM roles WHERE name = 'admin');"
        )

        is_valid, warnings = patch_mgr._validate_data_file_idempotent(sql_file)

        assert is_valid is True
        assert len(warnings) == 0

    def test_validate_non_idempotent_insert(self, patch_manager_with_data_files):
        """Test that plain INSERT without idempotency pattern generates warning."""
        patch_mgr, tmp_path, patches_dir = patch_manager_with_data_files

        sql_file = tmp_path / "test.sql"
        sql_file.write_text(
            "-- @HOP:data\n"
            "INSERT INTO roles (name) VALUES ('admin');"
        )

        is_valid, warnings = patch_mgr._validate_data_file_idempotent(sql_file)

        assert is_valid is False
        assert len(warnings) == 1
        assert "INSERT without idempotent pattern" in warnings[0]

    def test_validate_empty_file_is_valid(self, patch_manager_with_data_files):
        """Test that empty file is considered valid."""
        patch_mgr, tmp_path, patches_dir = patch_manager_with_data_files

        sql_file = tmp_path / "test.sql"
        sql_file.write_text("-- @HOP:data\n")

        is_valid, warnings = patch_mgr._validate_data_file_idempotent(sql_file)

        assert is_valid is True
        assert len(warnings) == 0


class TestCollectDataFilesFromPatches:
    """Test collecting data files from multiple patches."""

    def test_collect_data_files_from_multiple_patches(self, patch_manager_with_data_files):
        """Test collecting data files from multiple patches."""
        patch_mgr, tmp_path, patches_dir = patch_manager_with_data_files

        # Create first patch with data file
        patch1_dir = patches_dir / "456-auth"
        patch1_dir.mkdir()
        (patch1_dir / "README.md").write_text("# Patch 456")
        (patch1_dir / "01_roles.sql").write_text(
            "-- @HOP:data\nINSERT INTO roles (name) VALUES ('admin') ON CONFLICT DO NOTHING;"
        )

        # Create second patch with data file
        patch2_dir = patches_dir / "457-permissions"
        patch2_dir.mkdir()
        (patch2_dir / "README.md").write_text("# Patch 457")
        (patch2_dir / "01_permissions.sql").write_text(
            "-- @HOP:data\nINSERT INTO permissions (name) VALUES ('read') ON CONFLICT DO NOTHING;"
        )

        # Collect data files
        data_files = patch_mgr._collect_data_files_from_patches(["456-auth", "457-permissions"])

        assert len(data_files) == 2
        assert data_files[0].name == "01_roles.sql"
        assert data_files[1].name == "01_permissions.sql"

    def test_collect_data_files_empty_list(self, patch_manager_with_data_files):
        """Test collecting data files from empty patch list."""
        patch_mgr, tmp_path, patches_dir = patch_manager_with_data_files

        data_files = patch_mgr._collect_data_files_from_patches([])

        assert len(data_files) == 0

    def test_collect_data_files_no_data_in_patches(self, patch_manager_with_data_files):
        """Test collecting data files when patches have no data files."""
        patch_mgr, tmp_path, patches_dir = patch_manager_with_data_files

        # Create patch without data files
        patch_dir = patches_dir / "456-schema"
        patch_dir.mkdir()
        (patch_dir / "README.md").write_text("# Patch 456")
        (patch_dir / "01_users.sql").write_text("CREATE TABLE users (id SERIAL PRIMARY KEY);")

        # Collect data files
        data_files = patch_mgr._collect_data_files_from_patches(["456-schema"])

        assert len(data_files) == 0

    def test_collect_data_files_validates_idempotency(self, patch_manager_with_data_files, capsys):
        """Test that collecting data files validates idempotency and shows warnings."""
        patch_mgr, tmp_path, patches_dir = patch_manager_with_data_files

        # Create patch with non-idempotent data file
        patch_dir = patches_dir / "456-auth"
        patch_dir.mkdir()
        (patch_dir / "README.md").write_text("# Patch 456")
        (patch_dir / "01_roles.sql").write_text(
            "-- @HOP:data\nINSERT INTO roles (name) VALUES ('admin');"
        )

        # Collect data files (should show warning)
        data_files = patch_mgr._collect_data_files_from_patches(["456-auth"])

        # Should still return the file
        assert len(data_files) == 1

        # Should show warning in output
        captured = capsys.readouterr()
        assert "idempotency warnings" in captured.out
        assert "INSERT without idempotent pattern" in captured.out
