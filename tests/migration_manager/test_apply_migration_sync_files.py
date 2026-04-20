"""
Tests for apply_migration() sync_files auto-detection.

Verifies that files staged by a migration script via repo.hgit.add() are
automatically included in the sync_files result, even when the script does
not declare them explicitly.

Relies on the precondition that the git index is empty before migration
runs (clean repo guaranteed by the migrate command).
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock
from half_orm_dev.migration_manager import MigrationManager


def _make_mgr(tmp_path, staged_files=None):
    """
    Return a MigrationManager wired to a mock repo.

    staged_files: list of filenames that git diff --cached reports after
                  the migration script runs (simulates hgit.add() calls).
    """
    mock_repo = Mock()
    mock_repo.base_dir = str(tmp_path)

    # Wire git diff --cached to return the given staged file list
    mock_git = Mock()
    mock_git.diff.return_value = '\n'.join(staged_files or [])
    mock_git_repo = Mock()
    mock_git_repo.git = mock_git
    mock_hgit = Mock()
    mock_hgit._HGit__git_repo = mock_git_repo
    mock_repo.hgit = mock_hgit

    mgr = MigrationManager(mock_repo)
    return mgr


def _make_migration_dir(tmp_path, name='0.18.0', script_body=''):
    """Create a minimal migration directory with one script."""
    mdir = tmp_path / 'migrations' / name
    mdir.mkdir(parents=True)
    (mdir / '00_test.py').write_text(
        f"def get_description():\n    return 'test'\n\ndef migrate(repo):\n{script_body}\n"
    )
    return mdir


class TestApplyMigrationSyncFiles:
    """Tests for auto-detection of staged files in apply_migration()."""

    def test_staged_file_without_sync_files_declaration(self, tmp_path):
        """Script calls hgit.add() but returns None → file appears in sync_files."""
        mdir = _make_migration_dir(
            tmp_path,
            script_body="    repo.hgit.add('mypackage/__init__.py')\n",
        )
        mgr = _make_mgr(tmp_path, staged_files=['mypackage/__init__.py'])

        result = mgr.apply_migration('0.18.0', mdir)

        assert 'mypackage/__init__.py' in result['sync_files']

    def test_explicit_sync_files_merged_with_auto_staged(self, tmp_path):
        """Script returns sync_files=['explicit.py'] AND stages other.py → both present."""
        mdir = _make_migration_dir(
            tmp_path,
            script_body=(
                "    repo.hgit.add('other.py')\n"
                "    return {'sync_files': ['explicit.py']}\n"
            ),
        )
        mgr = _make_mgr(tmp_path, staged_files=['explicit.py', 'other.py'])

        result = mgr.apply_migration('0.18.0', mdir)

        assert 'explicit.py' in result['sync_files']
        assert 'other.py' in result['sync_files']

    def test_no_duplicates_when_declared_and_auto_staged_overlap(self, tmp_path):
        """File declared in sync_files AND staged → appears only once."""
        mdir = _make_migration_dir(
            tmp_path,
            script_body="    return {'sync_files': ['pyproject.toml']}\n",
        )
        mgr = _make_mgr(tmp_path, staged_files=['pyproject.toml'])

        result = mgr.apply_migration('0.18.0', mdir)

        assert result['sync_files'].count('pyproject.toml') == 1

    def test_no_staged_files_produces_empty_sync_files(self, tmp_path):
        """Script stages nothing → sync_files remains empty."""
        mdir = _make_migration_dir(tmp_path, script_body="    pass\n")
        mgr = _make_mgr(tmp_path, staged_files=[])

        result = mgr.apply_migration('0.18.0', mdir)

        assert result['sync_files'] == []

    def test_multiple_scripts_accumulate_sync_files(self, tmp_path):
        """Two scripts staging different files → both files in sync_files."""
        mdir = tmp_path / 'migrations' / '0.18.0'
        mdir.mkdir(parents=True)
        (mdir / '00_first.py').write_text(
            "def get_description(): return 'first'\n"
            "def migrate(repo):\n    repo.hgit.add('a.py')\n"
        )
        (mdir / '01_second.py').write_text(
            "def get_description(): return 'second'\n"
            "def migrate(repo):\n    repo.hgit.add('b.py')\n"
        )

        # git diff --cached is cumulative: after script 1 → 'a.py' staged;
        # after script 2 → both 'a.py' and 'b.py' staged.
        mock_repo = Mock()
        mock_repo.base_dir = str(tmp_path)
        mock_git = Mock()
        mock_git.diff.side_effect = ['a.py', 'a.py\nb.py']
        mock_git_repo = Mock()
        mock_git_repo.git = mock_git
        mock_hgit = Mock()
        mock_hgit._HGit__git_repo = mock_git_repo
        mock_repo.hgit = mock_hgit

        mgr = MigrationManager(mock_repo)
        result = mgr.apply_migration('0.18.0', mdir)

        assert 'a.py' in result['sync_files']
        assert 'b.py' in result['sync_files']
        # a.py appears in both rounds but deduplication removes duplicates
        assert result['sync_files'].count('a.py') == 1
        assert len(result['sync_files']) == 2