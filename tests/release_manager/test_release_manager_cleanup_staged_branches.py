"""
Tests for ReleaseManager._cleanup_release_branch() — staged branch deletion.

The bug: after production promotion the X.Y.Z-patches.toml file is deleted
(replaced by X.Y.Z.txt).  _cleanup_release_branch() used to read the .toml
to find staged patch IDs, so release_file.exists() returned False and NO
ho-staged/* branches were ever deleted.

The fix: read the production .txt file instead.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, call

from half_orm_dev.release_manager import ReleaseManager


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def release_mgr_cleanup(tmp_path):
    """Minimal ReleaseManager wired for _cleanup_release_branch tests."""
    releases_dir = tmp_path / ".hop" / "releases"
    releases_dir.mkdir(parents=True, exist_ok=True)

    mock_repo = Mock()
    mock_repo.name = "test_repo"
    mock_repo.base_dir = tmp_path
    mock_repo.releases_dir = str(releases_dir)
    mock_repo.model_dir = str(tmp_path / ".hop" / "model")
    mock_repo.allow_rc = False

    mock_hgit = Mock()
    mock_hgit.branch_exists.return_value = True
    mock_hgit.delete_local_branch = Mock()
    mock_hgit.delete_remote_branch = Mock()
    mock_hgit.delete_branch = Mock()
    mock_repo.hgit = mock_hgit

    mgr = ReleaseManager(mock_repo)
    return mgr, mock_repo, mock_hgit, releases_dir


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCleanupReleaseStagedBranches:
    """_cleanup_release_branch must delete ho-staged/* using the .txt file."""

    def test_no_toml_no_txt_deletes_release_branch_only(
        self, release_mgr_cleanup
    ):
        """No release file at all → only the release branch itself is deleted."""
        mgr, _, mock_hgit, _ = release_mgr_cleanup
        deleted = mgr._cleanup_release_branch('ho-release/0.2.0')
        assert 'ho-release/0.2.0' in deleted
        mock_hgit.delete_local_branch.assert_not_called()

    def test_toml_present_but_no_txt_skips_staged(
        self, release_mgr_cleanup
    ):
        """TOML exists (pre-production) — no .txt yet → no staged branches deleted.

        This is the case during RC promotion: the .txt hasn't been created yet,
        so ho-staged/* branches are intentionally kept alive.
        """
        mgr, _, mock_hgit, releases_dir = release_mgr_cleanup
        # Only TOML, no .txt
        (releases_dir / "0.2.0-patches.toml").write_text(
            '[patches]\n"42-foo" = {status = "staged", merge_commit = "aabbcc"}\n'
        )
        deleted = mgr._cleanup_release_branch('ho-release/0.2.0')
        mock_hgit.delete_local_branch.assert_not_called()

    def test_txt_present_deletes_staged_branches(
        self, release_mgr_cleanup
    ):
        """BUG REPRO: .txt exists (post-prod), .toml already deleted.

        _cleanup_release_branch must read the .txt file and delete every
        ho-staged/<patch_id> branch listed there.
        """
        mgr, _, mock_hgit, releases_dir = release_mgr_cleanup
        # Production .txt — TOML already deleted
        (releases_dir / "0.2.0.txt").write_text("42-foo\n99-bar\n")

        deleted = mgr._cleanup_release_branch('ho-release/0.2.0')

        mock_hgit.delete_local_branch.assert_any_call('ho-staged/42-foo')
        mock_hgit.delete_local_branch.assert_any_call('ho-staged/99-bar')
        mock_hgit.delete_remote_branch.assert_any_call('ho-staged/42-foo')
        mock_hgit.delete_remote_branch.assert_any_call('ho-staged/99-bar')
        assert 'ho-staged/42-foo' in deleted
        assert 'ho-staged/99-bar' in deleted

    def test_txt_with_nonexistent_local_branch_still_deletes_remote(
        self, release_mgr_cleanup
    ):
        """Local branch may already be gone; remote must still be deleted."""
        mgr, _, mock_hgit, releases_dir = release_mgr_cleanup
        mock_hgit.branch_exists.return_value = False
        (releases_dir / "0.2.0.txt").write_text("42-foo\n")

        mgr._cleanup_release_branch('ho-release/0.2.0')

        mock_hgit.delete_local_branch.assert_not_called()
        mock_hgit.delete_remote_branch.assert_any_call('ho-staged/42-foo')

    def test_txt_with_empty_lines_ignored(
        self, release_mgr_cleanup
    ):
        """Empty lines in the .txt file must not produce invalid branch names."""
        mgr, _, mock_hgit, releases_dir = release_mgr_cleanup
        (releases_dir / "0.2.0.txt").write_text("\n42-foo\n\n")

        deleted = mgr._cleanup_release_branch('ho-release/0.2.0')

        assert 'ho-staged/42-foo' in deleted
        # No call with an empty string
        for c in mock_hgit.delete_local_branch.call_args_list:
            assert c.args[0] != 'ho-staged/'


class TestCleanupOrphanedStagedBranches:
    """cleanup_orphaned_staged_branches() deletes ho-staged/* whose patch is
    already in production (ID listed in any .txt file in releases/).

    This sweeps branches that survived a failed or interrupted production
    promotion, or were left over from old releases.
    """

    def test_no_txt_files_nothing_deleted(self, release_mgr_cleanup):
        """No .txt files → no orphan detection possible → nothing deleted."""
        mgr, _, mock_hgit, _ = release_mgr_cleanup
        mock_hgit._HGit__git_repo.branches = []
        mgr.cleanup_orphaned_staged_branches()
        mock_hgit.delete_local_branch.assert_not_called()
        mock_hgit.delete_remote_branch.assert_not_called()

    def test_staged_branch_in_txt_is_deleted(self, release_mgr_cleanup):
        """A ho-staged/* branch whose ID is in a .txt file must be deleted."""
        mgr, _, mock_hgit, releases_dir = release_mgr_cleanup
        (releases_dir / "0.2.0.txt").write_text("42-foo\n99-bar\n")

        # Simulate two ho-staged branches present locally
        branch_42 = Mock(); branch_42.name = 'ho-staged/42-foo'
        branch_99 = Mock(); branch_99.name = 'ho-staged/99-bar'
        mock_hgit._HGit__git_repo.branches = [branch_42, branch_99]
        mock_hgit.branch_exists.return_value = True

        mgr.cleanup_orphaned_staged_branches()

        mock_hgit.delete_local_branch.assert_any_call('ho-staged/42-foo')
        mock_hgit.delete_local_branch.assert_any_call('ho-staged/99-bar')
        mock_hgit.delete_remote_branch.assert_any_call('ho-staged/42-foo')
        mock_hgit.delete_remote_branch.assert_any_call('ho-staged/99-bar')

    def test_staged_branch_in_toml_only_is_kept(self, release_mgr_cleanup):
        """A ho-staged/* branch still in a .toml (not yet in prod) is kept."""
        mgr, _, mock_hgit, releases_dir = release_mgr_cleanup
        # Only a TOML, no .txt
        (releases_dir / "0.3.0-patches.toml").write_text(
            '[patches]\n"55-live" = {status = "staged", merge_commit = "abc"}\n'
        )

        branch_55 = Mock(); branch_55.name = 'ho-staged/55-live'
        mock_hgit._HGit__git_repo.branches = [branch_55]

        mgr.cleanup_orphaned_staged_branches()

        mock_hgit.delete_local_branch.assert_not_called()
        mock_hgit.delete_remote_branch.assert_not_called()

    def test_non_staged_branches_not_touched(self, release_mgr_cleanup):
        """ho-patch/* and ho-release/* branches are never touched."""
        mgr, _, mock_hgit, releases_dir = release_mgr_cleanup
        (releases_dir / "0.2.0.txt").write_text("42-foo\n")

        patch_branch = Mock(); patch_branch.name = 'ho-patch/42-foo'
        release_branch = Mock(); release_branch.name = 'ho-release/0.2.0'
        mock_hgit._HGit__git_repo.branches = [patch_branch, release_branch]

        mgr.cleanup_orphaned_staged_branches()

        mock_hgit.delete_local_branch.assert_not_called()

    def test_multiple_txt_files_all_scanned(self, release_mgr_cleanup):
        """Patch IDs from all .txt files are collected before deciding."""
        mgr, _, mock_hgit, releases_dir = release_mgr_cleanup
        (releases_dir / "0.1.0.txt").write_text("10-alpha\n")
        (releases_dir / "0.2.0.txt").write_text("20-beta\n")

        branch_10 = Mock(); branch_10.name = 'ho-staged/10-alpha'
        branch_20 = Mock(); branch_20.name = 'ho-staged/20-beta'
        mock_hgit._HGit__git_repo.branches = [branch_10, branch_20]
        mock_hgit.branch_exists.return_value = True

        mgr.cleanup_orphaned_staged_branches()

        mock_hgit.delete_local_branch.assert_any_call('ho-staged/10-alpha')
        mock_hgit.delete_local_branch.assert_any_call('ho-staged/20-beta')