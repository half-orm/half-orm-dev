"""
Tests for Repo.init_git_centric_project() - Validation phase

Focused on:
- Package name validation (_validate_package_name)
- Project directory creation (_create_project_directory)
- Pre-requisite checks and error handling
"""

import pytest
import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from half_orm_dev.repo import Repo
from half_orm_dev.database import Database


class TestPackageNameValidation:
    """Test _validate_package_name() method."""

    def setup_method(self):
        """Clear singleton instances before each test."""
        Repo.clear_instances()

    def teardown_method(self):
        """Clear singleton instances after each test."""
        Repo.clear_instances()

    def test_validate_package_name_valid_lowercase(self):
        """Test validation of valid lowercase package name."""
        repo = Repo()

        # Should not raise any exception
        repo._validate_package_name("my_blog")
        repo._validate_package_name("my_app")
        repo._validate_package_name("database_project")

    def test_validate_package_name_valid_with_numbers(self):
        """Test validation of package name with numbers."""
        repo = Repo()

        # Should not raise - numbers allowed after first character
        repo._validate_package_name("app2024")
        repo._validate_package_name("my_app_v2")

    def test_validate_package_name_valid_with_hyphen_converted(self):
        """Test package name with hyphens (should be converted to underscores)."""
        repo = Repo()

        # Hyphens are common in project names, should convert to underscores
        repo._validate_package_name("my-blog")  # Internally converts to my_blog
        repo._validate_package_name("my-app-v2")

    def test_validate_package_name_empty_raises_error(self):
        """Test validation rejects empty package name."""
        repo = Repo()

        with pytest.raises(ValueError, match="Package name cannot be empty"):
            repo._validate_package_name("")

        with pytest.raises(ValueError, match="Package name cannot be empty"):
            repo._validate_package_name("   ")

    def test_validate_package_name_none_raises_error(self):
        """Test validation rejects None package name."""
        repo = Repo()

        with pytest.raises(ValueError, match="Package name cannot be None"):
            repo._validate_package_name(None)

    def test_validate_package_name_starts_with_digit_raises_error(self):
        """Test validation rejects package name starting with digit."""
        repo = Repo()

        with pytest.raises(ValueError, match="cannot start with a digit"):
            repo._validate_package_name("9app")

        with pytest.raises(ValueError, match="cannot start with a digit"):
            repo._validate_package_name("2024_project")

    def test_validate_package_name_invalid_characters_raises_error(self):
        """Test validation rejects invalid characters."""
        repo = Repo()

        with pytest.raises(ValueError, match="invalid characters"):
            repo._validate_package_name("my blog")  # Space

        with pytest.raises(ValueError, match="invalid characters"):
            repo._validate_package_name("my@app")  # Special char

        with pytest.raises(ValueError, match="invalid characters"):
            repo._validate_package_name("my.app")  # Dot (not valid in Python package)

    def test_validate_package_name_not_string_raises_error(self):
        """Test validation rejects non-string types."""
        repo = Repo()

        with pytest.raises(ValueError, match="must be a string"):
            repo._validate_package_name(123)

        with pytest.raises(ValueError, match="must be a string"):
            repo._validate_package_name(['my_app'])

    def test_validate_package_name_reserved_keywords_warning(self):
        """Test validation warns about Python reserved keywords."""
        repo = Repo()

        # Should raise warning or error for reserved keywords
        with pytest.raises(ValueError, match="reserved keyword"):
            repo._validate_package_name("import")

        with pytest.raises(ValueError, match="reserved keyword"):
            repo._validate_package_name("class")


class TestProjectDirectoryCreation:
    """Test _create_project_directory() method."""

    def setup_method(self):
        """Clear singleton instances before each test."""
        Repo.clear_instances()

    def teardown_method(self):
        """Clear singleton instances after each test."""
        Repo.clear_instances()

    @patch('os.makedirs')
    @patch('os.path.exists')
    @patch('os.path.abspath')
    def test_create_project_directory_success(self, mock_abspath, mock_exists, mock_makedirs):
        """Test successful project directory creation."""
        mock_abspath.return_value = "/current/path"
        mock_exists.return_value = False  # Directory doesn't exist

        # Create Repo without initializing (bypass __check)
        repo = Repo.__new__(Repo)
        repo._Repo__checked = False
        repo._Repo__base_dir = None

        repo._create_project_directory("my_blog")

        # Should create directory
        expected_path = "/current/path/my_blog"
        mock_makedirs.assert_called_once_with(expected_path)

        # Should store base_dir
        assert repo._Repo__base_dir == expected_path

    @patch('os.path.exists')
    @patch('os.path.abspath')
    def test_create_project_directory_already_exists_raises_error(self, mock_abspath, mock_exists):
        """Test error when project directory already exists."""
        mock_abspath.return_value = "/current/path"
        mock_exists.return_value = True  # Directory exists

        # Create Repo without initializing (bypass __check)
        repo = Repo.__new__(Repo)
        repo._Repo__checked = False
        repo._Repo__base_dir = None

        with pytest.raises(FileExistsError, match="already exists"):
            repo._create_project_directory("existing_project")

    @patch('os.makedirs')
    @patch('os.path.exists')
    @patch('os.path.abspath')
    def test_create_project_directory_permission_error(self, mock_abspath, mock_exists, mock_makedirs):
        """Test error when insufficient permissions to create directory."""
        mock_abspath.return_value = "/readonly/path"
        mock_exists.return_value = False
        mock_makedirs.side_effect = PermissionError("Permission denied")

        # Create Repo without initializing (bypass __check)
        repo = Repo.__new__(Repo)
        repo._Repo__checked = False
        repo._Repo__base_dir = None

        with pytest.raises(PermissionError):
            repo._create_project_directory("my_blog")