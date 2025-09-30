"""
Tests pour l'initialisation de la classe HGit.

Module de test focalisé uniquement sur TestHGitInitialization :
- Tests d'initialisation avec et sans paramètre repo
- Tests de __post_init et configuration des attributs privés
- Tests d'intégration avec git.Repo sans dépendance PostgreSQL
"""

import pytest
import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import git
from git.exc import GitCommandError

from half_orm_dev.hgit import HGit


class TestHGitInitialization:
    """Test HGit initialization and basic setup."""

    @pytest.fixture
    def mock_repo(self):
        """Mock repository object for testing."""
        repo = Mock()
        repo.git_origin = "https://github.com/user/project.git"
        repo.base_dir = "/tmp/test_project"
        return repo

    @pytest.fixture
    def mock_repo_empty_origin(self):
        """Mock repository object with empty git_origin."""
        repo = Mock()
        repo.git_origin = ""
        repo.base_dir = "/tmp/test_project"
        return repo

    def test_init_without_repo(self):
        """Test HGit initialization without repo parameter."""
        hgit = HGit()

        # Should initialize basic attributes as None
        assert hasattr(hgit, '_HGit__origin')
        assert hasattr(hgit, '_HGit__repo')
        assert hasattr(hgit, '_HGit__base_dir')
        assert hasattr(hgit, '_HGit__git_repo')

        # All should be None when no repo provided
        assert hgit._HGit__origin is None
        assert hgit._HGit__repo is None
        assert hgit._HGit__base_dir is None
        assert hgit._HGit__git_repo is None

    def test_init_with_none_repo(self):
        """Test HGit initialization with explicit None repo."""
        hgit = HGit(None)

        # Should behave same as no parameter
        assert hgit._HGit__origin is None
        assert hgit._HGit__repo is None
        assert hgit._HGit__base_dir is None
        assert hgit._HGit__git_repo is None

    @patch('git.Repo')
    def test_init_with_repo_triggers_post_init(self, mock_git_repo, mock_repo):
        """Test HGit initialization with repo triggers __post_init."""
        # Setup git.Repo mock
        mock_git_repo_instance = Mock()
        mock_git_repo.return_value = mock_git_repo_instance
        mock_git_repo_instance.git.remote.return_value = "https://github.com/user/project.git"
        mock_git_repo_instance.active_branch = "ho-prod"

        hgit = HGit(mock_repo)

        # Should have set attributes from repo
        assert hgit._HGit__origin == mock_repo.git_origin
        assert hgit._HGit__repo == mock_repo
        assert hgit._HGit__base_dir == mock_repo.base_dir

        # Should have called git.Repo with base_dir
        mock_git_repo.assert_called_once_with(mock_repo.base_dir)

    @patch('git.Repo')
    @patch('half_orm_dev.hgit.utils.warning')
    def test_post_init_no_origin_warning(self, mock_warning, mock_git_repo, mock_repo):
        """Test __post_init handles missing git origin with warning."""
        # Setup git.Repo to raise exception for get-url
        mock_git_repo_instance = Mock()
        mock_git_repo.return_value = mock_git_repo_instance
        mock_git_repo_instance.git.remote.side_effect = Exception("No remote origin")
        mock_git_repo_instance.active_branch = "ho-prod"

        hgit = HGit(mock_repo)

        # Should have warned about missing origin
        assert mock_warning.called
        warning_call_args = mock_warning.call_args[0][0]
        assert "No origin" in warning_call_args

    @patch('git.Repo')
    @patch('half_orm_dev.hgit.utils.error')
    def test_post_init_origin_mismatch_error(self, mock_error, mock_git_repo, mock_repo):
        """Test __post_init handles origin mismatch with error."""
        # Setup conflicting origins
        mock_repo.git_origin = "https://github.com/user/project.git"

        mock_git_repo_instance = Mock()
        mock_git_repo.return_value = mock_git_repo_instance
        mock_git_repo_instance.git.remote.return_value = "https://github.com/other/repo.git"
        mock_git_repo_instance.active_branch = "ho-prod"

        hgit = HGit(mock_repo)

        # Should have called error for origin mismatch
        assert mock_error.called
        error_call_args = mock_error.call_args[0][0]
        assert "Git remote origin should be" in error_call_args

    @patch('git.Repo')
    def test_post_init_sets_origin_from_git(self, mock_git_repo, mock_repo_empty_origin):
        """Test __post_init sets origin from git when repo origin is empty."""
        git_origin = "https://github.com/discovered/repo.git"

        # Setup mocks
        mock_git_repo_instance = Mock()
        mock_git_repo.return_value = mock_git_repo_instance
        mock_git_repo_instance.git.remote.return_value = git_origin
        mock_git_repo_instance.active_branch = "ho-prod"
        mock_git_repo_instance.git.push = Mock()

        # Mock file operations for config update
        with patch('os.path.join', return_value='.hop/config'):
            hgit = HGit(mock_repo_empty_origin)

        # Should have updated repo git_origin
        assert mock_repo_empty_origin.git_origin == git_origin

        # Should have added config file and committed
        mock_git_repo_instance.git.add.assert_called()
        mock_git_repo_instance.git.commit.assert_called()
        mock_git_repo_instance.git.push.assert_called_with('-u', 'origin', 'ho-prod')

    @patch('git.Repo')
    def test_post_init_stores_current_branch(self, mock_git_repo, mock_repo):
        """Test __post_init stores current branch."""
        branch_name = "hop_feature_branch"

        mock_git_repo_instance = Mock()
        mock_git_repo.return_value = mock_git_repo_instance
        mock_git_repo_instance.git.remote.return_value = mock_repo.git_origin
        mock_git_repo_instance.active_branch = branch_name

        hgit = HGit(mock_repo)

        # Should have stored current branch
        assert hasattr(hgit, '_HGit__current_branch')
        assert hgit._HGit__current_branch == str(branch_name)

    def test_str_representation_basic(self):
        """Test string representation of HGit object."""
        # Create HGit without triggering __post_init
        hgit = HGit()
        hgit._HGit__origin = "https://github.com/user/repo.git"
        hgit._HGit__current_branch = "ho-prod"

        # Mock the methods called by __str__
        with patch.object(hgit, 'repos_is_clean', return_value=True), \
             patch.object(hgit, 'last_commit', return_value='abc12345'):

            str_repr = str(hgit)

            # Should contain expected sections
            assert '[Git]' in str_repr
            assert 'origin:' in str_repr
            assert 'current branch:' in str_repr
            assert 'repo is clean:' in str_repr
            assert 'last commit:' in str_repr
            assert 'ho-prod' in str_repr
            assert 'abc12345' in str_repr

    @patch('half_orm_dev.hgit.utils.Color.red')
    def test_str_representation_no_origin(self, mock_color_red):
        """Test string representation with no origin."""
        mock_color_red.return_value = "No origin"

        hgit = HGit()
        hgit._HGit__origin = None
        hgit._HGit__current_branch = "ho-prod"

        with patch.object(hgit, 'repos_is_clean', return_value=True), \
             patch.object(hgit, 'last_commit', return_value='abc12345'):

            str_repr = str(hgit)

            # Should show "No origin" message
            assert 'No origin' in str_repr
            mock_color_red.assert_called_with("No origin")

    @patch('half_orm_dev.hgit.utils.Color.green')
    @patch('half_orm_dev.hgit.utils.Color.red')
    def test_str_representation_repo_status_colors(self, mock_color_red, mock_color_green):
        """Test string representation uses colors for repo status."""
        mock_color_green.return_value = "True"
        mock_color_red.return_value = "False"

        hgit = HGit()
        hgit._HGit__origin = "https://github.com/user/repo.git"
        hgit._HGit__current_branch = "ho-prod"

        # Test with clean repo
        with patch.object(hgit, 'repos_is_clean', return_value=True), \
             patch.object(hgit, 'last_commit', return_value='abc12345'):

            str_repr = str(hgit)
            mock_color_green.assert_called_with(True)

        # Test with dirty repo
        with patch.object(hgit, 'repos_is_clean', return_value=False), \
             patch.object(hgit, 'last_commit', return_value='abc12345'):

            str_repr = str(hgit)
            mock_color_red.assert_called_with(False)

    def test_attributes_after_initialization(self, mock_repo):
        """Test that all expected attributes exist after initialization."""
        with patch('git.Repo') as mock_git_repo:
            mock_git_repo_instance = Mock()
            mock_git_repo.return_value = mock_git_repo_instance
            mock_git_repo_instance.git.remote.return_value = mock_repo.git_origin
            mock_git_repo_instance.active_branch = "ho-prod"

            hgit = HGit(mock_repo)

            # Check all private attributes exist
            required_attrs = [
                '_HGit__origin',
                '_HGit__repo', 
                '_HGit__base_dir',
                '_HGit__git_repo',
                '_HGit__current_branch'
            ]

            for attr in required_attrs:
                assert hasattr(hgit, attr), f"Missing attribute: {attr}"
