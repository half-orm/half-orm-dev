"""
Tests for ReleaseManager._detect_stage_to_promote() - Stage detection and sorting.

Focused on testing:
- Single stage detection
- Multiple stages sorting (smallest first)
- Patch vs minor vs major version ordering
- Edge cases (no stages, invalid filenames)
"""

import pytest
from pathlib import Path
from unittest.mock import Mock

from half_orm_dev.release_manager import ReleaseManager, ReleaseManagerError


class TestDetectStageToPromote:
    """Test stage detection for promotion."""

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

    def test_single_stage_detected(self, release_manager_basic):
        """Test detection of single stage release."""
        release_mgr, releases_dir = release_manager_basic

        # Create single stage file
        (releases_dir / "1.3.5-stage.txt").touch()

        version, filename = release_mgr._detect_stage_to_promote()

        assert version == "1.3.5"
        assert filename == "1.3.5-stage.txt"

    def test_multiple_stages_returns_smallest(self, release_manager_basic):
        """Test that smallest version is returned when multiple stages exist."""
        release_mgr, releases_dir = release_manager_basic

        # Create multiple stage files
        (releases_dir / "1.3.5-stage.txt").touch()
        (releases_dir / "1.4.0-stage.txt").touch()
        (releases_dir / "2.0.0-stage.txt").touch()

        version, filename = release_mgr._detect_stage_to_promote()

        # Should return smallest (1.3.5)
        assert version == "1.3.5"
        assert filename == "1.3.5-stage.txt"

    def test_patch_versions_sorted_correctly(self, release_manager_basic):
        """Test patch versions sorted in ascending order."""
        release_mgr, releases_dir = release_manager_basic

        # Create patch versions
        (releases_dir / "1.3.7-stage.txt").touch()
        (releases_dir / "1.3.5-stage.txt").touch()
        (releases_dir / "1.3.10-stage.txt").touch()  # Double digit

        version, filename = release_mgr._detect_stage_to_promote()

        # Should return 1.3.5 (not 1.3.10)
        assert version == "1.3.5"
        assert filename == "1.3.5-stage.txt"

    def test_minor_versions_sorted_correctly(self, release_manager_basic):
        """Test minor versions sorted in ascending order."""
        release_mgr, releases_dir = release_manager_basic

        # Create minor versions
        (releases_dir / "1.5.0-stage.txt").touch()
        (releases_dir / "1.3.0-stage.txt").touch()
        (releases_dir / "1.10.0-stage.txt").touch()  # Double digit

        version, filename = release_mgr._detect_stage_to_promote()

        # Should return 1.3.0 (not 1.10.0)
        assert version == "1.3.0"
        assert filename == "1.3.0-stage.txt"

    def test_major_versions_sorted_correctly(self, release_manager_basic):
        """Test major versions sorted in ascending order."""
        release_mgr, releases_dir = release_manager_basic

        # Create major versions
        (releases_dir / "3.0.0-stage.txt").touch()
        (releases_dir / "1.0.0-stage.txt").touch()
        (releases_dir / "10.0.0-stage.txt").touch()  # Double digit

        version, filename = release_mgr._detect_stage_to_promote()

        # Should return 1.0.0 (not 10.0.0)
        assert version == "1.0.0"
        assert filename == "1.0.0-stage.txt"

    def test_patch_before_minor_before_major(self, release_manager_basic):
        """Test that patch < minor < major in sorting."""
        release_mgr, releases_dir = release_manager_basic

        # Create one of each type
        (releases_dir / "2.0.0-stage.txt").touch()  # Major
        (releases_dir / "1.4.0-stage.txt").touch()  # Minor
        (releases_dir / "1.3.5-stage.txt").touch()  # Patch

        version, filename = release_mgr._detect_stage_to_promote()

        # Should return patch version (1.3.5)
        assert version == "1.3.5"
        assert filename == "1.3.5-stage.txt"

    def test_mixed_versions_complex_sorting(self, release_manager_basic):
        """Test complex mix of versions sorted correctly."""
        release_mgr, releases_dir = release_manager_basic

        # Create complex mix
        (releases_dir / "1.3.10-stage.txt").touch()
        (releases_dir / "1.10.0-stage.txt").touch()
        (releases_dir / "2.0.0-stage.txt").touch()
        (releases_dir / "1.3.5-stage.txt").touch()
        (releases_dir / "1.3.7-stage.txt").touch()
        (releases_dir / "1.4.0-stage.txt").touch()

        version, filename = release_mgr._detect_stage_to_promote()

        # Should return absolute smallest (1.3.5)
        assert version == "1.3.5"
        assert filename == "1.3.5-stage.txt"

    def test_no_stages_raises_error(self, release_manager_basic):
        """Test error when no stage files exist."""
        release_mgr, releases_dir = release_manager_basic

        # No stage files created

        with pytest.raises(ReleaseManagerError, match="No stage releases|stage.*not found"):
            release_mgr._detect_stage_to_promote()

    def test_ignores_non_stage_files(self, release_manager_basic):
        """Test that non-stage files are ignored."""
        release_mgr, releases_dir = release_manager_basic

        # Create various non-stage files
        (releases_dir / "1.3.4.txt").touch()  # Production
        (releases_dir / "1.3.5-rc1.txt").touch()  # RC
        (releases_dir / "1.3.4-hotfix1.txt").touch()  # Hotfix
        (releases_dir / "README.md").touch()  # Other

        # Only one stage file
        (releases_dir / "1.3.6-stage.txt").touch()

        version, filename = release_mgr._detect_stage_to_promote()

        # Should return the stage file only
        assert version == "1.3.6"
        assert filename == "1.3.6-stage.txt"

    def test_stage_with_content_detected(self, release_manager_basic):
        """Test that stage files with content are detected correctly."""
        release_mgr, releases_dir = release_manager_basic

        # Create stage file with content
        stage_file = releases_dir / "1.3.5-stage.txt"
        stage_file.write_text("456-user-auth\n789-security\n")

        version, filename = release_mgr._detect_stage_to_promote()

        assert version == "1.3.5"
        assert filename == "1.3.5-stage.txt"

    def test_empty_stage_file_detected(self, release_manager_basic):
        """Test that empty stage files are detected."""
        release_mgr, releases_dir = release_manager_basic

        # Create empty stage file
        (releases_dir / "1.3.5-stage.txt").write_text("")

        version, filename = release_mgr._detect_stage_to_promote()

        assert version == "1.3.5"
        assert filename == "1.3.5-stage.txt"

    def test_returns_tuple_format(self, release_manager_basic):
        """Test that return value is correct tuple format."""
        release_mgr, releases_dir = release_manager_basic

        (releases_dir / "1.3.5-stage.txt").touch()

        result = release_mgr._detect_stage_to_promote()

        # Should be tuple of (version_str, filename)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], str)
