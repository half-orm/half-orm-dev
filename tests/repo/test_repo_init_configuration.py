"""
Tests for Repo.init_git_centric_project() - Configuration initialization

Focused on:
- .hop/config file creation (_initialize_configuration)
- Config object initialization
- Configuration persistence
"""

import pytest
import os
from pathlib import Path
from unittest.mock import Mock, patch, mock_open, call
from configparser import ConfigParser

from half_orm_dev.repo import Repo, Config


class TestConfigurationInitialization:
    """Test _initialize_configuration() method."""

    def setup_method(self):
        """Clear singleton instances before each test."""
        Repo.clear_instances()

    def teardown_method(self):
        """Clear singleton instances after each test."""
        Repo.clear_instances()

    @patch('os.makedirs')
    @patch('builtins.open', new_callable=mock_open)
    def test_initialize_configuration_creates_hop_directory(self, mock_file, mock_makedirs):
        """Test that .hop directory is created."""
        repo = Repo.__new__(Repo)
        repo._Repo__checked = False
        repo._Repo__base_dir = "/test/project"

        repo._initialize_configuration("my_blog", devel_mode=True, git_origin="git@git.example.com:user/repo")

        # Should create .hop directory
        expected_hop_dir = "/test/project/.hop"
        mock_makedirs.assert_called_once_with(expected_hop_dir, exist_ok=True)

    @patch('half_orm_dev.utils.hop_version')
    @patch('os.makedirs')
    @patch('builtins.open', new_callable=mock_open)
    def test_initialize_configuration_creates_config_file(self, mock_file, mock_makedirs, mock_hop_version):
        """Test that config file is created with correct content."""
        mock_hop_version.return_value = "0.16.0"

        repo = Repo.__new__(Repo)
        repo._Repo__checked = False
        repo._Repo__base_dir = "/test/project"

        repo._initialize_configuration("my_blog", devel_mode=True, git_origin="git@git.example.com:user/repo")

        # Should open config file for writing
        expected_config_path = "/test/project/.hop/config"
        mock_file.assert_called_with(expected_config_path, 'w', encoding='utf-8')

    @patch('os.makedirs')
    @patch('builtins.open', new_callable=mock_open)
    def test_initialize_configuration_writes_correct_content_devel_true(self, mock_file, mock_makedirs):
        """Test config content for development mode."""
        repo = Repo.__new__(Repo)
        repo._Repo__checked = False
        repo._Repo__base_dir = "/test/project"

        repo._initialize_configuration("my_blog", devel_mode=True, git_origin="git@git.example.com:user/repo")

        # Verify written content
        handle = mock_file()
        written_content = ''.join(call.args[0] for call in handle.write.call_args_list)

        # Should contain all required fields
        assert '[halfORM]' in written_content
        assert 'package_name = my_blog' in written_content
        assert 'hop_version =' in written_content  # Version is set by Config.write()
        assert 'git_origin =' in written_content  # Empty initially
        assert 'devel = True' in written_content

    @patch('half_orm_dev.utils.hop_version')
    @patch('os.makedirs')
    @patch('builtins.open', new_callable=mock_open)
    def test_initialize_configuration_writes_correct_content_devel_false(self, mock_file, mock_makedirs, mock_hop_version):
        """Test config content for sync-only mode."""
        mock_hop_version.return_value = "0.16.0"

        repo = Repo.__new__(Repo)
        repo._Repo__checked = False
        repo._Repo__base_dir = "/test/project"

        repo._initialize_configuration("legacy_app", devel_mode=False, git_origin="git@git.example.com:user/repo")

        # Verify written content
        handle = mock_file()
        written_content = ''.join(call.args[0] for call in handle.write.call_args_list)

        # Should have devel = False
        assert 'devel = False' in written_content or 'devel = false' in written_content
        assert 'package_name = legacy_app' in written_content

    @patch('half_orm_dev.utils.hop_version')
    @patch('os.makedirs')
    @patch('builtins.open', new_callable=mock_open)
    def test_initialize_configuration_creates_config_object(self, mock_file, mock_makedirs, mock_hop_version):
        """Test that Config object is created and stored."""
        mock_hop_version.return_value = "0.16.0"

        repo = Repo.__new__(Repo)
        repo._Repo__checked = False
        repo._Repo__base_dir = "/test/project"

        repo._initialize_configuration("my_blog", devel_mode=True, git_origin="git@git.example.com:user/repo")

        # Should have created and stored Config instance
        assert hasattr(repo, '_Repo__config')
        assert repo._Repo__config is not None
        assert isinstance(repo._Repo__config, Config)

    @patch('os.makedirs')
    @patch('builtins.open', new_callable=mock_open)
    def test_initialize_configuration_config_has_correct_attributes(self, mock_file, mock_makedirs):
        """Test that Config object has correct attributes."""
        repo = Repo.__new__(Repo)
        repo._Repo__checked = False
        repo._Repo__base_dir = "/test/project"

        repo._initialize_configuration("my_blog", devel_mode=True, git_origin="git@git.example.com:user/repo")

        config = repo._Repo__config

        # Verify config properties
        assert config.name == "my_blog"
        assert config.devel is True
        assert config.hop_version is not None  # Version set by Config.write()
        assert config.git_origin == "git@git.example.com:user/repo"

    @patch('os.makedirs')
    def test_initialize_configuration_handles_permission_error(self, mock_makedirs):
        """Test error handling when .hop directory creation fails."""
        mock_makedirs.side_effect = PermissionError("Permission denied")

        repo = Repo.__new__(Repo)
        repo._Repo__checked = False
        repo._Repo__base_dir = "/readonly/project"

        with pytest.raises(PermissionError):
            repo._initialize_configuration("my_blog", devel_mode=True, git_origin="git@git.example.com:user/repo")

    @patch('os.makedirs')
    @patch('builtins.open', new_callable=mock_open)
    def test_initialize_configuration_handles_write_error(self, mock_file, mock_makedirs):
        """Test error handling when config file write fails."""
        mock_file.side_effect = OSError("Disk full")

        repo = Repo.__new__(Repo)
        repo._Repo__checked = False
        repo._Repo__base_dir = "/test/project"

        with pytest.raises(OSError):
            repo._initialize_configuration("my_blog", devel_mode=True, git_origin="git@git.example.com:user/repo")