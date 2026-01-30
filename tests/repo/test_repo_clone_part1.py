"""
Unit tests for Repo.clone_repo() method - Part 1: Success cases and validation.

Tests covering:
- Successful clone workflow
- Destination directory name handling (.git extension removal)
- Custom database name with .hop/alt_config creation
- Production mode parameter usage
- Directory existence validation
"""

import pytest
import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, mock_open, call

from half_orm_dev.repo import Repo, RepoError, Config
from half_orm_dev.database import Database


class TestCloneRepoSuccess:
    """Test successful clone_repo workflows."""

    def setup_method(self):
        """Clear singleton instances before each test."""
        Repo.clear_instances()

    def teardown_method(self):
        """Clear singleton instances after each test."""
        Repo.clear_instances()

    @patch('subprocess.run')
    @patch('os.chdir')
    @patch('pathlib.Path.cwd')
    @patch('pathlib.Path.exists')
    @patch('half_orm_dev.repo.Config')
    @patch('half_orm_dev.database.Database.setup_database')
    def test_clone_repo_basic_success(
        self, mock_setup_db, mock_config, mock_exists, mock_cwd,
        mock_chdir, mock_subprocess
    ):
        """Test basic successful clone workflow."""
        # Setup mocks
        mock_cwd.return_value = Path('/current/dir')
        mock_exists.return_value = False  # Destination doesn't exist
        mock_subprocess.return_value = Mock(returncode=0, stderr='', stdout='')

        mock_config_instance = Mock()
        mock_config_instance.name = 'test_project'
        mock_config.return_value = mock_config_instance

        # Mock Repo instance
        mock_repo = Mock()
        mock_repo.restore_database_from_schema = Mock()
        mock_repo.install_git_hooks = Mock()

        with patch.object(Repo, '__new__', return_value=mock_repo):
            # Execute clone
            Repo.clone_repo("https://github.com/user/project.git")

        # Verify subprocess.run called twice (clone + checkout)
        assert mock_subprocess.call_count == 2

        # Verify git clone called with correct arguments
        clone_call = mock_subprocess.call_args_list[0]
        # First positional argument is the command list
        clone_cmd = clone_call[0][0]

        assert clone_cmd[0] == "git"
        assert clone_cmd[1] == "clone"
        assert clone_cmd[2] == "https://github.com/user/project.git"
        assert clone_cmd[3] == str(Path('/current/dir') / 'project')

        # Verify git checkout called
        checkout_call = mock_subprocess.call_args_list[1]
        checkout_cmd = checkout_call[0][0]

        assert checkout_cmd == ["git", "checkout", "ho-prod"]

        # Verify chdir to cloned directory
        mock_chdir.assert_called_once_with(Path('/current/dir') / 'project')

        # Verify database setup called
        mock_setup_db.assert_called_once()

        # Verify schema restoration called
        mock_repo.restore_database_from_schema.assert_called_once()

        # Verify Git hooks installation called
        mock_repo.install_git_hooks.assert_called_once()

    @patch('subprocess.run')
    @patch('os.chdir')
    @patch('pathlib.Path.cwd')
    @patch('pathlib.Path.exists')
    @patch('half_orm_dev.repo.Config')
    @patch('half_orm_dev.database.Database.setup_database')
    def test_clone_repo_removes_git_extension(
        self, mock_setup_db, mock_config, mock_exists, mock_cwd,
        mock_chdir, mock_subprocess
    ):
        """Test .git extension is removed from destination directory name."""
        mock_cwd.return_value = Path('/current/dir')
        mock_exists.return_value = False
        mock_subprocess.return_value = Mock(returncode=0, stderr='', stdout='')

        mock_config_instance = Mock()
        mock_config_instance.name = 'project'
        mock_config.return_value = mock_config_instance

        mock_repo = Mock()
        mock_repo.restore_database_from_schema = Mock()

        with patch.object(Repo, '__new__', return_value=mock_repo):
            Repo.clone_repo("https://github.com/user/project.git")

        # Verify destination path without .git extension
        # First call is git clone, first positional arg is the command list
        clone_call = mock_subprocess.call_args_list[0]
        clone_cmd = clone_call[0][0]

        # clone_cmd = ["git", "clone", "https://...", "/dest/path"]
        # Index 3 is the destination path
        dest_path = clone_cmd[3]
        assert dest_path == str(Path('/current/dir') / 'project')
        assert '.git' not in Path(dest_path).name

    @patch('subprocess.run')
    @patch('os.chdir')
    @patch('pathlib.Path.cwd')
    @patch('pathlib.Path.exists')
    @patch('builtins.open', new_callable=mock_open)
    @patch('half_orm_dev.repo.Config')
    @patch('half_orm_dev.database.Database.setup_database')
    def test_clone_repo_creates_alt_config(
        self, mock_setup_db, mock_config, mock_file, mock_exists,
        mock_cwd, mock_chdir, mock_subprocess
    ):
        """Test .hop/alt_config is created when custom database_name provided."""
        mock_cwd.return_value = Path('/current/dir')
        mock_exists.return_value = False
        mock_subprocess.return_value = Mock(returncode=0, stderr='', stdout='')

        mock_config_instance = Mock()
        mock_config_instance.name = 'custom_db_name'
        mock_config.return_value = mock_config_instance

        mock_repo = Mock()
        mock_repo.restore_database_from_schema = Mock()

        with patch.object(Repo, '__new__', return_value=mock_repo):
            Repo.clone_repo(
                "https://github.com/user/project.git",
                database_name="custom_db_name"
            )

        # Verify alt_config file created with correct path (accepts Path or str)
        assert mock_file.call_count == 1
        call_args = mock_file.call_args

        # Check path (can be Path or str)
        actual_path = call_args[0][0]
        expected_path = Path('/current/dir') / 'project' / '.hop' / 'alt_config'

        if isinstance(actual_path, Path):
            assert actual_path == expected_path
        else:
            assert actual_path == str(expected_path)

        # Check mode and encoding
        assert call_args[0][1] == 'w'
        assert call_args[1]['encoding'] == 'utf-8'

        # Verify database name written to file
        handle = mock_file()
        handle.write.assert_called_once_with("custom_db_name")

    @patch('subprocess.run')
    @patch('os.chdir')
    @patch('pathlib.Path.cwd')
    @patch('pathlib.Path.exists')
    @patch('half_orm_dev.repo.Config')
    @patch('half_orm_dev.database.Database.setup_database')
    def test_clone_repo_uses_production_parameter(
        self, mock_setup_db, mock_config, mock_exists, mock_cwd,
        mock_chdir, mock_subprocess
    ):
        """Test production parameter is passed to Database.setup_database."""
        mock_cwd.return_value = Path('/current/dir')
        mock_exists.return_value = False
        mock_subprocess.return_value = Mock(returncode=0, stderr='', stdout='')

        mock_config_instance = Mock()
        mock_config_instance.name = 'prod_project'
        mock_config.return_value = mock_config_instance

        mock_repo = Mock()
        mock_repo.restore_database_from_schema = Mock()

        with patch.object(Repo, '__new__', return_value=mock_repo):
            Repo.clone_repo(
                "https://github.com/user/project.git",
                connection_options={'production': True},
                create_db=False
            )

        # Verify production=True passed to setup_database
        call_kwargs = mock_setup_db.call_args[1]
        assert call_kwargs['connection_options']['production'] is True
        assert call_kwargs['create_db'] is False
