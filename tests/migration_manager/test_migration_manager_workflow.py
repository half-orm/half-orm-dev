"""
Test MigrationManager workflow (apply_migration, run_migrations).
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from half_orm_dev.migration_manager import MigrationManager, MigrationManagerError


@pytest.fixture
def mock_repo_with_migration_files(tmp_path):
    """
    Create mock repo with actual migration files for testing.
    """
    mock_repo = Mock()
    mock_repo.base_dir = str(tmp_path)

    # Mock config
    mock_config = Mock()
    mock_config.hop_version = "0.17.0"
    mock_config.write = Mock()
    mock_repo._Repo__config = mock_config

    # Mock local_config
    mock_local_config = Mock()
    mock_local_config.backups_dir = None
    mock_repo._Repo__local_config = mock_local_config

    # Mock hgit — wire git.diff so auto-detection of staged files works
    mock_git = Mock()
    mock_git.diff.return_value = ''  # no staged files by default
    mock_git_repo = Mock()
    mock_git_repo.git = mock_git
    mock_hgit = Mock()
    mock_hgit.add = Mock()
    mock_hgit.commit = Mock()
    mock_hgit._HGit__git_repo = mock_git_repo
    mock_hgit.get_active_branches_status.return_value = {
        'patch_branches': [],
        'release_branches': [],
        'staged_branches': [],
    }
    mock_repo.hgit = mock_hgit

    # Mock commit_and_sync_to_active_branches
    mock_repo.commit_and_sync_to_active_branches = Mock(return_value={
        'commit_hash': 'abc123',
        'pushed_branch': 'test-branch',
        'sync_result': {'synced_branches': [], 'skipped_branches': [], 'errors': []}
    })

    # Mock compare_versions method (uses packaging.version)
    from packaging import version
    def compare_versions(v1, v2):
        parsed_v1 = version.parse(v1)
        parsed_v2 = version.parse(v2)
        if parsed_v1 < parsed_v2:
            return -1
        elif parsed_v1 > parsed_v2:
            return 1
        else:
            return 0
    mock_repo.compare_versions = compare_versions

    # Create .hop directory structure
    hop_dir = tmp_path / ".hop"
    hop_dir.mkdir()

    # Create a test migration file in tmp_path
    migrations_root = tmp_path / "test_migrations"
    migration_dir = migrations_root / "0" / "17" / "1"
    migration_dir.mkdir(parents=True)

    # Create a simple migration file
    migration_file = migration_dir / "00_test_migration.py"
    migration_file.write_text("""
def migrate(repo):
    '''Test migration'''
    # Create a marker file to verify migration ran
    import os
    marker = os.path.join(repo.base_dir, '.hop', 'migration_marker.txt')
    with open(marker, 'w') as f:
        f.write('Migration ran successfully')

def get_description():
    return 'Test migration'
""")

    return mock_repo, tmp_path, migrations_root


class TestMigrationWorkflow:
    """Test migration workflow."""

    def test_apply_migration(self, mock_repo_with_migration_files):
        """Test applying a single migration."""
        mock_repo, tmp_path, migrations_root = mock_repo_with_migration_files

        mgr = MigrationManager(mock_repo)
        # Override migrations_root for testing
        mgr._migrations_root = migrations_root

        migration_dir = migrations_root / "0" / "17" / "1"
        result = mgr.apply_migration("0.17.1", migration_dir)

        # Check result
        assert result['version'] == "0.17.1"
        assert len(result['applied_files']) == 1
        assert '00_test_migration.py' in result['applied_files']
        assert len(result['errors']) == 0

        # Check that migration actually ran (marker file exists)
        marker_file = tmp_path / ".hop" / "migration_marker.txt"
        assert marker_file.exists()
        assert "Migration ran successfully" in marker_file.read_text()

    def test_apply_migration_no_files(self, mock_repo_with_migration_files):
        """Test applying migration with no migration files."""
        mock_repo, tmp_path, migrations_root = mock_repo_with_migration_files

        mgr = MigrationManager(mock_repo)
        mgr._migrations_root = migrations_root

        # Create empty migration directory
        empty_dir = migrations_root / "0" / "18" / "0"
        empty_dir.mkdir(parents=True)

        with pytest.raises(MigrationManagerError, match="No migration files found"):
            mgr.apply_migration("0.18.0", empty_dir)

    def test_apply_migration_missing_migrate_function(self, mock_repo_with_migration_files):
        """Test migration file without migrate() function."""
        mock_repo, tmp_path, migrations_root = mock_repo_with_migration_files

        # Create invalid migration file
        invalid_dir = migrations_root / "0" / "18" / "0"
        invalid_dir.mkdir(parents=True)
        invalid_file = invalid_dir / "00_invalid.py"
        invalid_file.write_text("""
