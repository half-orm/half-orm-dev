"""
Tests for ReleaseManager.upgrade_production() - Sequential upgrades.

Focused on testing:
- Multi-version sequential application
- Upgrade path calculation
- Patch ordering across releases
- Database version progression
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, call
from half_orm_dev.release_manager import ReleaseManager


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def release_manager_multi_version(tmp_path):
    """
    Setup ReleaseManager with multiple versions for sequential upgrade.

    Provides:
    - Releases: 1.3.6, 1.3.7, 1.4.0
    - Current version: 1.3.5
    - Multiple patches per release
    """
    # Create directories
    releases_dir = tmp_path / ".hop" / "releases"
    releases_dir.mkdir(parents=True, exist_ok=True)

    backups_dir = tmp_path / "backups"
    backups_dir.mkdir()

    # Create multiple release files
    (releases_dir / "1.3.6.txt").write_text("456-user-auth\n789-security\n")
    (releases_dir / "1.3.7.txt").write_text("999-bugfix\n")
    (releases_dir / "1.4.0.txt").write_text("111-feature-a\n222-feature-b\n333-feature-c\n")

    # Mock Repo
    mock_repo = Mock()
    mock_repo.name = "test_db"
    mock_repo.base_dir = tmp_path
    mock_repo.releases_dir = str(releases_dir)
    mock_repo.model_dir = str(tmp_path / ".hop" / "model")

    # Mock Database
    mock_database = Mock()
    mock_database.name = "test_db"
    mock_database.last_release_s = "1.3.5"
    mock_database.execute_pg_command = Mock()
    mock_database.register_release = Mock()
    mock_repo.database = mock_database

    # Mock HGit
    mock_hgit = Mock()
    mock_hgit.branch = "ho-prod"
    mock_hgit.repos_is_clean = Mock(return_value=True)
    mock_hgit.fetch_tags = Mock()

    # Mock tags for all releases
    mock_tag_136 = Mock()
    mock_tag_136.name = "v1.3.6"
    mock_tag_137 = Mock()
    mock_tag_137.name = "v1.3.7"
    mock_tag_140 = Mock()
    mock_tag_140.name = "v1.4.0"

    mock_hgit._HGit__git_repo = Mock()
    mock_hgit._HGit__git_repo.tags = [mock_tag_136, mock_tag_137, mock_tag_140]

    mock_repo.hgit = mock_hgit

    # Mock PatchManager
    mock_patch_manager = Mock()
    mock_patch_manager.apply_patch_files = Mock()
    mock_repo.patch_manager = mock_patch_manager

    # Create ReleaseManager
    release_mgr = ReleaseManager(mock_repo)

    return release_mgr, mock_repo, tmp_path, releases_dir


# ============================================================================
# SEQUENTIAL UPGRADE TESTS
# ============================================================================

class TestUpgradeProductionSequential:
    """Test multi-version sequential upgrades."""

    def test_applies_all_versions_sequentially(self, release_manager_multi_version):
        """Test upgrades through all versions: 1.3.5 → 1.3.6 → 1.3.7 → 1.4.0."""
        release_mgr, mock_repo, _, _ = release_manager_multi_version

        # Execute full upgrade
        result = release_mgr.upgrade_production(skip_backup=True)

        # Should apply all releases in order
        assert result['status'] == 'success'
        assert result['releases_applied'] == ['1.3.6', '1.3.7', '1.4.0']
        assert result['final_version'] == '1.4.0'

    def test_applies_patches_from_all_releases(self, release_manager_multi_version):
        """Test all patches from all releases are applied."""
        release_mgr, mock_repo, _, _ = release_manager_multi_version

        # Execute full upgrade
        result = release_mgr.upgrade_production(skip_backup=True)

        # Should have patches from all releases
        assert result['patches_applied'] == {
            '1.3.6': ['456-user-auth', '789-security'],
            '1.3.7': ['999-bugfix'],
            '1.4.0': ['111-feature-a', '222-feature-b', '333-feature-c']
        }

    def test_patch_application_order_across_releases(self, release_manager_multi_version):
        """Test patches applied in correct order across all releases."""
        release_mgr, mock_repo, _, _ = release_manager_multi_version

        # Execute full upgrade
        release_mgr.upgrade_production(skip_backup=True)

        # Verify apply_patch_files called in correct order
        # Total: 2 + 1 + 3 = 6 patches
        assert mock_repo.patch_manager.apply_patch_files.call_count == 6

        calls = mock_repo.patch_manager.apply_patch_files.call_args_list

        # Release 1.3.6
        assert calls[0][0][0] == '456-user-auth'
        assert calls[1][0][0] == '789-security'

        # Release 1.3.7
        assert calls[2][0][0] == '999-bugfix'

        # Release 1.4.0
        assert calls[3][0][0] == '111-feature-a'
        assert calls[4][0][0] == '222-feature-b'
        assert calls[5][0][0] == '333-feature-c'

    def test_database_version_updated_after_each_release(self, release_manager_multi_version):
        """Test database version updated after each release, not just at end."""
        release_mgr, mock_repo, _, _ = release_manager_multi_version

        # Execute full upgrade
        release_mgr.upgrade_production(skip_backup=True)

        # Should call register_release for each version
        assert mock_repo.database.register_release.call_count == 3

        calls = mock_repo.database.register_release.call_args_list

        # Version 1.3.6
        assert calls[0] == call(1, 3, 6)

        # Version 1.3.7
        assert calls[1] == call(1, 3, 7)

        # Version 1.4.0
        assert calls[2] == call(1, 4, 0)


# ============================================================================
# UPGRADE PATH TESTS
# ============================================================================

class TestUpgradeProductionPath:
    """Test upgrade path calculation and execution."""

    def test_upgrade_path_from_update_production(self, release_manager_multi_version):
        """Test uses upgrade_path from update_production()."""
        release_mgr, mock_repo, _, _ = release_manager_multi_version

        # Execute upgrade
        result = release_mgr.upgrade_production(skip_backup=True)

        # Should follow calculated upgrade path
        assert result['releases_applied'] == ['1.3.6', '1.3.7', '1.4.0']

    def test_sequential_upgrade_no_version_skipping(self, release_manager_multi_version):
        """Test cannot skip versions in upgrade path."""
        release_mgr, mock_repo, tmp_path, releases_dir = release_manager_multi_version

        # Even if 1.4.0 exists, must go through 1.3.6 and 1.3.7
        result = release_mgr.upgrade_production(skip_backup=True)

        # Should apply all intermediate versions
        assert '1.3.6' in result['releases_applied']
        assert '1.3.7' in result['releases_applied']
        assert '1.4.0' in result['releases_applied']

    def test_upgrade_respects_version_ordering(self, release_manager_multi_version):
        """Test versions applied in correct semantic order."""
        release_mgr, mock_repo, tmp_path, releases_dir = release_manager_multi_version

        # Add version 1.3.8 (should come after 1.3.7, before 1.4.0)
        (releases_dir / "1.3.8.txt").write_text("888-late-patch\n")

        mock_tag_138 = Mock()
        mock_tag_138.name = "v1.3.8"
        mock_repo.hgit._HGit__git_repo.tags.append(mock_tag_138)

        # Execute upgrade
        result = release_mgr.upgrade_production(skip_backup=True)

        # Should apply in semantic version order
        expected_order = ['1.3.6', '1.3.7', '1.3.8', '1.4.0']
        assert result['releases_applied'] == expected_order


# ============================================================================
# PARTIAL PROGRESS TESTS
# ============================================================================

class TestUpgradeProductionPartialProgress:
    """Test upgrade with partial progress (starting mid-path)."""

    def test_starts_from_current_version(self, release_manager_multi_version):
        """Test upgrade starts from current database version."""
        release_mgr, mock_repo, _, _ = release_manager_multi_version

        # Set current version to 1.3.6 (already upgraded once)
        mock_repo.database.last_release_s = "1.3.6"

        # Execute upgrade
        result = release_mgr.upgrade_production(skip_backup=True)

        # Should only apply remaining versions
        assert result['current_version'] == '1.3.6'
        assert result['releases_applied'] == ['1.3.7', '1.4.0']
        assert result['final_version'] == '1.4.0'

    def test_skips_already_applied_versions(self, release_manager_multi_version):
        """Test doesn't re-apply already applied versions."""
        release_mgr, mock_repo, _, _ = release_manager_multi_version

        # Set current version to 1.3.7
        mock_repo.database.last_release_s = "1.3.7"

        # Execute upgrade
        result = release_mgr.upgrade_production(skip_backup=True)

        # Should only apply 1.4.0
        assert result['releases_applied'] == ['1.4.0']

        # Should NOT call patches from 1.3.6 or 1.3.7
        calls = mock_repo.patch_manager.apply_patch_files.call_args_list
        patch_ids = [call[0][0] for call in calls]

        assert '456-user-auth' not in patch_ids  # From 1.3.6
        assert '789-security' not in patch_ids   # From 1.3.6
        assert '999-bugfix' not in patch_ids     # From 1.3.7

        assert '111-feature-a' in patch_ids      # From 1.4.0
        assert '222-feature-b' in patch_ids      # From 1.4.0
        assert '333-feature-c' in patch_ids      # From 1.4.0


