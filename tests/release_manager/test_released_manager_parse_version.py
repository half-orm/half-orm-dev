"""
Tests for ReleaseManager.parse_version_from_filename() method.

Focused on testing:
- Production release parsing (X.Y.Z.txt)
- Stage release parsing (X.Y.Z-stage.txt)
- RC release parsing (X.Y.Z-rc[N].txt)
- Hotfix release parsing (X.Y.Z-hotfix[N].txt)
- Invalid format error handling
"""

import pytest
from half_orm_dev.release_manager import ReleaseManager, ReleaseVersionError, Version


class TestReleaseManagerParseVersion:
    """Test parse_version_from_filename() method."""

    @pytest.fixture
    def release_manager_basic(self, tmp_path):
        """Create basic ReleaseManager instance."""
        from unittest.mock import Mock

        mock_repo = Mock()
        mock_repo.base_dir = str(tmp_path)
        mock_repo.model_dir = str(tmp_path / ".hop" / "model")

        # Create releases/ directory
        releases_dir = tmp_path / ".hop" / "releases"
        releases_dir.mkdir(parents=True, exist_ok=True)
        mock_repo.releases_dir = str(releases_dir)

        return ReleaseManager(mock_repo)

    def test_parse_production_release(self, release_manager_basic):
        """Test parsing production release format X.Y.Z.txt."""
        version = release_manager_basic.parse_version_from_filename("1.3.5.txt")

        assert version.major == 1
        assert version.minor == 3
        assert version.patch == 5
        assert version.stage is None

    def test_parse_stage_release(self, release_manager_basic):
        """Test parsing stage release format X.Y.Z-stage.txt."""
        version = release_manager_basic.parse_version_from_filename("1.4.0-stage.txt")

        assert version.major == 1
        assert version.minor == 4
        assert version.patch == 0
        assert version.stage == "stage"

    def test_parse_rc_release_with_number(self, release_manager_basic):
        """Test parsing RC release format X.Y.Z-rc[N].txt."""
        version = release_manager_basic.parse_version_from_filename("1.3.5-rc2.txt")

        assert version.major == 1
        assert version.minor == 3
        assert version.patch == 5
        assert version.stage == "rc2"

    def test_parse_rc1_release(self, release_manager_basic):
        """Test parsing first RC release X.Y.Z-rc1.txt."""
        version = release_manager_basic.parse_version_from_filename("2.0.0-rc1.txt")

        assert version.major == 2
        assert version.minor == 0
        assert version.patch == 0
        assert version.stage == "rc1"

    def test_parse_hotfix_release(self, release_manager_basic):
        """Test parsing hotfix release format X.Y.Z-hotfix[N].txt."""
        version = release_manager_basic.parse_version_from_filename("1.3.5-hotfix1.txt")

        assert version.major == 1
        assert version.minor == 3
        assert version.patch == 5
        assert version.stage == "hotfix1"

    def test_parse_hotfix_multiple(self, release_manager_basic):
        """Test parsing multiple hotfix release X.Y.Z-hotfix3.txt."""
        version = release_manager_basic.parse_version_from_filename("1.3.4-hotfix3.txt")

        assert version.major == 1
        assert version.minor == 3
        assert version.patch == 4
        assert version.stage == "hotfix3"

    def test_parse_large_version_numbers(self, release_manager_basic):
        """Test parsing with large version numbers."""
        version = release_manager_basic.parse_version_from_filename("10.20.30.txt")

        assert version.major == 10
        assert version.minor == 20
        assert version.patch == 30
        assert version.stage is None

    def test_parse_zero_version(self, release_manager_basic):
        """Test parsing version 0.0.1-stage.txt (first release)."""
        version = release_manager_basic.parse_version_from_filename("0.0.1-stage.txt")

        assert version.major == 0
        assert version.minor == 0
        assert version.patch == 1
        assert version.stage == "stage"

    def test_parse_missing_txt_extension(self, release_manager_basic):
        """Test error when .txt extension missing."""
        with pytest.raises(ReleaseVersionError, match="Invalid.*format|extension"):
            release_manager_basic.parse_version_from_filename("1.3.5")

    def test_parse_invalid_version_format(self, release_manager_basic):
        """Test error with invalid version format."""
        with pytest.raises(ReleaseVersionError, match="Invalid.*format"):
            release_manager_basic.parse_version_from_filename("1.3.txt")

    def test_parse_invalid_characters(self, release_manager_basic):
        """Test error with non-numeric version components."""
        with pytest.raises(ReleaseVersionError, match="Invalid.*format"):
            release_manager_basic.parse_version_from_filename("1.a.5.txt")

    def test_parse_too_many_components(self, release_manager_basic):
        """Test error with too many version components."""
        with pytest.raises(ReleaseVersionError, match="Invalid.*format"):
            release_manager_basic.parse_version_from_filename("1.3.5.7.txt")

    def test_parse_empty_filename(self, release_manager_basic):
        """Test error with empty filename."""
        with pytest.raises(ReleaseVersionError, match="Invalid.*format|empty"):
            release_manager_basic.parse_version_from_filename("")

    def test_parse_invalid_stage_format(self, release_manager_basic):
        """Test error with invalid stage format."""
        with pytest.raises(ReleaseVersionError, match="Invalid.*stage|format"):
            release_manager_basic.parse_version_from_filename("1.3.5-invalid.txt")

    def test_parse_negative_version(self, release_manager_basic):
        """Test error with negative version numbers."""
        with pytest.raises(ReleaseVersionError, match="Invalid.*format|negative"):
            release_manager_basic.parse_version_from_filename("-1.3.5.txt")

    def test_parse_without_path(self, release_manager_basic):
        """Test parsing works with just filename (no path)."""
        version = release_manager_basic.parse_version_from_filename("1.3.5-rc1.txt")

        assert version.major == 1
        assert version.minor == 3
        assert version.patch == 5
        assert version.stage == "rc1"

    def test_parse_with_path(self, release_manager_basic):
        """Test parsing works with full path."""
        version = release_manager_basic.parse_version_from_filename("releases/1.3.5.txt")

        assert version.major == 1
        assert version.minor == 3
        assert version.patch == 5
        assert version.stage is None
