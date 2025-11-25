"""
Tests for ReleaseManager.find_latest_version() method.

Focused on testing:
- No release files (returns None)
- Single release file
- Multiple releases with version sorting
- Stage priority (production > rc > stage > hotfix for same base version)
- Mixed versions and stages
"""

import pytest
from pathlib import Path
from unittest.mock import Mock

from half_orm_dev.release_manager import ReleaseManager, ReleaseFileError, Version


class TestReleaseManagerFindLatest:
    """Test find_latest_version() method."""

    @pytest.fixture
    def release_manager_with_files(self, tmp_path):
        """Create ReleaseManager with releases/ directory."""
        mock_repo = Mock()
        mock_repo.base_dir = str(tmp_path)

        # Create releases/ directory
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir(exist_ok=True)

        release_mgr = ReleaseManager(mock_repo)

        return release_mgr, releases_dir

    def test_no_release_files_returns_none(self, release_manager_with_files):
        """Test returns None when no release files exist."""
        release_mgr, releases_dir = release_manager_with_files

        # Empty releases/ directory
        result = release_mgr.find_latest_version()

        assert result is None

    def test_single_production_release(self, release_manager_with_files):
        """Test with single production release file."""
        release_mgr, releases_dir = release_manager_with_files

        # Create single release file
        (releases_dir / "1.3.5.txt").touch()

        result = release_mgr.find_latest_version()

        assert result.major == 1
        assert result.minor == 3
        assert result.patch == 5
        assert result.stage is None

    def test_single_stage_release(self, release_manager_with_files):
        """Test with single stage release file."""
        release_mgr, releases_dir = release_manager_with_files

        (releases_dir / "1.4.0-stage.txt").touch()

        result = release_mgr.find_latest_version()

        assert result.major == 1
        assert result.minor == 4
        assert result.patch == 0
        assert result.stage == "stage"

    def test_multiple_production_releases_returns_latest(self, release_manager_with_files):
        """Test returns highest version among multiple production releases."""
        release_mgr, releases_dir = release_manager_with_files

        (releases_dir / "1.3.4.txt").touch()
        (releases_dir / "1.3.5.txt").touch()
        (releases_dir / "1.3.3.txt").touch()

        result = release_mgr.find_latest_version()

        assert result.major == 1
        assert result.minor == 3
        assert result.patch == 5
        assert result.stage is None

    def test_version_sorting_major_takes_precedence(self, release_manager_with_files):
        """Test version sorting: major version takes precedence."""
        release_mgr, releases_dir = release_manager_with_files

        (releases_dir / "1.9.9.txt").touch()
        (releases_dir / "2.0.0.txt").touch()
        (releases_dir / "1.10.10.txt").touch()

        result = release_mgr.find_latest_version()

        assert result.major == 2
        assert result.minor == 0
        assert result.patch == 0

    def test_version_sorting_minor_takes_precedence(self, release_manager_with_files):
        """Test version sorting: minor version takes precedence over patch."""
        release_mgr, releases_dir = release_manager_with_files

        (releases_dir / "1.3.99.txt").touch()
        (releases_dir / "1.4.0.txt").touch()
        (releases_dir / "1.3.100.txt").touch()

        result = release_mgr.find_latest_version()

        assert result.major == 1
        assert result.minor == 4
        assert result.patch == 0

    def test_stage_priority_production_over_rc(self, release_manager_with_files):
        """Test stage priority: production > rc for same version."""
        release_mgr, releases_dir = release_manager_with_files

        (releases_dir / "1.3.5-rc2.txt").touch()
        (releases_dir / "1.3.5.txt").touch()

        result = release_mgr.find_latest_version()

        # Production should win
        assert result.major == 1
        assert result.minor == 3
        assert result.patch == 5
        assert result.stage is None

    def test_stage_priority_rc_over_stage(self, release_manager_with_files):
        """Test stage priority: rc > stage for same version."""
        release_mgr, releases_dir = release_manager_with_files

        (releases_dir / "1.3.5-stage.txt").touch()
        (releases_dir / "1.3.5-rc1.txt").touch()

        result = release_mgr.find_latest_version()

        # RC should win
        assert result.major == 1
        assert result.minor == 3
        assert result.patch == 5
        assert result.stage == "rc1"

    def test_stage_priority_stage_over_hotfix(self, release_manager_with_files):
        """Test stage priority: stage > hotfix for same version."""
        release_mgr, releases_dir = release_manager_with_files

        (releases_dir / "1.3.5-hotfix1.txt").touch()
        (releases_dir / "1.3.5-stage.txt").touch()

        result = release_mgr.find_latest_version()

        # Stage should win
        assert result.major == 1
        assert result.minor == 3
        assert result.patch == 5
        assert result.stage == "stage"

    def test_higher_rc_number_wins(self, release_manager_with_files):
        """Test among RCs, higher number wins."""
        release_mgr, releases_dir = release_manager_with_files

        (releases_dir / "1.3.5-rc1.txt").touch()
        (releases_dir / "1.3.5-rc3.txt").touch()
        (releases_dir / "1.3.5-rc2.txt").touch()

        result = release_mgr.find_latest_version()

        assert result.major == 1
        assert result.minor == 3
        assert result.patch == 5
        assert result.stage == "rc3"

    def test_mixed_versions_and_stages(self, release_manager_with_files):
        """Test complex scenario with mixed versions and stages."""
        release_mgr, releases_dir = release_manager_with_files

        # Create various releases
        (releases_dir / "1.3.4.txt").touch()        # Old production
        (releases_dir / "1.3.5-rc2.txt").touch()    # Current RC
        (releases_dir / "1.3.5-stage.txt").touch()  # Current stage
        (releases_dir / "1.4.0-stage.txt").touch()  # Future stage

        result = release_mgr.find_latest_version()

        # 1.4.0-stage should win (highest base version)
        assert result.major == 1
        assert result.minor == 4
        assert result.patch == 0
        assert result.stage == "stage"

    def test_ignores_non_txt_files(self, release_manager_with_files):
        """Test ignores files without .txt extension."""
        release_mgr, releases_dir = release_manager_with_files

        (releases_dir / "1.3.5.txt").touch()
        (releases_dir / "1.3.6.sql").touch()     # Should be ignored
        (releases_dir / "1.3.7.md").touch()      # Should be ignored
        (releases_dir / "README.txt").touch()    # Invalid format, ignored

        result = release_mgr.find_latest_version()

        assert result.major == 1
        assert result.minor == 3
        assert result.patch == 5

    def test_ignores_invalid_format_files(self, release_manager_with_files):
        """Test ignores files with invalid version format."""
        release_mgr, releases_dir = release_manager_with_files

        (releases_dir / "1.3.5.txt").touch()
        (releases_dir / "invalid.txt").touch()
        (releases_dir / "1.2.txt").touch()       # Missing patch

        result = release_mgr.find_latest_version()

        assert result.major == 1
        assert result.minor == 3
        assert result.patch == 5

    def test_with_hotfix_releases(self, release_manager_with_files):
        """Test with hotfix releases in mix."""
        release_mgr, releases_dir = release_manager_with_files

        (releases_dir / "1.3.4.txt").touch()
        (releases_dir / "1.3.4-hotfix1.txt").touch()
        (releases_dir / "1.3.4-hotfix2.txt").touch()

        result = release_mgr.find_latest_version()

        # Production 1.3.4 should win over hotfixes
        assert result.major == 1
        assert result.minor == 3
        assert result.patch == 4
        assert result.stage is None

    def test_releases_directory_not_exists(self, tmp_path):
        """Test error when releases/ directory doesn't exist."""
        mock_repo = Mock()
        mock_repo.base_dir = str(tmp_path)

        # Don't create releases/ directory
        release_mgr = ReleaseManager(mock_repo)

        with pytest.raises(ReleaseFileError, match="Releases.*not found|does not exist"):
            release_mgr.find_latest_version()

    def test_first_release_scenario(self, release_manager_with_files):
        """Test typical first release scenario (0.0.1-stage.txt)."""
        release_mgr, releases_dir = release_manager_with_files

        (releases_dir / "0.0.1-stage.txt").touch()

        result = release_mgr.find_latest_version()

        assert result.major == 0
        assert result.minor == 0
        assert result.patch == 1
        assert result.stage == "stage"
