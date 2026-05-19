"""
Tests for ho-current migration in ReleaseManager.update_production().

When a production server still tracks ho-prod (legacy), hop update should:
  - Create ho-current from v{current_version} tag (local-only)
  - Switch to ho-current

Conditions that trigger migration:
  - production=True in connection file
  - current branch is ho-prod
  - ho-current does not exist locally
"""

import pytest
from unittest.mock import Mock, call

from half_orm_dev.release_manager import ReleaseManager, ReleaseManagerError


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mgr_on_ho_prod(tmp_path):
    """
    ReleaseManager configured as a production server on ho-prod (legacy state).

    - production=True
    - branch = 'ho-prod'
    - ho-current does not exist
    - current version = 1.3.5 with matching tag v1.3.5
    """
    releases_dir = tmp_path / ".hop" / "releases"
    releases_dir.mkdir(parents=True, exist_ok=True)

    mock_repo = Mock()
    mock_repo.name = "test_repo"
    mock_repo.base_dir = tmp_path
    mock_repo.releases_dir = str(releases_dir)
    mock_repo.model_dir = str(tmp_path / ".hop" / "model")
    mock_repo.allow_rc = False
    mock_repo.production = True

    mock_database = Mock()
    mock_database.last_release_s = "1.3.5"
    mock_repo.database = mock_database

    mock_hgit = Mock()
    mock_hgit.branch = 'ho-prod'
    mock_hgit.fetch_tags = Mock()
    mock_hgit.branch_exists = Mock(return_value=False)  # ho-current does not exist
    mock_hgit.create_branch_from_tag = Mock()

    # Simulate existing tag v1.3.5
    mock_tag = Mock()
    mock_tag.name = "v1.3.5"

    mock_git_repo = Mock()
    mock_git_repo.tags = [mock_tag]

    # heads['ho-current'] must support .checkout()
    mock_head = Mock()
    mock_git_repo.heads = {'ho-current': mock_head}

    mock_hgit._HGit__git_repo = mock_git_repo
    mock_repo.hgit = mock_hgit

    return ReleaseManager(mock_repo), mock_repo, mock_hgit, mock_git_repo


# ============================================================================
# MIGRATION TESTS
# ============================================================================

class TestHoCurrentMigration:
    """Tests for ho-prod → ho-current migration in update_production()."""

    def test_creates_ho_current_from_tag(self, mgr_on_ho_prod):
        """Migration creates ho-current from v{current_version} tag."""
        mgr, _, mock_hgit, _ = mgr_on_ho_prod

        mgr.update_production()

        mock_hgit.create_branch_from_tag.assert_called_once_with('ho-current', 'v1.3.5')

    def test_switches_to_ho_current(self, mgr_on_ho_prod):
        """Migration checks out ho-current after creating it."""
        mgr, _, mock_hgit, mock_git_repo = mgr_on_ho_prod

        mgr.update_production()

        mock_git_repo.heads['ho-current'].checkout.assert_called_once()

    def test_migration_skipped_when_not_production(self, mgr_on_ho_prod):
        """Migration does not run when production=False."""
        mgr, mock_repo, mock_hgit, _ = mgr_on_ho_prod
        mock_repo.production = False

        mgr.update_production()

        mock_hgit.create_branch_from_tag.assert_not_called()

    def test_migration_skipped_when_already_on_ho_current(self, mgr_on_ho_prod):
        """Migration does not run when branch is already ho-current."""
        mgr, _, mock_hgit, _ = mgr_on_ho_prod
        mock_hgit.branch = 'ho-current'

        mgr.update_production()

        mock_hgit.create_branch_from_tag.assert_not_called()

    def test_migration_skipped_when_ho_current_exists(self, mgr_on_ho_prod):
        """Migration does not run when ho-current already exists locally."""
        mgr, _, mock_hgit, _ = mgr_on_ho_prod
        mock_hgit.branch_exists.return_value = True

        mgr.update_production()

        mock_hgit.create_branch_from_tag.assert_not_called()

    def test_migration_raises_when_tag_missing(self, mgr_on_ho_prod):
        """Migration raises ReleaseManagerError when tag v{version} is not found."""
        mgr, _, mock_hgit, mock_git_repo = mgr_on_ho_prod
        mock_git_repo.tags = []  # No tags at all

        with pytest.raises(ReleaseManagerError, match="tag v1.3.5 not found"):
            mgr.update_production()

        mock_hgit.create_branch_from_tag.assert_not_called()

    def test_migration_does_not_push_to_origin(self, mgr_on_ho_prod):
        """Migration is purely local — no push to origin."""
        mgr, _, mock_hgit, mock_git_repo = mgr_on_ho_prod

        mgr.update_production()

        # push must never be called anywhere during migration
        mock_hgit.push.assert_not_called()
        remotes = getattr(mock_git_repo, 'remotes', None)
        if remotes:
            mock_git_repo.remotes.origin.push.assert_not_called()
