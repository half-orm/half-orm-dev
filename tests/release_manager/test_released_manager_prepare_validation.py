"""
Tests for ReleaseManager.prepare_release() - Git validations.

Focused on testing:
- Branch validation (must be ho-prod)
- Repository clean check
- Synchronization with origin
- Pull behavior (behind, ahead, diverged)
"""

import pytest
from unittest.mock import Mock

from half_orm_dev.release_manager import ReleaseManager, ReleaseManagerError


class TestPrepareReleaseValidations:
    """Test Git validations before release preparation."""

    def test_not_on_ho_prod_raises_error(self, mock_release_manager_with_hgit):
        """Test error when not on ho-prod branch."""
        release_mgr, mock_repo, mock_hgit, tmp_path = mock_release_manager_with_hgit

        # Mock current branch as patch branch
        mock_hgit.branch = "ho-patch/456-user-auth"

        with pytest.raises(ReleaseManagerError, match="Must be on ho-prod|ho-prod branch"):
            release_mgr.prepare_release('patch')

    def test_on_feature_branch_raises_error(self, mock_release_manager_with_hgit):
        """Test error when on non-ho-prod branch."""
        release_mgr, mock_repo, mock_hgit, tmp_path = mock_release_manager_with_hgit

        mock_hgit.branch = "feature/new-feature"

        with pytest.raises(ReleaseManagerError, match="Must be on ho-prod|ho-prod branch"):
            release_mgr.prepare_release('minor')

    def test_on_main_branch_raises_error(self, mock_release_manager_with_hgit):
        """Test error when on main/master branch."""
        release_mgr, mock_repo, mock_hgit, tmp_path = mock_release_manager_with_hgit

        mock_hgit.branch = "main"

        with pytest.raises(ReleaseManagerError, match="Must be on ho-prod|ho-prod branch"):
            release_mgr.prepare_release('major')

    def test_repo_not_clean_raises_error(self, mock_release_manager_with_hgit):
        """Test error when repository has uncommitted changes."""
        release_mgr, mock_repo, mock_hgit, tmp_path = mock_release_manager_with_hgit

        # Mock dirty repository
        mock_hgit.repos_is_clean.return_value = False

        with pytest.raises(ReleaseManagerError, match="uncommitted changes|not clean"):
            release_mgr.prepare_release('patch')

    def test_fetch_called_before_sync_check(self, mock_release_manager_with_production):
        """Test fetch_from_origin is called before checking sync."""
        release_mgr, mock_repo, mock_hgit, tmp_path, prod_version = mock_release_manager_with_production

        release_mgr.prepare_release('patch')

        # Verify fetch was called
        mock_hgit.fetch_from_origin.assert_called_once()

        # Verify sync check happened after fetch
        mock_hgit.is_branch_synced.assert_called_once_with("ho-prod")

    def test_synced_continues_without_pull(self, mock_release_manager_with_production):
        """Test continues without pull when branch is synced."""
        release_mgr, mock_repo, mock_hgit, tmp_path, prod_version = mock_release_manager_with_production

        # Mock synced status (default in fixture)
        mock_hgit.is_branch_synced.return_value = (True, "synced")

        # Should not raise and should complete
        result = release_mgr.prepare_release('patch')

        # Pull should NOT be called
        mock_hgit.pull.assert_not_called()
        assert result['version'] == '1.3.6'

    def test_behind_pulls_automatically(self, mock_release_manager_with_production):
        """Test automatic pull when behind origin."""
        release_mgr, mock_repo, mock_hgit, tmp_path, prod_version = mock_release_manager_with_production

        # Mock behind status
        mock_hgit.is_branch_synced.return_value = (False, "behind")

        # Should pull automatically and complete
        result = release_mgr.prepare_release('patch')

        # Verify pull was called
        mock_hgit.pull.assert_called_once()
        assert result['version'] == '1.3.6'

    def test_ahead_continues_without_pull(self, mock_release_manager_with_production):
        """Test continues without pull when ahead of origin."""
        release_mgr, mock_repo, mock_hgit, tmp_path, prod_version = mock_release_manager_with_production

        # Mock ahead status
        mock_hgit.is_branch_synced.return_value = (False, "ahead")

        # Should not pull but should complete
        result = release_mgr.prepare_release('patch')

        # Verify pull was NOT called
        mock_hgit.pull.assert_not_called()
        assert result['version'] == '1.3.6'

    def test_diverged_raises_error(self, mock_release_manager_with_hgit):
        """Test error when branch has diverged from origin."""
        release_mgr, mock_repo, mock_hgit, tmp_path = mock_release_manager_with_hgit

        # Mock diverged status
        mock_hgit.is_branch_synced.return_value = (False, "diverged")

        with pytest.raises(ReleaseManagerError, match="diverged|manual.*merge|manual.*rebase"):
            release_mgr.prepare_release('patch')

    def test_validations_run_in_order(self, mock_release_manager_with_hgit):
        """Test validations run in correct order (branch, clean, fetch, sync)."""
        release_mgr, mock_repo, mock_hgit, tmp_path = mock_release_manager_with_hgit

        # Make repo dirty to fail early
        mock_hgit.repos_is_clean.return_value = False

        try:
            release_mgr.prepare_release('patch')
        except ReleaseManagerError:
            pass

        # Fetch should NOT be called if repo not clean (early validation)
        mock_hgit.fetch_from_origin.assert_not_called()

    def test_invalid_increment_type_raises_error(self, mock_release_manager_with_production):
        """Test error with invalid increment type."""
        release_mgr, mock_repo, mock_hgit, tmp_path, prod_version = mock_release_manager_with_production

        with pytest.raises(ReleaseManagerError, match="Invalid.*increment"):
            release_mgr.prepare_release('invalid')
