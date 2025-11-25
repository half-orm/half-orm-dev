"""
Tests for ReleaseManager.update_production() - Advanced scenarios.

Focused on testing:
- Upgrade path calculation
- Multiple releases
- Release type detection (production, rc, hotfix)
- Result formatting with patch counts
"""

import pytest
from pathlib import Path
from unittest.mock import Mock

from half_orm_dev.release_manager import ReleaseManager


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def release_manager_with_releases(tmp_path):
    """
    Setup ReleaseManager with multiple release files.

    Provides:
    - Release files: 1.3.6.txt, 1.3.7.txt, 1.4.0.txt
    - Current production version: 1.3.5
    """
    # Create releases directory
    releases_dir = tmp_path / "releases"
    releases_dir.mkdir(exist_ok=True)

    # Create release files with patches
    (releases_dir / "1.3.6.txt").write_text("456-user-auth\n789-security\n")
    (releases_dir / "1.3.7.txt").write_text("999-bugfix\n")
    (releases_dir / "1.4.0.txt").write_text("111-feature-a\n222-feature-b\n333-feature-c\n")

    # Mock Repo
    mock_repo = Mock()
    mock_repo.name = "test_repo"
    mock_repo.base_dir = tmp_path

    # Mock Database
    mock_database = Mock()
    mock_database.last_release_s = "1.3.5"
    mock_repo.database = mock_database

    # Mock HGit
    mock_hgit = Mock()
    mock_hgit.fetch_tags = Mock()
    mock_repo.hgit = mock_hgit

    # Create ReleaseManager
    release_mgr = ReleaseManager(mock_repo)

    return release_mgr, mock_repo, mock_hgit, releases_dir


# ============================================================================
# UPGRADE PATH CALCULATION TESTS
# ============================================================================

class TestUpdateProductionUpgradePath:
    """Test upgrade path calculation."""

    def test_calculates_sequential_upgrade_path(self, release_manager_with_releases):
        """Test calculates path for multi-version upgrade."""
        release_mgr, mock_repo, mock_hgit, _ = release_manager_with_releases

        # Mock tags: v1.3.6, v1.3.7, v1.4.0
        mock_tag_v136 = Mock()
        mock_tag_v136.name = "v1.3.6"
        mock_tag_v137 = Mock()
        mock_tag_v137.name = "v1.3.7"
        mock_tag_v140 = Mock()
        mock_tag_v140.name = "v1.4.0"

        mock_hgit._HGit__git_repo = Mock()
        mock_hgit._HGit__git_repo.tags = [mock_tag_v136, mock_tag_v137, mock_tag_v140]

        # Call update_production
        result = release_mgr.update_production()

        # Should calculate sequential path: 1.3.5 → 1.3.6 → 1.3.7 → 1.4.0
        assert result['upgrade_path'] == ["1.3.6", "1.3.7", "1.4.0"]

    def test_direct_upgrade_single_version(self, release_manager_with_releases):
        """Test direct upgrade to next version only."""
        release_mgr, mock_repo, mock_hgit, releases_dir = release_manager_with_releases

        # Create single release file
        (releases_dir / "1.3.6.txt").write_text("456-patch\n")

        # Mock single tag
        mock_tag = Mock()
        mock_tag.name = "v1.3.6"
        mock_hgit._HGit__git_repo = Mock()
        mock_hgit._HGit__git_repo.tags = [mock_tag]

        # Call update_production
        result = release_mgr.update_production()

        # Should have single-step path
        assert result['upgrade_path'] == ["1.3.6"]

    def test_upgrade_path_skips_missing_versions(self, release_manager_with_releases):
        """Test upgrade path only includes versions with tags."""
        release_mgr, mock_repo, mock_hgit, releases_dir = release_manager_with_releases

        # Create release file 1.3.8 but no tag for it
        (releases_dir / "1.3.8.txt").write_text("888-missing\n")

        # Mock tags: v1.3.6, v1.4.0 (missing v1.3.7, v1.3.8)
        mock_tag_v136 = Mock()
        mock_tag_v136.name = "v1.3.6"
        mock_tag_v140 = Mock()
        mock_tag_v140.name = "v1.4.0"

        mock_hgit._HGit__git_repo = Mock()
        mock_hgit._HGit__git_repo.tags = [mock_tag_v136, mock_tag_v140]

        # Call update_production
        result = release_mgr.update_production()

        # Should only include tagged versions
        assert result['upgrade_path'] == ["1.3.6", "1.4.0"]


# ============================================================================
# MULTIPLE RELEASES TESTS
# ============================================================================

