"""
Tests for Repo.init_git_centric_project() with git_origin parameter

Focused on:
- Accepting git_origin parameter
- Validating git_origin URL
- Storing git_origin in configuration
- Passing git_origin to HGit initialization
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, mock_open

from half_orm_dev.repo import Repo


class TestInitGitCentricProjectWithGitOrigin:
    """Test init_git_centric_project() with git_origin parameter."""

    def setup_method(self):
        """Clear singleton instances before each test."""
        Repo.clear_instances()

    def teardown_method(self):
        """Clear singleton instances after each test."""
        Repo.clear_instances()

    @pytest.fixture
    def mock_environment(self):
        """Mock environment for init_git_centric_project tests."""
        with patch('half_orm_dev.repo.HGit') as mock_hgit, \
             patch('half_orm_dev.repo.Database') as mock_db, \
             patch('half_orm.model.Model') as mock_model, \
             patch('half_orm_dev.modules.generate') as mock_generate, \
             patch('os.makedirs') as mock_makedirs, \
             patch('os.path.exists') as mock_exists, \
             patch('os.path.abspath') as mock_abspath, \
             patch('os.chmod') as mock_chmod, \
             patch('shutil.copy') as mock_shutil_copy, \
             patch('builtins.open', new_callable=mock_open) as mock_file:

            # Setup common defaults
            mock_abspath.return_value = "/test/path"
            mock_exists.return_value = False

            mock_model_instance = Mock()
            mock_model_instance.has_relation.return_value = True
            mock_model.return_value = mock_model_instance

            mock_db_instance = Mock()
            mock_db.return_value = mock_db_instance

            yield {
                'hgit': mock_hgit,
                'db': mock_db,
                'model': mock_model,
                'generate': mock_generate,
                'makedirs': mock_makedirs,
                'exists': mock_exists,
                'abspath': mock_abspath,
                'chmod': mock_chmod,
                'shutil_copy': mock_shutil_copy,
                'file': mock_file,
            }

    @pytest.fixture
    def bare_repo(self):
        """Create bare Repo instance for testing."""
        repo = Repo.__new__(Repo)
        repo._Repo__checked = False
        return repo

    def test_init_with_valid_git_origin_https(self, mock_environment, bare_repo):
        """Test init_git_centric_project with valid HTTPS git origin."""
        git_origin = "https://github.com/user/my_blog.git"

        # Should not raise exception
        bare_repo.init_git_centric_project(
            package_name="my_blog",
            git_origin=git_origin
        )

        # Verify git_origin was stored in config
        assert bare_repo._Repo__config.git_origin == git_origin

    def test_init_with_valid_git_origin_ssh(self, mock_environment, bare_repo):
        """Test init_git_centric_project with valid SSH git origin."""
        git_origin = "git@github.com:user/my_blog.git"

        # Should not raise exception
        bare_repo.init_git_centric_project(
            package_name="my_blog",
            git_origin=git_origin
        )

        # Verify git_origin was stored in config
        assert bare_repo._Repo__config.git_origin == git_origin

    def test_init_with_invalid_git_origin_raises_error(self, bare_repo):
        """Test init_git_centric_project with invalid git origin raises ValueError."""
        # Invalid URL should raise ValueError
        with pytest.raises(ValueError, match="Invalid Git origin URL format"):
            bare_repo.init_git_centric_project(
                package_name="my_blog",
                git_origin="not-a-valid-url"
            )

    def test_init_with_empty_git_origin_raises_error(self, bare_repo):
        """Test init_git_centric_project with empty git origin raises ValueError."""
        with pytest.raises(ValueError, match="Git origin URL cannot be empty"):
            bare_repo.init_git_centric_project(
                package_name="my_blog",
                git_origin=""
            )

    def test_init_with_none_git_origin_raises_error(self, bare_repo):
        """Test init_git_centric_project with None git origin raises ValueError."""
        with pytest.raises(ValueError, match="Git origin URL cannot be None"):
            bare_repo.init_git_centric_project(
                package_name="my_blog",
                git_origin=None
            )

    def test_init_validates_git_origin_before_other_steps(self, mock_environment, bare_repo):
        """Test git_origin validation happens early (before directory creation)."""
        # Should fail validation before any directory is created
        with pytest.raises(ValueError, match="Invalid Git origin URL format"):
            bare_repo.init_git_centric_project(
                package_name="my_blog",
                git_origin="invalid-url"
            )

        # Verify no directories were created (validation failed early)
        mock_environment['makedirs'].assert_not_called()

    def test_init_strips_whitespace_from_git_origin(self, mock_environment, bare_repo):
        """Test git_origin whitespace is stripped during validation."""
        git_origin_with_whitespace = "  https://github.com/user/my_blog.git  "
        expected_git_origin = "https://github.com/user/my_blog.git"

        bare_repo.init_git_centric_project(
            package_name="my_blog",
            git_origin=git_origin_with_whitespace
        )

        # Should have stripped whitespace
        assert bare_repo._Repo__config.git_origin == expected_git_origin

    def test_init_with_self_hosted_git_origin(self, mock_environment, bare_repo):
        """Test init_git_centric_project with self-hosted Git server."""
        git_origin = "https://git.company.com/team/my_blog.git"

        bare_repo.init_git_centric_project(
            package_name="my_blog",
            git_origin=git_origin
        )

        assert bare_repo._Repo__config.git_origin == git_origin

    def test_init_git_origin_stored_in_config_file(self, mock_environment, bare_repo):
        """Test git_origin is written to .hop/config file."""
        git_origin = "https://github.com/user/my_blog.git"

        bare_repo.init_git_centric_project(
            package_name="my_blog",
            git_origin=git_origin
        )

        # Verify config file was written with git_origin
        mock_file = mock_environment['file']
        handle = mock_file()

        # Get all written content
        written_content = ''.join(
            call.args[0] for call in handle.write.call_args_list if call.args
        )

        # Should contain git_origin in config
        assert 'git_origin' in written_content
        assert git_origin in written_content
