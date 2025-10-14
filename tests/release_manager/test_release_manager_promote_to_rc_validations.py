"""
Tests for ReleaseManager.promote_to_rc() - Pre-lock validations.

Focused on testing validations that occur BEFORE lock acquisition:
- On ho-prod branch validation
- Repository clean validation
- Stage releases existence validation

These tests ensure errors are caught early without acquiring lock.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock

from half_orm_dev.release_manager import ReleaseManager, ReleaseManagerError


class TestPromoteToRcPreLockValidations:
    """Test pre-lock validations for promote_to_rc()."""

    @pytest.fixture
    def release_manager_basic(self, tmp_path):
        """Create basic ReleaseManager with releases/ directory."""
        mock_repo = Mock()
        mock_repo.base_dir = str(tmp_path)

        # Create releases/ directory
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        # Mock HGit
        mock_hgit = Mock()
        mock_hgit.branch = "ho-prod"
        mock_hgit.repos_is_clean.return_value = True
        mock_repo.hgit = mock_hgit

        release_mgr = ReleaseManager(mock_repo)

        return release_mgr, releases_dir, mock_hgit

    def test_not_on_ho_prod_branch(self, release_manager_basic):
        """Test error if not on ho-prod branch."""
        release_mgr, releases_dir, mock_hgit = release_manager_basic

        # Mock current branch is not ho-prod
        mock_hgit.branch = "ho-patch/456-user-auth"

        # Should raise error before lock
        with pytest.raises(ReleaseManagerError, match="Must be on ho-prod|ho-prod branch"):
            release_mgr.promote_to_rc()

        # Verify lock not attempted (no acquire_branch_lock call)
        assert not hasattr(mock_hgit, 'acquire_branch_lock') or \
               mock_hgit.acquire_branch_lock.call_count == 0

    def test_repository_not_clean(self, release_manager_basic):
        """Test error if repository has uncommitted changes."""
        release_mgr, releases_dir, mock_hgit = release_manager_basic

        # Mock dirty repository
        mock_hgit.repos_is_clean.return_value = False

        # Should raise error before lock
        with pytest.raises(ReleaseManagerError, match="uncommitted changes|not clean"):
            release_mgr.promote_to_rc()

        # Verify lock not attempted
        assert not hasattr(mock_hgit, 'acquire_branch_lock') or \
               mock_hgit.acquire_branch_lock.call_count == 0

    def test_no_stage_releases_found(self, release_manager_basic):
        """Test error if no stage releases exist."""
        release_mgr, releases_dir, mock_hgit = release_manager_basic

        # No stage files in releases/
        # (releases/ directory exists but empty)

        # Should raise error before lock
        with pytest.raises(ReleaseManagerError, match="No stage releases|stage.*not found"):
            release_mgr.promote_to_rc()

        # Verify lock not attempted
        assert not hasattr(mock_hgit, 'acquire_branch_lock') or \
               mock_hgit.acquire_branch_lock.call_count == 0

    def test_validations_checked_in_order(self, release_manager_basic):
        """Test validations are checked in correct order."""
        release_mgr, releases_dir, mock_hgit = release_manager_basic

        # First validation fails (not on ho-prod)
        mock_hgit.branch = "ho-patch/123"
        mock_hgit.repos_is_clean.return_value = False  # Would fail second validation

        # Should fail on first validation (branch check)
        with pytest.raises(ReleaseManagerError, match="ho-prod"):
            release_mgr.promote_to_rc()

        # repos_is_clean should not be called (fail fast)
        # Note: In actual implementation, this depends on order
        # This test documents expected behavior

    @pytest.mark.skip("Not implemented")
    def test_all_validations_pass_proceeds_to_detection(self, release_manager_basic):
        """Test that passing validations proceeds to stage detection."""
        release_mgr, releases_dir, mock_hgit = release_manager_basic

        # Create a stage file so we pass "no stages" validation
        stage_file = releases_dir / "1.3.5-stage.txt"
        stage_file.write_text("456-user-auth\n")

        # Mock the helper methods to avoid full workflow
        release_mgr._detect_stage_to_promote = Mock(return_value=("1.3.5", "1.3.5-stage.txt"))
        release_mgr._validate_single_active_rc = Mock()
        mock_hgit.acquire_branch_lock = Mock(side_effect=Exception("Stop here for test"))

        # Should pass validations and reach lock acquisition
        with pytest.raises(Exception, match="Stop here"):
            release_mgr.promote_to_rc()

        # Verify detection was called (validations passed)
        release_mgr._detect_stage_to_promote.assert_called_once()
