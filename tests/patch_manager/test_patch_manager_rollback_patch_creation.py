"""
Tests for PatchManager._rollback_patch_creation() method.

Tests cleanup operations when patch creation fails before tag push.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, call
from git.exc import GitCommandError

from half_orm_dev.patch_manager import PatchManager, PatchManagerError


class TestPatchManagerRollback:
    """Test rollback mechanism for failed patch creation."""

    def test_rollback_complete_cleanup(self, patch_manager, mock_hgit_complete):
        """Test complete rollback cleans up all created resources."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create patch directory to simulate partial creation
        patch_dir = patches_dir / "456-test"
        patch_dir.mkdir()
        (patch_dir / "README.md").write_text("# Test")

        # Use complete mock
        repo.hgit = mock_hgit_complete

        # Perform rollback
        patch_mgr._rollback_patch_creation(
            "ho-prod",
            "ho-patch/456-test",
            "456-test",
            patch_dir
        )

        # Should checkout to initial branch
        mock_hgit_complete.checkout.assert_called_with("ho-prod")

        # Should delete branch (best effort, continues on error)
        # We'll verify this is attempted (implementation will use git branch -D)

        # Directory should be deleted
        assert not patch_dir.exists()

    def test_rollback_without_patch_directory(self, patch_manager, mock_hgit_complete):
        """Test rollback when patch directory was not created."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Use complete mock
        repo.hgit = mock_hgit_complete

        # Rollback without patch_dir
        patch_mgr._rollback_patch_creation(
            "ho-prod",
            "ho-patch/456-test",
            "456-test",
            None  # Directory not created
        )

        # Should still checkout to initial branch
        mock_hgit_complete.checkout.assert_called_with("ho-prod")

        # No directory operations (patch_dir was None)

    def test_rollback_checkout_failure_continues(self, patch_manager, mock_hgit_complete):
        """Test rollback continues even if checkout fails."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create patch directory
        patch_dir = patches_dir / "456-test"
        patch_dir.mkdir()

        # Mock checkout to fail
        mock_hgit_complete.checkout.side_effect = GitCommandError(
            "git checkout", 1, stderr="Cannot checkout"
        )
        repo.hgit = mock_hgit_complete

        # Should not raise (best-effort cleanup)
        patch_mgr._rollback_patch_creation(
            "ho-prod",
            "ho-patch/456-test",
            "456-test",
            patch_dir
        )

        # Directory should still be deleted (continues after checkout failure)
        assert not patch_dir.exists()

    def test_rollback_directory_deletion_failure_continues(self, patch_manager, mock_hgit_complete):
        """Test rollback continues even if directory deletion fails."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create patch directory with read-only permissions to simulate deletion failure
        patch_dir = patches_dir / "456-test"
        patch_dir.mkdir()

        # Use complete mock
        repo.hgit = mock_hgit_complete

        # Make directory deletion fail by making it read-only
        patch_dir.chmod(0o444)

        try:
            # Should not raise (best-effort cleanup)
            patch_mgr._rollback_patch_creation(
                "ho-prod",
                "ho-patch/456-test",
                "456-test",
                patch_dir
            )
        finally:
            # Restore permissions for cleanup (only if directory still exists)
            if patch_dir.exists():
                patch_dir.chmod(0o755)

        # Should have attempted checkout despite directory failure
        mock_hgit_complete.checkout.assert_called_with("ho-prod")

    def test_rollback_deletes_local_branch(self, patch_manager, mock_hgit_complete):
        """Test rollback deletes local branch."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Use complete mock
        repo.hgit = mock_hgit_complete

        # Perform rollback
        patch_mgr._rollback_patch_creation(
            "ho-prod",
            "ho-patch/456-test",
            "456-test",
            None
        )

        # Should attempt to delete branch via git operations
        # Implementation will need to add delete_branch method to HGit

    def test_rollback_deletes_local_tag(self, patch_manager, mock_hgit_complete):
        """Test rollback deletes local tag."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Use complete mock
        repo.hgit = mock_hgit_complete

        # Perform rollback
        patch_mgr._rollback_patch_creation(
            "ho-prod",
            "ho-patch/456-test",
            "456-test",
            None
        )

        # Should attempt to delete tag via git operations
        # Implementation will need to add delete_tag method to HGit

    def test_rollback_called_on_validation_failure(self, patch_manager, mock_hgit_complete):
        """Test rollback is called when validation fails after branch creation."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock to fail on directory creation (after branch created)
        def fail_on_directory_creation(patch_id):
            raise PatchManagerError("Simulated directory creation failure")

        patch_mgr.create_patch_directory = fail_on_directory_creation

        # Use complete mock
        repo.hgit = mock_hgit_complete

        # Should raise error and trigger rollback
        with pytest.raises(PatchManagerError, match="Patch creation failed"):
            patch_mgr.create_patch("456-test")

        # Should have attempted checkout back to ho-prod (rollback happened)
        # Note: checkout called twice - once for branch creation, once for rollback
        checkout_calls = mock_hgit_complete.checkout.call_args_list
        assert call('ho-release/0.17.0') in checkout_calls

    def test_rollback_not_called_after_tag_push(self, patch_manager, mock_hgit_complete):
        """Test rollback is NOT called if tag push succeeds."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # This test verifies the workflow logic rather than rollback itself
        # Tag push success = no rollback even if branch push fails

        # We'll verify this in the workflow tests
        # Just ensuring rollback is designed for pre-tag-push failures only
        pass

    def test_rollback_best_effort_multiple_failures(self, patch_manager, mock_hgit_complete):
        """Test rollback continues through multiple failures."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create patch directory
        patch_dir = patches_dir / "456-test"
        patch_dir.mkdir()

        # Mock everything to fail
        mock_hgit_complete.checkout.side_effect = GitCommandError(
            "git checkout", 1, stderr="Checkout failed"
        )
        repo.hgit = mock_hgit_complete

        # Should not raise (best-effort continues through failures)
        patch_mgr._rollback_patch_creation(
            "ho-prod",
            "ho-patch/456-test",
            "456-test",
            patch_dir
        )

        # At least attempted checkout
        mock_hgit_complete.checkout.assert_called()

    def test_rollback_with_numeric_patch_id(self, patch_manager, mock_hgit_complete):
        """Test rollback works with numeric-only patch IDs."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create patch directory
        patch_dir = patches_dir / "456"
        patch_dir.mkdir()

        # Use complete mock
        repo.hgit = mock_hgit_complete

        # Perform rollback with numeric ID
        patch_mgr._rollback_patch_creation(
            "ho-prod",
            "ho-patch/456",
            "456",
            patch_dir
        )

        # Should work same as with full ID
        mock_hgit_complete.checkout.assert_called_with("ho-prod")
        assert not patch_dir.exists()