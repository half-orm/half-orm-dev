"""
Tests for data SQL file generation during release promotion.

Tests the generation of data-X.Y.Z.sql files from patches with @HOP:data
annotation during promote_to_rc, promote_to_prod, and promote_to_hotfix.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock
from half_orm_dev.release_manager import ReleaseManager


@pytest.fixture
def release_manager_with_data_patches(tmp_path):
    """Create ReleaseManager with patches containing data files."""
    # Create directories
    releases_dir = tmp_path / ".hop" / "releases"
    releases_dir.mkdir(parents=True)
    patches_dir = tmp_path / "Patches"
    patches_dir.mkdir()

    # Create model directory
    model_dir = tmp_path / ".hop" / "model"
    model_dir.mkdir(parents=True)

    # Create mock repo
    mock_repo = Mock()
    mock_repo.base_dir = str(tmp_path)
    mock_repo.releases_dir = str(releases_dir)
    mock_repo.model_dir = str(model_dir)

    # Create mock patch_manager
    mock_patch_manager = Mock()
    mock_repo.patch_manager = mock_patch_manager

    # Create release manager
    rel_mgr = ReleaseManager(mock_repo)

    return rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir


class TestGenerateDataSqlFile:
    """Test _generate_data_sql_file helper method."""

    def test_generate_data_sql_file_with_data_files(self, release_manager_with_data_patches):
        """Test generating data SQL file from patches with data files."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir = release_manager_with_data_patches

        # Create mock data files
        data_file1 = patches_dir / "01_roles.sql"
        data_file1.write_text("-- @HOP:data\nINSERT INTO roles (name) VALUES ('admin') ON CONFLICT DO NOTHING;")

        data_file2 = patches_dir / "02_permissions.sql"
        data_file2.write_text("-- @HOP:data\nINSERT INTO permissions (name) VALUES ('read') ON CONFLICT DO NOTHING;")

        # Mock patch_manager to return data files
        mock_repo.patch_manager._collect_data_files_from_patches.return_value = [data_file1, data_file2]

        # Generate data SQL file
        result = rel_mgr._generate_data_sql_file(["456-auth"], "data-1.0.0.sql")

        assert result is not None
        assert result.exists()
        assert result.name == "data-1.0.0.sql"

        # Verify content
        content = result.read_text()
        assert "-- Data file for data-1.0.0" in content
        assert "-- Generated from patches: 456-auth" in content
        assert "INSERT INTO roles" in content
        assert "INSERT INTO permissions" in content
        assert "-- Source:" in content

    def test_generate_data_sql_file_strips_annotation(self, release_manager_with_data_patches):
        """Test that @HOP:data annotation is stripped from output."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir = release_manager_with_data_patches

        # Create mock data file with annotation
        data_file = patches_dir / "01_roles.sql"
        data_file.write_text("-- @HOP:data\nINSERT INTO roles (name) VALUES ('admin');")

        # Mock patch_manager
        mock_repo.patch_manager._collect_data_files_from_patches.return_value = [data_file]

        # Generate data SQL file
        result = rel_mgr._generate_data_sql_file(["456-auth"], "data-1.0.0.sql")

        content = result.read_text()
        # First line with annotation should not appear in generated content
        # (it's skipped during concatenation)
        lines = content.split('\n')
        assert not any(line.strip() == "-- @HOP:data" for line in lines)

    def test_generate_data_sql_file_no_data_files(self, release_manager_with_data_patches):
        """Test that no file is generated when there are no data files."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir = release_manager_with_data_patches

        # Mock patch_manager to return empty list
        mock_repo.patch_manager._collect_data_files_from_patches.return_value = []

        # Generate data SQL file
        result = rel_mgr._generate_data_sql_file(["456-schema"], "data-1.0.0.sql")

        assert result is None

    def test_generate_data_sql_file_empty_patch_list(self, release_manager_with_data_patches):
        """Test that no file is generated for empty patch list."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir = release_manager_with_data_patches

        # Generate with empty patch list
        result = rel_mgr._generate_data_sql_file([], "data-1.0.0.sql")

        assert result is None

    def test_generate_data_sql_file_multiple_patches(self, release_manager_with_data_patches):
        """Test generating data SQL file from multiple patches."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir = release_manager_with_data_patches

        # Create mock data files from different patches
        data_file1 = patches_dir / "01_roles.sql"
        data_file1.write_text("-- @HOP:data\nINSERT INTO roles (name) VALUES ('admin');")

        data_file2 = patches_dir / "02_permissions.sql"
        data_file2.write_text("-- @HOP:data\nINSERT INTO permissions (name) VALUES ('read');")

        # Mock patch_manager
        mock_repo.patch_manager._collect_data_files_from_patches.return_value = [data_file1, data_file2]

        # Generate data SQL file
        result = rel_mgr._generate_data_sql_file(["456-auth", "457-perms"], "data-1.0.0.sql")

        content = result.read_text()
        assert "456-auth, 457-perms" in content
        assert "INSERT INTO roles" in content
        assert "INSERT INTO permissions" in content


