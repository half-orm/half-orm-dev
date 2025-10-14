"""
Tests for ReleaseManager._determine_rc_number() - RC number calculation.

Focused on testing:
- No existing RCs → returns 1
- Existing rc1 → returns 2
- Existing rc1, rc2 → returns 3
- Gap in numbering → returns max + 1
- Different version RCs ignored
"""

import pytest
from pathlib import Path
from unittest.mock import Mock

from half_orm_dev.release_manager import ReleaseManager, ReleaseManagerError


class TestDetermineRCNumber:
    """Test RC number determination."""

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

    def test_no_existing_rc_returns_one(self, release_manager_basic):
        """Test returns 1 when no RC exists for version."""
        release_mgr, releases_dir = release_manager_basic

        # No RC files exist
        version = "1.3.5"

        rc_number = release_mgr._determine_rc_number(version)

        assert rc_number == 1

    def test_rc1_exists_returns_two(self, release_manager_basic):
        """Test returns 2 when rc1 exists."""
        release_mgr, releases_dir = release_manager_basic

        # Create rc1
        (releases_dir / "1.3.5-rc1.txt").touch()

        version = "1.3.5"

        rc_number = release_mgr._determine_rc_number(version)

        assert rc_number == 2

    def test_rc1_rc2_exist_returns_three(self, release_manager_basic):
        """Test returns 3 when rc1 and rc2 exist."""
        release_mgr, releases_dir = release_manager_basic

        # Create rc1 and rc2
        (releases_dir / "1.3.5-rc1.txt").touch()
        (releases_dir / "1.3.5-rc2.txt").touch()

        version = "1.3.5"

        rc_number = release_mgr._determine_rc_number(version)

        assert rc_number == 3

    def test_multiple_rcs_returns_max_plus_one(self, release_manager_basic):
        """Test returns max RC number + 1."""
        release_mgr, releases_dir = release_manager_basic

        # Create multiple RCs
        (releases_dir / "1.3.5-rc1.txt").touch()
        (releases_dir / "1.3.5-rc2.txt").touch()
        (releases_dir / "1.3.5-rc3.txt").touch()
        (releases_dir / "1.3.5-rc4.txt").touch()

        version = "1.3.5"

        rc_number = release_mgr._determine_rc_number(version)

        assert rc_number == 5

    def test_ignores_different_version_rcs(self, release_manager_basic):
        """Test ignores RC files of different versions."""
        release_mgr, releases_dir = release_manager_basic

        # Create RCs for different versions
        (releases_dir / "1.3.4-rc1.txt").touch()
        (releases_dir / "1.3.4-rc2.txt").touch()
        (releases_dir / "1.4.0-rc1.txt").touch()

        # Check version with no RCs
        version = "1.3.5"

        rc_number = release_mgr._determine_rc_number(version)

        # Should return 1 (other versions ignored)
        assert rc_number == 1

    def test_ignores_different_version_same_prefix(self, release_manager_basic):
        """Test correctly distinguishes versions with same prefix."""
        release_mgr, releases_dir = release_manager_basic

        # Create RCs for version with same prefix
        (releases_dir / "1.3.5-rc1.txt").touch()
        (releases_dir / "1.3.50-rc1.txt").touch()  # Different version (1.3.50)

        version = "1.3.5"

        rc_number = release_mgr._determine_rc_number(version)

        # Should return 2 (only count 1.3.5-rc1)
        assert rc_number == 2

    def test_handles_double_digit_rc_numbers(self, release_manager_basic):
        """Test handles RC numbers >= 10."""
        release_mgr, releases_dir = release_manager_basic

        # Create many RCs
        for i in range(1, 15):
            (releases_dir / f"1.3.5-rc{i}.txt").touch()

        version = "1.3.5"

        rc_number = release_mgr._determine_rc_number(version)

        assert rc_number == 15

    def test_out_of_order_rc_files_returns_max(self, release_manager_basic):
        """Test returns max even if RC files created out of order."""
        release_mgr, releases_dir = release_manager_basic

        # Create RCs in non-sequential order
        (releases_dir / "1.3.5-rc3.txt").touch()
        (releases_dir / "1.3.5-rc1.txt").touch()
        (releases_dir / "1.3.5-rc5.txt").touch()
        (releases_dir / "1.3.5-rc2.txt").touch()

        version = "1.3.5"

        rc_number = release_mgr._determine_rc_number(version)

        # Should return 6 (max=5, +1)
        assert rc_number == 6

    def test_gap_in_rc_numbering(self, release_manager_basic):
        """Test handles gaps in RC numbering (e.g., rc1, rc3, rc5)."""
        release_mgr, releases_dir = release_manager_basic

        # Create RCs with gaps (shouldn't happen, but handle it)
        (releases_dir / "1.3.5-rc1.txt").touch()
        (releases_dir / "1.3.5-rc3.txt").touch()
        (releases_dir / "1.3.5-rc5.txt").touch()

        version = "1.3.5"

        rc_number = release_mgr._determine_rc_number(version)

        # Should return 6 (max=5, +1, doesn't fill gaps)
        assert rc_number == 6

    def test_ignores_non_rc_files(self, release_manager_basic):
        """Test ignores non-RC files."""
        release_mgr, releases_dir = release_manager_basic

        # Create various non-RC files
        (releases_dir / "1.3.5-stage.txt").touch()
        (releases_dir / "1.3.5.txt").touch()  # Production
        (releases_dir / "1.3.5-hotfix1.txt").touch()
        (releases_dir / "README.md").touch()

        version = "1.3.5"

        rc_number = release_mgr._determine_rc_number(version)

        # Should return 1 (no RCs found)
        assert rc_number == 1

    def test_different_versions_independent(self, release_manager_basic):
        """Test RC numbering is independent per version."""
        release_mgr, releases_dir = release_manager_basic

        # Version 1.3.5 has rc1, rc2
        (releases_dir / "1.3.5-rc1.txt").touch()
        (releases_dir / "1.3.5-rc2.txt").touch()

        # Version 1.4.0 has rc1
        (releases_dir / "1.4.0-rc1.txt").touch()

        # Check 1.3.5 → should be 3
        assert release_mgr._determine_rc_number("1.3.5") == 3

        # Check 1.4.0 → should be 2
        assert release_mgr._determine_rc_number("1.4.0") == 2

        # Check new version → should be 1
        assert release_mgr._determine_rc_number("1.5.0") == 1

    def test_uses_get_rc_files_method(self, release_manager_basic):
        """Test uses existing get_rc_files() method."""
        release_mgr, releases_dir = release_manager_basic

        # Create RCs
        (releases_dir / "1.3.5-rc1.txt").touch()
        (releases_dir / "1.3.5-rc2.txt").touch()

        version = "1.3.5"

        # Should use get_rc_files() which returns sorted list
        rc_files = release_mgr.get_rc_files(version)
        
        # get_rc_files() returns Path objects sorted by RC number
        assert len(rc_files) == 2
        
        # _determine_rc_number should return len + 1
        rc_number = release_mgr._determine_rc_number(version)
        assert rc_number == 3
