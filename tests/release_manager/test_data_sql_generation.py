"""
Tests for data SQL file generation during release promotion.

Tests the generation of model/data-X.Y.Z.sql files from patches with @HOP:data
annotation during promote_to_prod.

Note: data files are only generated for production releases, not for RC or hotfix.
In production upgrades, data is inserted via patch application.
Data files are only used for from-scratch installations (clone, restore).
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

    # Mock repo
    mock_repo = Mock()
    mock_repo.base_dir = str(tmp_path)
    mock_repo.releases_dir = str(releases_dir)
    mock_repo.model_dir = str(model_dir)

    # Mock commit_and_sync_to_active_branches
    mock_repo.commit_and_sync_to_active_branches = Mock(return_value={
        'commit_hash': 'abc123',
        'pushed_branch': 'test-branch',
        'sync_result': {'synced_branches': [], 'skipped_branches': [], 'errors': []}
    })

    # Create mock patch_manager
    mock_patch_manager = Mock()
    mock_repo.patch_manager = mock_patch_manager

    # Create release manager
    rel_mgr = ReleaseManager(mock_repo)

    return rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir, model_dir


class TestGenerateDataSqlFile:
    """Test _generate_data_sql_file helper method."""

    def test_generate_data_sql_file_with_data_files(self, release_manager_with_data_patches):
        """Test generating data SQL file from patches with data files."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir, model_dir = release_manager_with_data_patches

        # Create mock data files
        data_file1 = patches_dir / "01_roles.sql"
        data_file1.write_text("-- @HOP:data\nINSERT INTO roles (name) VALUES ('admin') ON CONFLICT DO NOTHING;")

        data_file2 = patches_dir / "02_permissions.sql"
        data_file2.write_text("-- @HOP:data\nINSERT INTO permissions (name) VALUES ('read') ON CONFLICT DO NOTHING;")

        # Mock patch_manager to return data files
        mock_repo.patch_manager._collect_data_files_from_patches.return_value = [data_file1, data_file2]

        # Generate data SQL file
        result = rel_mgr._generate_data_sql_file(["456-auth"], "1.0.0")

        assert result is not None
        assert result.exists()
        assert result.name == "data-1.0.0.sql"
        assert result.parent == model_dir

        # Verify content
        content = result.read_text()
        assert "-- Data file for version 1.0.0" in content
        assert "-- Generated from patches: 456-auth" in content
        assert "INSERT INTO roles" in content
        assert "INSERT INTO permissions" in content
        assert "-- Source:" in content

    def test_generate_data_sql_file_strips_annotation(self, release_manager_with_data_patches):
        """Test that @HOP:data annotation is stripped from output."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir, model_dir = release_manager_with_data_patches

        # Create mock data file with annotation
        data_file = patches_dir / "01_roles.sql"
        data_file.write_text("-- @HOP:data\nINSERT INTO roles (name) VALUES ('admin');")

        # Mock patch_manager
        mock_repo.patch_manager._collect_data_files_from_patches.return_value = [data_file]

        # Generate data SQL file
        result = rel_mgr._generate_data_sql_file(["456-auth"], "1.0.0")

        content = result.read_text()
        # First line with annotation should not appear in generated content
        # (it's skipped during concatenation)
        lines = content.split('\n')
        assert not any(line.strip() == "-- @HOP:data" for line in lines)

    def test_generate_data_sql_file_no_data_files(self, release_manager_with_data_patches):
        """Test that no file is generated when there are no data files."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir, model_dir = release_manager_with_data_patches

        # Mock patch_manager to return empty list
        mock_repo.patch_manager._collect_data_files_from_patches.return_value = []

        # Generate data SQL file
        result = rel_mgr._generate_data_sql_file(["456-schema"], "1.0.0")

        assert result is None

    def test_generate_data_sql_file_empty_patch_list(self, release_manager_with_data_patches):
        """Test that no file is generated for empty patch list."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir, model_dir = release_manager_with_data_patches

        # Generate with empty patch list
        result = rel_mgr._generate_data_sql_file([], "1.0.0")

        assert result is None

    def test_generate_data_sql_file_multiple_patches(self, release_manager_with_data_patches):
        """Test generating data SQL file from multiple patches."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir, model_dir = release_manager_with_data_patches

        # Create mock data files from different patches
        data_file1 = patches_dir / "01_roles.sql"
        data_file1.write_text("-- @HOP:data\nINSERT INTO roles (name) VALUES ('admin');")

        data_file2 = patches_dir / "02_permissions.sql"
        data_file2.write_text("-- @HOP:data\nINSERT INTO permissions (name) VALUES ('read');")

        # Mock patch_manager
        mock_repo.patch_manager._collect_data_files_from_patches.return_value = [data_file1, data_file2]

        # Generate data SQL file
        result = rel_mgr._generate_data_sql_file(["456-auth", "457-perms"], "1.0.0")

        content = result.read_text()
        assert "456-auth, 457-perms" in content
        assert "INSERT INTO roles" in content
        assert "INSERT INTO permissions" in content


