"""
Tests for the "migration already applied by another developer" path in run_migrations().

When ho-prod is behind origin/ho-prod and origin already has the target hop_version,
run_migrations() should:
  - pull ho-prod from origin (fast-forward)
  - sync all active branches
  - reload the local config
  - return {'already_synced': True} instead of raising
"""

import pytest
from unittest.mock import Mock, patch, call
from configparser import ConfigParser

from half_orm_dev.migration_manager import MigrationManager, MigrationManagerError


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mgr_with_behind_ho_prod(tmp_path):
    """
    MigrationManager where ho-prod is 1 commit behind origin/ho-prod.
    The remote already has hop_version = target_version.
    """
    mock_repo = Mock()
    mock_repo.base_dir = str(tmp_path)

    mock_config = Mock()
    mock_config.hop_version = "1.0.0"
    mock_config.write = Mock()
    mock_config.read = Mock()
    mock_repo._Repo__config = mock_config

    from packaging import version as pkg_version
    def compare_versions(v1, v2):
        p1, p2 = pkg_version.parse(v1), pkg_version.parse(v2)
        return -1 if p1 < p2 else (1 if p1 > p2 else 0)
    mock_repo.compare_versions = compare_versions

    # git_repo mock — simulates ho-prod being 1 commit behind
    mock_git_repo = Mock()
    mock_git_repo.git.rev_list.return_value = "0\t1"

    # origin remote
    mock_origin = Mock()
    mock_git_repo.remotes.origin = mock_origin

    # git.show() returns a .hop/config with hop_version = target
    def _git_show(ref):
        cfg = ConfigParser()
        cfg['halfORM'] = {'hop_version': '1.0.0-a16'}
        import io
        buf = io.StringIO()
        cfg.write(buf)
        return buf.getvalue()
    mock_git_repo.git.show.side_effect = _git_show

    mock_hgit = Mock()
    mock_hgit.branch = 'ho-prod'
    mock_hgit._HGit__git_repo = mock_git_repo
    mock_hgit.sync_active_branches = Mock(return_value={'synced': [], 'skipped': [], 'errors': []})
    mock_repo.hgit = mock_hgit

    # Patch subprocess.run to report: ahead=0, behind=1
    import subprocess
    mock_proc = Mock()
    mock_proc.stdout = "0\t1\n"
    mock_proc.returncode = 0

    mgr = MigrationManager(mock_repo)
    return mgr, mock_repo, mock_hgit, mock_git_repo, mock_proc


# ============================================================================
# TESTS
# ============================================================================

class TestMigrationAlreadyApplied:
    """run_migrations() detects that origin already has the migration and syncs."""

    def test_returns_already_synced_flag(self, mgr_with_behind_ho_prod, tmp_path):
        """Result contains already_synced=True when migration was done remotely."""
        mgr, mock_repo, _, mock_git_repo, mock_proc = mgr_with_behind_ho_prod
        target = "1.0.0-a16"

        with patch('subprocess.run', return_value=mock_proc):
            result = mgr.run_migrations(target_version=target, create_commit=False)

        assert result.get('already_synced') is True

    def test_pulls_ho_prod_from_origin(self, mgr_with_behind_ho_prod, tmp_path):
        """Pulls ho-prod from origin to fast-forward the local branch."""
        mgr, mock_repo, mock_hgit, mock_git_repo, mock_proc = mgr_with_behind_ho_prod
        target = "1.0.0-a16"

        with patch('subprocess.run', return_value=mock_proc):
            mgr.run_migrations(target_version=target, create_commit=False)

        mock_git_repo.remotes.origin.pull.assert_called_once_with('ho-prod')

    def test_syncs_active_branches(self, mgr_with_behind_ho_prod, tmp_path):
        """Syncs all active ho-* branches after pulling."""
        mgr, mock_repo, mock_hgit, _, mock_proc = mgr_with_behind_ho_prod
        target = "1.0.0-a16"

        with patch('subprocess.run', return_value=mock_proc):
            mgr.run_migrations(target_version=target, create_commit=False)

        mock_hgit.sync_active_branches.assert_called_once_with(pattern="ho-*")

    def test_reloads_config(self, mgr_with_behind_ho_prod, tmp_path):
        """Reloads in-memory config after sync so the new hop_version is visible."""
        mgr, mock_repo, _, _, mock_proc = mgr_with_behind_ho_prod
        target = "1.0.0-a16"

        with patch('subprocess.run', return_value=mock_proc):
            mgr.run_migrations(target_version=target, create_commit=False)

        mock_repo._Repo__config.read.assert_called_once()

    def test_does_not_create_commit(self, mgr_with_behind_ho_prod, tmp_path):
        """No new commit is created when the migration was already applied remotely."""
        mgr, mock_repo, mock_hgit, _, mock_proc = mgr_with_behind_ho_prod
        target = "1.0.0-a16"

        with patch('subprocess.run', return_value=mock_proc):
            mgr.run_migrations(target_version=target, create_commit=False)

        mock_hgit.commit.assert_not_called()

    def test_raises_when_origin_has_different_version(self, mgr_with_behind_ho_prod):
        """Raises MigrationManagerError when behind but remote does NOT have target version."""
        mgr, mock_repo, _, mock_git_repo, mock_proc = mgr_with_behind_ho_prod

        # Remote has an older hop_version (not the target)
        from configparser import ConfigParser as CP
        import io
        cfg = CP()
        cfg['halfORM'] = {'hop_version': '1.0.0-a14'}
        buf = io.StringIO()
        cfg.write(buf)
        mock_git_repo.git.show.side_effect = lambda _: buf.getvalue()

        with patch('subprocess.run', return_value=mock_proc):
            with pytest.raises(MigrationManagerError, match="behind origin/ho-prod"):
                mgr.run_migrations(target_version="1.0.0-a16", create_commit=False)