"""
Tests for PatchManager.close_patch() method.

Tests the complete workflow of closing a patch:
1. Validation (must be on ho-patch/* branch)
2. Find version from candidates file
3. Merge patch into release branch
4. Move patch from candidates to staged
5. Delete patch branch
6. Sync to ho-prod
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call
from git.exc import GitCommandError

from half_orm_dev.patch_manager import PatchManager, PatchManagerError
from half_orm_dev.repo import Repo
from half_orm_dev.release_file import ReleaseFile


@pytest.fixture
def patch_manager(tmp_path):
    """Create PatchManager with mocked Repo for testing."""
    # Create directory structure
    base_dir = tmp_path
    hop_dir = base_dir / '.hop'
    hop_dir.mkdir()
    releases_dir = hop_dir / 'releases'
    releases_dir.mkdir()
    patches_dir = base_dir / 'Patches'
    patches_dir.mkdir()

    # Create config
    config_file = hop_dir / 'config'
    config_file.write_text('[halfORM]\nhop_version = "0.17.0"\n')

    # Mock Repo
    repo = Mock(spec=Repo)
    repo.base_dir = str(base_dir)
    repo.releases_dir = str(releases_dir)

    # Mock HGit
    repo.hgit = Mock()
    repo.hgit.branch = 'ho-patch/123-test'
    repo.hgit.checkout = Mock()
    repo.hgit.merge = Mock()
    repo.hgit.add = Mock()
    repo.hgit.commit = Mock()
    repo.hgit.push_branch = Mock()
    repo.hgit.branch_exists = Mock(return_value=True)
    repo.hgit.delete_local_branch = Mock()
    repo.hgit.delete_remote_branch = Mock()

    # Create PatchManager
    pm = PatchManager(repo)

    return pm, repo, tmp_path, releases_dir, patches_dir


class TestClosePatch:
    """Test PatchManager.close_patch() method."""

    def test_close_patch_validates_current_branch(self, patch_manager):
        """Test that close_patch fails if not on patch branch."""
        pm, repo, tmp_path, releases_dir, patches_dir = patch_manager

        # Set current branch to non-patch branch
        repo.hgit.branch = 'ho-prod'

        with pytest.raises(PatchManagerError, match="Must be on a patch branch"):
            pm.close_patch()

    def test_close_patch_finds_version_from_candidates(self, patch_manager):
        """Test that close_patch finds version from candidates file."""
        pm, repo, tmp_path, releases_dir, patches_dir = patch_manager

        # Create candidates file with patch
        candidates_file = releases_dir / '0.17.0-candidates.txt'
        candidates_file.write_text('123-test\n456-other\n')

        # Create patches TOML file
        release_file = ReleaseFile('0.17.0', releases_dir)
        release_file.create_empty()
        release_file.add_patch('123-test')

        # Mock _validate_patch_before_merge to avoid complex setup
        with patch.object(pm, '_validate_patch_before_merge'):
            with patch.object(pm, '_sync_release_files_to_ho_prod'):
                result = pm.close_patch()

        assert result['version'] == '0.17.0'
        assert result['patch_id'] == '123-test'

    def test_close_patch_merges_into_release_branch(self, patch_manager):
        """Test that close_patch merges patch into release branch."""
        pm, repo, tmp_path, releases_dir, patches_dir = patch_manager

        # Setup
        candidates_file = releases_dir / '0.17.0-candidates.txt'
        candidates_file.write_text('123-test\n')

        release_file = ReleaseFile('0.17.0', releases_dir)
        release_file.create_empty()
        release_file.add_patch('123-test')

        # Mock validation and sync
        with patch.object(pm, '_validate_patch_before_merge'):
            with patch.object(pm, '_sync_release_files_to_ho_prod'):
                result = pm.close_patch()

        # Verify checkout to release branch
        repo.hgit.checkout.assert_called_with('ho-release/0.17.0')

        # Verify merge
        repo.hgit.merge.assert_called_once()
        merge_call = repo.hgit.merge.call_args
        assert 'ho-patch/123-test' in str(merge_call)
        assert '123-test' in str(merge_call)

    def test_close_patch_moves_to_staged(self, patch_manager):
        """Test that close_patch moves patch from candidates to staged."""
        pm, repo, tmp_path, releases_dir, patches_dir = patch_manager

        # Setup
        candidates_file = releases_dir / '0.17.0-candidates.txt'
        candidates_file.write_text('123-test\n456-other\n')

        release_file = ReleaseFile('0.17.0', releases_dir)
        release_file.create_empty()
        release_file.add_patch('123-test')
        release_file.add_patch('456-other')

        # Mock validation and sync
        with patch.object(pm, '_validate_patch_before_merge'):
            with patch.object(pm, '_sync_release_files_to_ho_prod'):
                result = pm.close_patch()

        # Verify patch moved to staged
        release_file_after = ReleaseFile('0.17.0', releases_dir)
        staged_patches = release_file_after.get_patches(status="staged")

        # 123-test should be in staged
        assert '123-test' in staged_patches

    def test_close_patch_commits_and_pushes(self, patch_manager):
        """Test that close_patch commits and pushes changes."""
        pm, repo, tmp_path, releases_dir, patches_dir = patch_manager

        # Setup
        candidates_file = releases_dir / '0.17.0-candidates.txt'
        candidates_file.write_text('123-test\n')

        release_file = ReleaseFile('0.17.0', releases_dir)
        release_file.create_empty()
        release_file.add_patch('123-test')

        # Mock validation and sync
        with patch.object(pm, '_validate_patch_before_merge'):
            with patch.object(pm, '_sync_release_files_to_ho_prod'):
                result = pm.close_patch()

        # Verify commit with correct message
        repo.commit_and_sync_to_active_branches.assert_called_once()
        commit_call = repo.commit_and_sync_to_active_branches.call_args
        assert '123-test' in str(commit_call)
        assert 'candidate to stage' in str(commit_call)

    def test_close_patch_deletes_branch(self, patch_manager):
        """Test that close_patch deletes patch branch locally and remotely."""
        pm, repo, tmp_path, releases_dir, patches_dir = patch_manager

        # Setup
        candidates_file = releases_dir / '0.17.0-candidates.txt'
        candidates_file.write_text('123-test\n')

        release_file = ReleaseFile('0.17.0', releases_dir)
        release_file.create_empty()
        release_file.add_patch('123-test')

        # Mock validation and sync
        with patch.object(pm, '_validate_patch_before_merge'):
            with patch.object(pm, '_sync_release_files_to_ho_prod'):
                result = pm.close_patch()

        # Verify branch deletion
        repo.hgit.delete_local_branch.assert_called_once_with('ho-patch/123-test')
        repo.hgit.delete_remote_branch.assert_called_once_with('ho-patch/123-test')

    def test_close_patch_uses_commit_and_sync(self, patch_manager):
        """Test that close_patch uses commit_and_sync_to_active_branches."""
        pm, repo, tmp_path, releases_dir, patches_dir = patch_manager

        # Setup
        candidates_file = releases_dir / '0.17.0-candidates.txt'
        candidates_file.write_text('123-test\n')

        release_file = ReleaseFile('0.17.0', releases_dir)
        release_file.create_empty()
        release_file.add_patch('123-test')

        # Mock validation
        with patch.object(pm, '_validate_patch_before_merge'):
            result = pm.close_patch()

        # Verify commit_and_sync was called (sync is automatic via decorator)
        repo.commit_and_sync_to_active_branches.assert_called_once()

    def test_close_patch_fails_if_patch_not_in_candidates(self, patch_manager):
        """Test that close_patch fails if patch not found in any candidates file."""
        pm, repo, tmp_path, releases_dir, patches_dir = patch_manager

        # No candidates file exists
        with pytest.raises(PatchManagerError, match="not found in any candidates file"):
            pm.close_patch()

    def test_close_patch_fails_if_branch_not_exists(self, patch_manager):
        """Test that close_patch fails if patch branch doesn't exist."""
        pm, repo, tmp_path, releases_dir, patches_dir = patch_manager

        # Setup candidates file
        candidates_file = releases_dir / '0.17.0-candidates.txt'
        candidates_file.write_text('123-test\n')

        release_file = ReleaseFile('0.17.0', releases_dir)
        release_file.create_empty()
        release_file.add_patch('123-test')

        # Mock branch doesn't exist
        repo.hgit.branch_exists.return_value = False

        with pytest.raises(PatchManagerError, match="does not exist"):
            pm.close_patch()

    def test_close_patch_handles_merge_failure(self, patch_manager):
        """Test that close_patch handles merge failures gracefully."""
        pm, repo, tmp_path, releases_dir, patches_dir = patch_manager

        # Setup
        candidates_file = releases_dir / '0.17.0-candidates.txt'
        candidates_file.write_text('123-test\n')

        release_file = ReleaseFile('0.17.0', releases_dir)
        release_file.create_empty()
        release_file.add_patch('123-test')

        # Mock merge failure
        repo.hgit.merge.side_effect = GitCommandError(
            'git merge', 1, stderr='CONFLICT'
        )

        # Mock validation
        with patch.object(pm, '_validate_patch_before_merge'):
            with pytest.raises(PatchManagerError, match="Failed to merge"):
                pm.close_patch()

    def test_close_patch_return_structure(self, patch_manager):
        """Test that close_patch returns correct structure."""
        pm, repo, tmp_path, releases_dir, patches_dir = patch_manager

        # Setup
        candidates_file = releases_dir / '0.17.0-candidates.txt'
        candidates_file.write_text('123-test\n')

        release_file = ReleaseFile('0.17.0', releases_dir)
        release_file.create_empty()
        release_file.add_patch('123-test')

        # Mock validation and sync
        with patch.object(pm, '_validate_patch_before_merge'):
            with patch.object(pm, '_sync_release_files_to_ho_prod'):
                result = pm.close_patch()

        # Verify return structure
        assert 'version' in result
        assert 'patch_id' in result
        assert 'patches_file' in result
        assert 'merged_into' in result

        assert result['version'] == '0.17.0'
        assert result['patch_id'] == '123-test'
        assert result['merged_into'] == 'ho-release/0.17.0'

    def test_close_patch_with_description_in_branch_name(self, patch_manager):
        """Test close_patch with patch ID containing description."""
        pm, repo, tmp_path, releases_dir, patches_dir = patch_manager

        # Set branch with description
        repo.hgit.branch = 'ho-patch/123-add-user-auth'

        # Setup
        candidates_file = releases_dir / '0.17.0-candidates.txt'
        candidates_file.write_text('123-add-user-auth\n')

        release_file = ReleaseFile('0.17.0', releases_dir)
        release_file.create_empty()
        release_file.add_patch('123-add-user-auth')

        # Mock validation and sync
        with patch.object(pm, '_validate_patch_before_merge'):
            with patch.object(pm, '_sync_release_files_to_ho_prod'):
                result = pm.close_patch()

        assert result['patch_id'] == '123-add-user-auth'

        # Verify merge used full patch ID
        merge_call = repo.hgit.merge.call_args
        assert '123-add-user-auth' in str(merge_call)
