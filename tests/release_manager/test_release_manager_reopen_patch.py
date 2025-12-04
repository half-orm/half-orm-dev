"""
Tests for ReleaseManager.reopen_patch() method.

Focused on testing:
- Successful reopen when patch is in stage file
- Error when patch not found in any stage
- Error when not on ho-prod branch
- Error when repository not clean
- Error when tag doesn't exist
- Error when release branch doesn't exist
- Tag deletion after successful reopen
- Stage file update after reopen
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, call

from half_orm_dev.release_manager import ReleaseManager, ReleaseManagerError


class TestReopenPatch:
    """Test reopen_patch() method."""

    @pytest.fixture
    def release_manager_setup(self, tmp_path):
        """Create ReleaseManager with mocked repo and setup."""
        mock_repo = Mock()
        mock_repo.base_dir = str(tmp_path)

        # Mock HGit
        mock_hgit = Mock()
        mock_repo.hgit = mock_hgit

        # Default mocks for successful scenario
        mock_hgit.branch = "ho-prod"
        mock_hgit.repos_is_clean.return_value = True
        mock_hgit.is_branch_synced.return_value = (True, "synced")
        mock_hgit.tag_exists.return_value = True
        mock_hgit.branch_exists.return_value = True
        mock_hgit.checkout = Mock()
        mock_hgit.delete_branch = Mock()
        mock_hgit.delete_remote_branch = Mock()
        mock_hgit.push = Mock()
        mock_hgit.add = Mock()
        mock_hgit.commit = Mock()
        mock_hgit.delete_local_tag = Mock()
        mock_hgit.delete_remote_tag = Mock()
        mock_hgit.fetch_from_origin = Mock()
        mock_hgit.pull = Mock()

        # Create releases/ directory
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir(exist_ok=True)

        release_mgr = ReleaseManager(mock_repo)

        return release_mgr, releases_dir, mock_repo, mock_hgit

    def test_reopen_patch_success(self, release_manager_setup):
        """Test successful patch reopen."""
        release_mgr, releases_dir, mock_repo, mock_hgit = release_manager_setup

        # Create stage file with patch
        stage_file = releases_dir / "1.3.6-stage.txt"
        stage_file.write_text("456-user-auth\n789-other-patch\n")

        # Execute reopen
        result = release_mgr.reopen_patch("456-user-auth")

        # Verify result
        assert result['patch_id'] == "456-user-auth"
        assert result['branch'] == "ho-patch/456-user-auth"
        assert result['release'] == "1.3.6"
        assert result['status'] == "reopened"

        # Verify tag operations
        mock_hgit.tag_exists.assert_called_with("ho-patch/456")
        mock_hgit.delete_local_tag.assert_called_with("ho-patch/456")
        mock_hgit.delete_remote_tag.assert_called_with("ho-patch/456")

        # Verify branch operations
        mock_hgit.checkout.assert_any_call("ho-release/1.3.6")
        mock_hgit.checkout.assert_any_call("-b", "ho-patch/456-user-auth", "ho-patch/456")
        mock_hgit.checkout.assert_any_call("ho-prod")
        mock_hgit.checkout.assert_any_call("ho-patch/456-user-auth")

        # Verify stage file updated (patch removed)
        updated_content = stage_file.read_text()
        assert "456-user-auth" not in updated_content
        assert "789-other-patch" in updated_content

        # Verify commit
        mock_hgit.add.assert_called()
        mock_hgit.commit.assert_called_with("-m", "Reopen patch 456-user-auth from release 1.3.6-stage")
        mock_hgit.push.assert_called()

    def test_reopen_patch_not_found_in_stage(self, release_manager_setup):
        """Test error when patch not in any stage file."""
        release_mgr, releases_dir, mock_repo, mock_hgit = release_manager_setup

        # Create stage file WITHOUT the patch
        stage_file = releases_dir / "1.3.6-stage.txt"
        stage_file.write_text("789-other-patch\n")

        with pytest.raises(ReleaseManagerError, match="not found in any stage release"):
            release_mgr.reopen_patch("456-user-auth")

    def test_reopen_patch_switches_to_ho_prod(self, release_manager_setup):
        """Test that reopen automatically switches to ho-prod if needed."""
        release_mgr, releases_dir, mock_repo, mock_hgit = release_manager_setup

        # Set current branch to something else
        mock_hgit.branch = "ho-patch/123-test"

        # Create stage file with patch
        stage_file = releases_dir / "1.3.6-stage.txt"
        stage_file.write_text("456-user-auth\n")

        # Execute reopen
        result = release_mgr.reopen_patch("456-user-auth")

        # Verify checkout to ho-prod was called
        mock_hgit.checkout.assert_any_call("ho-prod")

        # Verify success
        assert result['status'] == "reopened"

    def test_reopen_patch_repository_not_clean(self, release_manager_setup):
        """Test error when repository has uncommitted changes."""
        release_mgr, releases_dir, mock_repo, mock_hgit = release_manager_setup

        # Repository not clean
        mock_hgit.repos_is_clean.return_value = False

        with pytest.raises(ReleaseManagerError, match="uncommitted changes"):
            release_mgr.reopen_patch("456-user-auth")

    def test_reopen_patch_tag_not_exists(self, release_manager_setup):
        """Test error when tag doesn't exist."""
        release_mgr, releases_dir, mock_repo, mock_hgit = release_manager_setup

        # Create stage file with patch
        stage_file = releases_dir / "1.3.6-stage.txt"
        stage_file.write_text("456-user-auth\n")

        # Tag doesn't exist
        mock_hgit.tag_exists.return_value = False

        with pytest.raises(ReleaseManagerError, match="Tag.*not found"):
            release_mgr.reopen_patch("456-user-auth")

    def test_reopen_patch_release_branch_not_exists(self, release_manager_setup):
        """Test error when release branch doesn't exist."""
        release_mgr, releases_dir, mock_repo, mock_hgit = release_manager_setup

        # Create stage file with patch
        stage_file = releases_dir / "1.3.6-stage.txt"
        stage_file.write_text("456-user-auth\n")

        # Release branch doesn't exist
        def branch_exists_side_effect(branch):
            return branch != "ho-release/1.3.6"

        mock_hgit.branch_exists.side_effect = branch_exists_side_effect

        with pytest.raises(ReleaseManagerError, match="Release branch.*not found"):
            release_mgr.reopen_patch("456-user-auth")

    def test_reopen_patch_sync_behind_pulls(self, release_manager_setup):
        """Test that behind branch triggers pull."""
        release_mgr, releases_dir, mock_repo, mock_hgit = release_manager_setup

        # Create stage file with patch
        stage_file = releases_dir / "1.3.6-stage.txt"
        stage_file.write_text("456-user-auth\n")

        # Branch is behind
        mock_hgit.is_branch_synced.return_value = (False, "behind")

        # Execute reopen
        result = release_mgr.reopen_patch("456-user-auth")

        # Verify pull was called
        mock_hgit.pull.assert_called_once()

        # Verify success
        assert result['status'] == "reopened"

    def test_reopen_patch_sync_diverged_raises_error(self, release_manager_setup):
        """Test error when branch diverged."""
        release_mgr, releases_dir, mock_repo, mock_hgit = release_manager_setup

        # Create stage file with patch
        stage_file = releases_dir / "1.3.6-stage.txt"
        stage_file.write_text("456-user-auth\n")

        # Branch diverged
        mock_hgit.is_branch_synced.return_value = (False, "diverged")

        with pytest.raises(ReleaseManagerError, match="diverged"):
            release_mgr.reopen_patch("456-user-auth")

    def test_reopen_patch_deletes_existing_branch(self, release_manager_setup):
        """Test that existing patch branch is deleted before recreation."""
        release_mgr, releases_dir, mock_repo, mock_hgit = release_manager_setup

        # Create stage file with patch
        stage_file = releases_dir / "1.3.6-stage.txt"
        stage_file.write_text("456-user-auth\n")

        # Patch branch already exists (first call returns True)
        branch_exists_calls = [True, True]  # First for ho-release, second for ho-patch
        mock_hgit.branch_exists.side_effect = lambda b: branch_exists_calls.pop(0) if branch_exists_calls else False

        # Execute reopen
        result = release_mgr.reopen_patch("456-user-auth")

        # Verify branch deletion
        mock_hgit.delete_branch.assert_called_with("ho-patch/456-user-auth", force=True)

        # Verify success
        assert result['status'] == "reopened"

    def test_reopen_patch_multiple_stages(self, release_manager_setup):
        """Test reopen finds patch in correct stage when multiple exist."""
        release_mgr, releases_dir, mock_repo, mock_hgit = release_manager_setup

        # Create multiple stage files
        (releases_dir / "1.3.6-stage.txt").write_text("789-other\n")
        (releases_dir / "1.4.0-stage.txt").write_text("456-user-auth\n999-third\n")
        (releases_dir / "2.0.0-stage.txt").write_text("111-another\n")

        # Execute reopen
        result = release_mgr.reopen_patch("456-user-auth")

        # Verify found in correct version
        assert result['release'] == "1.4.0"

        # Verify correct release branch checked out
        mock_hgit.checkout.assert_any_call("ho-release/1.4.0")

    def test_reopen_patch_removes_only_target_patch(self, release_manager_setup):
        """Test that only the target patch is removed from stage file."""
        release_mgr, releases_dir, mock_repo, mock_hgit = release_manager_setup

        # Create stage file with multiple patches
        stage_file = releases_dir / "1.3.6-stage.txt"
        original_content = "123-first\n456-user-auth\n789-third\n999-fourth\n"
        stage_file.write_text(original_content)

        # Execute reopen
        release_mgr.reopen_patch("456-user-auth")

        # Verify only target patch removed
        updated_content = stage_file.read_text()
        assert "456-user-auth" not in updated_content
        assert "123-first" in updated_content
        assert "789-third" in updated_content
        assert "999-fourth" in updated_content

    def test_reopen_patch_no_longer_in_stage_after_sync(self, release_manager_setup):
        """Test error when patch disappears after sync (race condition)."""
        release_mgr, releases_dir, mock_repo, mock_hgit = release_manager_setup

        # Create stage file with patch
        stage_file = releases_dir / "1.3.6-stage.txt"
        stage_file.write_text("456-user-auth\n")

        # Simulate patch removal after sync by deleting file during fetch
        def fetch_side_effect():
            stage_file.write_text("789-other\n")  # Patch removed by another user

        mock_hgit.fetch_from_origin.side_effect = fetch_side_effect

        with pytest.raises(ReleaseManagerError, match="no longer in stage release after sync"):
            release_mgr.reopen_patch("456-user-auth")

    def test_reopen_patch_adds_to_candidates(self, release_manager_setup):
        """Test that reopened patch is added back to candidates file."""
        release_mgr, releases_dir, mock_repo, mock_hgit = release_manager_setup

        # Create stage file with patch
        stage_file = releases_dir / "1.3.6-stage.txt"
        stage_file.write_text("456-user-auth\n789-other\n")

        # Create candidates file with existing patches
        candidates_file = releases_dir / "1.3.6-candidates.txt"
        candidates_file.write_text("123-existing\n")

        # Execute reopen
        result = release_mgr.reopen_patch("456-user-auth")

        # Verify patch added to candidates
        candidates_content = candidates_file.read_text()
        assert "456-user-auth" in candidates_content
        assert "123-existing" in candidates_content

        # Verify both files committed
        assert mock_hgit.add.call_count == 2
        mock_hgit.add.assert_any_call(str(stage_file))
        mock_hgit.add.assert_any_call(str(candidates_file))

        # Verify success
        assert result['status'] == "reopened"

    def test_reopen_patch_creates_candidates_if_missing(self, release_manager_setup):
        """Test that candidates file is created if it doesn't exist."""
        release_mgr, releases_dir, mock_repo, mock_hgit = release_manager_setup

        # Create stage file with patch
        stage_file = releases_dir / "1.3.6-stage.txt"
        stage_file.write_text("456-user-auth\n")

        # No candidates file exists

        # Execute reopen
        result = release_mgr.reopen_patch("456-user-auth")

        # Verify candidates file created with patch
        candidates_file = releases_dir / "1.3.6-candidates.txt"
        assert candidates_file.exists()
        candidates_content = candidates_file.read_text()
        assert "456-user-auth" in candidates_content

        # Verify success
        assert result['status'] == "reopened"
