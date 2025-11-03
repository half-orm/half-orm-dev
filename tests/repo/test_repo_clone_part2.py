"""
Unit tests for Repo.clone_repo() method - Part 2: Error cases.

Tests covering:
- Directory already exists error
- Git clone failures
- Git checkout failures
- .hop/alt_config creation errors
- Database setup failures
- Schema restoration failures
- Timeout handling
"""

import pytest
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch, mock_open

from half_orm_dev.repo import Repo, RepoError
from half_orm_dev.database import Database


class TestCloneRepoErrors:
    """Test error handling in clone_repo."""

    def setup_method(self):
        """Clear singleton instances before each test."""
        Repo.clear_instances()

    def teardown_method(self):
        """Clear singleton instances after each test."""
        Repo.clear_instances()

    @patch('pathlib.Path.cwd')
    @patch('pathlib.Path.exists')
    def test_clone_repo_directory_exists_error(self, mock_exists, mock_cwd):
        """Test error when destination directory already exists."""
        mock_cwd.return_value = Path('/current/dir')
        mock_exists.return_value = True  # Directory exists

        with pytest.raises(FileExistsError, match="already exists"):
            Repo.clone_repo("https://github.com/user/project.git")

    @patch('subprocess.run')
    @patch('pathlib.Path.cwd')
    @patch('pathlib.Path.exists')
    def test_clone_repo_git_clone_fails(self, mock_exists, mock_cwd, mock_subprocess):
        """Test error handling when git clone fails."""
        mock_cwd.return_value = Path('/current/dir')
        mock_exists.return_value = False

        # Simulate git clone failure
        mock_subprocess.side_effect = subprocess.CalledProcessError(
            returncode=128,
            cmd=["git", "clone"],
            stderr="fatal: repository not found"
        )

        with pytest.raises(RepoError, match="Git clone failed"):
            Repo.clone_repo("https://github.com/user/invalid.git")

    @patch('subprocess.run')
    @patch('pathlib.Path.cwd')
    @patch('pathlib.Path.exists')
    def test_clone_repo_git_clone_timeout(self, mock_exists, mock_cwd, mock_subprocess):
        """Test error handling when git clone times out."""
        mock_cwd.return_value = Path('/current/dir')
        mock_exists.return_value = False

        # Simulate timeout
        mock_subprocess.side_effect = subprocess.TimeoutExpired(
            cmd=["git", "clone"],
            timeout=300
        )

        with pytest.raises(RepoError, match="timed out"):
            Repo.clone_repo("https://github.com/user/huge-repo.git")

    @patch('subprocess.run')
    @patch('os.chdir')
    @patch('pathlib.Path.cwd')
    @patch('pathlib.Path.exists')
    def test_clone_repo_git_checkout_fails(
        self, mock_exists, mock_cwd, mock_chdir, mock_subprocess
    ):
        """Test error when git checkout ho-prod fails."""
        mock_cwd.return_value = Path('/current/dir')
        mock_exists.return_value = False

        # First call (clone) succeeds, second call (checkout) fails
        mock_subprocess.side_effect = [
            Mock(returncode=0, stderr='', stdout=''),  # git clone succeeds
            subprocess.CalledProcessError(
                returncode=1,
                cmd=["git", "checkout", "ho-prod"],
                stderr="error: pathspec 'ho-prod' did not match"
            )
        ]

        with pytest.raises(RepoError, match="Git checkout ho-prod failed"):
            Repo.clone_repo("https://github.com/user/project.git")

        # Verify chdir was called before checkout failure
        mock_chdir.assert_called_once()

    @patch('subprocess.run')
    @patch('os.chdir')
    @patch('pathlib.Path.cwd')
    @patch('pathlib.Path.exists')
    @patch('builtins.open', new_callable=mock_open)
    def test_clone_repo_alt_config_creation_fails(
        self, mock_file, mock_exists, mock_cwd, mock_chdir, mock_subprocess
    ):
        """Test error when .hop/alt_config creation fails."""
        mock_cwd.return_value = Path('/current/dir')
        mock_exists.return_value = False
        mock_subprocess.return_value = Mock(returncode=0, stderr='', stdout='')

        # Simulate file write error
        mock_file.side_effect = PermissionError("Permission denied")

        with pytest.raises(RepoError, match="Failed to create .hop/alt_config"):
            Repo.clone_repo(
                "https://github.com/user/project.git",
                database_name="custom_db"
            )

    @patch('subprocess.run')
    @patch('os.chdir')
    @patch('pathlib.Path.cwd')
    @patch('pathlib.Path.exists')
    @patch('half_orm_dev.repo.Config')
    @patch('half_orm_dev.database.Database.setup_database')
    def test_clone_repo_database_setup_fails(
        self, mock_setup_db, mock_config, mock_exists, mock_cwd,
        mock_chdir, mock_subprocess
    ):
        """Test error when Database.setup_database fails."""
        mock_cwd.return_value = Path('/current/dir')
        mock_exists.return_value = False
        mock_subprocess.return_value = Mock(returncode=0, stderr='', stdout='')

        mock_config_instance = Mock()
        mock_config_instance.name = 'test_project'
        mock_config.return_value = mock_config_instance

        # Simulate database setup failure
        mock_setup_db.side_effect = Exception("Connection refused")

        with pytest.raises(RepoError, match="Database setup failed"):
            Repo.clone_repo("https://github.com/user/project.git")

    @patch('subprocess.run')
    @patch('os.chdir')
    @patch('pathlib.Path.cwd')
    @patch('pathlib.Path.exists')
    @patch('half_orm_dev.repo.Config')
    @patch('half_orm_dev.database.Database.setup_database')
    def test_clone_repo_schema_restoration_fails(
        self, mock_setup_db, mock_config, mock_exists, mock_cwd,
        mock_chdir, mock_subprocess
    ):
        """Test error when restore_database_from_schema fails."""
        mock_cwd.return_value = Path('/current/dir')
        mock_exists.return_value = False
        mock_subprocess.return_value = Mock(returncode=0, stderr='', stdout='')

        mock_config_instance = Mock()
        mock_config_instance.name = 'test_project'
        mock_config.return_value = mock_config_instance

        # Mock Repo instance with failing restore
        mock_repo = Mock()
        mock_repo.restore_database_from_schema.side_effect = RepoError(
            "Schema file not found"
        )

        with patch.object(Repo, '__new__', return_value=mock_repo):
            with pytest.raises(RepoError, match="Failed to restore database from schema"):
                Repo.clone_repo("https://github.com/user/project.git")

    @patch('subprocess.run')
    @patch('pathlib.Path.cwd')
    @patch('pathlib.Path.exists')
    def test_clone_repo_custom_dest_dir(self, mock_exists, mock_cwd, mock_subprocess):
        """Test clone with custom destination directory name."""
        mock_cwd.return_value = Path('/current/dir')
        mock_exists.return_value = False
        mock_subprocess.return_value = Mock(returncode=0, stderr='', stdout='')

        with patch('os.chdir'), \
             patch('half_orm_dev.repo.Config') as mock_config, \
             patch('half_orm_dev.database.Database.setup_database'):

            mock_config_instance = Mock()
            mock_config_instance.name = 'test_project'
            mock_config.return_value = mock_config_instance

            mock_repo = Mock()
            mock_repo.restore_database_from_schema = Mock()

            with patch.object(Repo, '__new__', return_value=mock_repo):
                Repo.clone_repo(
                    "https://github.com/user/project.git",
                    dest_dir="custom_name"
                )

        # Verify custom destination used
        clone_call = mock_subprocess.call_args_list[0]
        clone_cmd = clone_call[0][0]  # First positional arg is the command list

        # clone_cmd = ["git", "clone", "https://...", "/dest/path"]
        # Index 3 is the destination path
        dest_path = clone_cmd[3]
        assert dest_path == str(Path('/current/dir') / 'custom_name')
