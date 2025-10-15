"""
Tests for ReleaseManager._ensure_patch_branch_synced() method.

Focused on testing:
- Already synced → no action taken
- Merge successful (behind or diverged)
- Manual resolution required (merge conflicts)
- Return to original branch after sync
- Push operations
- Error handling and cleanup
"""

import pytest
from unittest.mock import Mock, call
from git.exc import GitCommandError

from half_orm_dev.release_manager import ReleaseManager, ReleaseManagerError


class TestEnsurePatchBranchSynced:
    """Test _ensure_patch_branch_synced() method."""

    @pytest.fixture
    def release_manager_with_mock_hgit(self, tmp_path):
        """Create ReleaseManager with mocked HGit."""
        mock_repo = Mock()
        mock_repo.base_dir = str(tmp_path)

        # Create releases/ directory
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        # Mock HGit
        mock_hgit = Mock()
        mock_hgit.branch = "ho-prod"  # Current branch
        mock_repo.hgit = mock_hgit

        release_mgr = ReleaseManager(mock_repo)

        return release_mgr, mock_hgit

    def test_already_synced_no_action(self, release_manager_with_mock_hgit):
        """Test returns immediately when branch already synced."""
        release_mgr, mock_hgit = release_manager_with_mock_hgit

        # Mock already synced
        mock_hgit.is_branch_synced.return_value = (True, "synced")

        result = release_mgr._ensure_patch_branch_synced("456-user-auth")

        # Should check sync status
        mock_hgit.is_branch_synced.assert_called_once_with("ho-patch/456-user-auth")

        # Should NOT checkout, merge, or push
        mock_hgit.checkout.assert_not_called()
        mock_hgit.merge.assert_not_called()
        mock_hgit.push.assert_not_called()

        # Should return already-synced strategy
        assert result['strategy'] == 'already-synced'
        assert result['branch_name'] == 'ho-patch/456-user-auth'

    def test_merge_successful_behind(self, release_manager_with_mock_hgit):
        """Test merge when branch is behind."""
        release_mgr, mock_hgit = release_manager_with_mock_hgit

        # Mock behind status
        mock_hgit.is_branch_synced.return_value = (False, "behind")
        mock_hgit.branch = "ho-prod"

        # Mock successful merge
        mock_hgit.merge.return_value = None

        result = release_mgr._ensure_patch_branch_synced("456-user-auth")

        # Should checkout patch branch
        mock_hgit.checkout.assert_any_call("ho-patch/456-user-auth")

        # Should merge ho-prod
        mock_hgit.merge.assert_called_once_with("ho-prod")

        # Should push changes
        mock_hgit.push.assert_called_once()

        # Should return to original branch
        checkout_calls = [call[0][0] for call in mock_hgit.checkout.call_args_list]
        assert "ho-prod" == checkout_calls[-1]

        # Should return merge strategy
        assert result['strategy'] == 'merge'
        assert result['branch_name'] == 'ho-patch/456-user-auth'

    def test_merge_successful_diverged(self, release_manager_with_mock_hgit):
        """Test merge when branch has diverged."""
        release_mgr, mock_hgit = release_manager_with_mock_hgit

        # Mock diverged status
        mock_hgit.is_branch_synced.return_value = (False, "diverged")
        mock_hgit.branch = "ho-prod"

        # Mock successful merge
        mock_hgit.merge.return_value = None

        result = release_mgr._ensure_patch_branch_synced("456-user-auth")

        # Should checkout patch branch
        mock_hgit.checkout.assert_any_call("ho-patch/456-user-auth")

        # Should merge ho-prod
        mock_hgit.merge.assert_called_once_with("ho-prod")

        # Should push changes
        mock_hgit.push.assert_called_once()

        # Should return to original branch
        checkout_calls = [call[0][0] for call in mock_hgit.checkout.call_args_list]
        assert "ho-prod" == checkout_calls[-1]

        # Should return merge strategy
        assert result['strategy'] == 'merge'
        assert result['branch_name'] == 'ho-patch/456-user-auth'

    def test_merge_successful_ahead(self, release_manager_with_mock_hgit):
        """Test merge when branch is ahead (should still work)."""
        release_mgr, mock_hgit = release_manager_with_mock_hgit

        # Mock ahead status
        mock_hgit.is_branch_synced.return_value = (False, "ahead")
        mock_hgit.branch = "ho-prod"

        # Mock successful merge (no-op if already ahead)
        mock_hgit.merge.return_value = None

        result = release_mgr._ensure_patch_branch_synced("456-user-auth")

        # Should still attempt merge (git will handle it)
        mock_hgit.merge.assert_called_once_with("ho-prod")

        # Should return merge strategy
        assert result['strategy'] == 'merge'
        assert result['branch_name'] == 'ho-patch/456-user-auth'

    def test_manual_resolution_required_merge_conflicts(self, release_manager_with_mock_hgit):
        """Test raises error when merge has conflicts (manual resolution needed)."""
        release_mgr, mock_hgit = release_manager_with_mock_hgit

        # Mock diverged status
        mock_hgit.is_branch_synced.return_value = (False, "diverged")
        mock_hgit.branch = "ho-prod"

        # Mock merge conflict
        mock_hgit.merge.side_effect = GitCommandError(
            "merge", 1, stderr="CONFLICT (content): Merge conflict in file.py"
        )

        # Should raise ReleaseManagerError
        with pytest.raises(ReleaseManagerError) as exc_info:
            release_mgr._ensure_patch_branch_synced("456-user-auth")

        # Error message should mention manual resolution
        error_msg = str(exc_info.value).lower()
        assert "manual" in error_msg or "conflict" in error_msg
        assert "456-user-auth" in str(exc_info.value)
        assert "ho-patch/456-user-auth" in str(exc_info.value)

        # Should provide resolution instructions
        assert "git checkout" in str(exc_info.value)
        assert "git merge" in str(exc_info.value)

    def test_returns_to_original_branch_on_success(self, release_manager_with_mock_hgit):
        """Test always returns to original branch after successful sync."""
        release_mgr, mock_hgit = release_manager_with_mock_hgit

        # Mock behind status
        mock_hgit.is_branch_synced.return_value = (False, "behind")
        mock_hgit.branch = "ho-prod"

        result = release_mgr._ensure_patch_branch_synced("456-user-auth")

        # Should checkout patch branch, then return to ho-prod
        checkout_calls = [call[0][0] for call in mock_hgit.checkout.call_args_list]
        assert len(checkout_calls) == 2
        assert checkout_calls[0] == "ho-patch/456-user-auth"
        assert checkout_calls[1] == "ho-prod"

    def test_returns_to_original_branch_on_error(self, release_manager_with_mock_hgit):
        """Test returns to original branch even when sync fails."""
        release_mgr, mock_hgit = release_manager_with_mock_hgit

        # Mock diverged status
        mock_hgit.is_branch_synced.return_value = (False, "diverged")
        mock_hgit.branch = "ho-prod"

        # Mock merge failure
        mock_hgit.merge.side_effect = GitCommandError("merge", 1)

        # Should raise error
        with pytest.raises(ReleaseManagerError):
            release_mgr._ensure_patch_branch_synced("456-user-auth")

        # Should still return to original branch
        checkout_calls = [call[0][0] for call in mock_hgit.checkout.call_args_list]
        assert "ho-prod" == checkout_calls[-1]

    def test_push_called_after_successful_merge(self, release_manager_with_mock_hgit):
        """Test push is called after successful merge."""
        release_mgr, mock_hgit = release_manager_with_mock_hgit

        # Mock behind status
        mock_hgit.is_branch_synced.return_value = (False, "behind")
        mock_hgit.branch = "ho-prod"
        mock_hgit.merge.return_value = None

        release_mgr._ensure_patch_branch_synced("456-user-auth")

        # Should push after merge (standard push, no force)
        mock_hgit.push.assert_called_once_with()

    def test_multiple_patches_sequential_sync(self, release_manager_with_mock_hgit):
        """Test syncing multiple patches sequentially."""
        release_mgr, mock_hgit = release_manager_with_mock_hgit

        # Mock all behind
        mock_hgit.is_branch_synced.return_value = (False, "behind")
        mock_hgit.branch = "ho-prod"
        mock_hgit.merge.return_value = None

        # Sync multiple patches
        result1 = release_mgr._ensure_patch_branch_synced("456-user-auth")
        result2 = release_mgr._ensure_patch_branch_synced("789-security")
        result3 = release_mgr._ensure_patch_branch_synced("234-reports")

        # All should succeed
        assert result1['strategy'] == 'merge'
        assert result2['strategy'] == 'merge'
        assert result3['strategy'] == 'merge'

        # Should have checked out each branch
        checkout_calls = [call[0][0] for call in mock_hgit.checkout.call_args_list]
        assert "ho-patch/456-user-auth" in checkout_calls
        assert "ho-patch/789-security" in checkout_calls
        assert "ho-patch/234-reports" in checkout_calls

        # Should have merged 3 times
        assert mock_hgit.merge.call_count == 3

        # Should have pushed 3 times
        assert mock_hgit.push.call_count == 3

    def test_error_message_includes_instructions(self, release_manager_with_mock_hgit):
        """Test error message includes clear manual resolution instructions."""
        release_mgr, mock_hgit = release_manager_with_mock_hgit

        mock_hgit.is_branch_synced.return_value = (False, "diverged")
        mock_hgit.branch = "ho-prod"
        mock_hgit.merge.side_effect = GitCommandError("merge", 1)

        with pytest.raises(ReleaseManagerError) as exc_info:
            release_mgr._ensure_patch_branch_synced("456-user-auth")

        error_msg = str(exc_info.value)

        # Should include branch name
        assert "ho-patch/456-user-auth" in error_msg

        # Should include resolution steps
        assert "git checkout ho-patch/456-user-auth" in error_msg
        assert "git merge ho-prod" in error_msg
        assert "git add" in error_msg or "Resolve conflicts" in error_msg
        assert "git commit" in error_msg
        assert "git push" in error_msg

        # Should include retry instruction
        assert "half_orm dev add-to-release 456-user-auth" in error_msg

    def test_sync_from_non_ho_prod_branch(self, release_manager_with_mock_hgit):
        """Test sync works from any branch (not just ho-prod)."""
        release_mgr, mock_hgit = release_manager_with_mock_hgit

        # Mock current branch is a different patch branch
        mock_hgit.is_branch_synced.return_value = (False, "behind")
        mock_hgit.branch = "ho-patch/789-other"
        mock_hgit.merge.return_value = None

        result = release_mgr._ensure_patch_branch_synced("456-user-auth")

        # Should return to original branch (not ho-prod)
        checkout_calls = [call[0][0] for call in mock_hgit.checkout.call_args_list]
        assert "ho-patch/789-other" == checkout_calls[-1]

        # Should still succeed
        assert result['strategy'] == 'merge'
        assert result['branch_name'] == 'ho-patch/456-user-auth'

    def test_returns_to_original_branch_on_error(self, release_manager_with_mock_hgit):
        """Test returns to original branch even when sync fails."""
        release_mgr, mock_hgit = release_manager_with_mock_hgit

        # Mock diverged status
        mock_hgit.is_branch_synced.return_value = (False, "diverged")
        mock_hgit.branch = "ho-prod"

        # Mock all strategies fail
        mock_hgit.merge.side_effect = [
            GitCommandError("merge", 1),
            GitCommandError("merge", 1)
        ]
        mock_hgit.rebase.side_effect = [GitCommandError("rebase", 1)]

        # Should raise error
        with pytest.raises(ReleaseManagerError):
            release_mgr._ensure_patch_branch_synced("456-user-auth")

        # Should still return to original branch
        checkout_calls = [call[0][0] for call in mock_hgit.checkout.call_args_list]
        assert "ho-prod" == checkout_calls[-1]

    def test_push_with_correct_flags(self, release_manager_with_mock_hgit):
        """Test push uses correct flags based on sync strategy."""
        release_mgr, mock_hgit = release_manager_with_mock_hgit

        # Test: Simple merge - regular push (no force)
        mock_hgit.is_branch_synced.return_value = (False, "behind")
        mock_hgit.branch = "ho-prod"
        mock_hgit.merge.return_value = None
        mock_hgit.push.return_value = None  # Mock push success

        release_mgr._ensure_patch_branch_synced("456-user-auth")
        
        # Should push without force
        mock_hgit.push.assert_called_once_with()

        # Reset mocks for second test
        mock_hgit.reset_mock()

        # Test 2: Another patch - still regular push (no rebase in our simple strategy)
        mock_hgit.is_branch_synced.return_value = (False, "diverged")
        mock_hgit.branch = "ho-prod"
        mock_hgit.merge.return_value = None
        mock_hgit.push.return_value = None  # Mock push success

        release_mgr._ensure_patch_branch_synced("789-security")

        # Should push without force (simple merge strategy, no rebase)
        mock_hgit.push.assert_called_once_with()

    def test_checkout_failure_during_sync(self, release_manager_with_mock_hgit):
        """Test handles checkout failure gracefully."""
        release_mgr, mock_hgit = release_manager_with_mock_hgit

        # Mock sync needed
        mock_hgit.is_branch_synced.return_value = (False, "behind")
        mock_hgit.branch = "ho-prod"

        # Mock checkout failure
        mock_hgit.checkout.side_effect = GitCommandError("checkout", 1)

        # Should raise error
        with pytest.raises(GitCommandError):
            release_mgr._ensure_patch_branch_synced("456-user-auth")

    def test_push_failure_after_merge(self, release_manager_with_mock_hgit):
        """Test handles push failure after successful merge (raises ReleaseManagerError)."""
        release_mgr, mock_hgit = release_manager_with_mock_hgit

        # Mock sync needed
        mock_hgit.is_branch_synced.return_value = (False, "behind")
        mock_hgit.branch = "ho-prod"
        mock_hgit.merge.return_value = None

        # Mock push failure
        mock_hgit.push.side_effect = GitCommandError("push", 1)

        # Should raise ReleaseManagerError (implementation catches all GitCommandError)
        with pytest.raises(ReleaseManagerError) as exc_info:
            release_mgr._ensure_patch_branch_synced("456-user-auth")

        # Should mention the branch in error
        assert "ho-patch/456-user-auth" in str(exc_info.value)

        # Should have attempted both merge and push
        mock_hgit.merge.assert_called_once_with("ho-prod")
        mock_hgit.push.assert_called_once()