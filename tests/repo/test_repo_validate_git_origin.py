"""
Tests for Repo._validate_git_origin_url() method

Focused on:
- Git origin URL format validation
- Support for HTTPS, SSH, and Git protocols
- Support for common Git hosting services (GitHub, GitLab, Bitbucket)
- Support for self-hosted Git servers
- Error handling for invalid URLs
"""

import pytest
from half_orm_dev.repo import Repo


class TestValidateGitOriginUrl:
    """Test _validate_git_origin_url() method."""

    def setup_method(self):
        """Clear singleton instances before each test."""
        Repo.clear_instances()

    def teardown_method(self):
        """Clear singleton instances after each test."""
        Repo.clear_instances()

    # === HTTPS URLs ===

    def test_validate_https_github_url(self):
        """Test validation of HTTPS GitHub URL."""
        repo = Repo()

        # Should not raise exception
        repo._validate_git_origin_url("https://github.com/user/repo.git")
        repo._validate_git_origin_url("https://github.com/organization/project.git")

    def test_validate_https_gitlab_url(self):
        """Test validation of HTTPS GitLab URL."""
        repo = Repo()

        repo._validate_git_origin_url("https://gitlab.com/user/repo.git")
        repo._validate_git_origin_url("https://gitlab.com/group/subgroup/project.git")

    def test_validate_https_bitbucket_url(self):
        """Test validation of HTTPS Bitbucket URL."""
        repo = Repo()

        repo._validate_git_origin_url("https://bitbucket.org/user/repo.git")

    def test_validate_https_self_hosted_url(self):
        """Test validation of HTTPS self-hosted Git URL."""
        repo = Repo()

        repo._validate_git_origin_url("https://git.company.com/team/project.git")
        repo._validate_git_origin_url("https://git.example.org/user/repo.git")

    def test_validate_https_url_without_git_extension(self):
        """Test validation of HTTPS URL without .git extension."""
        repo = Repo()

        # GitHub/GitLab support URLs without .git
        repo._validate_git_origin_url("https://github.com/user/repo")
        repo._validate_git_origin_url("https://gitlab.com/user/repo")

    # === SSH URLs ===

    def test_validate_ssh_github_url(self):
        """Test validation of SSH GitHub URL."""
        repo = Repo()

        repo._validate_git_origin_url("git@github.com:user/repo.git")
        repo._validate_git_origin_url("git@github.com:organization/project.git")

    def test_validate_ssh_gitlab_url(self):
        """Test validation of SSH GitLab URL."""
        repo = Repo()

        repo._validate_git_origin_url("git@gitlab.com:user/repo.git")
        repo._validate_git_origin_url("git@gitlab.com:group/subgroup/project.git")

    def test_validate_ssh_bitbucket_url(self):
        """Test validation of SSH Bitbucket URL."""
        repo = Repo()

        repo._validate_git_origin_url("git@bitbucket.org:user/repo.git")

    def test_validate_ssh_self_hosted_url(self):
        """Test validation of SSH self-hosted Git URL."""
        repo = Repo()

        repo._validate_git_origin_url("git@git.company.com:team/project.git")
        repo._validate_git_origin_url("git@git.example.org:user/repo.git")

    def test_validate_ssh_url_without_git_extension(self):
        """Test validation of SSH URL without .git extension."""
        repo = Repo()

        repo._validate_git_origin_url("git@github.com:user/repo")
        repo._validate_git_origin_url("git@gitlab.com:user/repo")

    def test_validate_ssh_url_with_custom_port(self):
        """Test validation of SSH URL with custom port."""
        repo = Repo()

        repo._validate_git_origin_url("ssh://git@git.company.com:2222/team/project.git")
        repo._validate_git_origin_url("git@git.company.com:2222:team/project.git")

    # === Git protocol URLs ===

    def test_validate_git_protocol_url(self):
        """Test validation of git:// protocol URL."""
        repo = Repo()

        repo._validate_git_origin_url("git://github.com/user/repo.git")
        repo._validate_git_origin_url("git://git.company.com/team/project.git")

    # === Invalid URLs ===

    def test_validate_empty_url_raises_error(self):
        """Test validation rejects empty URL."""
        repo = Repo()

        with pytest.raises(ValueError, match="Git origin URL cannot be empty"):
            repo._validate_git_origin_url("")

        with pytest.raises(ValueError, match="Git origin URL cannot be empty"):
            repo._validate_git_origin_url("   ")

    def test_validate_none_url_raises_error(self):
        """Test validation rejects None URL."""
        repo = Repo()

        with pytest.raises(ValueError, match="Git origin URL cannot be None"):
            repo._validate_git_origin_url(None)

    def test_validate_invalid_protocol_raises_error(self):
        """Test validation rejects invalid protocol."""
        repo = Repo()

        with pytest.raises(ValueError, match="Invalid Git origin URL format"):
            repo._validate_git_origin_url("ftp://github.com/user/repo.git")

        with pytest.raises(ValueError, match="Invalid Git origin URL format"):
            repo._validate_git_origin_url("http://github.com/user/repo.git")  # No HTTP

    def test_validate_malformed_url_raises_error(self):
        """Test validation rejects malformed URLs."""
        repo = Repo()

        with pytest.raises(ValueError, match="Invalid Git origin URL format"):
            repo._validate_git_origin_url("not-a-url")

        with pytest.raises(ValueError, match="Invalid Git origin URL format"):
            repo._validate_git_origin_url("github.com/user/repo")  # Missing protocol

    def test_validate_url_without_path_raises_error(self):
        """Test validation rejects URL without repository path."""
        repo = Repo()

        # These URLs don't match the regex patterns (no path after domain)
        with pytest.raises(ValueError, match="Invalid Git origin URL format"):
            repo._validate_git_origin_url("https://github.com")

        with pytest.raises(ValueError, match="Invalid Git origin URL format"):
            repo._validate_git_origin_url("git@github.com")

    def test_validate_not_string_raises_error(self):
        """Test validation rejects non-string types."""
        repo = Repo()

        with pytest.raises(ValueError, match="Git origin URL must be a string"):
            repo._validate_git_origin_url(123)

        with pytest.raises(ValueError, match="Git origin URL must be a string"):
            repo._validate_git_origin_url(['https://github.com/user/repo.git'])

    # === Edge cases ===

    def test_validate_url_with_credentials_raises_warning(self):
        """Test validation warns about URLs with embedded credentials."""
        repo = Repo()

        # Should warn but not fail - credentials in URL are discouraged
        with pytest.warns(UserWarning, match=r"embedded credentials"):
            repo._validate_git_origin_url("https://user:password@github.com/user/repo.git")

    def test_validate_url_strips_whitespace(self):
        """Test validation strips leading/trailing whitespace."""
        repo = Repo()

        # Should not raise - whitespace stripped
        repo._validate_git_origin_url("  https://github.com/user/repo.git  ")
        repo._validate_git_origin_url("\nhttps://github.com/user/repo.git\n")