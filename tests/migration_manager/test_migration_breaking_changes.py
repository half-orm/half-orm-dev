"""
Tests for MigrationManager.get_breaking_changes().

Verifies that breaking-changes documents are correctly collected for all
versions in ]current, target] across both the hop/ and half_orm/ components.
"""
import pytest
from pathlib import Path
from unittest.mock import Mock
from half_orm_dev.migration_manager import MigrationManager


@pytest.fixture
def mgr_with_bc_dir(tmp_path):
    """
    MigrationManager whose _migrations_root points to a temporary directory.

    Creates hop/ and half_orm/ subdirectories ready to receive
    BREAKING_CHANGES-X.Y.Z.md files.
    """
    mock_repo = Mock()
    mock_repo.base_dir = str(tmp_path)

    from packaging import version as pkg_version

    def compare_versions(v1, v2):
        p1 = pkg_version.parse(v1)
        p2 = pkg_version.parse(v2)
        return 0 if p1 == p2 else (1 if p1 > p2 else -1)

    mock_repo.compare_versions = compare_versions

    mgr = MigrationManager(mock_repo)

    # Redirect migrations root to tmp_path so tests don't touch the real files
    bc_root = tmp_path / 'migrations'
    (bc_root / 'hop').mkdir(parents=True)
    (bc_root / 'half_orm').mkdir(parents=True)
    mgr._migrations_root = bc_root

    return mgr, bc_root


