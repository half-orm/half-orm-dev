"""
Tests for Repo.init_git_centric_project() - Git-centric structure creation

Focused on:
- Git-centric directory structure (_create_git_centric_structure)
- Patches/, releases/, model/, backups/ creation
- README files generation
"""

import pytest
import os
from pathlib import Path
from unittest.mock import Mock, patch, mock_open, call

from half_orm_dev.repo import Repo


class TestGitCentricStructureCreation:
    """Test _create_git_centric_structure() method."""

    def setup_method(self):
        """Clear singleton instances before each test."""
        Repo.clear_instances()

    def teardown_method(self):
        """Clear singleton instances after each test."""
        Repo.clear_instances()

    @patch('builtins.open', new_callable=mock_open)
    @patch('os.makedirs')
    def test_create_git_centric_structure_development_mode(self, mock_makedirs, mock_file):
        """Test structure creation in development mode."""
        repo = Repo.__new__(Repo)
        repo._Repo__checked = False
        repo._Repo__base_dir = "/test/project"
        repo._Repo__config = Mock()
        repo._Repo__config.devel = True

        repo._create_git_centric_structure()

        # Should create all required directories
        expected_calls = [
            call("/test/project/Patches", exist_ok=True),
            call("/test/project/releases", exist_ok=True),
            call("/test/project/model", exist_ok=True),
            call("/test/project/backups", exist_ok=True)
        ]
        mock_makedirs.assert_has_calls(expected_calls, any_order=True)

    @patch('os.makedirs')
    def test_create_git_centric_structure_sync_only_mode(self, mock_makedirs):
        """Test structure NOT created in sync-only mode."""
        repo = Repo.__new__(Repo)
        repo._Repo__checked = False
        repo._Repo__base_dir = "/test/project"
        repo._Repo__config = Mock()
        repo._Repo__config.devel = False  # Sync-only mode

        repo._create_git_centric_structure()

        # Should NOT create directories in sync-only mode
        mock_makedirs.assert_not_called()

    @patch('builtins.open', new_callable=mock_open)
    @patch('os.makedirs')
    def test_create_git_centric_structure_creates_patches_readme(self, mock_makedirs, mock_file):
        """Test Patches/README.md creation."""
        repo = Repo.__new__(Repo)
        repo._Repo__checked = False
        repo._Repo__base_dir = "/test/project"
        repo._Repo__config = Mock()
        repo._Repo__config.devel = True

        repo._create_git_centric_structure()

        # Should create Patches/README.md
        expected_path = "/test/project/Patches/README.md"
        mock_file.assert_any_call(expected_path, 'w', encoding='utf-8')

        # Verify content mentions patch development
        handle = mock_file()
        written_content = ''.join(call.args[0] for call in handle.write.call_args_list if call.args)
        assert 'patch' in written_content.lower() or 'Patch' in written_content

    @patch('builtins.open', new_callable=mock_open)
    @patch('os.makedirs')
    def test_create_git_centric_structure_creates_releases_readme(self, mock_makedirs, mock_file):
        """Test releases/README.md creation."""
        repo = Repo.__new__(Repo)
        repo._Repo__checked = False
        repo._Repo__base_dir = "/test/project"
        repo._Repo__config = Mock()
        repo._Repo__config.devel = True

        repo._create_git_centric_structure()

        # Should create releases/README.md
        expected_path = "/test/project/releases/README.md"
        mock_file.assert_any_call(expected_path, 'w', encoding='utf-8')

        # Verify content mentions release workflow
        handle = mock_file()
        written_content = ''.join(call.args[0] for call in handle.write.call_args_list if call.args)
        assert 'release' in written_content.lower() or 'Release' in written_content

    @patch('os.makedirs')
    def test_create_git_centric_structure_handles_permission_error(self, mock_makedirs):
        """Test error handling when directory creation fails."""
        mock_makedirs.side_effect = PermissionError("Permission denied")

        repo = Repo.__new__(Repo)
        repo._Repo__checked = False
        repo._Repo__base_dir = "/readonly/project"
        repo._Repo__config = Mock()
        repo._Repo__config.devel = True

        with pytest.raises(PermissionError):
            repo._create_git_centric_structure()

    @patch('builtins.open', new_callable=mock_open)
    @patch('os.makedirs')
    def test_create_git_centric_structure_all_directories_created(self, mock_makedirs, mock_file):
        """Test all required directories are created."""
        repo = Repo.__new__(Repo)
        repo._Repo__checked = False
        repo._Repo__base_dir = "/test/project"
        repo._Repo__config = Mock()
        repo._Repo__config.devel = True

        repo._create_git_centric_structure()

        # Verify exact number of makedirs calls (4 directories)
        assert mock_makedirs.call_count == 4

        # Verify all expected directories
        created_dirs = [call[0][0] for call in mock_makedirs.call_args_list]
        assert "/test/project/Patches" in created_dirs
        assert "/test/project/releases" in created_dirs
        assert "/test/project/model" in created_dirs
        assert "/test/project/backups" in created_dirs