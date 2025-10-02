"""
Tests updates for simplified HGit.__post_init()

Changes:
- No origin: raises SystemExit (not warning)
- Origin mismatch: raises SystemExit (not just error call)
- Remove test for auto-discovery behavior (removed from implementation)
"""

import pytest
from unittest.mock import Mock, patch
from half_orm_dev.hgit import HGit


class TestPostInitSimplified:
    """Test simplified __post_init behavior."""

    @pytest.fixture
    def mock_repo(self):
        """Mock repository object for testing."""
        repo = Mock()
        repo.git_origin = "https://github.com/user/project.git"
        repo.base_dir = "/tmp/test_project"
        return repo

    @patch('git.Repo')
    def test_post_init_no_origin_raises_system_exit(self, mock_git_repo, mock_repo):
        """Test __post_init raises SystemExit when no git origin configured."""
        # Setup git.Repo to raise exception for get-url (no remote)
        mock_git_repo_instance = Mock()
        mock_git_repo.return_value = mock_git_repo_instance
        mock_git_repo_instance.git.remote.side_effect = Exception("fatal: No such remote 'origin'")
        mock_git_repo_instance.active_branch = "ho-prod"

        # Should raise SystemExit due to utils.error(exit_code=1)
        with pytest.raises(SystemExit) as exc_info:
            HGit(mock_repo)

        # Verify exit code
        assert exc_info.value.code == 1

    @patch('git.Repo')
    def test_post_init_origin_mismatch_raises_system_exit(self, mock_git_repo, mock_repo):
        """Test __post_init raises SystemExit on origin mismatch."""
        # Setup conflicting origins
        mock_repo.git_origin = "https://github.com/user/project.git"

        mock_git_repo_instance = Mock()
        mock_git_repo.return_value = mock_git_repo_instance
        mock_git_repo_instance.git.remote.return_value = "https://github.com/other/repo.git"
        mock_git_repo_instance.active_branch = "ho-prod"

        # Should raise SystemExit due to utils.error(exit_code=1)
        with pytest.raises(SystemExit) as exc_info:
            HGit(mock_repo)

        # Verify exit code
        assert exc_info.value.code == 1

    @patch('git.Repo')
    def test_post_init_success_when_origins_match(self, mock_git_repo, mock_repo):
        """Test __post_init succeeds when origins match."""
        mock_repo.git_origin = "https://github.com/user/project.git"

        mock_git_repo_instance = Mock()
        mock_git_repo.return_value = mock_git_repo_instance
        mock_git_repo_instance.git.remote.return_value = "https://github.com/user/project.git"
        mock_git_repo_instance.active_branch = "ho-prod"

        # Should not raise
        hgit = HGit(mock_repo)

        # Should have stored current branch
        assert hasattr(hgit, '_HGit__current_branch')
        assert hgit._HGit__current_branch == "ho-prod"

    @patch('git.Repo')
    def test_post_init_empty_origin_in_config_with_git_remote_raises(self, mock_git_repo):
        """Test __post_init with empty config origin but git remote exists."""
        # Mock repo with empty git_origin
        mock_repo = Mock()
        mock_repo.git_origin = ""  # Empty in config
        mock_repo.base_dir = "/tmp/test_project"

        mock_git_repo_instance = Mock()
        mock_git_repo.return_value = mock_git_repo_instance
        mock_git_repo_instance.git.remote.return_value = "https://github.com/discovered/repo.git"
        mock_git_repo_instance.active_branch = "ho-prod"

        # Should raise SystemExit (mismatch: '' != 'https://...')
        with pytest.raises(SystemExit) as exc_info:
            HGit(mock_repo)

        assert exc_info.value.code == 1