# Missing migrate() function
def get_description():
    return 'Invalid migration'
""")

        mgr = MigrationManager(mock_repo)
        mgr._migrations_root = migrations_root

        with pytest.raises(MigrationManagerError, match="missing migrate\\(\\) function"):
            mgr.apply_migration("0.18.0", invalid_dir)

    def test_get_pending_migrations(self, mock_repo_with_migration_files):
        """Test getting list of pending migrations."""
        mock_repo, tmp_path, migrations_root = mock_repo_with_migration_files

        mgr = MigrationManager(mock_repo)
        mgr._migrations_root = migrations_root

        # Get pending migrations from 0.17.0 to 0.17.1
        pending = mgr.get_pending_migrations("0.17.0", "0.17.1")

        assert len(pending) == 1
        assert pending[0][0] == "0.17.1"
        assert pending[0][1] == migrations_root / "0" / "17" / "1"

    def test_get_pending_migrations_none(self, mock_repo_with_migration_files):
        """Test getting pending migrations when all are applied."""
        mock_repo, tmp_path, migrations_root = mock_repo_with_migration_files

        mgr = MigrationManager(mock_repo)
        mgr._migrations_root = migrations_root

        # Get pending migrations from 0.17.1 to 0.17.1 (same version - should be empty)
        pending = mgr.get_pending_migrations("0.17.1", "0.17.1")

        assert len(pending) == 0

    def test_run_migrations_complete_workflow(self, mock_repo_with_migration_files):
        """Test complete migration workflow."""
        mock_repo, tmp_path, migrations_root = mock_repo_with_migration_files

        mgr = MigrationManager(mock_repo)
        mgr._migrations_root = migrations_root

        # Run migrations
        result = mgr.run_migrations(
            target_version="0.17.1",
            create_commit=True
        )

        # Check result
        assert result['target_version'] == "0.17.1"
        assert len(result['migrations_applied']) == 1
        assert result['migrations_applied'][0]['version'] == "0.17.1"
        assert result['commit_created'] is True

        # Check that hop_version was updated in config
        assert mock_repo._Repo__config.hop_version == "0.17.1"
        mock_repo._Repo__config.write.assert_called_once()

        # Check that Git commands were called via commit_and_sync
        mock_repo.commit_and_sync_to_active_branches.assert_called_once()

        # Check commit message
        call_args = mock_repo.commit_and_sync_to_active_branches.call_args
        commit_msg = call_args[1]['message']  # keyword argument
        assert "[HOP] Migration from 0.17.0 to 0.17.1" in commit_msg

        # Check reason parameter
        reason = call_args[1]['reason']
        assert "migration 0.17.0 → 0.17.1" == reason

    def test_run_migrations_no_pending(self, mock_repo_with_migration_files):
        """Test run_migrations() with no pending migrations."""
        mock_repo, tmp_path, migrations_root = mock_repo_with_migration_files

        mgr = MigrationManager(mock_repo)
        mgr._migrations_root = migrations_root

        # Set config version to same as target (no migrations needed)
        mock_repo._Repo__config.hop_version = "0.17.1"

        # Run migrations (should do nothing)
        result = mgr.run_migrations(
            target_version="0.17.1",
            create_commit=True
        )

        # Check result
        assert len(result['migrations_applied']) == 0
        assert result['commit_created'] is False

        # Config should not be updated
        mock_repo._Repo__config.write.assert_not_called()

    def test_run_migrations_without_commit(self, mock_repo_with_migration_files):
        """Test running migrations without creating Git commit."""
        mock_repo, tmp_path, migrations_root = mock_repo_with_migration_files

        mgr = MigrationManager(mock_repo)
        mgr._migrations_root = migrations_root

        # Run migrations without commit
        result = mgr.run_migrations(
            target_version="0.17.1",
            create_commit=False
        )

        # Check result
        assert len(result['migrations_applied']) == 1


def _make_minimal_repo(active_branches_status=None):
    """Build a minimal mock repo for _ensure_active_branches_synced tests."""
    mock_repo = Mock()
    mock_git_repo = Mock()
    mock_git_repo.active_branch.name = 'ho-prod'
    mock_hgit = Mock()
    mock_hgit._HGit__git_repo = mock_git_repo
    mock_hgit.get_active_branches_status.return_value = active_branches_status or {
        'patch_branches': [],
        'release_branches': [],
        'staged_branches': [],
    }
    mock_repo.hgit = mock_hgit
    return mock_repo


class TestEnsureActiveBranchesSynced:
    """Tests for _ensure_active_branches_synced error messages."""

    def _mgr(self, active_branches_status=None):
        repo = _make_minimal_repo(active_branches_status)
        return MigrationManager(repo)

    def test_all_synced_no_error(self):
        mgr = self._mgr({
            'patch_branches': [{'name': 'ho-patch/1-foo'}],
            'release_branches': [],
            'staged_branches': [],
        })
        mgr._repo.hgit.is_branch_synced.return_value = (True, 'synced')
        mgr._ensure_active_branches_synced()  # must not raise

    def test_behind_branch_is_fast_forwarded(self):
        mgr = self._mgr({
            'patch_branches': [{'name': 'ho-patch/1-foo'}],
            'release_branches': [],
            'staged_branches': [],
        })
        mgr._repo.hgit.is_branch_synced.return_value = (False, 'behind')
        mgr._ensure_active_branches_synced()
        mgr._repo.hgit._HGit__git_repo.git.merge.assert_called_once_with(
            '--ff-only', 'origin/ho-patch/1-foo'
        )

    def test_ahead_branch_blocks_with_push_hint(self):
        mgr = self._mgr({
            'patch_branches': [{'name': 'ho-patch/2-bar'}],
            'release_branches': [],
            'staged_branches': [],
        })
        mgr._repo.hgit.is_branch_synced.return_value = (False, 'ahead')
        with pytest.raises(MigrationManagerError) as exc_info:
            mgr._ensure_active_branches_synced()
        msg = str(exc_info.value)
        assert 'ahead' in msg
        assert 'git push origin ho-patch/2-bar' in msg

    def test_diverged_branch_blocks_with_rebase_hint(self):
        mgr = self._mgr({
            'patch_branches': [{'name': 'ho-patch/3-baz'}],
            'release_branches': [],
            'staged_branches': [],
        })
        mgr._repo.hgit.is_branch_synced.return_value = (False, 'diverged')
        with pytest.raises(MigrationManagerError) as exc_info:
            mgr._ensure_active_branches_synced()
        msg = str(exc_info.value)
        assert 'diverged' in msg
        assert 'ho-patch/3-baz' in msg

    def test_mixed_ahead_and_diverged_both_reported(self):
        mgr = self._mgr({
            'patch_branches': [
                {'name': 'ho-patch/1-ahead'},
                {'name': 'ho-patch/2-diverged'},
            ],
            'release_branches': [],
            'staged_branches': [],
        })
        def is_synced(branch):
            if 'ahead' in branch:
                return (False, 'ahead')
            return (False, 'diverged')
        mgr._repo.hgit.is_branch_synced.side_effect = is_synced
        with pytest.raises(MigrationManagerError) as exc_info:
            mgr._ensure_active_branches_synced()
        msg = str(exc_info.value)
        assert 'git push origin ho-patch/1-ahead' in msg
        assert 'ho-patch/2-diverged' in msg