class TestCollectAllVersionPatches:
    """Test _collect_all_version_patches helper method."""

    def test_collect_base_release_patches(self, release_manager_with_data_patches):
        """Test collecting patches from base release only."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir, model_dir = release_manager_with_data_patches

        # Create base release file
        release_file = releases_dir / "1.0.0.txt"
        release_file.write_text("456-auth\n789-schema\n")

        # Collect patches
        patches = rel_mgr._collect_all_version_patches("1.0.0")

        assert patches == ["456-auth", "789-schema"]

    def test_collect_patches_with_hotfixes(self, release_manager_with_data_patches):
        """Test collecting patches from base release and hotfixes."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir, model_dir = release_manager_with_data_patches

        # Create base release file
        release_file = releases_dir / "1.0.0.txt"
        release_file.write_text("456-auth\n")

        # Create hotfix files
        hotfix1 = releases_dir / "1.0.0-hotfix1.txt"
        hotfix1.write_text("789-fix1\n")

        hotfix2 = releases_dir / "1.0.0-hotfix2.txt"
        hotfix2.write_text("999-fix2\n")

        # Collect patches
        patches = rel_mgr._collect_all_version_patches("1.0.0")

        assert patches == ["456-auth", "789-fix1", "999-fix2"]

    def test_collect_patches_empty_release(self, release_manager_with_data_patches):
        """Test collecting patches from empty release."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir, model_dir = release_manager_with_data_patches

        # Create empty release file
        release_file = releases_dir / "1.0.0.txt"
        release_file.write_text("")

        # Collect patches
        patches = rel_mgr._collect_all_version_patches("1.0.0")

        assert patches == []

    def test_collect_patches_nonexistent_release(self, release_manager_with_data_patches):
        """Test collecting patches from nonexistent release."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir, model_dir = release_manager_with_data_patches

        # No release file created

        # Collect patches
        patches = rel_mgr._collect_all_version_patches("1.0.0")

        assert patches == []


class TestPromoteToProdWithDataFiles:
    """Test promote_to_prod with data file generation."""

    def test_promote_prod_generates_data_file_in_model(self, release_manager_with_data_patches):
        """Test that promote_to_prod generates model/data-X.Y.Z.sql if data exists."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir, model_dir = release_manager_with_data_patches

        # Setup: create stage file with patches
        from half_orm_dev.release_file import ReleaseFile

        release_file = ReleaseFile("1.0.0", releases_dir)
        release_file.create_empty()
        release_file.add_patch("789-data-patch")
        release_file.move_to_staged("789-data-patch", "commit789")

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
        mock_hgit.delete_local_branch = Mock()
        mock_repo.hgit = mock_hgit

        mock_repo.patch_manager._collect_data_files_from_patches.return_value = [data_file]

        # Mock database and other dependencies
        mock_database = Mock()
        mock_database._generate_schema_sql = Mock()
        mock_repo.database = mock_database

        # Mock _get_latest_rc_number and read_release_patches
        rel_mgr._get_latest_rc_number = Mock(return_value=0)
        rel_mgr.read_release_patches = Mock(return_value=["789-data-patch"])

        # Promote to prod
        result = rel_mgr.promote_to_prod()

        # Verify data file was generated in model/ directory
        data_file_path = model_dir / "data-1.0.0.sql"
        assert data_file_path.exists()

        # Verify data file was added to git
        add_calls = [str(call[0][0]) for call in mock_hgit.add.call_args_list]
        assert any("data-1.0.0.sql" in call for call in add_calls)

        # Verify push and sync were called (new workflow uses push + sync instead of commit_and_sync)
        mock_hgit.push_branch.assert_called()
        mock_repo.sync_hop_to_active_branches.assert_called()


class TestPromoteToRCNoDataFile:
    """Test that promote_to_rc does NOT generate data files."""

    def test_promote_rc_does_not_generate_data_file(self, release_manager_with_data_patches):
        """Test that promote_to_rc does not generate data file (data loaded via patches)."""
        rel_mgr, mock_repo, tmp_path, releases_dir, patches_dir, model_dir = release_manager_with_data_patches

        # Setup: create stage file
        from half_orm_dev.release_file import ReleaseFile

        release_file = ReleaseFile("1.0.0", releases_dir)
        release_file.create_empty()
        release_file.add_patch("456-auth")
        release_file.move_to_staged("456-auth", "commit456")

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

        # Verify NO data file was generated in releases/
        data_file_path = releases_dir / "data-1.0.0-rc1.sql"
        assert not data_file_path.exists()

        # Verify NO data file was generated in model/
        data_file_path_model = model_dir / "data-1.0.0-rc1.sql"
        assert not data_file_path_model.exists()