class TestGetBreakingChanges:
    """Unit tests for MigrationManager.get_breaking_changes()."""

    def test_no_files_returns_empty(self, mgr_with_bc_dir):
        """No breaking-changes files → empty list."""
        mgr, _ = mgr_with_bc_dir
        assert mgr.get_breaking_changes('0.17.0', '1.0.0') == []

    def test_file_in_range_is_returned(self, mgr_with_bc_dir):
        """A file whose version is inside ]current, target] is returned."""
        mgr, bc_root = mgr_with_bc_dir
        (bc_root / 'hop' / 'BREAKING_CHANGES-1.0.0.md').write_text('hop 1.0.0 changes')

        result = mgr.get_breaking_changes('0.17.0', '1.0.0')

        assert len(result) == 1
        assert result[0]['component'] == 'hop'
        assert result[0]['version'] == '1.0.0'
        assert result[0]['content'] == 'hop 1.0.0 changes'

    def test_file_equal_to_current_is_excluded(self, mgr_with_bc_dir):
        """A file whose version equals current_version is NOT returned (exclusive lower bound)."""
        mgr, bc_root = mgr_with_bc_dir
        (bc_root / 'hop' / 'BREAKING_CHANGES-0.17.0.md').write_text('already applied')

        assert mgr.get_breaking_changes('0.17.0', '1.0.0') == []

    def test_file_below_current_is_excluded(self, mgr_with_bc_dir):
        """A file whose version is below current_version is NOT returned."""
        mgr, bc_root = mgr_with_bc_dir
        (bc_root / 'hop' / 'BREAKING_CHANGES-0.16.0.md').write_text('old change')

        assert mgr.get_breaking_changes('0.17.0', '1.0.0') == []

    def test_file_above_target_is_excluded(self, mgr_with_bc_dir):
        """A file whose version exceeds target_version is NOT returned."""
        mgr, bc_root = mgr_with_bc_dir
        (bc_root / 'hop' / 'BREAKING_CHANGES-2.0.0.md').write_text('future change')

        assert mgr.get_breaking_changes('0.17.0', '1.0.0') == []

    def test_both_components_returned(self, mgr_with_bc_dir):
        """Files in both hop/ and half_orm/ are returned when in range."""
        mgr, bc_root = mgr_with_bc_dir
        (bc_root / 'hop' / 'BREAKING_CHANGES-1.0.0.md').write_text('hop changes')
        (bc_root / 'half_orm' / 'BREAKING_CHANGES-1.0.0.md').write_text('half_orm changes')

        result = mgr.get_breaking_changes('0.17.0', '1.0.0')

        assert len(result) == 2
        components = {r['component'] for r in result}
        assert components == {'hop', 'half_orm'}

    def test_multiple_versions_sorted(self, mgr_with_bc_dir):
        """Multiple files in range are returned sorted by version ascending."""
        mgr, bc_root = mgr_with_bc_dir
        (bc_root / 'hop' / 'BREAKING_CHANGES-1.0.0.md').write_text('1.0.0')
        (bc_root / 'hop' / 'BREAKING_CHANGES-0.18.0.md').write_text('0.18.0')
        (bc_root / 'hop' / 'BREAKING_CHANGES-1.1.0.md').write_text('1.1.0')

        result = mgr.get_breaking_changes('0.17.0', '1.1.0')

        assert [r['version'] for r in result] == ['0.18.0', '1.0.0', '1.1.0']

    def test_skips_nonmigration_target_only_version(self, mgr_with_bc_dir):
        """Only the target version (inclusive) is included, not above."""
        mgr, bc_root = mgr_with_bc_dir
        (bc_root / 'hop' / 'BREAKING_CHANGES-1.0.0.md').write_text('target')
        (bc_root / 'hop' / 'BREAKING_CHANGES-1.0.1.md').write_text('above target')

        result = mgr.get_breaking_changes('0.17.0', '1.0.0')

        assert len(result) == 1
        assert result[0]['version'] == '1.0.0'

    def test_invalid_filename_is_skipped(self, mgr_with_bc_dir):
        """Files with unparseable version strings are silently ignored."""
        mgr, bc_root = mgr_with_bc_dir
        (bc_root / 'hop' / 'BREAKING_CHANGES-not-a-version.md').write_text('bad')
        (bc_root / 'hop' / 'BREAKING_CHANGES-1.0.0.md').write_text('good')

        result = mgr.get_breaking_changes('0.17.0', '1.0.0')

        assert len(result) == 1
        assert result[0]['version'] == '1.0.0'

    def test_prerelease_versions_compared_correctly(self, mgr_with_bc_dir):
        """Pre-release versions are handled via packaging.version semantics."""
        mgr, bc_root = mgr_with_bc_dir
        # 1.0.0-a1 < 1.0.0 so it should be included in ]0.17.0, 1.0.0]
        (bc_root / 'hop' / 'BREAKING_CHANGES-1.0.0-a1.md').write_text('alpha change')

        result = mgr.get_breaking_changes('0.17.0', '1.0.0')

        assert len(result) == 1
        assert result[0]['version'] == '1.0.0-a1'

    def test_stable_file_included_when_target_is_prerelease(self, mgr_with_bc_dir):
        """A file named '1.0.0' is shown when migrating to '1.0.0-a1'.

        base_version comparison: 0.18.0 < 1.0.0 <= 1.0.0 (base of 1.0.0-a1) → True.
        This is the expected usage pattern: breaking-changes files are named
        after the stable series (e.g. 1.0.0) even when the first release is a
        pre-release (1.0.0-a1).
        """
        mgr, bc_root = mgr_with_bc_dir
        (bc_root / 'hop' / 'BREAKING_CHANGES-1.0.0.md').write_text('series change')

        result = mgr.get_breaking_changes('0.18.0-a1', '1.0.0-a1')

        assert len(result) == 1
        assert result[0]['version'] == '1.0.0'

    def test_stable_file_not_repeated_when_already_on_prerelease(self, mgr_with_bc_dir):
        """When current is 1.0.0-a1 → 1.0.0-a2, the '1.0.0' BC file is NOT shown again.

        base_version of 1.0.0-a1 is 1.0.0, so current_base = 1.0.0.
        The condition 1.0.0 < 1.0.0 is False → file excluded.
        """
        mgr, bc_root = mgr_with_bc_dir
        (bc_root / 'hop' / 'BREAKING_CHANGES-1.0.0.md').write_text('series change')

        result = mgr.get_breaking_changes('1.0.0-a1', '1.0.0-a2')

        assert result == []

    def test_missing_component_dir_is_skipped(self, mgr_with_bc_dir):
        """If one component directory is absent, the other still works."""
        mgr, bc_root = mgr_with_bc_dir
        import shutil
        shutil.rmtree(bc_root / 'half_orm')
        (bc_root / 'hop' / 'BREAKING_CHANGES-1.0.0.md').write_text('hop only')

        result = mgr.get_breaking_changes('0.17.0', '1.0.0')

        assert len(result) == 1
        assert result[0]['component'] == 'hop'

    def test_invalid_current_or_target_version_returns_empty(self, mgr_with_bc_dir):
        """Unparseable current/target versions return empty list instead of crashing."""
        mgr, bc_root = mgr_with_bc_dir
        (bc_root / 'hop' / 'BREAKING_CHANGES-1.0.0.md').write_text('change')

        assert mgr.get_breaking_changes('not-a-version', '1.0.0') == []
        assert mgr.get_breaking_changes('0.17.0', 'not-a-version') == []
