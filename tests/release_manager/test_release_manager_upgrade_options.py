"""
Tests for ReleaseManager.upgrade_production() - Command options.

Focused on testing:
- --dry-run (simulation mode)
- --to-release (partial upgrade)
- --force (backup overwrite)
- --skip-backup (no backup creation)
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from half_orm_dev.release_manager import ReleaseManager, ReleaseManagerError


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def release_manager_with_options(tmp_path):
    """
    Setup ReleaseManager for testing command options.

    Provides:
    - Multiple releases: 1.3.6, 1.3.7, 1.4.0
    - Current version: 1.3.5
    - Mocked dependencies
    """
    releases_dir = tmp_path / "releases"
    releases_dir.mkdir(exist_ok=True)

    backups_dir = tmp_path / "backups"
    backups_dir.mkdir()

    # Create release files
    (releases_dir / "1.3.6.txt").write_text("456-user-auth\n789-security\n")
    (releases_dir / "1.3.7.txt").write_text("999-bugfix\n")
    (releases_dir / "1.4.0.txt").write_text("111-feature\n")

    # Mock Repo
    mock_repo = Mock()
    mock_repo.name = "test_db"
    mock_repo.base_dir = tmp_path

    # Mock Database
    mock_database = Mock()
    mock_database.name = "test_db"
    mock_database.last_release_s = "1.3.5"
    mock_database.execute_pg_command = Mock()
    mock_database.register_release = Mock()
    mock_repo.database = mock_database

    # Mock HGit
    mock_hgit = Mock()
    mock_hgit.branch = "ho-prod"
    mock_hgit.repos_is_clean = Mock(return_value=True)
    mock_hgit.fetch_tags = Mock()

    mock_tag_136 = Mock()
    mock_tag_136.name = "v1.3.6"
    mock_tag_137 = Mock()
    mock_tag_137.name = "v1.3.7"
    mock_tag_140 = Mock()
    mock_tag_140.name = "v1.4.0"

    mock_hgit._HGit__git_repo = Mock()
    mock_hgit._HGit__git_repo.tags = [mock_tag_136, mock_tag_137, mock_tag_140]

    mock_repo.hgit = mock_hgit

    # Mock PatchManager
    mock_patch_manager = Mock()
    mock_patch_manager.apply_patch_files = Mock()
    mock_repo.patch_manager = mock_patch_manager

    # Create ReleaseManager
    release_mgr = ReleaseManager(mock_repo)

    return release_mgr, mock_repo, tmp_path, backups_dir


# ============================================================================
# DRY RUN TESTS
# ============================================================================

class TestUpgradeProductionDryRun:
    """Test dry-run mode (simulation without changes)."""

    def test_dry_run_returns_simulation(self, release_manager_with_options):
        """Test dry_run=True returns simulation without changes."""
        release_mgr, mock_repo, _, _ = release_manager_with_options

        # Execute dry run
        result = release_mgr.upgrade_production(dry_run=True)

        # Should be marked as dry run
        assert result['status'] == 'dry_run'
        assert result['dry_run'] is True

    def test_dry_run_no_backup_created(self, release_manager_with_options):
        """Test dry run doesn't create backup."""
        release_mgr, mock_repo, _, backups_dir = release_manager_with_options

        # Execute dry run
        result = release_mgr.upgrade_production(dry_run=True)

        # No backup should exist
        assert not (backups_dir / "1.3.5.sql").exists()

        # pg_dump should not be called
        pg_dump_calls = [
            call for call in mock_repo.database.execute_pg_command.call_args_list
            if 'pg_dump' in str(call)
        ]
        assert len(pg_dump_calls) == 0

    def test_dry_run_no_patches_applied(self, release_manager_with_options):
        """Test dry run doesn't apply patches."""
        release_mgr, mock_repo, _, _ = release_manager_with_options

        # Execute dry run
        result = release_mgr.upgrade_production(dry_run=True)

        # Patches should not be applied
        assert mock_repo.patch_manager.apply_patch_files.call_count == 0

    def test_dry_run_no_version_updated(self, release_manager_with_options):
        """Test dry run doesn't update database version."""
        release_mgr, mock_repo, _, _ = release_manager_with_options

        # Execute dry run
        result = release_mgr.upgrade_production(dry_run=True)

        # Version should not be updated
        assert mock_repo.database.register_release.call_count == 0

    def test_dry_run_shows_what_would_happen(self, release_manager_with_options):
        """Test dry run shows what would be applied."""
        release_mgr, mock_repo, _, _ = release_manager_with_options

        # Execute dry run
        result = release_mgr.upgrade_production(dry_run=True)

        # Should show simulation data
        assert 'backup_would_be_created' in result
        assert result['backup_would_be_created'] == 'backups/1.3.5.sql'

        assert 'releases_would_apply' in result
        assert result['releases_would_apply'] == ['1.3.6', '1.3.7', '1.4.0']

        assert 'patches_would_apply' in result
        assert result['patches_would_apply'] == {
            '1.3.6': ['456-user-auth', '789-security'],
            '1.3.7': ['999-bugfix'],
            '1.4.0': ['111-feature']
        }


# ============================================================================
# TO-RELEASE TESTS
# ============================================================================

