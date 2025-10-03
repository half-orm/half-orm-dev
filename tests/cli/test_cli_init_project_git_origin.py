"""
Tests for init-project CLI command with --git-origin parameter

Focused on:
- --git-origin parameter (optional)
- Interactive prompt when git_origin not provided
- Validation of git_origin from CLI or prompt
- Error handling for invalid URLs
"""

import pytest
from click.testing import CliRunner
from unittest.mock import patch, Mock

from half_orm_dev.cli.commands.init_project import init_project


class TestInitProjectCLIWithGitOrigin:
    """Test init-project CLI command with git_origin parameter."""

    @pytest.fixture
    def runner(self):
        """Create Click CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def mock_repo_success(self):
        """Mock successful Repo.init_git_centric_project()."""
        with patch('half_orm_dev.cli.commands.init_project.Repo') as mock_repo_class:
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.init_git_centric_project = Mock()
            yield mock_repo

    # === With --git-origin parameter ===

    def test_init_project_with_git_origin_parameter_https(self, runner, mock_repo_success):
        """Test init-project with --git-origin HTTPS URL."""
        result = runner.invoke(init_project, [
            'my_blog',
            '--git-origin', 'https://github.com/user/my_blog.git'
        ])

        # Should succeed
        assert result.exit_code == 0
        assert '✅' in result.output
        assert 'initialized successfully' in result.output

        # Should have called init_git_centric_project with git_origin
        mock_repo_success.init_git_centric_project.assert_called_once_with(
            package_name='my_blog',
            git_origin='https://github.com/user/my_blog.git'
        )

    def test_init_project_with_git_origin_parameter_ssh(self, runner, mock_repo_success):
        """Test init-project with --git-origin SSH URL."""
        result = runner.invoke(init_project, [
            'my_blog',
            '--git-origin', 'git@github.com:user/my_blog.git'
        ])

        assert result.exit_code == 0
        mock_repo_success.init_git_centric_project.assert_called_once_with(
            package_name='my_blog',
            git_origin='git@github.com:user/my_blog.git'
        )

    def test_init_project_with_invalid_git_origin_parameter(self, runner, mock_repo_success):
        """Test init-project with invalid --git-origin raises error."""
        # Mock validation error
        mock_repo_success.init_git_centric_project.side_effect = ValueError(
            "Invalid Git origin URL format"
        )

        result = runner.invoke(init_project, [
            'my_blog',
            '--git-origin', 'invalid-url'
        ])

        # Should fail with error message
        assert result.exit_code != 0
        assert 'Invalid Git origin URL format' in result.output

    # === Without --git-origin parameter (interactive) ===

    def test_init_project_without_git_origin_prompts(self, runner, mock_repo_success):
        """Test init-project without --git-origin prompts interactively."""
        result = runner.invoke(init_project, ['my_blog'], input='https://github.com/user/my_blog.git\n')

        # Should succeed
        assert result.exit_code == 0
        assert '✅' in result.output

        # Should have prompted for git_origin
        assert 'Git remote origin URL' in result.output

        # Should have called init_git_centric_project with prompted value
        mock_repo_success.init_git_centric_project.assert_called_once_with(
            package_name='my_blog',
            git_origin='https://github.com/user/my_blog.git'
        )

    def test_init_project_prompt_validates_url(self, runner, mock_repo_success):
        """Test interactive prompt validates URL and re-prompts on invalid input."""
        # First input invalid, second valid
        result = runner.invoke(
            init_project,
            ['my_blog'],
            input='invalid-url\nhttps://github.com/user/my_blog.git\n'
        )

        # Should eventually succeed
        assert result.exit_code == 0

        # Should show validation error for first attempt
        assert 'Invalid Git origin URL format' in result.output or 'invalid' in result.output.lower()

        # Should have called init_git_centric_project with valid value
        mock_repo_success.init_git_centric_project.assert_called_once()

    def test_init_project_prompt_strips_whitespace(self, runner, mock_repo_success):
        """Test interactive prompt strips whitespace from input."""
        result = runner.invoke(
            init_project,
            ['my_blog'],
            input='  https://github.com/user/my_blog.git  \n'
        )

        assert result.exit_code == 0

        # Should have called with stripped URL
        mock_repo_success.init_git_centric_project.assert_called_once_with(
            package_name='my_blog',
            git_origin='https://github.com/user/my_blog.git'
        )

    def test_init_project_prompt_empty_input_re_prompts(self, runner, mock_repo_success):
        """Test interactive prompt re-prompts on empty input."""
        result = runner.invoke(
            init_project,
            ['my_blog'],
            input='\nhttps://github.com/user/my_blog.git\n'
        )

        # Should eventually succeed (click.prompt re-prompts automatically on empty)
        assert result.exit_code == 0

        # Should have called with valid URL eventually
        mock_repo_success.init_git_centric_project.assert_called_once_with(
            package_name='my_blog',
            git_origin='https://github.com/user/my_blog.git'
        )

    # === Mixed scenarios ===

    def test_init_project_cli_parameter_takes_precedence(self, runner, mock_repo_success):
        """Test --git-origin parameter takes precedence over prompt."""
        # Even if we provide input, CLI parameter should be used
        result = runner.invoke(
            init_project,
            ['my_blog', '--git-origin', 'https://github.com/user/my_blog.git'],
            input='https://github.com/other/repo.git\n'  # This should be ignored
        )

        assert result.exit_code == 0

        # Should use CLI parameter, not prompt input
        mock_repo_success.init_git_centric_project.assert_called_once_with(
            package_name='my_blog',
            git_origin='https://github.com/user/my_blog.git'
        )

    def test_init_project_help_shows_git_origin_option(self, runner):
        """Test --help shows --git-origin option."""
        result = runner.invoke(init_project, ['--help'])

        assert result.exit_code == 0
        assert '--git-origin' in result.output
        assert 'Git remote origin URL' in result.output

    # === Edge cases ===

    def test_init_project_with_self_hosted_git_url(self, runner, mock_repo_success):
        """Test init-project with self-hosted Git server URL."""
        result = runner.invoke(init_project, [
            'my_blog',
            '--git-origin', 'https://git.company.com/team/project.git'
        ])

        assert result.exit_code == 0
        mock_repo_success.init_git_centric_project.assert_called_once_with(
            package_name='my_blog',
            git_origin='https://git.company.com/team/project.git'
        )
