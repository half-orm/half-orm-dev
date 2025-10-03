"""
Tests for ReleaseManager.prepare_release() - Complete workflow.

Focused on testing:
- Stage file creation (ALWAYS X.Y.Z-stage.txt)
- Git commit and push
- Complete workflow integration
- Return structure validation
- Error cases (file exists, etc.)
"""

import pytest
from pathlib import Path
from unittest.mock import Mock

from half_orm_dev.release_manager import ReleaseManager, ReleaseFileError


class TestPrepareReleaseWorkflow:
    """Test complete workflow for release preparation."""

    def test_creates_stage_file_patch(self, mock_release_manager_with_production):
        """Test creates X.Y.Z-stage.txt file for patch increment."""
        release_mgr, mock_repo, mock_hgit, tmp_path, prod_version = mock_release_manager_with_production

        result = release_mgr.prepare_release('patch')

        # Should create stage file
        stage_file = tmp_path / "releases" / "1.3.6-stage.txt"
        assert stage_file.exists()
        assert result['file'] == str(stage_file)

    def test_creates_stage_file_minor(self, mock_release_manager_with_production):
        """Test creates X.Y.Z-stage.txt file for minor increment."""
        release_mgr, mock_repo, mock_hgit, tmp_path, prod_version = mock_release_manager_with_production

        result = release_mgr.prepare_release('minor')

        stage_file = tmp_path / "releases" / "1.4.0-stage.txt"
        assert stage_file.exists()
        assert result['file'] == str(stage_file)

    def test_creates_stage_file_major(self, mock_release_manager_with_production):
        """Test creates X.Y.Z-stage.txt file for major increment."""
        release_mgr, mock_repo, mock_hgit, tmp_path, prod_version = mock_release_manager_with_production

        result = release_mgr.prepare_release('major')

        stage_file = tmp_path / "releases" / "2.0.0-stage.txt"
        assert stage_file.exists()
        assert result['file'] == str(stage_file)

    def test_stage_file_is_empty(self, mock_release_manager_with_production):
        """Test created stage file is empty (ready for patches)."""
        release_mgr, mock_repo, mock_hgit, tmp_path, prod_version = mock_release_manager_with_production

        result = release_mgr.prepare_release('patch')

        stage_file = Path(result['file'])
        content = stage_file.read_text()
        assert content == ""

    def test_git_workflow_complete(self, mock_release_manager_with_production):
        """Test complete Git workflow: add, commit, push."""
        release_mgr, mock_repo, mock_hgit, tmp_path, prod_version = mock_release_manager_with_production

        result = release_mgr.prepare_release('patch')

        stage_file = str(tmp_path / "releases" / "1.3.6-stage.txt")

        # Verify Git operations called in order
        mock_hgit.add.assert_called_once_with(stage_file)
        mock_hgit.commit.assert_called_once()
        mock_hgit.push.assert_called_once()

    def test_commit_message_format(self, mock_release_manager_with_production):
        """Test commit message contains version."""
        release_mgr, mock_repo, mock_hgit, tmp_path, prod_version = mock_release_manager_with_production

        release_mgr.prepare_release('patch')

        # Get commit call arguments
        commit_call = mock_hgit.commit.call_args
        commit_message = str(commit_call)

        # Should contain version in message
        assert "1.3.6" in commit_message
        assert "stage" in commit_message.lower()

    def test_stage_file_already_exists_raises_error(self, mock_release_manager_with_production):
        """Test error when stage file already exists."""
        release_mgr, mock_repo, mock_hgit, tmp_path, prod_version = mock_release_manager_with_production

        # Create existing stage file
        releases_dir = tmp_path / "releases"
        existing_stage = releases_dir / "1.3.6-stage.txt"
        existing_stage.write_text("")

        with pytest.raises(ReleaseFileError, match="already exists|Stage file.*exists"):
            release_mgr.prepare_release('patch')

    def test_no_git_operations_if_file_exists(self, mock_release_manager_with_production):
        """Test no Git operations performed if file already exists."""
        release_mgr, mock_repo, mock_hgit, tmp_path, prod_version = mock_release_manager_with_production

        # Create existing stage file
        releases_dir = tmp_path / "releases"
        existing_stage = releases_dir / "1.3.6-stage.txt"
        existing_stage.write_text("")

        try:
            release_mgr.prepare_release('patch')
        except ReleaseFileError:
            pass

        # Git operations should NOT have been called
        mock_hgit.add.assert_not_called()
        mock_hgit.commit.assert_not_called()
        mock_hgit.push.assert_not_called()

    def test_return_structure_complete(self, mock_release_manager_with_production):
        """Test return dictionary has all required keys."""
        release_mgr, mock_repo, mock_hgit, tmp_path, prod_version = mock_release_manager_with_production

        result = release_mgr.prepare_release('patch')

        # Verify all required keys present
        required_keys = {'version', 'file', 'previous_version'}
        assert set(result.keys()) == required_keys

        # Verify types
        assert isinstance(result['version'], str)
        assert isinstance(result['file'], str)
        assert isinstance(result['previous_version'], str)

    def test_return_version_is_without_stage_suffix(self, mock_release_manager_with_production):
        """Test returned version is X.Y.Z without -stage suffix."""
        release_mgr, mock_repo, mock_hgit, tmp_path, prod_version = mock_release_manager_with_production

        result = release_mgr.prepare_release('patch')

        # Version should be just "1.3.6", not "1.3.6-stage"
        assert result['version'] == '1.3.6'
        assert '-stage' not in result['version']

    def test_file_path_contains_stage_suffix(self, mock_release_manager_with_production):
        """Test file path contains -stage.txt suffix."""
        release_mgr, mock_repo, mock_hgit, tmp_path, prod_version = mock_release_manager_with_production

        result = release_mgr.prepare_release('patch')

        # File should end with "-stage.txt"
        assert result['file'].endswith('-stage.txt')
        assert '1.3.6-stage.txt' in result['file']

    def test_multiple_releases_can_be_prepared(self, mock_release_manager_with_production):
        """Test multiple stage releases can exist simultaneously."""
        release_mgr, mock_repo, mock_hgit, tmp_path, prod_version = mock_release_manager_with_production

        # Prepare patch release
        result1 = release_mgr.prepare_release('patch')
        assert result1['version'] == '1.3.6'

        # Prepare minor release (should work, different version)
        result2 = release_mgr.prepare_release('minor')
        assert result2['version'] == '1.4.0'

        # Both files should exist
        stage1 = tmp_path / "releases" / "1.3.6-stage.txt"
        stage2 = tmp_path / "releases" / "1.4.0-stage.txt"
        assert stage1.exists()
        assert stage2.exists()