class TestPromoteToRCWithDataFiles:
    """Test promote_to_rc with data file generation."""

    def test_promote_rc_generates_data_file(self, release_manager_with_data_patches):
        """Test that promote_to_rc generates data-X.Y.Z-rcN.sql if data exists."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir = release_manager_with_data_patches

        # Setup: create stage file
        from half_orm_dev.release_file import ReleaseFile

        release_file = ReleaseFile("1.0.0", releases_dir)

        release_file.create_empty()

        release_file.add_patch("456-auth")

        release_file.move_to_staged("456-auth")

        # Mock data file
        data_file = patches_dir / "01_roles.sql"
        data_file.write_text("-- @HOP:data\nINSERT INTO roles (name) VALUES ('admin') ON CONFLICT DO NOTHING;")

        # Mock dependencies
        mock_hgit = Mock()
        mock_hgit.branch = "ho-prod"
        mock_hgit.checkout = Mock()
        mock_hgit.list_tags = Mock(return_value=[])
        mock_hgit.create_tag = Mock()
        mock_hgit.push_tag = Mock()
        mock_hgit.push_branch = Mock()
        mock_hgit.add = Mock()
        mock_hgit.commit = Mock()
        mock_repo.hgit = mock_hgit

        mock_repo.patch_manager._collect_data_files_from_patches.return_value = [data_file]
        mock_repo.patch_manager._sync_release_files_to_ho_prod = Mock()

        # Mock _apply_release_patches to avoid database operations
        rel_mgr._apply_release_patches = Mock()

        # Promote to RC
        result = rel_mgr.promote_to_rc()

        # Verify data file was generated
        data_file_path = releases_dir / "data-1.0.0-rc1.sql"
        assert data_file_path.exists()

        # Verify data file was added to git
        add_calls = [str(call[0][0]) for call in mock_hgit.add.call_args_list]
        assert any("data-1.0.0-rc1.sql" in call for call in add_calls)

    def test_promote_rc_no_data_file_when_no_data(self, release_manager_with_data_patches):
        """Test that promote_to_rc doesn't generate data file if no data exists."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir = release_manager_with_data_patches

        # Setup: create stage file
        from half_orm_dev.release_file import ReleaseFile

        release_file = ReleaseFile("1.0.0", releases_dir)

        release_file.create_empty()

        release_file.add_patch("456-schema")

        release_file.move_to_staged("456-schema")

        # Mock dependencies
        mock_hgit = Mock()
        mock_hgit.branch = "ho-prod"
        mock_hgit.checkout = Mock()
        mock_hgit.list_tags = Mock(return_value=[])
        mock_hgit.create_tag = Mock()
        mock_hgit.push_tag = Mock()
        mock_hgit.push_branch = Mock()
        mock_hgit.add = Mock()
        mock_hgit.commit = Mock()
        mock_repo.hgit = mock_hgit

        mock_repo.patch_manager._collect_data_files_from_patches.return_value = []
        mock_repo.patch_manager._sync_release_files_to_ho_prod = Mock()

        # Mock _apply_release_patches
        rel_mgr._apply_release_patches = Mock()

        # Promote to RC
        result = rel_mgr.promote_to_rc()

        # Verify no data file was generated
        data_file_path = releases_dir / "data-1.0.0-rc1.sql"
        assert not data_file_path.exists()


