"""
Tests for PatchManager.attach_patch() method.

Tests the workflow of reattaching an orphaned patch to a release:
1. Validate patch exists and is orphaned
2. Validate target release exists
3. Add patch to TOML as candidate
4. Move directory from Patches/orphaned/ to Patches/
5. Commit and sync changes
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from half_orm_dev.patch_manager import PatchManager, PatchManagerError
from half_orm_dev.repo import Repo
from half_orm_dev.release_file import ReleaseFile


@pytest.fixture
def patch_manager_for_attach(tmp_path):
    """Create PatchManager with mocked Repo for attach testing."""
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

    # Create orphaned patch directory
    patch_orphaned_dir = orphaned_dir / '123-feature'
    patch_orphaned_dir.mkdir()
    (patch_orphaned_dir / '01_schema.sql').write_text('CREATE TABLE test (id INT);')

    # Create candidate patch directory
    patch_candidate_dir = patches_dir / '456-active'
    patch_candidate_dir.mkdir()

    # Create staged patch directory
    patch_staged_dir = staged_dir / '789-staged'
    patch_staged_dir.mkdir()

    # Create config
    config_file = hop_dir / 'config'
    config_file.write_text('[halfORM]\nhop_version = "0.17.0"\n')

    # Create release file with existing patches
    release_file = ReleaseFile('0.17.0', releases_dir)
    release_file.create_empty()
    release_file.add_patch('456-active')
    release_file.add_patch('789-staged')
    release_file.move_to_staged('789-staged', 'commit789')

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
    # The patch branch exists only on origin (not checked out in this clone)
    repo.hgit.fetch_from_origin = Mock()
    repo.hgit.branch_exists = Mock(return_value=False)
    repo.hgit.get_remote_branches = Mock(return_value=['origin/ho-detached/123-feature'])
    repo.hgit.rename_branch_with_remote = Mock()

    # Mock commit_and_sync
    repo.commit_and_sync_to_active_branches = Mock()

    # Create PatchManager
    pm = PatchManager(repo)

    return pm, repo, tmp_path, releases_dir, patches_dir


class TestAttachPatch:
    """Test PatchManager.attach_patch() method."""

    def test_attach_orphaned_patch_success(self, patch_manager_for_attach):
        """Test successfully attaching an orphaned patch."""
        pm, repo, tmp_path, releases_dir, patches_dir = patch_manager_for_attach

        result = pm.attach_patch('123-feature', '0.17.0')
        print(result)

        assert result['patch_id'] == '123-feature'
        assert result['version'] == '0.17.0'
        assert '123-feature' in result['patch_path']
        assert '/orphaned/' not in result['patch_path']

        # Verify git operations were called
        repo.hgit.add.assert_called()
        repo.hgit.mv.assert_called_once()

        # Verify commit_and_sync was called
        repo.commit_and_sync_to_active_branches.assert_called_once()
        call_args = repo.commit_and_sync_to_active_branches.call_args
        assert 'attach' in call_args[1]['message'].lower()
        assert '123-feature' in call_args[1]['message']

    def test_attach_renames_branch_back_to_ho_patch(self, patch_manager_for_attach):
        pm, repo, *_ = patch_manager_for_attach

        result = pm.attach_patch('123-feature', '0.17.0')

        repo.hgit.rename_branch_with_remote.assert_called_once_with(
            'ho-detached/123-feature', 'ho-patch/123-feature')
        assert result['branch'] == 'ho-patch/123-feature'

    def test_attach_legacy_ho_patch_branch(self, patch_manager_for_attach):
        """A patch detached before ho-detached/ existed keeps its ho-patch/
        branch: attached without rename."""
        pm, repo, *_ = patch_manager_for_attach
        repo.hgit.get_remote_branches.return_value = ['origin/ho-patch/123-feature']

        pm.attach_patch('123-feature', '0.17.0')

        repo.hgit.rename_branch_with_remote.assert_not_called()
        repo.commit_and_sync_to_active_branches.assert_called_once()

    def test_attach_without_any_branch_fails(self, patch_manager_for_attach):
        pm, repo, *_ = patch_manager_for_attach
        repo.hgit.get_remote_branches.return_value = []

        with pytest.raises(PatchManagerError, match='No branch'):
            pm.attach_patch('123-feature', '0.17.0')
        repo.commit_and_sync_to_active_branches.assert_not_called()

    @pytest.mark.parametrize('status', ['ahead', 'diverged'])
    def test_attach_refuses_detached_branch_not_identical_to_origin(
            self, patch_manager_for_attach, status):
        """Commits on the frozen branch, or a rewrite, are never attached
        blindly: nothing is changed."""
        pm, repo, tmp_path, releases_dir, patches_dir = patch_manager_for_attach
        repo.hgit.branch_exists = Mock(return_value=True)
        repo.hgit.get_remote_branches.return_value = ['origin/ho-detached/123-feature']
        repo.hgit.is_branch_synced = Mock(return_value=(False, status))

        with pytest.raises(PatchManagerError, match=status):
            pm.attach_patch('123-feature', '0.17.0')

        repo.commit_and_sync_to_active_branches.assert_not_called()
        repo.hgit.rename_branch_with_remote.assert_not_called()
        assert '123-feature' not in ReleaseFile('0.17.0', releases_dir).get_patches()

    def test_attach_adds_patch_to_toml(self, patch_manager_for_attach):
        """Test that attach adds the patch to TOML file as candidate."""
        pm, repo, tmp_path, releases_dir, patches_dir = patch_manager_for_attach

        # Verify patch is NOT in release before attach
        release_file = ReleaseFile('0.17.0', releases_dir)
        assert '123-feature' not in release_file.get_patches()

        pm.attach_patch('123-feature', '0.17.0')

        # Verify patch is added to release as candidate
        release_file = ReleaseFile('0.17.0', releases_dir)
        assert release_file.get_patch_status('123-feature') == 'candidate'

    def test_attach_candidate_patch_fails(self, patch_manager_for_attach):
        """Test that attaching a candidate patch raises error."""
        pm, repo, tmp_path, releases_dir, patches_dir = patch_manager_for_attach

        with pytest.raises(PatchManagerError, match="already a candidate"):
            pm.attach_patch('456-active', '0.17.0')

    def test_attach_staged_patch_fails(self, patch_manager_for_attach):
        """Test that attaching a staged patch raises error."""
        pm, repo, tmp_path, releases_dir, patches_dir = patch_manager_for_attach

        with pytest.raises(PatchManagerError, match="Cannot attach staged"):
            pm.attach_patch('789-staged', '0.17.0')

    def test_attach_nonexistent_patch_fails(self, patch_manager_for_attach):
        """Test that attaching unknown patch raises error."""
        pm, repo, tmp_path, releases_dir, patches_dir = patch_manager_for_attach

        with pytest.raises(PatchManagerError, match="not found"):
            pm.attach_patch('999-unknown', '0.17.0')

    def test_attach_moves_directory_from_orphaned(self, patch_manager_for_attach):
        """Test that attach calls git mv to move directory from orphaned."""
        pm, repo, tmp_path, releases_dir, patches_dir = patch_manager_for_attach

        pm.attach_patch('123-feature', '0.17.0')

        repo.hgit.mv.assert_called_once()
        call_args = repo.hgit.mv.call_args[0]
        assert 'orphaned' in call_args[0]     # Source: orphaned/
        assert '123-feature' in call_args[0]
        assert '123-feature' in call_args[1]   # Destination: root
        assert 'orphaned' not in call_args[1]

    def test_attach_updates_status_cache(self, patch_manager_for_attach):
        """Test that cache is updated after attach."""
        pm, repo, tmp_path, releases_dir, patches_dir = patch_manager_for_attach

        # Get initial status
        status_map = pm.get_patch_status_map()
        assert status_map.get('123-feature', {}).get('status') == 'orphaned'

        pm.attach_patch('123-feature', '0.17.0')

        # Verify cache was updated
        status_map = pm.get_patch_status_map()
        assert status_map.get('123-feature', {}).get('status') == 'candidate'

    def test_attach_invalid_release_fails(self, patch_manager_for_attach):
        """Test that attaching to nonexistent release raises error."""
        pm, repo, tmp_path, releases_dir, patches_dir = patch_manager_for_attach

        with pytest.raises(PatchManagerError, match="Release .* not found"):
            pm.attach_patch('123-feature', '9.9.9')


class TestAttachPatchEdgeCases:
    """Test edge cases for attach_patch."""

    def test_attach_with_missing_directory(self, patch_manager_for_attach):
        """Test attach when orphaned directory doesn't exist."""
        pm, repo, tmp_path, releases_dir, patches_dir = patch_manager_for_attach

        # Remove the orphaned directory (but keep on filesystem scan)
        import shutil
        shutil.rmtree(patches_dir / 'orphaned' / '123-feature')

        # Manually set status to orphaned (since filesystem scan won't find it)
        pm._patch_status_map = {
            '123-feature': {'status': 'orphaned'},
            '456-active': {'status': 'candidate', 'version': '0.17.0'},
            '789-staged': {'status': 'staged', 'version': '0.17.0'},
        }

        result = pm.attach_patch('123-feature', '0.17.0')

        # git mv should NOT be called (no directory to move)
        repo.hgit.mv.assert_not_called()

        # But TOML should still be updated
        release_file = ReleaseFile('0.17.0', releases_dir)
        assert '123-feature' in release_file.get_patches()

    def test_attach_preserves_other_patches(self, patch_manager_for_attach):
        """Test that attaching one patch doesn't affect others."""
        pm, repo, tmp_path, releases_dir, patches_dir = patch_manager_for_attach

        pm.attach_patch('123-feature', '0.17.0')

        # Verify other patches are preserved
        release_file = ReleaseFile('0.17.0', releases_dir)
        patches = release_file.get_patches()
        assert '123-feature' in patches
        assert '456-active' in patches
        assert '789-staged' in patches