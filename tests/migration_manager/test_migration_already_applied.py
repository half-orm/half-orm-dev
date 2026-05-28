"""
Tests that run_migrations() delegates origin sync to check_and_update().

The "already applied by another developer" case is now handled transparently:
check_and_update() pulls ho-prod + syncs all branches, then
the version comparison in run_migrations() detects nothing left to do.
"""

import pytest
from unittest.mock import Mock, patch

from half_orm_dev.migration_manager import MigrationManager


@pytest.fixture
def mgr_already_at_target(tmp_path):
    """MigrationManager where current version already equals target."""
    mock_repo = Mock()
    mock_repo.base_dir = str(tmp_path)

    mock_config = Mock()
    mock_config.hop_version = "1.0.0-a16"
    mock_repo.config = mock_config

    from packaging import version as pkg_version
    def compare_versions(v1, v2):
        p1, p2 = pkg_version.parse(v1), pkg_version.parse(v2)
        return -1 if p1 < p2 else (1 if p1 > p2 else 0)
    mock_repo.compare_versions = compare_versions
    mock_hgit = Mock()
    mock_repo.hgit = mock_hgit

    hop_dir = tmp_path / ".hop"
    hop_dir.mkdir()

    return MigrationManager(mock_repo), mock_repo


class TestRunMigrationsOriginSync:
    def test_no_commit_when_already_at_target(self, mgr_already_at_target):
        """No migration commit when version is already at target after sync."""
        mgr, mock_repo = mgr_already_at_target
        result = mgr.run_migrations(target_version="1.0.0-a16", create_commit=False)
        assert result['commit_created'] is False
        assert result['migrations_applied'] == []
