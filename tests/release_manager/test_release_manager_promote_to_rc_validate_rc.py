"""
Tests for ReleaseManager._validate_single_active_rc() - Single active RC rule.

Focused on testing the single active RC rule:
- No RC exists → OK
- Same version RC exists → OK (rc1 → rc2)
- Different version RC exists → ERROR
- Multiple RCs of same version → OK
"""

import pytest
from pathlib import Path
from unittest.mock import Mock

from half_orm_dev.release_manager import ReleaseManager, ReleaseManagerError


class TestValidateSingleActiveRC:
    """Test single active RC validation."""

    @pytest.fixture
    def release_manager_basic(self, tmp_path):
        """Create basic ReleaseManager with releases/ directory."""
        mock_repo = Mock()
        mock_repo.base_dir = str(tmp_path)

        # Create releases/ directory
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_mgr = ReleaseManager(mock_repo)

        return release_mgr, releases_dir

    def test_no_rc_exists_allows_promotion(self, release_manager_basic):
        """Test promotion allowed when no RC exists."""
        release_mgr, releases_dir = release_manager_basic

        # No RC files exist
        stage_version = "1.3.5"

        # Should not raise error
        release_mgr._validate_single_active_rc(stage_version)

    def test_same_version_rc_exists_allows_promotion(self, release_manager_basic):
        """Test promotion allowed when same version RC exists (rc1 → rc2)."""
        release_mgr, releases_dir = release_manager_basic

        # Create RC of same version
        (releases_dir / "1.3.5-rc1.txt").touch()

        stage_version = "1.3.5"

        # Should not raise error (promoting to rc2)
        release_mgr._validate_single_active_rc(stage_version)

    def test_different_version_rc_blocks_promotion(self, release_manager_basic):
        """Test error when different version RC exists."""
        release_mgr, releases_dir = release_manager_basic

        # Create RC of different version
        (releases_dir / "1.3.5-rc1.txt").touch()

        stage_version = "1.4.0"

        # Should raise error
        with pytest.raises(ReleaseManagerError, match="Cannot promote.*1.4.0.*1.3.5-rc1.*must be deployed"):
            release_mgr._validate_single_active_rc(stage_version)

    def test_multiple_rcs_same_version_allows_promotion(self, release_manager_basic):
        """Test promotion allowed with multiple RCs of same version (rc2 → rc3)."""
        release_mgr, releases_dir = release_manager_basic

        # Create multiple RCs of same version
        (releases_dir / "1.3.5-rc1.txt").touch()
        (releases_dir / "1.3.5-rc2.txt").touch()

        stage_version = "1.3.5"

        # Should not raise error (promoting to rc3)
        release_mgr._validate_single_active_rc(stage_version)

    def test_patch_vs_minor_version_blocks(self, release_manager_basic):
        """Test patch version RC blocks minor version promotion."""
        release_mgr, releases_dir = release_manager_basic

        # RC for patch version
        (releases_dir / "1.3.5-rc1.txt").touch()

        # Try to promote minor version
        stage_version = "1.4.0"

        with pytest.raises(ReleaseManagerError, match="1.3.5-rc1.*must be deployed"):
            release_mgr._validate_single_active_rc(stage_version)

    def test_minor_vs_major_version_blocks(self, release_manager_basic):
        """Test minor version RC blocks major version promotion."""
        release_mgr, releases_dir = release_manager_basic

        # RC for minor version
        (releases_dir / "1.4.0-rc1.txt").touch()

        # Try to promote major version
        stage_version = "2.0.0"

        with pytest.raises(ReleaseManagerError, match="1.4.0-rc1.*must be deployed"):
            release_mgr._validate_single_active_rc(stage_version)

    def test_lower_version_stage_blocked_by_higher_rc(self, release_manager_basic):
        """Test that even lower version is blocked if different RC exists."""
        release_mgr, releases_dir = release_manager_basic

        # RC for version 1.4.0
        (releases_dir / "1.4.0-rc1.txt").touch()

        # Try to promote lower version 1.3.5
        # (This scenario: 1.4.0 was promoted first, now want to add 1.3.5)
        stage_version = "1.3.5"

        with pytest.raises(ReleaseManagerError, match="1.4.0-rc1.*must be deployed"):
            release_mgr._validate_single_active_rc(stage_version)

    def test_error_message_includes_rc_version(self, release_manager_basic):
        """Test error message includes the blocking RC version."""
        release_mgr, releases_dir = release_manager_basic

        # Create RC
        (releases_dir / "1.3.5-rc1.txt").touch()

        stage_version = "1.4.0"

        # Verify error message format
        with pytest.raises(ReleaseManagerError) as exc_info:
            release_mgr._validate_single_active_rc(stage_version)

        error_msg = str(exc_info.value)
        assert "1.4.0" in error_msg  # Stage version being promoted
        assert "1.3.5" in error_msg  # Blocking RC version
        assert "rc1" in error_msg or "RC" in error_msg

    def test_multiple_different_rc_versions_reports_first(self, release_manager_basic):
        """Test that if multiple different RCs exist, reports one of them."""
        release_mgr, releases_dir = release_manager_basic

        # Create multiple RCs of different versions (edge case, shouldn't happen)
        (releases_dir / "1.3.5-rc1.txt").touch()
        (releases_dir / "1.4.0-rc1.txt").touch()  # Both exist somehow

        stage_version = "2.0.0"

        # Should raise error mentioning at least one of the RCs
        with pytest.raises(ReleaseManagerError, match="rc.*must be deployed"):
            release_mgr._validate_single_active_rc(stage_version)
