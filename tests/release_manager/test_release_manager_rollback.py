"""
Tests for ReleaseManager rollback production workflow.

Covers:
- _slug_to_version: slug → version string conversion
- _list_rollback_versions: snapshot enumeration and sorting
- rollback_production: DB restore + branch checkout
"""

import pytest
from unittest.mock import Mock, patch, call
from half_orm_dev.release_manager import ReleaseManager, ReleaseManagerError


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def release_manager_for_rollback(tmp_path):
    """ReleaseManager with minimal mocks for rollback testing."""
    releases_dir = tmp_path / ".hop" / "releases"
    releases_dir.mkdir(parents=True, exist_ok=True)

    mock_repo = Mock()
    mock_repo.name = "test_db"
    mock_repo.base_dir = tmp_path
    mock_repo.releases_dir = str(releases_dir)
    mock_repo.model_dir = str(tmp_path / ".hop" / "model")

    mock_database = Mock()
    mock_database.name = "myapp"
    mock_database.last_release_s = "1.3.6"
    mock_database.has_createdb_privilege = Mock(return_value=True)
    mock_database._get_connection_params = Mock(
        return_value={'host': '', 'port': 5432, 'user': '', 'password': ''}
    )
    mock_database.terminate_active_connections = Mock()
    mock_database.restore_from_snapshot = Mock()
    mock_database.list_snapshots = Mock(return_value=[])
    mock_repo.database = mock_database

    mock_hgit = Mock()
    mock_hgit.branch = "ho-prod-1.3.6"
    mock_hgit.repos_is_clean = Mock(return_value=True)
    mock_hgit._HGit__git_repo = Mock()
    mock_hgit._HGit__git_repo.heads = []
    mock_repo.hgit = mock_hgit

    return ReleaseManager(mock_repo), mock_repo


# ============================================================================
# _slug_to_version
# ============================================================================

class TestSlugToVersion:

    @pytest.fixture
    def mgr(self, release_manager_for_rollback):
        return release_manager_for_rollback[0]

    def test_simple_version(self, mgr):
        assert mgr._slug_to_version("1_3_5") == "1.3.5"

    def test_zero_version(self, mgr):
        assert mgr._slug_to_version("0_17_0") == "0.17.0"

    def test_prerelease_version(self, mgr):
        assert mgr._slug_to_version("1_0_0_a29") == "1.0.0-a29"

    def test_prerelease_multi_part(self, mgr):
        assert mgr._slug_to_version("1_0_0_rc1") == "1.0.0-rc1"

    def test_too_short_returns_none(self, mgr):
        assert mgr._slug_to_version("1_3") is None

    def test_non_numeric_start_returns_none(self, mgr):
        assert mgr._slug_to_version("abc_1_0") is None


# ============================================================================
# _list_rollback_versions
# ============================================================================

class TestListRollbackVersions:

    def test_returns_versions_sorted_descending(self, release_manager_for_rollback):
        mgr, mock_repo = release_manager_for_rollback
        mock_repo.database.list_snapshots.return_value = [
            "myapp_hop_snap_1_3_4",
            "myapp_hop_snap_1_3_5",
            "myapp_hop_snap_1_3_6",
        ]
        versions = mgr._list_rollback_versions()
        assert versions == ["1.3.6", "1.3.5", "1.3.4"]

    def test_filters_unrelated_databases(self, release_manager_for_rollback):
        mgr, mock_repo = release_manager_for_rollback
        mock_repo.database.list_snapshots.return_value = [
            "myapp_hop_snap_1_3_5",
            "other_db_hop_snap_1_3_5",
            "myapp_something_else",
        ]
        versions = mgr._list_rollback_versions()
        assert versions == ["1.3.5"]

    def test_empty_when_no_snapshots(self, release_manager_for_rollback):
        mgr, mock_repo = release_manager_for_rollback
        mock_repo.database.list_snapshots.return_value = []
        assert mgr._list_rollback_versions() == []

    def test_prerelease_versions_included(self, release_manager_for_rollback):
        mgr, mock_repo = release_manager_for_rollback
        mock_repo.database.list_snapshots.return_value = [
            "myapp_hop_snap_1_0_0_a29",
            "myapp_hop_snap_1_0_0_a28",
        ]
        versions = mgr._list_rollback_versions()
        assert "1.0.0-a29" in versions
        assert "1.0.0-a28" in versions


