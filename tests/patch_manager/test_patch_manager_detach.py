"""
Tests for PatchManager.detach_patch() method.

Tests the workflow of detaching a candidate patch from its release:
1. Validate patch exists and is a candidate (not staged)
2. Remove patch from TOML file
3. Move directory to Patches/orphaned/
4. Keep git branch (for future reattachment)
5. Commit and sync changes
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from half_orm_dev.patch_manager import PatchManager, PatchManagerError
from half_orm_dev.repo import Repo
from half_orm_dev.release_file import ReleaseFile


@pytest.fixture
def patch_manager_for_detach(tmp_path):
    """Create PatchManager with mocked Repo for detach testing."""
    # Create directory structure
    base_dir = tmp_path
    hop_dir = base_dir / '.hop'
    hop_dir.mkdir()
    releases_dir = hop_dir / 'releases'
    releases_dir.mkdir()
    patches_dir = base_dir / 'Patches'
    patches_dir.mkdir()
    orphaned_dir = patches_dir / 'orphaned'
    orphaned_dir.mkdir()
    staged_dir = patches_dir / 'staged'
    staged_dir.mkdir()

    # Create candidate patch directory
    patch_candidate_dir = patches_dir / '123-feature'
    patch_candidate_dir.mkdir()
    (patch_candidate_dir / '01_schema.sql').write_text('CREATE TABLE test (id INT);')

    # Create staged patch directory
    patch_staged_dir = staged_dir / '456-staged'
    patch_staged_dir.mkdir()
    (patch_staged_dir / '01_schema.sql').write_text('CREATE TABLE staged (id INT);')

    # Create orphaned patch directory
    patch_orphaned_dir = orphaned_dir / '789-orphan'
    patch_orphaned_dir.mkdir()

    # Create config
    config_file = hop_dir / 'config'
    config_file.write_text('[halfORM]\nhop_version = "0.17.0"\n')

    # Create release file with patches
    release_file = ReleaseFile('0.17.0', releases_dir)
    release_file.create_empty()
    release_file.add_patch('123-feature')
    release_file.add_patch('456-staged')
    release_file.move_to_staged('456-staged', 'commit456')

    # Mock Repo
    repo = Mock(spec=Repo)
    repo.base_dir = str(base_dir)
    repo.releases_dir = str(releases_dir)

    # Mock HGit
    repo.hgit = Mock()
    repo.hgit.branch = 'ho-release/0.17.0'
    repo.hgit.add = Mock()
    repo.hgit.mv = Mock()
    repo.hgit.commit = Mock()

    # Mock commit_and_sync
    repo.commit_and_sync_to_active_branches = Mock()

    # Create PatchManager
    pm = PatchManager(repo)

    return pm, repo, tmp_path, releases_dir, patches_dir


class TestDetachPatch:
    """Test PatchManager.detach_patch() method."""

    def test_detach_candidate_patch_success(self, patch_manager_for_detach):
        """Test successfully detaching a candidate patch."""
        pm, repo, tmp_path, releases_dir, patches_dir = patch_manager_for_detach

        # Execute detach
        result = pm.detach_patch('123-feature')

        # Verify result
        assert result['patch_id'] == '123-feature'
        assert result['version'] == '0.17.0'
        assert 'orphaned' in result['orphaned_path']

        # Verify git operations were called
        repo.hgit.add.assert_called()
        repo.hgit.mv.assert_called_once()

        # Verify commit_and_sync was called
        repo.commit_and_sync_to_active_branches.assert_called_once()
        call_args = repo.commit_and_sync_to_active_branches.call_args
        assert 'detach' in call_args[1]['message'].lower()
        assert '123-feature' in call_args[1]['message']

    def test_detach_removes_patch_from_toml(self, patch_manager_for_detach):
        """Test that detach removes the patch from TOML file."""
        pm, repo, tmp_path, releases_dir, patches_dir = patch_manager_for_detach

        # Verify patch is in release before detach
        release_file = ReleaseFile('0.17.0', releases_dir)
        assert '123-feature' in release_file.get_patches()

        # Execute detach
        pm.detach_patch('123-feature')

        # Verify patch is removed from release
        release_file = ReleaseFile('0.17.0', releases_dir)
        assert '123-feature' not in release_file.get_patches()

    def test_detach_staged_patch_fails(self, patch_manager_for_detach):
        """Test that detaching a staged patch raises error."""
        pm, repo, tmp_path, releases_dir, patches_dir = patch_manager_for_detach

        with pytest.raises(PatchManagerError, match="Cannot detach staged"):
            pm.detach_patch('456-staged')

    def test_detach_orphaned_patch_fails(self, patch_manager_for_detach):
        """Test that detaching an already orphaned patch raises error."""
        pm, repo, tmp_path, releases_dir, patches_dir = patch_manager_for_detach

        # Manually mark as orphaned in status map
        pm._patch_status_map = {
            '789-orphan': {'status': 'orphaned', 'version': None}
        }

        with pytest.raises(PatchManagerError, match="already orphaned"):
            pm.detach_patch('789-orphan')

    def test_detach_nonexistent_patch_fails(self, patch_manager_for_detach):
        """Test that detaching unknown patch raises error."""
        pm, repo, tmp_path, releases_dir, patches_dir = patch_manager_for_detach

        with pytest.raises(PatchManagerError, match="not found"):
            pm.detach_patch('999-unknown')

    def test_detach_moves_directory_to_orphaned(self, patch_manager_for_detach):
        """Test that detach calls git mv to move directory."""
        pm, repo, tmp_path, releases_dir, patches_dir = patch_manager_for_detach

        pm.detach_patch('123-feature')

        # Verify git mv was called with correct paths
        repo.hgit.mv.assert_called_once()
        call_args = repo.hgit.mv.call_args[0]
        assert '123-feature' in call_args[0]  # Source path
        assert 'orphaned' in call_args[1]     # Destination path

    def test_detach_updates_status_cache(self, patch_manager_for_detach):
        """Test that cache is updated after detach."""
        pm, repo, tmp_path, releases_dir, patches_dir = patch_manager_for_detach

        # Get initial status
        status_map = pm.get_patch_status_map()
        assert status_map.get('123-feature', {}).get('status') == 'candidate'

        # Execute detach
        pm.detach_patch('123-feature')

        # Verify cache was updated
        status_map = pm.get_patch_status_map()
        assert status_map.get('123-feature', {}).get('status') == 'orphaned'


class TestDetachPatchEdgeCases:
    """Test edge cases for detach_patch."""

    def test_detach_with_missing_directory(self, patch_manager_for_detach):
        """Test detach when patch directory doesn't exist (only in TOML)."""
        pm, repo, tmp_path, releases_dir, patches_dir = patch_manager_for_detach

        # Remove the patch directory (but keep in TOML)
        patch_dir = patches_dir / '123-feature'
        import shutil
        shutil.rmtree(patch_dir)

        # Execute detach - should work but not call git mv
        result = pm.detach_patch('123-feature')

        # Verify git mv was NOT called (no directory to move)
        repo.hgit.mv.assert_not_called()

        # But TOML should still be updated
        release_file = ReleaseFile('0.17.0', releases_dir)
        assert '123-feature' not in release_file.get_patches()

    def test_detach_preserves_other_patches(self, patch_manager_for_detach):
        """Test that detaching one patch doesn't affect others."""
        pm, repo, tmp_path, releases_dir, patches_dir = patch_manager_for_detach

        # Add another candidate patch
        release_file = ReleaseFile('0.17.0', releases_dir)
        release_file.add_patch('999-other')

        # Detach first patch
        pm.detach_patch('123-feature')

        # Verify other patches are preserved
        release_file = ReleaseFile('0.17.0', releases_dir)
        patches = release_file.get_patches()
        assert '123-feature' not in patches
        assert '456-staged' in patches  # Staged patch preserved
        assert '999-other' in patches    # Other candidate preserved