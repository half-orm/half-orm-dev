"""
Tests for PatchManager remote validation and patch ID reservation.

Focused on testing:
- _validate_has_remote(): Remote configuration validation
- _push_branch_to_reserve_id(): Branch push for ID reservation
- Integration with create_patch() workflow
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, call
from git.exc import GitCommandError

from half_orm_dev.patch_manager import PatchManager, PatchManagerError


class TestPatchManagerRemoteValidation:
    """Test remote validation and patch ID reservation."""

    def test_validate_has_remote_success(self, patch_manager):
        """Test validation passes when remote is configured."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit to return True for has_remote
        mock_hgit = Mock()
        mock_hgit.has_remote.return_value = True
        repo.hgit = mock_hgit

        # Should not raise any exception
        patch_mgr._validate_has_remote()

    def test_validate_has_remote_no_remote(self, patch_manager):
        """Test validation fails when no remote configured."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit to return False for has_remote
        mock_hgit = Mock()
        mock_hgit.has_remote.return_value = False
        repo.hgit = mock_hgit

        # Should raise PatchManagerError with clear message
        with pytest.raises(PatchManagerError, match="No git remote configured"):
            patch_mgr._validate_has_remote()

        # Error message should mention global uniqueness
        with pytest.raises(PatchManagerError, match="globally unique"):
            patch_mgr._validate_has_remote()

        # Error message should suggest solution
        with pytest.raises(PatchManagerError, match="git remote add origin"):
            patch_mgr._validate_has_remote()

    def test_push_branch_to_reserve_id_success(self, patch_manager):
        """Test successful branch push for ID reservation."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit
        mock_hgit = Mock()
        mock_hgit.push_branch = Mock()
        repo.hgit = mock_hgit

        # Should push branch with upstream tracking
        patch_mgr._push_branch_to_reserve_id("ho-patch/456-user-auth")

        # Should have called push_branch
        mock_hgit.push_branch.assert_called_once_with("ho-patch/456-user-auth", set_upstream=True)

    def test_push_branch_to_reserve_id_push_failure(self, patch_manager):
        """Test error handling when push fails."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit to raise error on push
        mock_hgit = Mock()
        mock_hgit.push_branch.side_effect = GitCommandError("git push", 1, stderr="Authentication failed")
        repo.hgit = mock_hgit

        # Should raise PatchManagerError with helpful message
        with pytest.raises(PatchManagerError, match="Failed to push branch"):
            patch_mgr._push_branch_to_reserve_id("ho-patch/456-user-auth")

        # Error message should mention patch ID reservation
        with pytest.raises(PatchManagerError, match="Patch ID reservation"):
            patch_mgr._push_branch_to_reserve_id("ho-patch/456-user-auth")

    def test_create_patch_validates_remote_before_branch_creation(self, patch_manager):
        """Test that remote validation happens before branch creation."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit with no remote
        mock_hgit = Mock()
        mock_hgit.branch = "ho-prod"
        mock_hgit.repos_is_clean.return_value = True
        mock_hgit.has_remote.return_value = False  # No remote
        repo.hgit = mock_hgit

        # Should fail on remote validation before creating branch
        with pytest.raises(PatchManagerError, match="No git remote configured"):
            patch_mgr.create_patch("456")

        # Branch creation should NOT be called
        assert not mock_hgit.checkout.called

    def test_create_patch_pushes_branch_after_creation(self, patch_manager, mock_hgit_complete):
        """Test that branch is pushed after creation."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit with valid setup
        repo.hgit = mock_hgit_complete

        # Create patch
        result = patch_mgr.create_patch("456")

        # Should have pushed branch
        calls = mock_hgit_complete.push_branch.call_args_list
        assert calls[1] == call("ho-patch/456", set_upstream=True)

    def test_create_patch_validation_order_with_remote(self, patch_manager):
        """Test validation order includes remote check."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit: wrong branch, dirty repo, no remote
        mock_hgit = Mock()
        mock_hgit.branch = "main"
        mock_hgit.repos_is_clean.return_value = False
        mock_hgit.has_remote.return_value = False
        repo.hgit = mock_hgit

        # Should fail on branch validation first
        with pytest.raises(PatchManagerError, match="Must be on ho-prod branch"):
            patch_mgr.create_patch("456")

    def test_create_patch_network_error_on_push(self, patch_manager, mock_hgit_complete, capsys):
        """Test handling of network errors during branch push after tag push succeeds."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock push_branch: ho-prod succeeds, branch patch fails
        def push_branch_side_effect(branch_name, set_upstream=True):
            if branch_name == 'ho-prod':
                return None  # Success for ho-prod
            else:
                raise GitCommandError("git push", 1, stderr="Could not resolve host")

        mock_hgit_complete.push_branch.side_effect = push_branch_side_effect
        repo.hgit = mock_hgit_complete

        # Should NOT raise - tag was pushed successfully, patch is reserved
        result = patch_mgr.create_patch("456")

        # Patch should be created successfully
        assert result['patch_id'] == "456"
        assert result['branch_name'] == "ho-patch/456"

        # Directory should exist
        expected_dir = patches_dir / "456"
        assert expected_dir.exists()

        # Tag should have been pushed (reservation complete)
        mock_hgit_complete.push_tag.assert_called_once_with("ho-patch/456")

        # Should have attempted branch push 3 times
        assert mock_hgit_complete.push_branch.call_count == 4

        # Should display warning about branch push failure
        captured = capsys.readouterr()
        assert "Warning: Branch push failed after 3 attempts" in captured.out
        assert "Patch 456 is reserved (tag pushed successfully)" in captured.out
        assert "Push branch manually: git push -u origin ho-patch/456" in captured.out

    def test_create_patch_complete_workflow_with_remote(self, patch_manager, mock_hgit_complete):
        """Test complete workflow includes remote push and tag reservation."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit with valid setup
        repo.hgit = mock_hgit_complete

        # Create patch
        result = patch_mgr.create_patch("456-user-auth")

        # Verify complete workflow executed
        # 1. Validations passed
        mock_hgit_complete.has_remote.assert_called()

        # 2. Tag availability check
        mock_hgit_complete.fetch_tags.assert_called_once()
        mock_hgit_complete.tag_exists.assert_called_with("ho-patch/456")

        # 3. Branch created
        assert mock_hgit_complete.checkout.call_count >= 2  # create + checkout

        # 4. Reservation tag created and pushed
        mock_hgit_complete.create_tag.assert_called_once_with(
            "ho-patch/456",
            "Patch 456 reserved"
        )
        mock_hgit_complete.push_tag.assert_called_once_with("ho-patch/456")

        # 5. Branch pushed for tracking
        calls = mock_hgit_complete.push_branch.call_args_list
        assert calls[0] == call("ho-prod")
        assert calls[1] == call("ho-patch/456-user-auth", set_upstream=True)

        # 6. Directory created
        expected_dir = patches_dir / "456-user-auth"
        assert expected_dir.exists()

        # 7. Result returned
        assert result['patch_id'] == "456-user-auth"
        assert result['branch_name'] == "ho-patch/456-user-auth"