"""
Tests for BootstrapManager.

Tests the bootstrap script management functionality including:
- File listing and sorting
- Execution tracking
- Patch exclusion
- Filename parsing
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from half_orm_dev.bootstrap_manager import BootstrapManager, BootstrapManagerError


@pytest.fixture
def mock_repo(tmp_path):
    """Create a mock repository with bootstrap directory."""
    repo = Mock()
    repo.base_dir = str(tmp_path)
    repo.database = Mock()
    repo.database.model = Mock()
    repo.database.model.execute_query = Mock(return_value=[])
    return repo


@pytest.fixture
def bootstrap_manager(mock_repo, tmp_path):
    """Create BootstrapManager with mock repo."""
    # Create bootstrap directory
    bootstrap_dir = tmp_path / 'bootstrap'
    bootstrap_dir.mkdir()
    return BootstrapManager(mock_repo)


class TestBootstrapManagerInit:
    """Test BootstrapManager initialization."""

    def test_init_sets_repo(self, mock_repo):
        """Test that init stores the repo reference."""
        mgr = BootstrapManager(mock_repo)
        assert mgr._repo is mock_repo

    def test_bootstrap_dir_property(self, mock_repo, tmp_path):
        """Test bootstrap_dir returns correct path."""
        mgr = BootstrapManager(mock_repo)
        expected = tmp_path / 'bootstrap'
        assert mgr.bootstrap_dir == expected


class TestGetBootstrapFiles:
    """Test get_bootstrap_files method."""

    def test_empty_directory(self, bootstrap_manager):
        """Test with no bootstrap files."""
        files = bootstrap_manager.get_bootstrap_files()
        assert files == []

    def test_returns_sql_files(self, bootstrap_manager, tmp_path):
        """Test that SQL files are returned."""
        bootstrap_dir = tmp_path / 'bootstrap'
        (bootstrap_dir / '1-init-0.1.0.sql').write_text('-- SQL')

        files = bootstrap_manager.get_bootstrap_files()
        assert len(files) == 1
        assert files[0].name == '1-init-0.1.0.sql'

    def test_returns_python_files(self, bootstrap_manager, tmp_path):
        """Test that Python files are returned."""
        bootstrap_dir = tmp_path / 'bootstrap'
        (bootstrap_dir / '1-init-0.1.0.py').write_text('# Python')

        files = bootstrap_manager.get_bootstrap_files()
        assert len(files) == 1
        assert files[0].name == '1-init-0.1.0.py'

    def test_ignores_readme(self, bootstrap_manager, tmp_path):
        """Test that README files are ignored."""
        bootstrap_dir = tmp_path / 'bootstrap'
        (bootstrap_dir / 'README.md').write_text('# Readme')
        (bootstrap_dir / '1-init-0.1.0.sql').write_text('-- SQL')

        files = bootstrap_manager.get_bootstrap_files()
        assert len(files) == 1
        assert files[0].name == '1-init-0.1.0.sql'

    def test_numeric_sorting(self, bootstrap_manager, tmp_path):
        """Test that files are sorted numerically, not lexicographically."""
        bootstrap_dir = tmp_path / 'bootstrap'
        (bootstrap_dir / '2-second-0.1.0.sql').write_text('-- 2')
        (bootstrap_dir / '10-tenth-0.1.0.sql').write_text('-- 10')
        (bootstrap_dir / '1-first-0.1.0.sql').write_text('-- 1')

        files = bootstrap_manager.get_bootstrap_files()
        names = [f.name for f in files]

        # Should be 1, 2, 10 (numeric order), not 1, 10, 2 (lexicographic)
        assert names == ['1-first-0.1.0.sql', '2-second-0.1.0.sql', '10-tenth-0.1.0.sql']

    def test_nonexistent_directory(self, mock_repo, tmp_path):
        """Test with non-existent bootstrap directory."""
        # Don't create bootstrap directory
        mgr = BootstrapManager(mock_repo)
        files = mgr.get_bootstrap_files()
        assert files == []


class TestGetExecutedFiles:
    """Test get_executed_files method."""

    def test_returns_executed_filenames(self, bootstrap_manager, mock_repo):
        """Test that executed filenames are returned from database."""
        mock_repo.database.model.execute_query.return_value = [
            ('1-init-0.1.0.sql',),
            ('2-seed-0.1.0.sql',)
        ]

        executed = bootstrap_manager.get_executed_files()
        assert executed == {'1-init-0.1.0.sql', '2-seed-0.1.0.sql'}

    def test_empty_table(self, bootstrap_manager, mock_repo):
        """Test with no executed files."""
        mock_repo.database.model.execute_query.return_value = []

        executed = bootstrap_manager.get_executed_files()
        assert executed == set()

    def test_handles_missing_table(self, bootstrap_manager, mock_repo):
        """Test that missing table returns empty set."""
        mock_repo.database.model.execute_query.side_effect = Exception("relation does not exist")

        executed = bootstrap_manager.get_executed_files()
        assert executed == set()


class TestGetPendingFiles:
    """Test get_pending_files method."""

    def test_returns_unexecuted_files(self, bootstrap_manager, tmp_path, mock_repo):
        """Test that only unexecuted files are returned."""
        bootstrap_dir = tmp_path / 'bootstrap'
        (bootstrap_dir / '1-init-0.1.0.sql').write_text('-- 1')
        (bootstrap_dir / '2-seed-0.1.0.sql').write_text('-- 2')
        (bootstrap_dir / '3-data-0.1.0.sql').write_text('-- 3')

        # Mark first file as executed
        mock_repo.database.model.execute_query.return_value = [('1-init-0.1.0.sql',)]

        pending = bootstrap_manager.get_pending_files()
        names = [f.name for f in pending]

        assert '1-init-0.1.0.sql' not in names
        assert '2-seed-0.1.0.sql' in names
        assert '3-data-0.1.0.sql' in names


class TestParseFilename:
    """Test _parse_filename method."""

    def test_valid_sql_filename(self, bootstrap_manager):
        """Test parsing valid SQL filename."""
        num, patch_id, version = bootstrap_manager._parse_filename('1-init-users-0.1.0.sql')
        assert num == 1
        assert patch_id == 'init-users'
        assert version == '0.1.0'

    def test_valid_python_filename(self, bootstrap_manager):
        """Test parsing valid Python filename."""
        num, patch_id, version = bootstrap_manager._parse_filename('42-seed-data-1.2.3.py')
        assert num == 42
        assert patch_id == 'seed-data'
        assert version == '1.2.3'

    def test_complex_patch_id(self, bootstrap_manager):
        """Test parsing filename with complex patch_id."""
        num, patch_id, version = bootstrap_manager._parse_filename('5-456-user-auth-feature-0.17.0.sql')
        assert num == 5
        assert patch_id == '456-user-auth-feature'
        assert version == '0.17.0'

    def test_invalid_filename_raises(self, bootstrap_manager):
        """Test that invalid filename raises ValueError."""
        with pytest.raises(ValueError, match="Invalid bootstrap filename"):
            bootstrap_manager._parse_filename('invalid.sql')

    def test_missing_version_raises(self, bootstrap_manager):
        """Test that missing version raises ValueError."""
        with pytest.raises(ValueError, match="Invalid bootstrap filename"):
            bootstrap_manager._parse_filename('1-init.sql')


class TestFileBelongsToPatch:
    """Test _file_belongs_to_patch method."""

    def test_matching_patch(self, bootstrap_manager):
        """Test with matching patch_id."""
        assert bootstrap_manager._file_belongs_to_patch(
            '1-my-patch-0.1.0.sql', 'my-patch'
        ) is True

    def test_non_matching_patch(self, bootstrap_manager):
        """Test with non-matching patch_id."""
        assert bootstrap_manager._file_belongs_to_patch(
            '1-my-patch-0.1.0.sql', 'other-patch'
        ) is False

    def test_invalid_filename(self, bootstrap_manager):
        """Test with invalid filename returns False."""
        assert bootstrap_manager._file_belongs_to_patch(
            'invalid.sql', 'my-patch'
        ) is False


class TestExtractVersionFromFilename:
    """Test _extract_version_from_filename method."""

    def test_valid_filename(self, bootstrap_manager):
        """Test extracting version from valid filename."""
        version = bootstrap_manager._extract_version_from_filename('1-init-0.1.0.sql')
        assert version == '0.1.0'

    def test_invalid_filename(self, bootstrap_manager):
        """Test that invalid filename returns 'unknown'."""
        version = bootstrap_manager._extract_version_from_filename('invalid.sql')
        assert version == 'unknown'


class TestGetNextBootstrapNumber:
    """Test get_next_bootstrap_number method."""

    def test_empty_directory(self, bootstrap_manager):
        """Test with no existing files."""
        assert bootstrap_manager.get_next_bootstrap_number() == 1

    def test_with_existing_files(self, bootstrap_manager, tmp_path):
        """Test with existing files."""
        bootstrap_dir = tmp_path / 'bootstrap'
        (bootstrap_dir / '1-init-0.1.0.sql').write_text('-- 1')
        (bootstrap_dir / '2-seed-0.1.0.sql').write_text('-- 2')

        assert bootstrap_manager.get_next_bootstrap_number() == 3

    def test_with_gaps(self, bootstrap_manager, tmp_path):
        """Test with gaps in numbering."""
        bootstrap_dir = tmp_path / 'bootstrap'
        (bootstrap_dir / '1-init-0.1.0.sql').write_text('-- 1')
        (bootstrap_dir / '5-seed-0.1.0.sql').write_text('-- 5')

        # Should return next after max (5), not fill gap
        assert bootstrap_manager.get_next_bootstrap_number() == 6


class TestRunBootstrap:
    """Test run_bootstrap method."""

    def test_dry_run(self, bootstrap_manager, tmp_path, mock_repo):
        """Test dry run mode doesn't execute files."""
        bootstrap_dir = tmp_path / 'bootstrap'
        (bootstrap_dir / '1-init-0.1.0.sql').write_text('-- SQL')
        mock_repo.database.model.execute_query.return_value = []

        result = bootstrap_manager.run_bootstrap(dry_run=True)

        assert '1-init-0.1.0.sql' in result['executed']
        # execute_query is called twice: once in get_pending_files() -> get_executed_files()
        # and once more in run_bootstrap() to calculate skipped files
        # No record_execution should be called (which would add more calls)
        assert mock_repo.database.model.execute_query.call_count == 2

    def test_exclude_patch_id(self, bootstrap_manager, tmp_path, mock_repo):
        """Test that files matching exclude_patch_id are excluded."""
        bootstrap_dir = tmp_path / 'bootstrap'
        (bootstrap_dir / '1-init-0.1.0.sql').write_text('-- init')
        (bootstrap_dir / '2-my-patch-0.1.0.sql').write_text('-- my-patch')
        mock_repo.database.model.execute_query.return_value = []

        result = bootstrap_manager.run_bootstrap(
            dry_run=True,
            exclude_patch_id='my-patch'
        )

        assert '1-init-0.1.0.sql' in result['executed']
        assert '2-my-patch-0.1.0.sql' in result['excluded']

    def test_skips_already_executed(self, bootstrap_manager, tmp_path, mock_repo):
        """Test that already executed files are skipped."""
        bootstrap_dir = tmp_path / 'bootstrap'
        (bootstrap_dir / '1-init-0.1.0.sql').write_text('-- init')
        (bootstrap_dir / '2-seed-0.1.0.sql').write_text('-- seed')

        # Mark first file as executed
        mock_repo.database.model.execute_query.return_value = [('1-init-0.1.0.sql',)]

        result = bootstrap_manager.run_bootstrap(dry_run=True)

        assert '1-init-0.1.0.sql' in result['skipped']
        assert '2-seed-0.1.0.sql' in result['executed']

    def test_force_reexecutes_all(self, bootstrap_manager, tmp_path, mock_repo):
        """Test that force mode re-executes all files."""
        bootstrap_dir = tmp_path / 'bootstrap'
        (bootstrap_dir / '1-init-0.1.0.sql').write_text('-- init')

        # Mark file as executed
        mock_repo.database.model.execute_query.return_value = [('1-init-0.1.0.sql',)]

        result = bootstrap_manager.run_bootstrap(dry_run=True, force=True)

        # Should be in executed, not skipped
        assert '1-init-0.1.0.sql' in result['executed']
        assert result['skipped'] == []


class TestEnsureBootstrapDir:
    """Test ensure_bootstrap_dir method."""

    def test_creates_directory(self, mock_repo, tmp_path):
        """Test that directory is created if missing."""
        mgr = BootstrapManager(mock_repo)
        bootstrap_dir = tmp_path / 'bootstrap'

        assert not bootstrap_dir.exists()
        mgr.ensure_bootstrap_dir()
        assert bootstrap_dir.exists()

    def test_idempotent(self, bootstrap_manager, tmp_path):
        """Test that calling twice doesn't raise."""
        bootstrap_dir = tmp_path / 'bootstrap'
        assert bootstrap_dir.exists()

        # Should not raise
        bootstrap_manager.ensure_bootstrap_dir()
        assert bootstrap_dir.exists()
