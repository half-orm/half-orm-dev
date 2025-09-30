"""
Tests for PatchManager.create_patch() validation logic.

Focused on testing validation helpers:
- _validate_on_ho_prod(): Must be on ho-prod branch
- _validate_repo_clean(): No uncommitted changes allowed
- Patch ID format validation
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, PropertyMock

from half_orm_dev.patch_manager import PatchManager, PatchManagerError


class TestCreatePatchValidation:
    """Test validation logic for create_patch operation."""

    @pytest.mark.skip(reason="create_patch not implemented yet")
    def test_validate_on_ho_prod_success(self, patch_manager):
        """Test validation passes when on ho-prod branch."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit to return ho-prod branch
        mock_hgit = Mock()
        mock_hgit.branch = "ho-prod"
        repo.hgit = mock_hgit

        # Should not raise any exception
        patch_mgr._validate_on_ho_prod()

    @pytest.mark.skip(reason="create_patch not implemented yet")
    def test_validate_on_ho_prod_wrong_branch(self, patch_manager):
        """Test validation fails when not on ho-prod branch."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit to return different branch
        mock_hgit = Mock()
        mock_hgit.branch = "ho-patch/123-existing"
        repo.hgit = mock_hgit

        # Should raise PatchManagerError
        with pytest.raises(PatchManagerError, match="Must be on ho-prod branch"):
            patch_mgr._validate_on_ho_prod()

    @pytest.mark.skip(reason="create_patch not implemented yet")
    def test_validate_on_ho_prod_main_branch(self, patch_manager):
        """Test validation fails when on main/master branch."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit to return main branch
        mock_hgit = Mock()
        mock_hgit.branch = "main"
        repo.hgit = mock_hgit

        # Should raise PatchManagerError
        with pytest.raises(PatchManagerError, match="Must be on ho-prod branch"):
            patch_mgr._validate_on_ho_prod()

    @pytest.mark.skip(reason="create_patch not implemented yet")
    def test_validate_repo_clean_success(self, patch_manager):
        """Test validation passes when repo is clean."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit repos_is_clean to return True
        mock_hgit = Mock()
        mock_hgit.repos_is_clean.return_value = True
        repo.hgit = mock_hgit

        # Should not raise any exception
        patch_mgr._validate_repo_clean()

    @pytest.mark.skip(reason="create_patch not implemented yet")
    def test_validate_repo_clean_dirty_repo(self, patch_manager):
        """Test validation fails when repo has uncommitted changes."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit repos_is_clean to return False
        mock_hgit = Mock()
        mock_hgit.repos_is_clean.return_value = False
        repo.hgit = mock_hgit

        # Should raise PatchManagerError
        with pytest.raises(PatchManagerError, match="Repository has uncommitted changes"):
            patch_mgr._validate_repo_clean()

    @pytest.mark.skip(reason="create_patch not implemented yet")
    def test_validate_repo_clean_untracked_files(self, patch_manager):
        """Test validation fails with untracked files."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit repos_is_clean to return False (includes untracked)
        mock_hgit = Mock()
        mock_hgit.repos_is_clean.return_value = False
        repo.hgit = mock_hgit

        # Should raise PatchManagerError
        with pytest.raises(PatchManagerError, match="Repository has uncommitted changes"):
            patch_mgr._validate_repo_clean()

    @pytest.mark.skip(reason="create_patch not implemented yet")
    def test_create_patch_invalid_patch_id_format(self, patch_manager):
        """Test create_patch fails with invalid patch ID format."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit for valid context
        mock_hgit = Mock()
        mock_hgit.branch = "ho-prod"
        mock_hgit.repos_is_clean.return_value = True
        repo.hgit = mock_hgit

        # Invalid patch IDs (no number prefix)
        invalid_ids = [
            "no-number",
            "invalid@patch",
            "",
            "   ",
            "@#$%"
        ]

        for invalid_id in invalid_ids:
            with pytest.raises(PatchManagerError, match="Invalid patch ID"):
                patch_mgr.create_patch(invalid_id)

    @pytest.mark.skip(reason="create_patch not implemented yet")
    def test_create_patch_whitespace_in_patch_id(self, patch_manager):
        """Test create_patch handles whitespace in patch ID."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit and git operations
        mock_hgit = Mock()
        mock_hgit.branch = "ho-prod"
        mock_hgit.repos_is_clean.return_value = True
        repo.hgit = mock_hgit

        # Patch ID with leading/trailing whitespace should be normalized
        result = patch_mgr.create_patch("  456-user-auth  ")

        # Should normalize to "456-user-auth"
        assert result['patch_id'] == "456-user-auth"
        assert result['branch_name'] == "ho-patch/456-user-auth"

    @pytest.mark.skip(reason="create_patch not implemented yet")
    def test_create_patch_numeric_only_patch_id(self, patch_manager):
        """Test create_patch accepts numeric-only patch ID."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit and git operations
        mock_hgit = Mock()
        mock_hgit.branch = "ho-prod"
        mock_hgit.repos_is_clean.return_value = True
        repo.hgit = mock_hgit

        # Numeric-only patch ID should be valid
        result = patch_mgr.create_patch("456")

        assert result['patch_id'] == "456"
        assert result['branch_name'] == "ho-patch/456"

    @pytest.mark.skip(reason="create_patch not implemented yet")
    def test_create_patch_validation_order(self, patch_manager):
        """Test validations are performed in correct order."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit: wrong branch AND dirty repo
        mock_hgit = Mock()
        mock_hgit.branch = "main"
        mock_hgit.repos_is_clean.return_value = False
        repo.hgit = mock_hgit

        # Should fail on branch validation first (before checking clean state)
        with pytest.raises(PatchManagerError, match="Must be on ho-prod branch"):
            patch_mgr.create_patch("456-test")

    @pytest.mark.skip(reason="create_patch not implemented yet")
    def test_validate_on_ho_prod_case_sensitive(self, patch_manager):
        """Test branch validation is case-sensitive."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit with uppercase HO-PROD
        mock_hgit = Mock()
        mock_hgit.branch = "HO-PROD"
        repo.hgit = mock_hgit

        # Should fail (case-sensitive)
        with pytest.raises(PatchManagerError, match="Must be on ho-prod branch"):
            patch_mgr._validate_on_ho_prod()