# ============================================================================
# COMPLEX SCENARIOS TESTS
# ============================================================================

class TestUpgradeProductionComplexScenarios:
    """Test complex upgrade scenarios."""

    def test_many_sequential_versions(self, tmp_path):
        """Test upgrade through many versions (stress test)."""
        # Create 10 sequential versions: 1.3.5 → 1.3.6 → ... → 1.3.14
        releases_dir = tmp_path / ".hop" / "releases"
        releases_dir.mkdir(parents=True, exist_ok=True)

        for i in range(6, 15):
            (releases_dir / f"1.3.{i}.txt").write_text(f"{i}00-patch\n")

        # Mock Repo
        mock_repo = Mock()
        mock_repo.name = "test_db"
        mock_repo.base_dir = tmp_path
        mock_repo.releases_dir = str(releases_dir)
        mock_repo.model_dir = str(tmp_path / ".hop" / "model")
        mock_database = Mock()
        mock_database.name = "test_db"
        mock_database.last_release_s = "1.3.5"
        mock_database.execute_pg_command = Mock()
        mock_database.register_release = Mock()
        mock_repo.database = mock_database

        # Mock HGit with all tags
        mock_hgit = Mock()
        mock_hgit.branch = "ho-prod"
        mock_hgit.repos_is_clean = Mock(return_value=True)
        mock_hgit.fetch_tags = Mock()

        tags = []
        for i in range(6, 15):
            tag = Mock()
            tag.name = f"v1.3.{i}"
            tags.append(tag)

        mock_hgit._HGit__git_repo = Mock()
        mock_hgit._HGit__git_repo.tags = tags
        mock_repo.hgit = mock_hgit

        mock_patch_manager = Mock()
        mock_patch_manager.apply_patch_files = Mock()
        mock_repo.patch_manager = mock_patch_manager

        # Create ReleaseManager
        release_mgr = ReleaseManager(mock_repo)

        # Execute upgrade
        result = release_mgr.upgrade_production(skip_backup=True)

        # Should apply all 9 versions
        assert len(result['releases_applied']) == 9
        assert result['final_version'] == '1.3.14'

    def test_major_version_upgrade(self, release_manager_multi_version):
        """Test upgrade across major version boundary."""
        release_mgr, mock_repo, tmp_path, releases_dir = release_manager_multi_version

        # Add 2.0.0 release
        (releases_dir / "2.0.0.txt").write_text("1000-breaking-change\n")

        mock_tag_200 = Mock()
        mock_tag_200.name = "v2.0.0"
        mock_repo.hgit._HGit__git_repo.tags.append(mock_tag_200)

        # Execute upgrade
        result = release_mgr.upgrade_production(skip_backup=True)

        # Should upgrade through major version
        assert result['releases_applied'] == ['1.3.6', '1.3.7', '1.4.0', '2.0.0']
        assert result['final_version'] == '2.0.0'
