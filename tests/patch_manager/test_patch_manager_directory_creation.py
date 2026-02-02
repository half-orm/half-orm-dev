"""
Tests pour la création de répertoires de patches.

Module de test focalisé sur create_patch_directory() utilisant
les fixtures communes définies dans conftest.py.
"""

import pytest
import shutil
from pathlib import Path
from unittest.mock import patch as mock_patch

from half_orm_dev.patch_manager import (
    PatchManager,
    PatchManagerError,
    PatchStructureError
)


class TestCreatePatchDirectory:
    """Test patch directory creation functionality."""

    def test_create_patch_directory_numeric_id(self, patch_manager):
        """Test creating patch directory with numeric ID."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        result_path = patch_mgr.create_patch_directory("456")

        expected_path = patches_dir / "456"
        assert result_path == expected_path
        assert expected_path.exists()
        assert expected_path.is_dir()

        # README.md should be created
        readme_path = expected_path / "README.md"
        assert readme_path.exists()
        assert readme_path.is_file()

        # Check minimal README content
        readme_content = readme_path.read_text()
        assert readme_content == "# Patch 456\n"

    def test_create_patch_directory_full_id(self, patch_manager):
        """Test creating patch directory with full ID."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        result_path = patch_mgr.create_patch_directory("456-user-authentication")

        expected_path = patches_dir / "456-user-authentication"
        assert result_path == expected_path
        assert expected_path.exists()

        # Check README content with full name
        readme_path = expected_path / "README.md"
        readme_content = readme_path.read_text()
        assert readme_content == "# Patch 456-user-authentication\n"

    def test_create_patch_directory_already_exists(self, patch_manager):
        """Test creating patch directory that already exists."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create first patch
        patch_mgr.create_patch_directory("456")

        # Second attempt should fail
        with pytest.raises(PatchStructureError, match="already exists"):
            patch_mgr.create_patch_directory("456")

    def test_create_patch_directory_invalid_id(self, patch_manager):
        """Test creating patch directory with invalid ID."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        invalid_ids = ["invalid@patch", "", "   ", "no-number"]

        for invalid_id in invalid_ids:
            with pytest.raises(PatchManagerError, match="Invalid patch ID"):
                patch_mgr.create_patch_directory(invalid_id)

    def test_create_patch_directory_whitespace_normalization(self, patch_manager):
        """Test patch ID whitespace normalization."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        result_path = patch_mgr.create_patch_directory("  456-user-auth  ")

        # Should create normalized directory name
        expected_path = patches_dir / "456-user-auth"
        assert result_path == expected_path
        assert expected_path.exists()

    def test_create_patch_directory_permission_error(self, patch_manager):
        """Test permission error during directory creation."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Make parent directory read-only
        patches_dir.chmod(0o444)

        try:
            with pytest.raises(PatchManagerError, match="Permission denied"):
                patch_mgr.create_patch_directory("456")
        finally:
            # Restore permissions
            patches_dir.chmod(0o755)

    def test_create_patch_directory_readme_write_failure(self, patch_manager):
        """Test README.md write failure with cleanup."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        def failing_write_text(self, content, encoding=None):
            raise OSError("Disk full")

        with mock_patch.object(Path, 'write_text', failing_write_text):
            with pytest.raises(PatchManagerError, match="Failed to create README.md"):
                patch_mgr.create_patch_directory("456-test")

        # Directory should be cleaned up after failure
        assert not (patches_dir / "456-test").exists()

    def test_create_patch_directory_returns_path(self, patch_manager):
        """Test that correct Path object is returned."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        result_path = patch_mgr.create_patch_directory("789-test")

        assert isinstance(result_path, Path)
        assert result_path.is_absolute()
        assert result_path.parent == patches_dir
        assert result_path.exists()

    def test_create_patch_directory_multiple_creation(self, patch_manager):
        """Test creating multiple patch directories."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        patch_ids = ["111-first", "222-second", "333-third"]

        for patch_id in patch_ids:
            path = patch_mgr.create_patch_directory(patch_id)
            assert path.exists()
            readme = path / "README.md"
            assert readme.exists()
            assert readme.read_text() == f"# Patch {patch_id}\n"

        # All patches should exist as directories
        for patch_id in patch_ids:
            assert (patches_dir / patch_id).exists()
            assert (patches_dir / patch_id).is_dir()

    def test_create_patch_directory_concurrent_protection(self, patch_manager):
        """Test protection against concurrent directory creation."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Simulate race condition by creating directory manually
        race_path = patches_dir / "555-race"
        race_path.mkdir()

        with pytest.raises(PatchStructureError, match="already exists"):
            patch_mgr.create_patch_directory("555-race")

    def test_create_patch_directory_utf8_encoding(self, patch_manager):
        """Test UTF-8 encoding for README.md."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        patch_mgr.create_patch_directory("999-unicode")

        readme_path = patches_dir / "999-unicode" / "README.md"

        # Should be able to write and read unicode content
        unicode_content = "# Patch 999-unicode\n\nTest: 测试 français"
        readme_path.write_text(unicode_content, encoding='utf-8')

        read_content = readme_path.read_text(encoding='utf-8')
        assert unicode_content == read_content
