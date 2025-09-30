"""
Tests for PatchManager.create_patch() creation logic.

Focused on testing creation operations:
- _create_git_branch(): Create ho-patch/xxx branch
- _checkout_branch(): Checkout to new branch
- Patches/xxx/ directory creation
- Return value structure
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from git.exc import GitCommandError

from half_orm_dev.patch_manager import PatchManager, PatchManagerError


class TestCreatePatchCreation:
    """Test creation logic for create_patch operation."""

    def test_create_git_branch_success(self, patch_manager):
        """Test successful git branch creation."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit
        mock_hgit = Mock()
        mock_git_proxy = Mock()
        mock_hgit.checkout = mock_git_proxy
        repo.hgit = mock_hgit

        # Create branch
        branch_name = "ho-patch/456-user-auth"
        patch_mgr._create_git_branch(branch_name)

        # Should call git checkout -b
        mock_git_proxy.assert_called_once_with('-b', branch_name)

    def test_create_git_branch_already_exists(self, patch_manager):
        """Test error when branch already exists."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit to raise error for existing branch
        mock_hgit = Mock()
        mock_git_proxy = Mock()
        mock_git_proxy.side_effect = GitCommandError("git checkout", 1, stderr="already exists")
        mock_hgit.checkout = mock_git_proxy
        repo.hgit = mock_hgit

        # Should raise PatchManagerError
        with pytest.raises(PatchManagerError, match="Branch already exists"):
            patch_mgr._create_git_branch("ho-patch/456-existing")

    def test_create_git_branch_git_error(self, patch_manager):
        """Test handling of generic git errors during branch creation."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit to raise generic git error
        mock_hgit = Mock()
        mock_git_proxy = Mock()
        mock_git_proxy.side_effect = GitCommandError("git checkout", 1, stderr="generic error")
        mock_hgit.checkout = mock_git_proxy
        repo.hgit = mock_hgit

        # Should raise PatchManagerError
        with pytest.raises(PatchManagerError, match="Failed to create branch"):
            patch_mgr._create_git_branch("ho-patch/456-test")

    def test_checkout_branch_success(self, patch_manager):
        """Test successful branch checkout."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit
        mock_hgit = Mock()
        mock_git_proxy = Mock()
        mock_hgit.checkout = mock_git_proxy
        repo.hgit = mock_hgit

        # Checkout branch
        branch_name = "ho-patch/456-user-auth"
        patch_mgr._checkout_branch(branch_name)

        # Should call git checkout
        mock_git_proxy.assert_called_once_with(branch_name)

    def test_checkout_branch_error(self, patch_manager):
        """Test error handling during checkout."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit to raise error
        mock_hgit = Mock()
        mock_git_proxy = Mock()
        mock_git_proxy.side_effect = GitCommandError("git checkout", 1, stderr="checkout failed")
        mock_hgit.checkout = mock_git_proxy
        repo.hgit = mock_hgit

        # Should raise PatchManagerError
        with pytest.raises(PatchManagerError, match="Failed to checkout"):
            patch_mgr._checkout_branch("ho-patch/456-test")

    def test_create_patch_creates_directory(self, patch_manager):
        """Test that create_patch creates Patches/xxx/ directory."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit for valid context
        mock_hgit = Mock()
        mock_hgit.branch = "ho-prod"
        mock_hgit.repos_is_clean.return_value = True
        mock_hgit.checkout = Mock()
        repo.hgit = mock_hgit

        # Create patch
        result = patch_mgr.create_patch("456-user-auth")

        # Directory should be created
        expected_dir = patches_dir / "456-user-auth"
        assert expected_dir.exists()
        assert expected_dir.is_dir()

        # README.md should be created
        readme_path = expected_dir / "README.md"
        assert readme_path.exists()

    def test_create_patch_return_structure(self, patch_manager):
        """Test that create_patch returns correct dict structure."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit for valid context
        mock_hgit = Mock()
        mock_hgit.branch = "ho-prod"
        mock_hgit.repos_is_clean.return_value = True
        mock_hgit.checkout = Mock()
        repo.hgit = mock_hgit

        # Create patch
        result = patch_mgr.create_patch("456-user-auth")

        # Check return structure
        assert isinstance(result, dict)
        assert 'patch_id' in result
        assert 'branch_name' in result
        assert 'patch_dir' in result
        assert 'on_branch' in result

        # Check values
        assert result['patch_id'] == "456-user-auth"
        assert result['branch_name'] == "ho-patch/456-user-auth"
        assert isinstance(result['patch_dir'], Path)
        assert result['on_branch'] == "ho-patch/456-user-auth"

    def test_create_patch_with_description(self, patch_manager):
        """Test create_patch with optional description."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit for valid context
        mock_hgit = Mock()
        mock_hgit.branch = "ho-prod"
        mock_hgit.repos_is_clean.return_value = True
        mock_hgit.checkout = Mock()
        repo.hgit = mock_hgit

        # Create patch with description
        description = "Add user authentication system"
        result = patch_mgr.create_patch("456-user-auth", description=description)

        # Directory should be created
        expected_dir = patches_dir / "456-user-auth"
        assert expected_dir.exists()

        # README should contain description
        readme_path = expected_dir / "README.md"
        readme_content = readme_path.read_text()
        assert description in readme_content

    def test_create_patch_numeric_id_creates_correct_paths(self, patch_manager):
        """Test create_patch with numeric ID creates correct paths."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit for valid context
        mock_hgit = Mock()
        mock_hgit.branch = "ho-prod"
        mock_hgit.repos_is_clean.return_value = True
        mock_hgit.checkout = Mock()
        repo.hgit = mock_hgit

        # Create patch with numeric ID
        result = patch_mgr.create_patch("456")

        # Check paths
        assert result['patch_id'] == "456"
        assert result['branch_name'] == "ho-patch/456"
        
        # Directory should be created with numeric name only
        expected_dir = patches_dir / "456"
        assert expected_dir.exists()

    def test_create_patch_directory_already_exists(self, patch_manager):
        """Test error when patch directory already exists."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit for valid context
        mock_hgit = Mock()
        mock_hgit.branch = "ho-prod"
        mock_hgit.repos_is_clean.return_value = True
        mock_hgit.checkout = Mock()
        repo.hgit = mock_hgit

        # Create patch directory manually
        existing_dir = patches_dir / "456-user-auth"
        existing_dir.mkdir()

        # Should raise error (directory already exists)
        with pytest.raises(PatchManagerError, match="already exists"):
            patch_mgr.create_patch("456-user-auth")
