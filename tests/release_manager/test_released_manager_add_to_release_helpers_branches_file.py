"""
Tests for ReleaseManager helper methods:
- _get_active_patch_branches()
- _apply_patch_change_to_stage_file()

Focused on testing:
- Listing remote patch branches after fetch
- Filtering by ho-patch/* pattern
- Empty list when no patches
- File append operations
- File creation if doesn't exist
- Error handling for file operations
"""

import pytest
from pathlib import Path
from unittest.mock import Mock

from half_orm_dev.release_manager import ReleaseManager, ReleaseManagerError


class TestGetActivePatchBranches:
    """Test _get_active_patch_branches() method."""

    @pytest.fixture
    def release_manager_with_mock_hgit(self, tmp_path):
        """Create ReleaseManager with mocked HGit."""
        mock_repo = Mock()
        mock_repo.base_dir = str(tmp_path)

        # Create releases/ directory
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir(exist_ok=True)

        # Mock HGit with git repo access
        mock_hgit = Mock()
        mock_git_repo = Mock()
        mock_hgit._HGit__git_repo = mock_git_repo
        mock_repo.hgit = mock_hgit

        release_mgr = ReleaseManager(mock_repo)

        return release_mgr, mock_hgit, mock_git_repo

    def test_no_patch_branches_returns_empty(self, release_manager_with_mock_hgit):
        """Test returns empty list when no patch branches exist."""
        release_mgr, mock_hgit, mock_git_repo = release_manager_with_mock_hgit

        # Mock remote with no patch branches
        mock_remote = Mock()
        mock_remote.refs = []
        mock_git_repo.remote.return_value = mock_remote

        result = release_mgr._get_active_patch_branches()

        assert result == []

    def test_single_patch_branch(self, release_manager_with_mock_hgit):
        """Test with single patch branch."""
        release_mgr, mock_hgit, mock_git_repo = release_manager_with_mock_hgit

        # Mock remote with one patch branch
        mock_ref = Mock()
        mock_ref.name = "origin/ho-patch/456-user-auth"

        mock_remote = Mock()
        mock_remote.refs = [mock_ref]
        mock_git_repo.remote.return_value = mock_remote

        result = release_mgr._get_active_patch_branches()

        assert result == ["ho-patch/456-user-auth"]

    def test_multiple_patch_branches(self, release_manager_with_mock_hgit):
        """Test with multiple patch branches."""
        release_mgr, mock_hgit, mock_git_repo = release_manager_with_mock_hgit

        # Mock remote with multiple patch branches
        mock_ref1 = Mock()
        mock_ref1.name = "origin/ho-patch/456-user-auth"
        mock_ref2 = Mock()
        mock_ref2.name = "origin/ho-patch/789-security"
        mock_ref3 = Mock()
        mock_ref3.name = "origin/ho-patch/234-reports"

        mock_refs = [mock_ref1, mock_ref2, mock_ref3]

        mock_remote = Mock()
        mock_remote.refs = mock_refs
        mock_git_repo.remote.return_value = mock_remote

        result = release_mgr._get_active_patch_branches()

        assert len(result) == 3
        assert "ho-patch/456-user-auth" in result
        assert "ho-patch/789-security" in result
        assert "ho-patch/234-reports" in result

    def test_filters_non_patch_branches(self, release_manager_with_mock_hgit):
        """Test that non-patch branches are filtered out."""
        release_mgr, mock_hgit, mock_git_repo = release_manager_with_mock_hgit

        # Mock remote with mixed branches
        mock_ref1 = Mock()
        mock_ref1.name = "origin/ho-prod"
        mock_ref2 = Mock()
        mock_ref2.name = "origin/ho-patch/456-user-auth"
        mock_ref3 = Mock()
        mock_ref3.name = "origin/ho-release/1.3.6/123-initial"
        mock_ref4 = Mock()
        mock_ref4.name = "origin/ho-patch/789-security"
        mock_ref5 = Mock()
        mock_ref5.name = "origin/main"
        mock_refs = [mock_ref1, mock_ref2, mock_ref3, mock_ref4, mock_ref5]

        mock_remote = Mock()
        mock_remote.refs = mock_refs
        mock_git_repo.remote.return_value = mock_remote

        result = release_mgr._get_active_patch_branches()

        # Should only include ho-patch/* branches
        assert len(result) == 2
        assert "ho-patch/456-user-auth" in result
        assert "ho-patch/789-security" in result
        assert "ho-prod" not in result
        assert "ho-release/1.3.6/123-initial" not in result


