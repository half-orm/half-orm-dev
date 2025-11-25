"""
Tests for PatchManager tag-based patch number reservation.

Focused on testing:
- _check_patch_id_available(): Check via tag lookup (ho-patch/{number})
- _create_reservation_tag(): Create and push reservation tag
- Integration with create_patch() workflow
- Tag-based reservation is more efficient than branch scanning
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, call
from git.exc import GitCommandError

from half_orm_dev.patch_manager import PatchManager, PatchManagerError


class TestPatchManagerTagReservation:
    """Test tag-based patch number reservation."""

    def test_check_patch_id_available_success(self, patch_manager, mock_hgit_complete):
        """Test check passes when tag doesn't exist."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Use complete mock with tag methods
        mock_hgit_complete.tag_exists.return_value = False
        repo.hgit = mock_hgit_complete

        # Should not raise
        patch_mgr._check_patch_id_available("456-user-auth")

        # Should have fetched tags and checked
        mock_hgit_complete.fetch_tags.assert_called_once()
        mock_hgit_complete.tag_exists.assert_called_once_with("ho-patch/456")

    def test_check_patch_id_available_tag_exists(self, patch_manager, mock_hgit_complete):
        """Test check fails when tag exists (number already reserved)."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Use complete mock: tag exists
        mock_hgit_complete.tag_exists.return_value = True
        repo.hgit = mock_hgit_complete

        # Should raise PatchManagerError
        with pytest.raises(PatchManagerError, match="Patch number 456 already reserved"):
            patch_mgr._check_patch_id_available("456-user-auth")

        # Error message should mention the tag
        with pytest.raises(PatchManagerError, match="Tag ho-patch/456 exists"):
            patch_mgr._check_patch_id_available("456-user-auth")

        # Error message should suggest choosing different number
        with pytest.raises(PatchManagerError, match="Choose a different patch number"):
            patch_mgr._check_patch_id_available("456-user-auth")

    def test_check_patch_id_available_numeric_only(self, patch_manager, mock_hgit_complete):
        """Test check extracts number correctly from numeric-only ID."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Use complete mock
        mock_hgit_complete.tag_exists.return_value = False
        repo.hgit = mock_hgit_complete

        # Check with numeric-only ID
        patch_mgr._check_patch_id_available("456")

        # Should check for tag ho-patch/456
        mock_hgit_complete.tag_exists.assert_called_once_with("ho-patch/456")

    def test_check_patch_id_available_fetch_failure(self, patch_manager, mock_hgit_complete):
        """Test check handles fetch failure."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Use complete mock: fetch fails
        mock_hgit_complete.fetch_tags.side_effect = GitCommandError(
            "git fetch --tags", 1, stderr="Network error"
        )
        repo.hgit = mock_hgit_complete

        # Should raise PatchManagerError about fetch failure
        with pytest.raises(PatchManagerError, match="Failed to fetch tags from remote"):
            patch_mgr._check_patch_id_available("456-user-auth")

        # Error message should mention network/remote
        with pytest.raises(PatchManagerError, match="Cannot verify patch number availability"):
            patch_mgr._check_patch_id_available("456-user-auth")

    def test_create_reservation_tag_success(self, patch_manager, mock_hgit_complete):
        """Test successful tag creation and push."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Use complete mock
        repo.hgit = mock_hgit_complete

        # Create reservation tag
        patch_mgr._create_reservation_tag("456-user-auth", "Add user authentication")

        # Should have created and pushed tag
        mock_hgit_complete.create_tag.assert_called_once_with(
            "ho-patch/456",
            "Patch 456: Add user authentication"
        )
        mock_hgit_complete.push_tag.assert_called_once_with("ho-patch/456")

    def test_create_reservation_tag_without_description(self, patch_manager, mock_hgit_complete):
        """Test tag creation without description."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Use complete mock
        repo.hgit = mock_hgit_complete

        # Create tag without description
        patch_mgr._create_reservation_tag("456-user-auth")

        # Should use default message
        mock_hgit_complete.create_tag.assert_called_once_with(
            "ho-patch/456",
            "Patch 456 reserved"
        )

    def test_create_reservation_tag_numeric_only(self, patch_manager, mock_hgit_complete):
        """Test tag creation with numeric-only patch ID."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Use complete mock
        repo.hgit = mock_hgit_complete

        # Create tag with numeric ID
        patch_mgr._create_reservation_tag("456")

        # Should create tag ho-patch/456
        mock_hgit_complete.create_tag.assert_called_once_with(
            "ho-patch/456",
            "Patch 456 reserved"
        )

    def test_create_reservation_tag_creation_failure(self, patch_manager, mock_hgit_complete):
        """Test error handling when tag creation fails."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Use complete mock: create_tag fails
        mock_hgit_complete.create_tag.side_effect = GitCommandError(
            "git tag", 1, stderr="tag already exists"
        )
        repo.hgit = mock_hgit_complete

        # Should raise PatchManagerError
        with pytest.raises(PatchManagerError, match="Failed to create reservation tag"):
            patch_mgr._create_reservation_tag("456-user-auth")

    def test_create_reservation_tag_push_failure(self, patch_manager, mock_hgit_complete):
        """Test error handling when tag push fails."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Use complete mock: push_tag fails
        mock_hgit_complete.push_tag.side_effect = GitCommandError(
            "git push", 1, stderr="Network error"
        )
        repo.hgit = mock_hgit_complete

        # Should raise PatchManagerError
        with pytest.raises(PatchManagerError, match="Failed to create reservation tag"):
            patch_mgr._create_reservation_tag("456-user-auth")

        # Error message should mention reservation failure
        with pytest.raises(PatchManagerError, match="Patch number reservation failed"):
            patch_mgr._create_reservation_tag("456-user-auth")

    def test_create_patch_checks_tag_before_branch_creation(self, patch_manager, mock_hgit_complete):
        """Test create_patch checks tag availability before creating branch."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock HGit: tag already exists (number reserved)
        mock_hgit_complete.fetch_tags = Mock()
        mock_hgit_complete.tag_exists.return_value = True  # Number taken
        repo.hgit = mock_hgit_complete

        # Should fail before creating branch
        with pytest.raises(PatchManagerError, match="Patch number 456 already reserved"):
            patch_mgr.create_patch("456-user-auth")

        # Branch creation should NOT be called
        assert not mock_hgit_complete.checkout.called

    def test_create_patch_creates_tag_after_branch(self, patch_manager, mock_hgit_complete):
        """Test create_patch creates reservation tag after branch."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Use complete mock with tag methods
        repo.hgit = mock_hgit_complete

        # Create patch
        result = patch_mgr.create_patch("456-user-auth")

        # Verify tag check happened
        mock_hgit_complete.fetch_tags.assert_called_once()
        mock_hgit_complete.tag_exists.assert_called()

        # Verify tag creation happened
        mock_hgit_complete.create_tag.assert_called_once()
        mock_hgit_complete.push_tag.assert_called_once_with("ho-patch/456")

        # Verify workflow completed
        assert result['patch_id'] == "456-user-auth"
        expected_dir = patches_dir / "456-user-auth"
        assert expected_dir.exists()

    def test_create_patch_workflow_with_tag_reservation(self, patch_manager, mock_hgit_complete):
        """Test complete workflow includes tag-based reservation."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Use complete mock
        repo.hgit = mock_hgit_complete

        # Create patch with description
        description = "Add user authentication"
        result = patch_mgr.create_patch("456-user-auth", description=description)

        # Verify complete workflow:
        # 1. Tag check
        mock_hgit_complete.fetch_tags.assert_called_once()
        mock_hgit_complete.tag_exists.assert_called_with("ho-patch/456")

        # 2. Branch creation
        assert mock_hgit_complete.checkout.call_count >= 2  # create + checkout

        # 3. Tag creation with description
        mock_hgit_complete.create_tag.assert_called_once_with(
            "ho-patch/456",
            "Patch 456: Add user authentication"
        )

        # 4. Tag push
        mock_hgit_complete.push_tag.assert_called_once_with("ho-patch/456")

        # 5. Branch push
        calls = mock_hgit_complete.push_branch.call_args_list
        assert calls[1] == call("ho-patch/456-user-auth", set_upstream=True)

        # 6. Directory created
        expected_dir = patches_dir / "456-user-auth"
        assert expected_dir.exists()

    def test_create_patch_validation_order_with_tag_check(self, patch_manager, mock_hgit_complete):
        """Test validation order includes tag check at right time."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Use complete mock: wrong branch (should fail before tag check)
        mock_hgit_complete.branch = "main"
        repo.hgit = mock_hgit_complete

        # Should fail on branch validation (before fetching tags)
        with pytest.raises(PatchManagerError, match="Must be on ho-release/X.Y.Z branch to create patch."):
            patch_mgr.create_patch("456-user-auth")

        # Fetch tags should NOT be called (validation failed earlier)
        mock_hgit_complete.fetch_tags.assert_not_called()

    def test_tag_reservation_more_efficient_than_branch_scan(self, patch_manager, mock_hgit_complete):
        """Test that tag checking is O(1) not O(n) like branch scanning."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Use complete mock
        mock_hgit_complete.tag_exists.return_value = False
        repo.hgit = mock_hgit_complete

        # Check availability
        patch_mgr._check_patch_id_available("456-user-auth")

        # Should only fetch tags once (efficient)
        mock_hgit_complete.fetch_tags.assert_called_once()

        # tag_exists is O(1) lookup in list
        mock_hgit_complete.tag_exists.assert_called_once()

        # Note: Old approach would scan all branches (O(n) with n = number of patches)
        # Tag approach is O(1) lookup after single fetch

    def test_different_descriptions_same_number_conflict(self, patch_manager, mock_hgit_complete):
        """Test that same number with different descriptions conflicts."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Use complete mock: tag exists (number 456 reserved)
        mock_hgit_complete.tag_exists.return_value = True
        repo.hgit = mock_hgit_complete

        # Both should fail (same number, different descriptions)
        with pytest.raises(PatchManagerError, match="Patch number 456 already reserved"):
            patch_mgr._check_patch_id_available("456-user-auth")

        with pytest.raises(PatchManagerError, match="Patch number 456 already reserved"):
            patch_mgr._check_patch_id_available("456-security-fix")

        # Tag name is based on number only: ho-patch/456