class TestUpdateProductionMultipleReleases:
    """Test with multiple available releases."""

    def test_lists_all_available_releases(self, release_manager_with_releases):
        """Test lists all releases with details."""
        release_mgr, mock_repo, mock_hgit, _ = release_manager_with_releases

        # Mock tags
        mock_tag_v136 = Mock()
        mock_tag_v136.name = "v1.3.6"
        mock_tag_v137 = Mock()
        mock_tag_v137.name = "v1.3.7"
        mock_tag_v140 = Mock()
        mock_tag_v140.name = "v1.4.0"

        mock_hgit._HGit__git_repo = Mock()
        mock_hgit._HGit__git_repo.tags = [mock_tag_v136, mock_tag_v137, mock_tag_v140]

        # Call update_production
        result = release_mgr.update_production()

        # Should list all releases
        assert len(result['available_releases']) == 3
        versions = [rel['version'] for rel in result['available_releases']]
        assert "1.3.6" in versions
        assert "1.3.7" in versions
        assert "1.4.0" in versions

    def test_includes_patch_counts_in_releases(self, release_manager_with_releases):
        """Test each release includes patch count."""
        release_mgr, mock_repo, mock_hgit, _ = release_manager_with_releases

        # Mock tags
        mock_tag_v136 = Mock()
        mock_tag_v136.name = "v1.3.6"
        mock_tag_v140 = Mock()
        mock_tag_v140.name = "v1.4.0"

        mock_hgit._HGit__git_repo = Mock()
        mock_hgit._HGit__git_repo.tags = [mock_tag_v136, mock_tag_v140]

        # Call update_production
        result = release_mgr.update_production()

        # Find releases
        rel_136 = next(r for r in result['available_releases'] if r['version'] == '1.3.6')
        rel_140 = next(r for r in result['available_releases'] if r['version'] == '1.4.0')

        # Verify patch counts
        assert len(rel_136['patches']) == 2  # 456-user-auth, 789-security
        assert len(rel_140['patches']) == 3  # 111-feature-a, 222-feature-b, 333-feature-c


# ============================================================================
# RELEASE TYPE DETECTION TESTS
# ============================================================================

class TestUpdateProductionReleaseTypes:
    """Test release type detection (production, rc, hotfix)."""

    def test_detects_production_release_type(self, release_manager_with_releases):
        """Test identifies production releases correctly."""
        release_mgr, mock_repo, mock_hgit, releases_dir = release_manager_with_releases

        # Create release file
        (releases_dir / "1.3.6.txt").write_text("456-patch\n")

        # Mock production tag
        mock_tag = Mock()
        mock_tag.name = "v1.3.6"
        mock_hgit._HGit__git_repo = Mock()
        mock_hgit._HGit__git_repo.tags = [mock_tag]

        # Call update_production
        result = release_mgr.update_production()

        # Should detect as production
        release = result['available_releases'][0]
        assert release['type'] == 'production'

    def test_detects_rc_release_type(self, release_manager_with_releases):
        """Test identifies RC releases correctly."""
        release_mgr, mock_repo, mock_hgit, releases_dir = release_manager_with_releases

        # Create RC release file
        (releases_dir / "1.3.6-rc1.txt").write_text("456-patch\n")

        # Mock RC tag
        mock_tag = Mock()
        mock_tag.name = "v1.3.6-rc1"
        mock_hgit._HGit__git_repo = Mock()
        mock_hgit._HGit__git_repo.tags = [mock_tag]

        # Call with allow_rc=True
        mock_repo.allow_rc = True
        result = release_mgr.update_production()

        # Should detect as rc
        release = result['available_releases'][0]
        assert release['type'] == 'rc'

    @pytest.mark.skip(reason="Hotfix type detection not implemented yet")
    def test_detects_hotfix_release_type(self, release_manager_with_releases):
        """Test identifies hotfix releases correctly."""
        release_mgr, mock_repo, mock_hgit, releases_dir = release_manager_with_releases

        # Create hotfix release file
        (releases_dir / "1.3.5-hotfix1.txt").write_text("999-critical\n")

        # Mock hotfix tag
        mock_tag = Mock()
        mock_tag.name = "v1.3.5-hotfix1"
        mock_hgit._HGit__git_repo = Mock()
        mock_hgit._HGit__git_repo.tags = [mock_tag]

        # Call update_production
        result = release_mgr.update_production()

        # Should detect as hotfix
        release = result['available_releases'][0]
        assert release['type'] == 'hotfix'