class TestApplyPatchChangeToStageFile:
    """Test _apply_patch_change_to_stage_file() method."""

    @pytest.fixture
    def release_manager_basic(self, tmp_path):
        """Create basic ReleaseManager with releases/ directory."""
        mock_repo = Mock()
        mock_repo.base_dir = str(tmp_path)

        # Create releases/ directory
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir(exist_ok=True)

        release_mgr = ReleaseManager(mock_repo)

        return release_mgr, releases_dir

    def test_append_to_existing_file(self, release_manager_basic):
        """Test appending patch to existing stage file."""
        release_mgr, releases_dir = release_manager_basic

        # Create existing stage file with content
        stage_file = releases_dir / "1.3.6-stage.txt"
        stage_file.write_text("123-initial\n456-security\n")

        # Append new patch
        release_mgr._apply_patch_change_to_stage_file("1.3.6-stage.txt", "789-reports")

        # Verify content
        content = stage_file.read_text()
        lines = content.strip().split('\n')

        assert len(lines) == 3
        assert lines[0] == "123-initial"
        assert lines[1] == "456-security"
        assert lines[2] == "789-reports"

    def test_append_to_empty_file(self, release_manager_basic):
        """Test appending to empty stage file."""
        release_mgr, releases_dir = release_manager_basic

        # Create empty stage file
        stage_file = releases_dir / "1.3.6-stage.txt"
        stage_file.write_text("")

        # Append patch
        release_mgr._apply_patch_change_to_stage_file("1.3.6-stage.txt", "456-user-auth")

        # Verify content
        content = stage_file.read_text()
        assert content.strip() == "456-user-auth"

    def test_create_file_if_not_exists(self, release_manager_basic):
        """Test creates file if it doesn't exist."""
        release_mgr, releases_dir = release_manager_basic

        # File doesn't exist
        stage_file = releases_dir / "1.3.6-stage.txt"
        assert not stage_file.exists()

        # Append patch (should create file)
        release_mgr._apply_patch_change_to_stage_file("1.3.6-stage.txt", "456-user-auth")

        # Verify file created with content
        assert stage_file.exists()
        content = stage_file.read_text()
        assert content.strip() == "456-user-auth"

    def test_preserves_existing_content(self, release_manager_basic):
        """Test that existing content is preserved."""
        release_mgr, releases_dir = release_manager_basic

        # Create file with multiple patches
        stage_file = releases_dir / "1.3.6-stage.txt"
        original_content = "123-initial\n456-security\n789-performance\n"
        stage_file.write_text(original_content)

        # Append new patch
        release_mgr._apply_patch_change_to_stage_file("1.3.6-stage.txt", "999-bugfix")

        # Verify all content preserved
        content = stage_file.read_text()
        lines = content.strip().split('\n')

        assert len(lines) == 4
        assert lines[0] == "123-initial"
        assert lines[1] == "456-security"
        assert lines[2] == "789-performance"
        assert lines[3] == "999-bugfix"

    def test_handles_patch_id_with_special_chars(self, release_manager_basic):
        """Test handles patch IDs with special characters."""
        release_mgr, releases_dir = release_manager_basic

        # Create stage file
        stage_file = releases_dir / "1.3.6-stage.txt"
        stage_file.write_text("")

        # Append patch with special chars
        release_mgr._apply_patch_change_to_stage_file(
            "1.3.6-stage.txt",
            "456-user-auth-v2"
        )

        # Verify content
        content = stage_file.read_text()
        assert content.strip() == "456-user-auth-v2"

    def test_newline_handling(self, release_manager_basic):
        """Test proper newline handling."""
        release_mgr, releases_dir = release_manager_basic

        # Create file with content (with trailing newline)
        stage_file = releases_dir / "1.3.6-stage.txt"
        stage_file.write_text("123-initial\n")

        # Append patch
        release_mgr._apply_patch_change_to_stage_file("1.3.6-stage.txt", "456-user-auth")

        # Verify proper newlines
        content = stage_file.read_text()
        lines = content.split('\n')

        # Should have: "123-initial\n456-user-auth\n"
        assert lines[0] == "123-initial"
        assert lines[1] == "456-user-auth"

    def test_error_on_permission_denied(self, release_manager_basic):
        """Test error when file write fails due to permissions."""
        release_mgr, releases_dir = release_manager_basic

        # Create read-only file
        stage_file = releases_dir / "1.3.6-stage.txt"
        stage_file.write_text("123-initial\n")
        stage_file.chmod(0o444)  # Read-only

        # Should raise error
        with pytest.raises(ReleaseManagerError, match="Failed to.*stage file|Permission"):
            release_mgr._apply_patch_change_to_stage_file("1.3.6-stage.txt", "456-user-auth")

        # Cleanup
        stage_file.chmod(0o644)
