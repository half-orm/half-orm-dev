"""
Tests for Repo version validation.

Ensures that the installed half_orm_dev version is compatible with
the repository's required version specified in .hop/config.
"""

import pytest
import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch

from half_orm_dev.repo import Repo, RepoError, OutdatedHalfORMDevError


@pytest.fixture
def temp_hop_dir(tmp_path):
    """Create a temporary directory with .hop structure."""
    # Cleanup BEFORE creating the directory to ensure clean state
    Repo.clear_instances()

    hop_dir = tmp_path / '.hop'
    hop_dir.mkdir()

    yield tmp_path

    # Cleanup AFTER test
    Repo.clear_instances()


def create_hop_config(temp_dir, hop_version):
    """Helper to create .hop/config with specified version."""
    hop_dir = Path(temp_dir) / '.hop'

    config_content = f"""[halfORM]
hop_version = {hop_version}
devel = True
"""
    (hop_dir / 'config').write_text(config_content)


class TestVersionValidation:
    """Test _validate_version() method."""

    @patch('half_orm_dev.repo.Database')
    @patch('half_orm_dev.repo.HGit')
    def test_validate_version_compatible(self, mock_hgit, mock_database, temp_hop_dir):
        """Test validation passes when installed version meets requirement."""
        create_hop_config(temp_hop_dir, '0.17.0')

        with patch('half_orm_dev.repo.Repo._find_base_dir', return_value=str(temp_hop_dir)):
            with patch('half_orm_dev.repo.hop_version', return_value='0.17.2'):
                Repo.clear_instances()  # Clear inside patch context
                repo = Repo()
                assert repo.checked

    @patch('half_orm_dev.repo.Database')
    @patch('half_orm_dev.repo.HGit')
    def test_validate_version_exact_match(self, mock_hgit, mock_database, temp_hop_dir):
        """Test validation passes when versions match exactly."""
        create_hop_config(temp_hop_dir, '0.17.2')

        with patch('half_orm_dev.repo.Repo._find_base_dir', return_value=str(temp_hop_dir)):
            with patch('half_orm_dev.repo.hop_version', return_value='0.17.2'):
                Repo.clear_instances()
                repo = Repo()
                assert repo.checked

    def test_validate_version_incompatible_raises_error(self, temp_hop_dir):
        """Test validation fails when installed version is too old."""
        create_hop_config(temp_hop_dir, '0.18.0')

        with patch('half_orm_dev.repo.Repo._find_base_dir', return_value=str(temp_hop_dir)):
            with patch('half_orm_dev.repo.hop_version', return_value='0.17.2'):
                Repo.clear_instances()
                with pytest.raises(OutdatedHalfORMDevError) as exc_info:
                    Repo()

                # Check exception attributes
                assert exc_info.value.required_version == '0.18.0'
                assert exc_info.value.installed_version == '0.17.2'

                # Check error message
                error_message = str(exc_info.value)
                assert "0.18.0" in error_message
                assert "0.17.2" in error_message
                assert "pip install --upgrade half_orm_dev" in error_message

    @patch('half_orm_dev.repo.Database')
    @patch('half_orm_dev.repo.HGit')
    def test_validate_version_no_requirement_passes(self, mock_hgit, mock_database, temp_hop_dir):
        """Test validation passes when no hop_version is specified."""
        # Config without hop_version
        hop_dir = Path(temp_hop_dir) / '.hop'
        config_content = """[halfORM]
devel = True
"""
        (hop_dir / 'config').write_text(config_content)

        with patch('half_orm_dev.repo.Repo._find_base_dir', return_value=str(temp_hop_dir)):
            with patch('half_orm_dev.repo.hop_version', return_value='0.17.2'):
                Repo.clear_instances()
                repo = Repo()
                assert repo.checked

    @patch('half_orm_dev.repo.Database')
    @patch('half_orm_dev.repo.HGit')
    def test_validate_version_empty_requirement_passes(self, mock_hgit, mock_database, temp_hop_dir):
        """Test validation passes when hop_version is empty string."""
        create_hop_config(temp_hop_dir, '')

        with patch('half_orm_dev.repo.Repo._find_base_dir', return_value=str(temp_hop_dir)):
            with patch('half_orm_dev.repo.hop_version', return_value='0.17.2'):
                Repo.clear_instances()
                repo = Repo()
                assert repo.checked

    @patch('half_orm_dev.repo.Database')
    @patch('half_orm_dev.repo.HGit')
    def test_validate_version_patch_increment(self, mock_hgit, mock_database, temp_hop_dir):
        """Test validation with patch version increments."""
        create_hop_config(temp_hop_dir, '0.17.1')

        with patch('half_orm_dev.repo.Repo._find_base_dir', return_value=str(temp_hop_dir)):
            # Installed version 0.17.2 > required 0.17.1
            with patch('half_orm_dev.repo.hop_version', return_value='0.17.2'):
                Repo.clear_instances()
                repo = Repo()
                assert repo.checked

    @patch('half_orm_dev.repo.Database')
    @patch('half_orm_dev.repo.HGit')
    def test_validate_version_minor_increment(self, mock_hgit, mock_database, temp_hop_dir):
        """Test validation with minor version increments."""
        create_hop_config(temp_hop_dir, '0.16.5')

        with patch('half_orm_dev.repo.Repo._find_base_dir', return_value=str(temp_hop_dir)):
            # Installed version 0.17.0 > required 0.16.5
            with patch('half_orm_dev.repo.hop_version', return_value='0.17.0'):
                Repo.clear_instances()
                repo = Repo()
                assert repo.checked

    def test_validate_version_major_incompatibility(self, temp_hop_dir):
        """Test validation fails with major version incompatibility."""
        create_hop_config(temp_hop_dir, '1.0.0')

        with patch('half_orm_dev.repo.Repo._find_base_dir', return_value=str(temp_hop_dir)):
            # Installed version 0.17.2 < required 1.0.0
            with patch('half_orm_dev.repo.hop_version', return_value='0.17.2'):
                Repo.clear_instances()
                with pytest.raises(OutdatedHalfORMDevError) as exc_info:
                    Repo()

                error_message = str(exc_info.value)
                assert "1.0.0" in error_message
                assert "0.17.2" in error_message

    def test_validate_version_alpha_versions(self, temp_hop_dir):
        """Test validation with alpha/dev versions."""
        create_hop_config(temp_hop_dir, '0.17.2')

        with patch('half_orm_dev.repo.Repo._find_base_dir', return_value=str(temp_hop_dir)):
            # Installed alpha version
            with patch('half_orm_dev.repo.hop_version', return_value='0.17.2-a1'):
                Repo.clear_instances()
                # Alpha 0.17.2-a1 < 0.17.2, should raise error
                with pytest.raises(OutdatedHalfORMDevError):
                    Repo()

    @patch('half_orm_dev.repo.Database')
    @patch('half_orm_dev.repo.HGit')
    def test_validate_version_newer_alpha(self, mock_hgit, mock_database, temp_hop_dir):
        """Test validation with newer alpha version."""
        create_hop_config(temp_hop_dir, '0.17.1')

        with patch('half_orm_dev.repo.Repo._find_base_dir', return_value=str(temp_hop_dir)):
            # Installed version 0.17.2-a1 > required 0.17.1
            with patch('half_orm_dev.repo.hop_version', return_value='0.17.2-a1'):
                Repo.clear_instances()
                repo = Repo()
                assert repo.checked

    def test_validate_version_helpful_error_message(self, temp_hop_dir):
        """Test error message provides clear guidance."""
        create_hop_config(temp_hop_dir, '0.18.5')

        with patch('half_orm_dev.repo.Repo._find_base_dir', return_value=str(temp_hop_dir)):
            with patch('half_orm_dev.repo.hop_version', return_value='0.17.2'):
                Repo.clear_instances()
                with pytest.raises(OutdatedHalfORMDevError) as exc_info:
                    Repo()

                # Check exception attributes
                assert exc_info.value.required_version == '0.18.5'
                assert exc_info.value.installed_version == '0.17.2'

                error_message = str(exc_info.value)

                # Should mention both versions clearly
                assert "requires half_orm_dev >= 0.18.5" in error_message
                assert "0.17.2 is installed" in error_message

                # Should provide upgrade command
                assert "pip install --upgrade half_orm_dev" in error_message

    @patch('half_orm_dev.repo.Database')
    @patch('half_orm_dev.repo.HGit')
    def test_validate_version_invalid_version_format_warns(self, mock_hgit, mock_database, temp_hop_dir):
        """Test graceful handling of invalid version formats."""
        create_hop_config(temp_hop_dir, 'invalid.version')

        with patch('half_orm_dev.repo.Repo._find_base_dir', return_value=str(temp_hop_dir)):
            with patch('half_orm_dev.repo.hop_version', return_value='0.17.2'):
                Repo.clear_instances()
                # Should issue warning but not raise RepoError
                with pytest.warns(UserWarning, match="Could not parse version"):
                    repo = Repo()
                    assert repo.checked