class TestUpgradeProductionToRelease:
    """Test to_version option (partial upgrade)."""

    def test_stops_at_target_version(self, release_manager_with_options):
        """Test to_version stops at specified release."""
        release_mgr, mock_repo, _, _ = release_manager_with_options

        # Upgrade only to 1.3.7
        result = release_mgr.upgrade_production(
            to_version="1.3.7",
            skip_backup=True
        )

        # Should stop at 1.3.7
        assert result['target_version'] == '1.3.7'
        assert result['releases_applied'] == ['1.3.6', '1.3.7']
        assert result['final_version'] == '1.3.7'

    def test_to_release_applies_only_up_to_target(self, release_manager_with_options):
        """Test patches only applied up to target version."""
        release_mgr, mock_repo, _, _ = release_manager_with_options

        # Upgrade only to 1.3.6
        result = release_mgr.upgrade_production(
            to_version="1.3.6",
            skip_backup=True
        )

        # Should only have patches from 1.3.6
        assert result['patches_applied'] == {
            '1.3.6': ['456-user-auth', '789-security']
        }

        # 1.3.7 and 1.4.0 patches should NOT be applied
        calls = mock_repo.patch_manager.apply_patch_files.call_args_list
        patch_ids = [call[0][0] for call in calls]

        assert '999-bugfix' not in patch_ids  # From 1.3.7
        assert '111-feature' not in patch_ids  # From 1.4.0

    def test_to_release_invalid_version_raises(self, release_manager_with_options):
        """Test invalid to_version raises error."""
        release_mgr, mock_repo, _, _ = release_manager_with_options

        # Try to upgrade to non-existent version
        with pytest.raises(ReleaseManagerError, match="not in upgrade path"):
            release_mgr.upgrade_production(
                to_version="9.9.9",
                skip_backup=True
            )

    def test_to_release_with_dry_run(self, release_manager_with_options):
        """Test to_version works with dry_run."""
        release_mgr, mock_repo, _, _ = release_manager_with_options

        # Dry run to specific version
        result = release_mgr.upgrade_production(
            to_version="1.3.7",
            dry_run=True
        )

        # Should show simulation only up to target
        assert result['status'] == 'dry_run'
        assert result['target_version'] == '1.3.7'
        assert result['releases_would_apply'] == ['1.3.6', '1.3.7']


# ============================================================================
# FORCE BACKUP TESTS
# ============================================================================

class TestUpgradeProductionForceBackup:
    """Test force_backup option."""

    def test_force_overwrites_existing_backup(self, release_manager_with_options):
        """Test force=True overwrites existing backup."""
        release_mgr, mock_repo, _, backups_dir = release_manager_with_options

        # Create existing backup
        existing_backup = backups_dir / "1.3.5.sql"
        existing_backup.write_text("OLD BACKUP CONTENT")

        # Execute with force
        result = release_mgr.upgrade_production(force_backup=True)

        # Should succeed without prompt
        assert result['status'] == 'success'
        assert result['backup_created'] == existing_backup

    def test_without_force_prompts_user(self, release_manager_with_options):
        """Test without force prompts user when backup exists."""
        release_mgr, mock_repo, _, backups_dir = release_manager_with_options

        # Create existing backup
        existing_backup = backups_dir / "1.3.5.sql"
        existing_backup.write_text("OLD BACKUP")

        # Mock user declining
        with patch('builtins.input', return_value='n'):
            with pytest.raises(ReleaseManagerError, match="already exists"):
                release_mgr.upgrade_production(force_backup=False)

    def test_user_accepts_overwrite(self, release_manager_with_options):
        """Test user can accept overwrite when prompted."""
        release_mgr, mock_repo, _, backups_dir = release_manager_with_options

        # Create existing backup
        existing_backup = backups_dir / "1.3.5.sql"
        existing_backup.write_text("OLD BACKUP")

        # Mock user accepting
        with patch('builtins.input', return_value='y'):
            result = release_mgr.upgrade_production(force_backup=False)

            # Should succeed
            assert result['status'] == 'success'


# ============================================================================
# SKIP BACKUP TESTS
# ============================================================================

class TestUpgradeProductionSkipBackup:
    """Test skip_backup option."""

    def test_skip_backup_no_backup_created(self, release_manager_with_options):
        """Test skip_backup=True skips backup creation."""
        release_mgr, mock_repo, _, backups_dir = release_manager_with_options

        # Execute with skip_backup
        result = release_mgr.upgrade_production(skip_backup=True)

        # No backup should be created
        assert result['backup_created'] is None
        assert not (backups_dir / "1.3.5.sql").exists()

    def test_skip_backup_still_applies_patches(self, release_manager_with_options):
        """Test skip_backup doesn't affect patch application."""
        release_mgr, mock_repo, _, _ = release_manager_with_options

        # Execute with skip_backup
        result = release_mgr.upgrade_production(skip_backup=True)

        # Patches should still be applied
        assert result['releases_applied'] == ['1.3.6', '1.3.7', '1.4.0']
        assert mock_repo.patch_manager.apply_patch_files.call_count > 0


# ============================================================================
# COMBINED OPTIONS TESTS
# ============================================================================

class TestUpgradeProductionCombinedOptions:
    """Test combinations of options."""

    def test_to_release_with_force_backup(self, release_manager_with_options):
        """Test to_version combined with force_backup."""
        release_mgr, mock_repo, _, backups_dir = release_manager_with_options

        # Create existing backup
        (backups_dir / "1.3.5.sql").write_text("OLD")

        # Execute with both options
        result = release_mgr.upgrade_production(
            to_version="1.3.7",
            force_backup=True
        )

        # Should work with both options
        assert result['target_version'] == '1.3.7'
        assert result['releases_applied'] == ['1.3.6', '1.3.7']
        assert result['backup_created'] is not None

    def test_dry_run_ignores_backup_options(self, release_manager_with_options):
        """Test dry_run ignores backup-related options."""
        release_mgr, mock_repo, _, _ = release_manager_with_options

        # Execute with dry_run + force + skip (conflicting)
        result = release_mgr.upgrade_production(
            dry_run=True,
            force_backup=True,
            skip_backup=True
        )

        # Should be dry run (ignores backup options)
        assert result['status'] == 'dry_run'
        assert 'backup_would_be_created' in result
