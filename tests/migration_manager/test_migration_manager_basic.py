"""
Test MigrationManager basic functionality.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch
from half_orm_dev.migration_manager import MigrationManager, MigrationManagerError


@pytest.fixture
def mock_repo_for_migration(tmp_path):
    """
    Create mock repo for migration tests.
    """
    mock_repo = Mock()
    mock_repo.base_dir = str(tmp_path)

    # Mock config with hop_version
    mock_config = Mock()
    mock_config.hop_version = "0.17.0"
    mock_config.write = Mock()
    mock_repo._Repo__config = mock_config

    # Mock hgit
    mock_hgit = Mock()
    mock_hgit.add = Mock()
    mock_hgit.commit = Mock()
    mock_repo.hgit = mock_hgit

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

    # Create .hop directory
    hop_dir = tmp_path / ".hop"
    hop_dir.mkdir()

    return mock_repo, tmp_path


class TestMigrationManagerBasic:
    """Test basic MigrationManager functionality."""

    def test_init(self, mock_repo_for_migration):
        """Test MigrationManager initialization."""
        mock_repo, tmp_path = mock_repo_for_migration

        mgr = MigrationManager(mock_repo)

        assert mgr._repo == mock_repo
        assert mgr._migrations_root.name == 'migrations'

    def test_version_to_path(self, mock_repo_for_migration):
        """Test version string to path conversion."""
        mock_repo, tmp_path = mock_repo_for_migration
        mgr = MigrationManager(mock_repo)

        path = mgr._version_to_path('0.17.1')
        assert path.parts[-3:] == ('0', '17', '1')

        path_pre = mgr._version_to_path('1.0.0a20')
        assert path_pre.parts[-4:] == ('1', '0', '0', 'a20')

        path_pre_dash = mgr._version_to_path('1.0.0-a20')
        assert path_pre_dash.parts[-4:] == ('1', '0', '0', 'a20')

    def test_check_migration_needed_yes(self, mock_repo_for_migration):
        """Test check_migration_needed() when migration is needed."""
        mock_repo, tmp_path = mock_repo_for_migration

        # Config has 0.17.0, current is 0.17.1
        mgr = MigrationManager(mock_repo)
        assert mgr.check_migration_needed("0.17.1") is True

    def test_check_migration_needed_no(self, mock_repo_for_migration):
        """Test check_migration_needed() when no migration is needed."""
        mock_repo, tmp_path = mock_repo_for_migration

        # Config has 0.17.0, current is also 0.17.0
        mgr = MigrationManager(mock_repo)
        assert mgr.check_migration_needed("0.17.0") is False

    def test_check_migration_needed_downgrade(self, mock_repo_for_migration):
        """Test check_migration_needed() when current version is lower (downgrade)."""
        mock_repo, tmp_path = mock_repo_for_migration

        # Config has 0.17.0, current is 0.16.0 (downgrade - should not migrate)
        mgr = MigrationManager(mock_repo)
        assert mgr.check_migration_needed("0.16.0") is False


class TestMigrationManagerCommitMessage:
    """Test commit message generation."""

    def test_create_migration_commit_message(self, mock_repo_for_migration):
        """Test migration commit message creation."""
        mock_repo, tmp_path = mock_repo_for_migration
        mgr = MigrationManager(mock_repo)

        migrations = [
            {
                'version': '0.17.1',
                'applied_files': ['00_move_to_hop.py']
            }
        ]

        msg = mgr._create_migration_commit_message("0.17.0", "0.17.1", migrations)

        assert "[HOP] Migration from 0.17.0 to 0.17.1" in msg
        assert "0.17.1: 00_move_to_hop.py" in msg

    def test_create_migration_commit_message_multiple(self, mock_repo_for_migration):
        """Test commit message with multiple migration files."""
        mock_repo, tmp_path = mock_repo_for_migration
        mgr = MigrationManager(mock_repo)

        migrations = [
            {
                'version': '0.17.1',
                'applied_files': ['00_move_to_hop.py', '01_update_config.py']
            }
        ]

        msg = mgr._create_migration_commit_message("0.17.0", "0.17.1", migrations)

        assert "00_move_to_hop.py, 01_update_config.py" in msg


class TestGetPendingMigrationsPreRelease:
    """Test get_pending_migrations with pre-release (4th level) directories."""

    def _make_migration(self, root: Path, version_str: str, filename: str = '00_dummy.py'):
        """Create a minimal migration file at the correct path."""
        from packaging import version as pkg_version
        v = pkg_version.parse(version_str)
        major, minor, patch = v.release[:3]
        path = root / str(major) / str(minor) / str(patch)
        if v.pre:
            path = path / ''.join(str(p) for p in v.pre)
        path.mkdir(parents=True, exist_ok=True)
        (path / filename).write_text(
            "def get_description(): return 'dummy'\ndef migrate(repo): return {}\n"
        )
        return path

    def test_prerelease_versions_between_a16_and_a32(self, mock_repo_for_migration, tmp_path):
        """Jumping from a16 to a32 collects all intermediate scripts in PEP 440 order."""
        mock_repo, _ = mock_repo_for_migration
        mgr = MigrationManager(mock_repo)

        # Override migrations root with a temp directory
        migrations_root = tmp_path / 'migrations'
        mgr._migrations_root = migrations_root

        # Create scripts for a17, a9 (to test numeric vs lexicographic), a20, a32
        for pre in ('a9', 'a17', 'a20', 'a32'):
            self._make_migration(migrations_root, f'1.0.0{pre}')

        # a16 is NOT present — create it too so we know it's skipped (current)
        self._make_migration(migrations_root, '1.0.0a16')

        pending = mgr.get_pending_migrations('1.0.0-a16', '1.0.0-a32')

        versions = [v for v, _ in pending]
        # a16 excluded (current), a9 excluded (< a16), a17/a20/a32 included
        assert '1.0.0a9' not in versions
        assert '1.0.0a16' not in versions
        assert versions == ['1.0.0a17', '1.0.0a20', '1.0.0a32']

    def test_stable_and_prerelease_ordering(self, mock_repo_for_migration, tmp_path):
        """Pre-release scripts run before their stable counterpart."""
        mock_repo, _ = mock_repo_for_migration
        mgr = MigrationManager(mock_repo)

        migrations_root = tmp_path / 'migrations'
        mgr._migrations_root = migrations_root

        self._make_migration(migrations_root, '1.0.0a20')
        self._make_migration(migrations_root, '1.0.0')

        pending = mgr.get_pending_migrations('1.0.0-a19', '1.0.0')

        versions = [v for v, _ in pending]
        assert versions == ['1.0.0a20', '1.0.0']