class TestPromoteToProdWithDataFiles:
    """Test promote_to_prod with data file generation."""

    def test_promote_prod_generates_data_file(self, release_manager_with_data_patches):
        """Test that promote_to_prod generates data-X.Y.Z.sql if data exists."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir = release_manager_with_data_patches

        # Setup: create stage file with patches
        from half_orm_dev.release_file import ReleaseFile

        release_file = ReleaseFile("1.0.0", releases_dir)

        release_file.create_empty()

        release_file.add_patch("789-data-patch")

        release_file.move_to_staged("789-data-patch")

        # Mock data file
        data_file = patches_dir / "01_data.sql"
        data_file.write_text("-- @HOP:data\nINSERT INTO test (value) VALUES ('data') ON CONFLICT DO NOTHING;")

        # Mock dependencies
        mock_hgit = Mock()
        mock_hgit.branch = "ho-prod"
        mock_hgit.checkout = Mock()
        mock_hgit.merge = Mock()
        mock_hgit.create_tag = Mock()
        mock_hgit.push_tag = Mock()
        mock_hgit.push_branch = Mock()
        mock_hgit.add = Mock()
        mock_hgit.commit = Mock()
        mock_hgit.delete_branch = Mock()
        mock_hgit.delete_remote_branch = Mock()
        mock_repo.hgit = mock_hgit

        mock_repo.patch_manager._collect_data_files_from_patches.return_value = [data_file]

        # Mock database and other dependencies
        mock_database = Mock()
        mock_database._generate_schema_sql = Mock()
        mock_repo.database = mock_database

        model_dir = tmp_path / "model"
        model_dir.mkdir()

        # Mock _get_latest_rc_number and read_release_patches
        rel_mgr._get_latest_rc_number = Mock(return_value=0)
        rel_mgr.read_release_patches = Mock(return_value=["789-data-patch"])

        # Promote to prod
        result = rel_mgr.promote_to_prod()

        # Verify data file was generated
        data_file_path = releases_dir / "data-1.0.0.sql"
        assert data_file_path.exists()

        # Verify data file was added to git
        add_calls = [str(call[0][0]) for call in mock_hgit.add.call_args_list]
        assert any("data-1.0.0.sql" in call for call in add_calls)


class TestPromoteToHotfixWithDataFiles:
    """Test promote_to_hotfix with data file generation."""

    def test_promote_hotfix_generates_data_file(self, release_manager_with_data_patches):
        """Test that promote_to_hotfix generates data-X.Y.Z-hotfixN.sql if data exists."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir = release_manager_with_data_patches

        # Setup: create stage file
        from half_orm_dev.release_file import ReleaseFile

        release_file = ReleaseFile("1.0.0", releases_dir)

        release_file.create_empty()

        release_file.add_patch("999-hotfix-patch")

        release_file.move_to_staged("999-hotfix-patch")

        # Mock data file
        data_file = patches_dir / "01_hotfix_data.sql"
        data_file.write_text("-- @HOP:data\nINSERT INTO hotfix (value) VALUES ('fix') ON CONFLICT DO NOTHING;")

        # Mock dependencies
        mock_hgit = Mock()
        mock_hgit.branch = "ho-release/1.0.0"
        mock_hgit.checkout = Mock()
        mock_hgit.merge = Mock()
        mock_hgit.create_tag = Mock()
        mock_hgit.push_tag = Mock()
        mock_hgit.push_branch = Mock()
        mock_hgit.add = Mock()
        mock_hgit.commit = Mock()
        mock_hgit.delete_branch = Mock()
        mock_hgit.delete_remote_branch = Mock()
        mock_repo.hgit = mock_hgit

        mock_repo.patch_manager._collect_data_files_from_patches.return_value = [data_file]

        # Mock _apply_release_patches
        rel_mgr._apply_release_patches = Mock()
        rel_mgr._determine_hotfix_number = Mock(return_value=1)
        rel_mgr.read_release_patches = Mock(return_value=["999-hotfix-patch"])

        # Promote to hotfix
        result = rel_mgr.promote_to_hotfix()

        # Verify data file was generated
        data_file_path = releases_dir / "data-1.0.0-hotfix1.sql"
        assert data_file_path.exists()

        # Verify data file was added to git
        add_calls = [str(call[0][0]) for call in mock_hgit.add.call_args_list]
        assert any("data-1.0.0-hotfix1.sql" in call for call in add_calls)
