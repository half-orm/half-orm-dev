"""
Tests for PatchManager._validate_branch_synced_with_origin() method.

Focused on testing:
- Validation passes when ho-prod is synced with origin
- Validation fails with clear error when ahead
- Validation fails with clear error when behind
- Validation fails with clear error when diverged
"""

import pytest
from pathlib import Path
from unittest.mock import Mock
from git.exc import GitCommandError

from half_orm_dev.patch_manager import PatchManager, PatchManagerError

@pytest.skip(allow_module_level=True)
class TestPatchManagerSyncValidation:
    """Test _validate_branch_synced_with_origin() validation method."""

    @pytest.fixture
    def patch_manager_with_mock_hgit(self, tmp_path):
        """Create PatchManager with mocked HGit."""
        # Create temporary directory structure
        patches_dir = tmp_path / "Patches"
        patches_dir.mkdir()

        # Mock repo
        mock_repo = Mock()
        mock_repo.base_dir = str(tmp_path)
        mock_repo.model_dir = str(tmp_path / ".hop" / "model")
        mock_repo.devel = True
        mock_repo.name = "test_repo"

        # Mock HGit
        mock_hgit = Mock()
        mock_repo.hgit = mock_hgit

        # Create PatchManager
        patch_mgr = PatchManager(mock_repo)

        return patch_mgr, mock_repo, mock_hgit

    def test_validate_ho_prod_synced_success(self, patch_manager_with_mock_hgit):
        """Test validation passes when ho-prod is synced."""
        patch_mgr, mock_repo, mock_hgit = patch_manager_with_mock_hgit

        # Mock is_branch_synced to return synced
        mock_hgit.is_branch_synced.return_value = (True, "synced")

        # Should not raise
        patch_mgr._validate_branch_synced_with_origin()

        # Should have checked ho-prod sync
        mock_hgit.is_branch_synced.assert_called_once_with("ho-prod", remote="origin")

    def test_validate_ho_prod_ahead_fails(self, patch_manager_with_mock_hgit):
        """Test validation fails when ho-prod is ahead of origin."""
        patch_mgr, mock_repo, mock_hgit = patch_manager_with_mock_hgit

        # Mock is_branch_synced to return ahead
        mock_hgit.is_branch_synced.return_value = (False, "ahead")

        # Should raise with clear message
        with pytest.raises(PatchManagerError) as exc_info:
            patch_mgr._validate_branch_synced_with_origin()

        error_message = str(exc_info.value)
        assert "ahead of origin/ho-prod" in error_message
        assert "git push" in error_message

    def test_validate_ho_prod_behind_fails(self, patch_manager_with_mock_hgit):
        """Test validation fails when ho-prod is behind origin."""
        patch_mgr, mock_repo, mock_hgit = patch_manager_with_mock_hgit

        # Mock is_branch_synced to return behind
        mock_hgit.is_branch_synced.return_value = (False, "behind")

        # Should raise with clear message
        with pytest.raises(PatchManagerError) as exc_info:
            patch_mgr._validate_branch_synced_with_origin()

        error_message = str(exc_info.value)
        assert "behind origin/ho-prod" in error_message
        assert "git pull" in error_message

    def test_validate_ho_prod_diverged_fails(self, patch_manager_with_mock_hgit):
        """Test validation fails when ho-prod has diverged from origin."""
        patch_mgr, mock_repo, mock_hgit = patch_manager_with_mock_hgit

        # Mock is_branch_synced to return diverged
        mock_hgit.is_branch_synced.return_value = (False, "diverged")

        # Should raise with clear message
        with pytest.raises(PatchManagerError) as exc_info:
            patch_mgr._validate_branch_synced_with_origin()

        error_message = str(exc_info.value)
        assert "diverged from origin/ho-prod" in error_message
        assert "merge" in error_message.lower() or "rebase" in error_message.lower()

    def test_validate_ho_prod_synced_checks_origin_remote(self, patch_manager_with_mock_hgit):
        """Test validation specifically checks origin remote."""
        patch_mgr, mock_repo, mock_hgit = patch_manager_with_mock_hgit

        mock_hgit.is_branch_synced.return_value = (True, "synced")

        patch_mgr._validate_branch_synced_with_origin()

        # Should check against 'origin' remote specifically
        mock_hgit.is_branch_synced.assert_called_once_with("ho-prod", remote="origin")

    def test_validate_ho_prod_synced_git_error_propagated(self, patch_manager_with_mock_hgit):
        """Test git errors are properly propagated."""
        patch_mgr, mock_repo, mock_hgit = patch_manager_with_mock_hgit

        # Mock is_branch_synced to raise GitCommandError
        mock_hgit.is_branch_synced.side_effect = GitCommandError(
            "git", 1, stderr="Branch not found"
        )

        # Should raise PatchManagerError wrapping GitCommandError
        with pytest.raises(PatchManagerError) as exc_info:
            patch_mgr._validate_branch_synced_with_origin()

        error_message = str(exc_info.value)
        assert "sync" in error_message.lower()

    def test_validate_ho_prod_synced_different_status_messages(self, patch_manager_with_mock_hgit):
        """Test different status messages produce appropriate errors."""
        patch_mgr, mock_repo, mock_hgit = patch_manager_with_mock_hgit

        test_cases = [
            ("ahead", "ahead", "push"),
            ("behind", "behind", "pull"),
            ("diverged", "diverged", "merge")
        ]

        for is_synced_value, status, expected_keyword in test_cases:
            mock_hgit.is_branch_synced.return_value = (False, status)

            with pytest.raises(PatchManagerError) as exc_info:
                patch_mgr._validate_branch_synced_with_origin("ho-prod")

            error_message = str(exc_info.value).lower()
            assert status in error_message
            assert expected_keyword in error_message
