"""
Tests for ReleaseManager.calculate_next_version() method.

Focused on testing:
- First release calculation (None -> 0.0.1)
- Major increment (1.3.5 -> 2.0.0)
- Minor increment (1.3.5 -> 1.4.0)
- Patch increment (1.3.5 -> 1.3.6)
- Invalid increment type error
- Edge cases with large numbers
"""

import pytest
from unittest.mock import Mock

from half_orm_dev.release_manager import ReleaseManager, ReleaseVersionError, Version


class TestReleaseManagerCalculateNext:
    """Test calculate_next_version() method."""

    @pytest.fixture
    def release_manager_basic(self, tmp_path):
        """Create basic ReleaseManager instance."""
        mock_repo = Mock()
        mock_repo.base_dir = str(tmp_path)

        # Create releases/ directory
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        return ReleaseManager(mock_repo)

    # def test_none_version_raises_error(self, release_manager_basic):
    #     """Test error when no production version (sync-only mode)."""
    #     with pytest.raises(ReleaseVersionError, match="No production version|sync-only mode"):
    #         release_manager_basic.calculate_next_version(None, 'patch')

    def test_first_release_from_0_0_0(self, release_manager_basic):
        """Test first release after init-database (from 0.0.0)."""
        current = Version(0, 0, 0)

        # patch: 0.0.0 -> 0.0.1
        assert release_manager_basic.calculate_next_version(current, 'patch') == "0.0.1"

        # minor: 0.0.0 -> 0.1.0
        assert release_manager_basic.calculate_next_version(current, 'minor') == "0.1.0"

        # major: 0.0.0 -> 1.0.0
        assert release_manager_basic.calculate_next_version(current, 'major') == "1.0.0"

    def test_increment_patch_simple(self, release_manager_basic):
        """Test patch increment: X.Y.Z -> X.Y.(Z+1)."""
        current = Version(1, 3, 5)

        result = release_manager_basic.calculate_next_version(current, 'patch')

        assert result == "1.3.6"

    def test_increment_minor_resets_patch(self, release_manager_basic):
        """Test minor increment: X.Y.Z -> X.(Y+1).0."""
        current = Version(1, 3, 5)

        result = release_manager_basic.calculate_next_version(current, 'minor')

        assert result == "1.4.0"

    def test_increment_major_resets_minor_and_patch(self, release_manager_basic):
        """Test major increment: X.Y.Z -> (X+1).0.0."""
        current = Version(1, 3, 5)

        result = release_manager_basic.calculate_next_version(current, 'major')

        assert result == "2.0.0"

    def test_increment_patch_from_zero_patch(self, release_manager_basic):
        """Test patch increment when patch is already 0."""
        current = Version(1, 4, 0)

        result = release_manager_basic.calculate_next_version(current, 'patch')

        assert result == "1.4.1"

    def test_increment_minor_from_zero_minor(self, release_manager_basic):
        """Test minor increment when minor is 0."""
        current = Version(2, 0, 0)

        result = release_manager_basic.calculate_next_version(current, 'minor')

        assert result == "2.1.0"

    def test_increment_major_from_large_version(self, release_manager_basic):
        """Test major increment with large version numbers."""
        current = Version(9, 99, 99)

        result = release_manager_basic.calculate_next_version(current, 'major')

        assert result == "10.0.0"

    def test_increment_patch_from_large_patch(self, release_manager_basic):
        """Test patch increment with large patch number."""
        current = Version(1, 3, 99)

        result = release_manager_basic.calculate_next_version(current, 'patch')

        assert result == "1.3.100"

    def test_increment_minor_from_large_minor(self, release_manager_basic):
        """Test minor increment with large minor number."""
        current = Version(1, 99, 5)

        result = release_manager_basic.calculate_next_version(current, 'minor')

        assert result == "1.100.0"

    def test_increment_from_version_with_stage_ignores_stage(self, release_manager_basic):
        """Test that stage info is ignored in calculation."""
        current = Version(1, 3, 5, stage="rc2")

        result = release_manager_basic.calculate_next_version(current, 'patch')

        # Stage ignored, just increments base version
        assert result == "1.3.6"

    def test_increment_invalid_type_raises_error(self, release_manager_basic):
        """Test error with invalid increment type."""
        current = Version(1, 3, 5)

        with pytest.raises(ReleaseVersionError, match="Invalid.*increment.*type|unknown.*level"):
            release_manager_basic.calculate_next_version(current, 'invalid')

    def test_increment_empty_string_raises_error(self, release_manager_basic):
        """Test error with empty increment type."""
        current = Version(1, 3, 5)

        with pytest.raises(ReleaseVersionError, match="Invalid.*increment.*type|empty"):
            release_manager_basic.calculate_next_version(current, '')

    def test_increment_case_sensitivity(self, release_manager_basic):
        """Test that increment type is case-sensitive (lowercase required)."""
        current = Version(1, 3, 5)

        # Uppercase should fail
        with pytest.raises(ReleaseVersionError, match="Invalid.*increment.*type"):
            release_manager_basic.calculate_next_version(current, 'PATCH')

        with pytest.raises(ReleaseVersionError, match="Invalid.*increment.*type"):
            release_manager_basic.calculate_next_version(current, 'Minor')

    def test_increment_from_zero_version(self, release_manager_basic):
        """Test increment from 0.0.1 (typical first release)."""
        current = Version(0, 0, 1)

        # Patch: 0.0.1 -> 0.0.2
        assert release_manager_basic.calculate_next_version(current, 'patch') == "0.0.2"

        # Minor: 0.0.1 -> 0.1.0
        assert release_manager_basic.calculate_next_version(current, 'minor') == "0.1.0"

        # Major: 0.0.1 -> 1.0.0
        assert release_manager_basic.calculate_next_version(current, 'major') == "1.0.0"

    def test_increment_patch_sequence(self, release_manager_basic):
        """Test sequence of patch increments."""
        versions = [
            Version(1, 3, 5),
            Version(1, 3, 6),
            Version(1, 3, 7),
        ]

        for i, current in enumerate(versions[:-1]):
            result = release_manager_basic.calculate_next_version(current, 'patch')
            expected = f"1.3.{6 + i}"
            assert result == expected

    def test_return_type_is_string(self, release_manager_basic):
        """Test that return value is always a string."""
        current = Version(1, 3, 5)

        for increment_type in ['patch', 'minor', 'major']:
            result = release_manager_basic.calculate_next_version(current, increment_type)
            assert isinstance(result, str)
