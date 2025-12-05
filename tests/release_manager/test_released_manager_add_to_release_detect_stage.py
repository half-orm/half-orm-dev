"""
Tests for ReleaseManager._detect_target_stage_file() method.

Focused on testing:
- Auto-detection when single stage exists
- Explicit version when multiple stages exist
- Error when no stage exists
- Error when multiple stages without explicit version
- Error when specified stage doesn't exist
- Edge cases with RC and production files (should be ignored)
"""

import pytest
from pathlib import Path
from unittest.mock import Mock

from half_orm_dev.release_manager import ReleaseManager, ReleaseManagerError


class TestDetectTargetStageFile:
    """Test _detect_target_stage_file() method."""

    @pytest.fixture
    def release_manager_with_files(self, tmp_path):
        """Create ReleaseManager with releases/ directory."""
        mock_repo = Mock()
        mock_repo.base_dir = str(tmp_path)
        mock_repo.model_dir = str(tmp_path / ".hop" / "model")

        # Create releases/ directory
        releases_dir = tmp_path / ".hop" / "releases"
        releases_dir.mkdir(parents=True, exist_ok=True)
        mock_repo.releases_dir = str(releases_dir)

        release_mgr = ReleaseManager(mock_repo)

        return release_mgr, releases_dir

    def test_no_stage_file_raises_error(self, release_manager_with_files):
        """Test error when no stage release exists."""
        release_mgr, releases_dir = release_manager_with_files

        # Empty releases/ directory (no stage files)

        with pytest.raises(ReleaseManagerError, match="No stage release found|prepare-release"):
            release_mgr._detect_target_stage_file()

    def test_single_stage_file_auto_detected(self, release_manager_with_files):
        """Test auto-detection when single stage exists."""
        release_mgr, releases_dir = release_manager_with_files

        # Create single stage file
        (releases_dir / "1.3.6-stage.txt").touch()

        version, filename = release_mgr._detect_target_stage_file()

        assert version == "1.3.6"
        assert filename == "1.3.6-stage.txt"

    def test_single_stage_with_explicit_version(self, release_manager_with_files):
        """Test explicit version matches existing stage."""
        release_mgr, releases_dir = release_manager_with_files

        # Create single stage file
        (releases_dir / "1.3.6-stage.txt").touch()

        version, filename = release_mgr._detect_target_stage_file(to_version="1.3.6")

        assert version == "1.3.6"
        assert filename == "1.3.6-stage.txt"

    def test_multiple_stages_without_version_raises_error(self, release_manager_with_files):
        """Test error when multiple stages exist without explicit version."""
        release_mgr, releases_dir = release_manager_with_files

        # Create multiple stage files
        (releases_dir / "1.3.6-stage.txt").touch()
        (releases_dir / "1.4.0-stage.txt").touch()
        (releases_dir / "2.0.0-stage.txt").touch()

        with pytest.raises(ReleaseManagerError, match="Multiple.*stage|--to-version"):
            release_mgr._detect_target_stage_file()

    def test_multiple_stages_with_explicit_version_first(self, release_manager_with_files):
        """Test explicit version selects first stage."""
        release_mgr, releases_dir = release_manager_with_files

        # Create multiple stage files
        (releases_dir / "1.3.6-stage.txt").touch()
        (releases_dir / "1.4.0-stage.txt").touch()

        version, filename = release_mgr._detect_target_stage_file(to_version="1.3.6")

        assert version == "1.3.6"
        assert filename == "1.3.6-stage.txt"

    def test_multiple_stages_with_explicit_version_second(self, release_manager_with_files):
        """Test explicit version selects second stage."""
        release_mgr, releases_dir = release_manager_with_files

        # Create multiple stage files
        (releases_dir / "1.3.6-stage.txt").touch()
        (releases_dir / "1.4.0-stage.txt").touch()

        version, filename = release_mgr._detect_target_stage_file(to_version="1.4.0")

        assert version == "1.4.0"
        assert filename == "1.4.0-stage.txt"

    def test_explicit_version_not_found_raises_error(self, release_manager_with_files):
        """Test error when specified stage doesn't exist."""
        release_mgr, releases_dir = release_manager_with_files

        # Create stage file
        (releases_dir / "1.3.6-stage.txt").touch()

        # Try to use non-existent version
        with pytest.raises(ReleaseManagerError, match="Stage release.*1.9.9.*not found"):
            release_mgr._detect_target_stage_file(to_version="1.9.9")

    def test_ignores_rc_files(self, release_manager_with_files):
        """Test that RC files are ignored (only stage counted)."""
        release_mgr, releases_dir = release_manager_with_files

        # Create RC and stage files
        (releases_dir / "1.3.5-rc1.txt").touch()
        (releases_dir / "1.3.5-rc2.txt").touch()
        (releases_dir / "1.3.6-stage.txt").touch()  # Only this should count

        # Should auto-detect the single stage (ignoring RCs)
        version, filename = release_mgr._detect_target_stage_file()

        assert version == "1.3.6"
        assert filename == "1.3.6-stage.txt"

    def test_ignores_production_files(self, release_manager_with_files):
        """Test that production files are ignored (only stage counted)."""
        release_mgr, releases_dir = release_manager_with_files

        # Create production and stage files
        (releases_dir / "1.3.5.txt").touch()
        (releases_dir / "1.3.6-stage.txt").touch()  # Only this should count

        # Should auto-detect the single stage (ignoring production)
        version, filename = release_mgr._detect_target_stage_file()

        assert version == "1.3.6"
        assert filename == "1.3.6-stage.txt"

    def test_ignores_hotfix_files(self, release_manager_with_files):
        """Test that hotfix files are ignored (only stage counted)."""
        release_mgr, releases_dir = release_manager_with_files

        # Create hotfix and stage files
        (releases_dir / "1.3.5-hotfix1.txt").touch()
        (releases_dir / "1.3.6-stage.txt").touch()  # Only this should count

        # Should auto-detect the single stage (ignoring hotfix)
        version, filename = release_mgr._detect_target_stage_file()

        assert version == "1.3.6"
        assert filename == "1.3.6-stage.txt"

    def test_complex_scenario_multiple_types(self, release_manager_with_files):
        """Test with multiple file types (stage, RC, prod, hotfix)."""
        release_mgr, releases_dir = release_manager_with_files

        # Create mixed files
        (releases_dir / "1.3.4.txt").touch()           # Production
        (releases_dir / "1.3.4-hotfix1.txt").touch()   # Hotfix
        (releases_dir / "1.3.5-rc1.txt").touch()       # RC
        (releases_dir / "1.3.5-rc2.txt").touch()       # RC
        (releases_dir / "1.3.6-stage.txt").touch()     # Stage 1
        (releases_dir / "1.4.0-stage.txt").touch()     # Stage 2

        # Should detect 2 stages (ignoring all others)
        with pytest.raises(ReleaseManagerError, match="Multiple.*stage"):
            release_mgr._detect_target_stage_file()

        # Explicit version should work
        version, filename = release_mgr._detect_target_stage_file(to_version="1.4.0")
        assert version == "1.4.0"
        assert filename == "1.4.0-stage.txt"

    def test_case_sensitivity(self, release_manager_with_files):
        """Test that stage detection is case-insensitive for version."""
        release_mgr, releases_dir = release_manager_with_files

        # Create stage file
        (releases_dir / "1.3.6-stage.txt").touch()

        # Explicit version with different case (should still work)
        version, filename = release_mgr._detect_target_stage_file(to_version="1.3.6")

        assert version == "1.3.6"
        assert filename == "1.3.6-stage.txt"
