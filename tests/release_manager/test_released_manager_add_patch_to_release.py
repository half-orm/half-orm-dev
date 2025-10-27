"""
Tests for ReleaseManager.add_patch_to_release() - Complete workflow.

Focused on testing:
- Complete successful workflow with lock
- Lock acquisition and release
- Validation failures rollback properly
- Tests failure cleanup
- Push failure handling
- Lock release in finally block (even on error)
- Pre-lock validations (branch, clean, patch exists)
- Branch archiving after success
- Notifications sent after success
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, call
from git.exc import GitCommandError

from half_orm_dev.release_manager import ReleaseManager, ReleaseManagerError


class TestAddPatchToReleaseWorkflow:
    """Test complete add_patch_to_release() workflow."""

    @pytest.fixture
    def release_manager_complete_mock(self, tmp_path):
        """Create ReleaseManager with complete mocks."""
        mock_repo = Mock()
        mock_repo.base_dir = str(tmp_path)

        # Create directories
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()
        patches_dir = tmp_path / "Patches"
        patches_dir.mkdir()

        # Create patch directory
        patch_dir = patches_dir / "456-user-auth"
        patch_dir.mkdir()
        (patch_dir / "01_create_table.sql").write_text("CREATE TABLE users;")

        # Mock HGit
        mock_hgit = Mock()
        mock_hgit.branch = "ho-prod"
        mock_hgit.repos_is_clean.return_value = True
        mock_hgit.branch_exists = Mock(return_value=True)
        mock_hgit.last_commit = Mock(return_value="abc123de")

        # Mock lock operations
        mock_hgit.acquire_branch_lock = Mock(return_value="lock-ho-prod-1704123456789")
        mock_hgit.release_branch_lock = Mock()

        # Mock fetch/sync
        mock_hgit.fetch_from_origin = Mock()
        mock_hgit.is_branch_synced = Mock(return_value=(True, "synced"))

        # Mock branch operations
        mock_hgit.checkout = Mock()
        mock_hgit.add = Mock()
        mock_hgit.commit = Mock()
        mock_hgit.push = Mock()
        mock_hgit.rename_branch = Mock()

        # Mock git repo for branch deletion
        mock_git_repo = Mock()
        mock_git_repo.git.branch = Mock()
        mock_hgit._HGit__git_repo = mock_git_repo

        mock_repo.hgit = mock_hgit

        release_mgr = ReleaseManager(mock_repo)

        return release_mgr, releases_dir, patches_dir, mock_hgit

    def test_successful_workflow_complete(self, release_manager_complete_mock):
        """Test complete successful workflow."""
        release_mgr, releases_dir, patches_dir, mock_hgit = release_manager_complete_mock

        # Create stage file WITHOUT the patch we're adding
        stage_file = releases_dir / "1.3.6-stage.txt"
        stage_file.write_text("123-initial\n")

        # Mock helper methods
        release_mgr._detect_target_stage_file = Mock(return_value=("1.3.6", "1.3.6-stage.txt"))
        release_mgr._get_active_patch_branches = Mock(return_value=["ho-patch/789-security"])
        release_mgr._run_validation_tests = Mock()  # Tests pass
        # First call returns without patch (for duplication check), second with patch (for result)
        release_mgr.read_release_patches = Mock(side_effect=[
            ["123-initial"],  # Before add (duplication check)
            ["123-initial", "456-user-auth"]  # After add (result)
        ])

        # Execute
        result = release_mgr.add_patch_to_release("456-user-auth")

        # Verify lock acquired
        mock_hgit.acquire_branch_lock.assert_called_once_with("ho-prod", timeout_minutes=30)

        # Verify sync operations
        mock_hgit.fetch_from_origin.assert_called_once()
        assert mock_hgit.is_branch_synced.call_count == 2
        mock_hgit.is_branch_synced.assert_any_call("ho-patch/456-user-auth")
        mock_hgit.is_branch_synced.assert_any_call("ho-prod")

        # Verify temp branch created
        assert any("temp-valid-1.3.6" in str(call) for call in mock_hgit.checkout.call_args_list)

        # Verify tests run
        release_mgr._run_validation_tests.assert_called_once()

        # Verify commit on ho-prod
        commit_calls = mock_hgit.commit.call_args_list
        assert len(commit_calls) == 2  # Once on temp, once on ho-prod

        # Verify push
        mock_hgit.push.assert_called()

        # Verify branch renamed
        mock_hgit.rename_branch.assert_called_once_with(
            "ho-patch/456-user-auth",
            "ho-release/1.3.6/456-user-auth",
            delete_remote_old=True
        )

        # Verify lock released
        mock_hgit.release_branch_lock.assert_called_once_with("lock-ho-prod-1704123456789")

        # Verify result structure
        assert result['status'] == 'success'
        assert result['patch_id'] == '456-user-auth'
        assert result['target_version'] == '1.3.6'

    def test_lock_acquisition_failure_exits_early(self, release_manager_complete_mock):
        """Test exits early if lock acquisition fails."""
        release_mgr, releases_dir, patches_dir, mock_hgit = release_manager_complete_mock

        # Create stage file
        (releases_dir / "1.3.6-stage.txt").touch()

        # Mock lock acquisition failure
        mock_hgit.acquire_branch_lock.side_effect = GitCommandError("Lock held by another process", 1)

        # Mock helper
        release_mgr._detect_target_stage_file = Mock(return_value=("1.3.6", "1.3.6-stage.txt"))

        # Should raise error
        with pytest.raises(GitCommandError, match="Lock"):
            release_mgr.add_patch_to_release("456-user-auth")

        # Verify no further operations attempted
        mock_hgit.checkout.assert_not_called()
        mock_hgit.commit.assert_not_called()

    def test_tests_failure_triggers_cleanup(self, release_manager_complete_mock):
        """Test cleanup when tests fail on temp branch."""
        release_mgr, releases_dir, patches_dir, mock_hgit = release_manager_complete_mock

        # Create stage file
        (releases_dir / "1.3.6-stage.txt").touch()

        # Mock helpers
        release_mgr._detect_target_stage_file = Mock(return_value=("1.3.6", "1.3.6-stage.txt"))
        release_mgr._run_validation_tests = Mock(side_effect=ReleaseManagerError("Tests failed"))

        # Should raise error
        with pytest.raises(ReleaseManagerError, match="Tests failed"):
            release_mgr.add_patch_to_release("456-user-auth")

        # Verify temp branch was created
        temp_branch_created = any("temp-valid-1.3.6" in str(call) for call in mock_hgit.checkout.call_args_list)
        assert temp_branch_created

        # Verify returned to ho-prod
        checkout_calls = [call[0][0] for call in mock_hgit.checkout.call_args_list if call[0]]
        assert "ho-prod" in checkout_calls

        # Verify temp branch deleted
        mock_git_repo = mock_hgit._HGit__git_repo
        delete_calls = mock_git_repo.git.branch.call_args_list
        temp_deleted = any("-D" in str(call) and "temp-valid-1.3.6" in str(call) for call in delete_calls)
        assert temp_deleted

        # Verify lock released (in finally)
        mock_hgit.release_branch_lock.assert_called_once()

        # Verify no push occurred
        mock_hgit.push.assert_not_called()

    def test_lock_released_on_any_error(self, release_manager_complete_mock):
        """Test lock always released even on unexpected error."""
        release_mgr, releases_dir, patches_dir, mock_hgit = release_manager_complete_mock

        # Create stage file
        (releases_dir / "1.3.6-stage.txt").touch()

        # Mock helpers
        release_mgr._detect_target_stage_file = Mock(return_value=("1.3.6", "1.3.6-stage.txt"))

        # Mock unexpected error during workflow
        mock_hgit.checkout.side_effect = [
            None,  # First checkout (temp branch) succeeds
            RuntimeError("Unexpected error")  # Second fails
        ]

        # Should raise error
        with pytest.raises(RuntimeError, match="Unexpected"):
            release_mgr.add_patch_to_release("456-user-auth")

        # Verify lock was released (in finally block)
        mock_hgit.release_branch_lock.assert_called_once_with("lock-ho-prod-1704123456789")

    def test_validation_not_on_ho_prod(self, release_manager_complete_mock):
        """Test error if not on ho-prod branch."""
        release_mgr, releases_dir, patches_dir, mock_hgit = release_manager_complete_mock

        # Mock current branch is not ho-prod
        mock_hgit.branch = "ho-patch/999-other"

        # Should raise error before lock
        with pytest.raises(ReleaseManagerError, match="Must be on ho-prod|ho-prod branch"):
            release_mgr.add_patch_to_release("456-user-auth")

        # Verify lock not attempted
        mock_hgit.acquire_branch_lock.assert_not_called()

    def test_validation_repo_not_clean(self, release_manager_complete_mock):
        """Test error if repository not clean."""
        release_mgr, releases_dir, patches_dir, mock_hgit = release_manager_complete_mock

        # Mock dirty repository
        mock_hgit.repos_is_clean.return_value = False

        # Should raise error before lock
        with pytest.raises(ReleaseManagerError, match="uncommitted changes|not clean"):
            release_mgr.add_patch_to_release("456-user-auth")

        # Verify lock not attempted
        mock_hgit.acquire_branch_lock.assert_not_called()

    def test_validation_patch_not_exists(self, release_manager_complete_mock):
        """Test error if patch directory doesn't exist."""
        release_mgr, releases_dir, patches_dir, mock_hgit = release_manager_complete_mock

        # Patch directory doesn't exist (only 456 created in fixture)

        # Should raise error before lock
        with pytest.raises(ReleaseManagerError, match="Patch.*not found|doesn't exist"):
            release_mgr.add_patch_to_release("999-nonexistent")

        # Verify lock not attempted
        mock_hgit.acquire_branch_lock.assert_not_called()

    def test_ho_prod_behind_pulls_automatically(self, release_manager_complete_mock):
        """Test automatic pull when ho-prod is behind origin."""
        release_mgr, releases_dir, patches_dir, mock_hgit = release_manager_complete_mock

        # Create stage file WITHOUT the patch
        (releases_dir / "1.3.6-stage.txt").write_text("123-initial\n")

        # Mock ho-prod behind origin
        mock_hgit.is_branch_synced.return_value = (False, "behind")

        # Mock helpers
        release_mgr._detect_target_stage_file = Mock(return_value=("1.3.6", "1.3.6-stage.txt"))
        release_mgr._get_active_patch_branches = Mock(return_value=[])
        release_mgr._send_rebase_notifications = Mock(return_value=[])
        release_mgr._run_validation_tests = Mock()
        release_mgr.read_release_patches = Mock(side_effect=[
            ["123-initial"],  # Before add
            ["123-initial", "456-user-auth"]  # After add
        ])

        # Execute
        result = release_mgr.add_patch_to_release("456-user-auth")

        # Verify pull was called
        mock_hgit.pull.assert_called_once()

        # Verify workflow completed
        assert result['status'] == 'success'

    def test_ho_prod_diverged_raises_error(self, release_manager_complete_mock):
        """Test error when ho-prod has diverged from origin."""
        release_mgr, releases_dir, patches_dir, mock_hgit = release_manager_complete_mock

        # Create stage file
        (releases_dir / "1.3.6-stage.txt").touch()

        # Mock ho-prod diverged
        mock_hgit.is_branch_synced.return_value = (False, "diverged")

        # Mock helper
        release_mgr._detect_target_stage_file = Mock(return_value=("1.3.6", "1.3.6-stage.txt"))

        # Should raise error
        with pytest.raises(ReleaseManagerError, match="diverged|manual.*merge"):
            release_mgr.add_patch_to_release("456-user-auth")

        # Verify lock released
        mock_hgit.release_branch_lock.assert_called_once()

    def test_patch_already_in_release_raises_error(self, release_manager_complete_mock):
        """Test error if patch already in release."""
        release_mgr, releases_dir, patches_dir, mock_hgit = release_manager_complete_mock

        # Create stage file with patch already in it
        stage_file = releases_dir / "1.3.6-stage.txt"
        stage_file.write_text("123-initial\n456-user-auth\n")

        # Mock helper
        release_mgr._detect_target_stage_file = Mock(return_value=("1.3.6", "1.3.6-stage.txt"))

        # Should raise error
        with pytest.raises(ReleaseManagerError, match="already in release"):
            release_mgr.add_patch_to_release("456-user-auth")

        # Verify lock not acquired (error before lock)
        mock_hgit.acquire_branch_lock.assert_not_called()