# ============================================================================
# rollback_production
# ============================================================================

class TestRollbackProduction:

    def test_rollback_default_to_previous_version(self, release_manager_for_rollback):
        mgr, mock_repo = release_manager_for_rollback
        mock_repo.database.list_snapshots.return_value = [
            "myapp_hop_snap_1_3_4",
            "myapp_hop_snap_1_3_5",
        ]

        result = mgr.rollback_production()

        assert result['from_version'] == "1.3.6"
        assert result['to_version'] == "1.3.5"
        assert result['snapshot'] == "myapp_hop_snap_1_3_5"
        assert result['branch'] == "ho-prod-1.3.5"

    def test_rollback_explicit_version(self, release_manager_for_rollback):
        mgr, mock_repo = release_manager_for_rollback
        mock_repo.database.list_snapshots.return_value = [
            "myapp_hop_snap_1_3_4",
            "myapp_hop_snap_1_3_5",
        ]

        result = mgr.rollback_production(to_version="1.3.4")

        assert result['to_version'] == "1.3.4"
        assert result['snapshot'] == "myapp_hop_snap_1_3_4"

    def test_rollback_calls_restore_from_snapshot(self, release_manager_for_rollback):
        mgr, mock_repo = release_manager_for_rollback
        mock_repo.database.list_snapshots.return_value = ["myapp_hop_snap_1_3_5"]

        mgr.rollback_production(to_version="1.3.5")

        mock_repo.database.terminate_active_connections.assert_called_once()
        mock_repo.database.restore_from_snapshot.assert_called_once_with("myapp_hop_snap_1_3_5")

    def test_rollback_checkouts_existing_local_branch(self, release_manager_for_rollback):
        mgr, mock_repo = release_manager_for_rollback
        mock_repo.database.list_snapshots.return_value = ["myapp_hop_snap_1_3_5"]

        mock_head = Mock()
        mock_head.name = "ho-prod-1.3.5"
        mock_repo.hgit._HGit__git_repo.heads = [mock_head]

        mgr.rollback_production(to_version="1.3.5")

        mock_head.checkout.assert_called_once()

    def test_rollback_creates_branch_from_remote_if_not_local(self, release_manager_for_rollback):
        mgr, mock_repo = release_manager_for_rollback
        mock_repo.database.list_snapshots.return_value = ["myapp_hop_snap_1_3_5"]
        mock_repo.hgit._HGit__git_repo.heads = []

        mgr.rollback_production(to_version="1.3.5")

        mock_repo.hgit._HGit__git_repo.git.checkout.assert_called_once_with(
            '-b', 'ho-prod-1.3.5', 'origin/ho-prod-1.3.5'
        )

    def test_rollback_raises_when_no_snapshots(self, release_manager_for_rollback):
        mgr, mock_repo = release_manager_for_rollback
        mock_repo.database.list_snapshots.return_value = []

        with pytest.raises(ReleaseManagerError, match="No snapshots available"):
            mgr.rollback_production()

    def test_rollback_raises_when_no_previous_version(self, release_manager_for_rollback):
        mgr, mock_repo = release_manager_for_rollback
        # Only snapshots >= current version
        mock_repo.database.list_snapshots.return_value = ["myapp_hop_snap_1_3_6"]

        with pytest.raises(ReleaseManagerError, match="No previous version"):
            mgr.rollback_production()

    def test_rollback_raises_when_explicit_version_not_available(self, release_manager_for_rollback):
        mgr, mock_repo = release_manager_for_rollback
        mock_repo.database.list_snapshots.return_value = ["myapp_hop_snap_1_3_5"]

        with pytest.raises(ReleaseManagerError, match="No snapshot available"):
            mgr.rollback_production(to_version="1.3.4")

    def test_rollback_default_selects_latest_previous(self, release_manager_for_rollback):
        """When multiple previous versions exist, default is the latest one."""
        mgr, mock_repo = release_manager_for_rollback
        mock_repo.database.list_snapshots.return_value = [
            "myapp_hop_snap_1_3_3",
            "myapp_hop_snap_1_3_4",
            "myapp_hop_snap_1_3_5",
        ]

        result = mgr.rollback_production()

        assert result['to_version'] == "1.3.5"
