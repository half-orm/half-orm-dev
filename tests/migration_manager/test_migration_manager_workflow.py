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

    # Mock hgit
    mock_hgit = Mock()
    mock_hgit.add = Mock()
    mock_hgit.commit = Mock()
    mock_repo.hgit = mock_hgit

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

    # Create log file
    log_file = migrations_root / "log"
    log_file.write_text("0.17.0\n")

    return mock_repo, tmp_path, migrations_root


class TestMigrationWorkflow:
    """Test migration workflow."""

    def test_apply_migration(self, mock_repo_with_migration_files):
        """Test applying a single migration."""
        mock_repo, tmp_path, migrations_root = mock_repo_with_migration_files

        mgr = MigrationManager(mock_repo)
        # Override migrations_root for testing
        mgr._migrations_root = migrations_root
        mgr._log_file = migrations_root / "log"

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
        mgr._log_file = migrations_root / "log"

        # Get pending migrations (0.17.1 not in log yet)
        pending = mgr.get_pending_migrations("0.17.1")

        assert len(pending) == 1
        assert pending[0][0] == "0.17.1"
        assert pending[0][1] == migrations_root / "0" / "17" / "1"

    def test_get_pending_migrations_none(self, mock_repo_with_migration_files):
        """Test getting pending migrations when all are applied."""
        mock_repo, tmp_path, migrations_root = mock_repo_with_migration_files

        mgr = MigrationManager(mock_repo)
        mgr._migrations_root = migrations_root
        mgr._log_file = migrations_root / "log"

        # Mark 0.17.1 as applied
        with open(mgr._log_file, 'a') as f:
            f.write("0.17.1\n")

        # Get pending migrations (should be empty)
        pending = mgr.get_pending_migrations("0.17.1")

        assert len(pending) == 0

    def test_run_migrations_complete_workflow(self, mock_repo_with_migration_files):
        """Test complete migration workflow."""
        mock_repo, tmp_path, migrations_root = mock_repo_with_migration_files

        mgr = MigrationManager(mock_repo)
        mgr._migrations_root = migrations_root
        mgr._log_file = migrations_root / "log"

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

        # Check that Git commands were called
        mock_repo.hgit.add.assert_called_once_with('.')
        mock_repo.hgit.commit.assert_called_once()

        # Check commit message
        commit_msg = mock_repo.hgit.commit.call_args[0][0]
        assert "[HOP] Migration from 0.17.0 to 0.17.1" in commit_msg

    def test_run_migrations_no_pending(self, mock_repo_with_migration_files):
        """Test run_migrations() with no pending migrations."""
        mock_repo, tmp_path, migrations_root = mock_repo_with_migration_files

        mgr = MigrationManager(mock_repo)
        mgr._migrations_root = migrations_root
        mgr._log_file = migrations_root / "log"

        # Mark all migrations as applied
        with open(mgr._log_file, 'a') as f:
            f.write("0.17.1\n")

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
        mgr._log_file = migrations_root / "log"

        # Run migrations without commit
        result = mgr.run_migrations(
            target_version="0.17.1",
            create_commit=False
        )

        # Check result
        assert len(result['migrations_applied']) == 1
        assert result['commit_created'] is False

        # Git commands should not be called
        mock_repo.hgit.add.assert_not_called()
        mock_repo.hgit.commit.assert_not_called()
