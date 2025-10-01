"""
Tests for PatchManager._fetch_from_remote() method.

Tests remote synchronization before patch creation to ensure
up-to-date view of all remote references (branches and tags).
"""

import pytest
from unittest.mock import Mock
from git.exc import GitCommandError

from half_orm_dev.patch_manager import PatchManager, PatchManagerError


class TestPatchManagerFetchFromRemote:
    """Test remote fetch synchronization."""

    def test_fetch_from_remote_success(self, patch_manager, mock_hgit_complete):
        """Test successful fetch from remote."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Use complete mock
        repo.hgit = mock_hgit_complete

        # Should not raise
        patch_mgr._fetch_from_remote()

        # Should have called fetch on origin
        mock_hgit_complete.fetch_from_origin.assert_called_once()

    def test_fetch_from_remote_network_error(self, patch_manager, mock_hgit_complete):
        """Test fetch failure due to network error."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock fetch to raise network error
        mock_hgit_complete.fetch_from_origin.side_effect = GitCommandError(
            "git fetch", 1, stderr="Network unreachable"
        )
        repo.hgit = mock_hgit_complete

        # Should raise PatchManagerError
        with pytest.raises(PatchManagerError, match="Failed to fetch from remote"):
            patch_mgr._fetch_from_remote()

        # Error message should mention network
        with pytest.raises(PatchManagerError, match="Check network connection"):
            patch_mgr._fetch_from_remote()

    def test_fetch_from_remote_authentication_error(self, patch_manager, mock_hgit_complete):
        """Test fetch failure due to authentication."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock fetch to raise auth error
        mock_hgit_complete.fetch_from_origin.side_effect = GitCommandError(
            "git fetch", 1, stderr="Authentication failed"
        )
        repo.hgit = mock_hgit_complete

        # Should raise PatchManagerError
        with pytest.raises(PatchManagerError, match="Failed to fetch from remote"):
            patch_mgr._fetch_from_remote()

    def test_fetch_from_remote_no_remote(self, patch_manager, mock_hgit_complete):
        """Test fetch failure when no remote exists."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Mock fetch to raise no remote error
        mock_hgit_complete.fetch_from_origin.side_effect = GitCommandError(
            "git fetch", 1, stderr="No such remote 'origin'"
        )
        repo.hgit = mock_hgit_complete

        # Should raise PatchManagerError
        with pytest.raises(PatchManagerError, match="Failed to fetch from remote"):
            patch_mgr._fetch_from_remote()

    def test_fetch_called_before_availability_check(self, patch_manager, mock_hgit_complete):
        """Test that fetch happens before checking patch availability."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Use complete mock
        repo.hgit = mock_hgit_complete

        # Track call order
        call_order = []

        def track_fetch():
            call_order.append('fetch')

        def track_fetch_tags():
            call_order.append('fetch_tags')

        mock_hgit_complete.fetch_from_origin.side_effect = track_fetch
        mock_hgit_complete.fetch_tags.side_effect = track_fetch_tags

        # Create patch
        result = patch_mgr.create_patch("456-test")

        # fetch_from_origin should be called before fetch_tags
        assert call_order[0] == 'fetch'
        assert 'fetch_tags' in call_order
        assert call_order.index('fetch') < call_order.index('fetch_tags')