class TestCompareVersions:
    """Test compare_versions() method."""

    def setup_method(self):
        """Clear singleton instances before each test."""
        Repo.clear_instances()

    def teardown_method(self):
        """Clear singleton instances after each test."""
        Repo.clear_instances()

    def test_compare_versions_alpha_increment(self):
        """Test comparing alpha version increments."""
        repo = Repo()

        # 0.17.2-a5 > 0.17.2-a3
        assert repo.compare_versions("0.17.2-a5", "0.17.2-a3") == 1
        assert repo.compare_versions("0.17.2-a3", "0.17.2-a5") == -1

    def test_compare_versions_alpha_to_release(self):
        """Test comparing alpha to release version."""
        repo = Repo()

        # 0.17.2 > 0.17.2-a5 (release > pre-release)
        assert repo.compare_versions("0.17.2", "0.17.2-a5") == 1
        assert repo.compare_versions("0.17.2-a5", "0.17.2") == -1

    def test_compare_versions_equal(self):
        """Test comparing equal versions."""
        repo = Repo()

        assert repo.compare_versions("0.17.2-a5", "0.17.2-a5") == 0
        assert repo.compare_versions("0.17.2", "0.17.2") == 0

    def test_compare_versions_semantic(self):
        """Test comparing semantic versions."""
        repo = Repo()

        assert repo.compare_versions("0.17.2", "0.17.1") == 1
        assert repo.compare_versions("0.18.0", "0.17.2") == 1
        assert repo.compare_versions("0.17.1", "0.17.2") == -1

    def test_compare_versions_invalid_format(self):
        """Test error handling for invalid version strings."""
        repo = Repo()

        with pytest.raises(RepoError):
            repo.compare_versions("invalid", "0.17.2")

        with pytest.raises(RepoError):
            repo.compare_versions("0.17.2", "x.y.z")
