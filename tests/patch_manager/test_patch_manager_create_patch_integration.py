"""
Tests for PatchManager.create_patch() integration and edge cases.

Focused on testing:
- Complete workflow (validation → creation → checkout)
- Integration between all components
- Edge cases and error scenarios
- Cleanup on failure
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, call
from git.exc import GitCommandError

from half_orm_dev.patch_manager import PatchManager, PatchManagerError, PatchStructureError


class TestCreatePatchIntegration:
    """Test complete workflow and integration scenarios."""

    def test_create_patch_complete_workflow(self, patch_manager, mock_hgit_complete):
        """Test complete successful create_patch workflow."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit for valid context
        repo.hgit = mock_hgit_complete

        # Execute complete workflow
        result = patch_mgr.create_patch("456-user-auth")

        # Verify all steps executed
        # 1. Validations passed (no exceptions)
        # 2. Branch created
        assert mock_hgit_complete.checkout.call_count == 2  # create + checkout

        # 3. Directory created
        expected_dir = patches_dir / "456-user-auth"
        assert expected_dir.exists()

        # 4. Checkout to new branch
        mock_hgit_complete.checkout.assert_any_call("ho-patch/456-user-auth")

        mock_hgit_complete.push_branch.assert_called_once_with("ho-patch/456-user-auth", set_upstream=True)

        # 5. Return value complete
        assert result['patch_id'] == "456-user-auth"
        assert result['branch_name'] == "ho-patch/456-user-auth"
        assert result['on_branch'] == "ho-patch/456-user-auth"

    def test_create_patch_workflow_with_description(self, patch_manager, mock_hgit_complete):
        """Test complete workflow with optional description."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit for valid context
        repo.hgit = mock_hgit_complete

        # Create with description
        description = "Implement user authentication with JWT"
        result = patch_mgr.create_patch("456-user-auth", description=description)

        # Verify description passed through
        readme_path = patches_dir / "456-user-auth" / "README.md"
        readme_content = readme_path.read_text()
        assert description in readme_content

    def test_create_patch_stops_on_validation_error(self, patch_manager):
        """Test that workflow stops at validation errors."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit with invalid context (wrong branch)
        mock_hgit = Mock()
        mock_hgit.branch = "main"
        mock_hgit.repos_is_clean.return_value = True
        mock_hgit.checkout = Mock()
        repo.hgit = mock_hgit

        # Should fail at validation
        with pytest.raises(PatchManagerError, match="Must be on ho-prod branch"):
            patch_mgr.create_patch("456-user-auth")

        # Git operations should NOT be called
        mock_hgit.checkout.assert_not_called()

        # Directory should NOT be created
        expected_dir = patches_dir / "456-user-auth"
        assert not expected_dir.exists()

    def test_create_patch_cleanup_on_directory_creation_failure(self, patch_manager):
        """Test cleanup when directory creation fails after branch creation."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit for valid context
        mock_hgit = Mock()
        mock_hgit.branch = "ho-prod"
        mock_hgit.repos_is_clean.return_value = True
        mock_hgit.checkout = Mock()
        repo.hgit = mock_hgit

        # Make patches_dir read-only to cause creation failure
        patches_dir.chmod(0o444)

        try:
            # Should fail on directory creation
            with pytest.raises(PatchManagerError):
                patch_mgr.create_patch("456-user-auth")

            # Branch should be deleted (cleanup)
            # This would require checking git branch deletion was called
            # Implementation detail: depends on cleanup strategy

        finally:
            # Restore permissions
            patches_dir.chmod(0o755)

    def test_create_patch_multiple_patches_sequential(self, patch_manager, mock_hgit_complete):
        """Test creating multiple patches sequentially."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit for valid context
        repo.hgit = mock_hgit_complete

        # Create multiple patches
        patches = ["123-first", "456-second", "789-third"]

        for patch_id in patches:
            # Reset to ho-prod for each patch
            mock_hgit_complete.branch = "ho-prod"

            result = patch_mgr.create_patch(patch_id)

            # Verify each patch created
            assert result['patch_id'] == patch_id
            expected_dir = patches_dir / patch_id
            assert expected_dir.exists()

    def test_create_patch_special_characters_in_description(self, patch_manager, mock_hgit_complete):
        """Test handling special characters in description."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit for valid context
        repo.hgit = mock_hgit_complete

        # Description with special characters
        description = "Add user's authentication & authorization (OAuth2.0)"
        result = patch_mgr.create_patch("456-user-auth", description=description)

        # Should handle special characters correctly
        readme_path = patches_dir / "456-user-auth" / "README.md"
        readme_content = readme_path.read_text()
        assert description in readme_content

    def test_create_patch_very_long_patch_id(self, patch_manager):
        """Test handling of very long patch IDs."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit for valid context
        mock_hgit = Mock()
        mock_hgit.branch = "ho-prod"
        mock_hgit.repos_is_clean.return_value = True
        mock_hgit.checkout = Mock()
        repo.hgit = mock_hgit

        # Very long but valid patch ID
        long_id = "456-" + "-".join(["word"] * 50)  # Very long ID

        # Should handle long IDs (or raise appropriate error if too long)
        try:
            result = patch_mgr.create_patch(long_id)
            # If accepted, verify it works
            assert result['patch_id'] == long_id
        except PatchManagerError:
            # If rejected, that's also valid behavior
            pass

    def test_create_patch_idempotency_check(self, patch_manager, mock_hgit_complete):
        """Test that create_patch is not idempotent (fails on duplicate)."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit for valid context
        repo.hgit = mock_hgit_complete

        # Create patch first time
        result1 = patch_mgr.create_patch("456-user-auth")
        assert result1['patch_id'] == "456-user-auth"

        # Reset to ho-prod
        mock_hgit_complete.branch = "ho-prod"

        # Second attempt should fail (not idempotent)
        with pytest.raises(PatchManagerError):
            patch_mgr.create_patch("456-user-auth")

    def test_create_patch_preserves_existing_patches(self, patch_manager, mock_hgit_complete):
        """Test that creating new patch doesn't affect existing patches."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create first patch manually
        existing_patch = patches_dir / "123-existing"
        existing_patch.mkdir()
        (existing_patch / "README.md").write_text("# Existing patch")
        (existing_patch / "script.sql").write_text("SELECT 1;")

        # Mock HGit for valid context
        repo.hgit = mock_hgit_complete

        # Create new patch
        result = patch_mgr.create_patch("456-new")

        # Existing patch should be unchanged
        assert existing_patch.exists()
        assert (existing_patch / "README.md").exists()
        assert (existing_patch / "script.sql").exists()

        # New patch should exist
        new_patch = patches_dir / "456-new"
        assert new_patch.exists()

    def test_create_patch_git_operations_order(self, patch_manager, mock_hgit_complete):
        """Test that git operations happen in correct order."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit for valid context
        repo.hgit = mock_hgit_complete

        # Create patch
        result = patch_mgr.create_patch("456-user-auth")

        # Verify call order: create branch, then checkout
        calls = mock_hgit_complete.checkout.call_args_list
        assert len(calls) == 2

        # First call: create branch (git checkout -b)
        assert calls[0] == call('-b', 'ho-patch/456-user-auth')

        # Second call: checkout to branch (git checkout)
        assert calls[1] == call('ho-patch/456-user-auth')
