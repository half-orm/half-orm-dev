"""
Tests for ReleaseManager.upgrade_production() - Basic scenarios.

Focused on testing:
- Backup creation
- Production environment validation
- Single version upgrade
- Already up-to-date scenario
- Basic error handling
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, call, patch, ANY
from half_orm_dev.release_manager import ReleaseManager, ReleaseManagerError


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def release_manager_for_upgrade(tmp_path):
    """
    Setup ReleaseManager with production upgrade configuration.

    Provides:
    - Releases directory with production release files
    - Backups directory for backup creation
    - Mocked Repo with database at version 1.3.5
    - Mocked HGit on ho-prod branch
    """
    # Create directories
    releases_dir = tmp_path / "releases"
    releases_dir.mkdir()

    backups_dir = tmp_path / "backups"
    backups_dir.mkdir()

    # Create release files
    (releases_dir / "1.3.6.txt").write_text("456-user-auth\n789-security\n")
    (releases_dir / "1.3.7.txt").write_text("999-bugfix\n")

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

    # Mock tags for releases - IMPORTANT: tag.name doit être string
    mock_tag_136 = Mock()
    mock_tag_136.name = "v1.3.6"  # String, pas Mock
    mock_tag_137 = Mock()
    mock_tag_137.name = "v1.3.7"  # String, pas Mock

    mock_hgit._HGit__git_repo = Mock()
    mock_hgit._HGit__git_repo.tags = [mock_tag_136, mock_tag_137]

    mock_repo.hgit = mock_hgit

    # Mock PatchManager
    mock_patch_manager = Mock()
    mock_patch_manager.apply_patch_files = Mock()
    mock_repo.patch_manager = mock_patch_manager

    # Create ReleaseManager
    release_mgr = ReleaseManager(mock_repo)

    return release_mgr, mock_repo, tmp_path, releases_dir, backups_dir


# ============================================================================
# BACKUP CREATION TESTS
# ============================================================================

class TestUpgradeProductionBackup:
    """Test backup creation during upgrade."""

    def test_creates_backup_before_upgrade(self, release_manager_for_upgrade):
        """Test backup is created before any changes."""
        release_mgr, mock_repo, tmp_path, _, backups_dir = release_manager_for_upgrade

        # Execute upgrade
        result = release_mgr.upgrade_production()

        # Backup path should be returned
        assert result['backup_created'] is not None
        assert result['backup_created'].name == "1.3.5.sql"

        # Note: actual file won't exist because pg_dump is mocked
        # But pg_dump should be called with correct path
        mock_repo.database.execute_pg_command.assert_any_call(
            'pg_dump',
            '-f', str(backups_dir / "1.3.5.sql")
        )

    def test_backup_created_before_validation(self, release_manager_for_upgrade):
        """Test backup happens even if validation would fail later."""
        release_mgr, mock_repo, tmp_path, _, backups_dir = release_manager_for_upgrade

        # Make patch application fail AFTER backup
        mock_repo.patch_manager.apply_patch_files.side_effect = Exception("Patch failed")

        # Execute upgrade (will fail on patch application)
        with pytest.raises(ReleaseManagerError):
            release_mgr.upgrade_production()

        # pg_dump should still have been called (backup created first)
        pg_dump_calls = [
            call for call in mock_repo.database.execute_pg_command.call_args_list
            if 'pg_dump' in str(call)
        ]
        assert len(pg_dump_calls) > 0

    def test_backup_with_force_overwrites_existing(self, release_manager_for_upgrade):
        """Test force=True overwrites existing backup without prompt."""
        release_mgr, mock_repo, tmp_path, _, backups_dir = release_manager_for_upgrade

        # Create existing backup
        existing_backup = backups_dir / "1.3.5.sql"
        existing_backup.write_text("OLD BACKUP")

        # Execute upgrade with force
        result = release_mgr.upgrade_production(force_backup=True)

        # Should overwrite without error
        assert result['backup_created'] == existing_backup

    def test_backup_prompts_if_exists_without_force(self, release_manager_for_upgrade):
        """Test prompts user if backup exists and force=False."""
        release_mgr, mock_repo, tmp_path, _, backups_dir = release_manager_for_upgrade

        # Create existing backup
        existing_backup = backups_dir / "1.3.5.sql"
        existing_backup.write_text("OLD BACKUP")

        # Mock user input decline
        with patch('builtins.input', return_value='n'):
            with pytest.raises(ReleaseManagerError, match="already exists"):
                release_mgr.upgrade_production(force_backup=False)

    def test_skip_backup_option(self, release_manager_for_upgrade):
        """Test skip_backup=True skips backup creation."""
        release_mgr, mock_repo, tmp_path, _, backups_dir = release_manager_for_upgrade

        # Execute upgrade with skip_backup
        result = release_mgr.upgrade_production(skip_backup=True)

        # No backup should be created
        assert result['backup_created'] is None

        # pg_dump should not be called
        pg_dump_calls = [
            call for call in mock_repo.database.execute_pg_command.call_args_list
            if 'pg_dump' in str(call)
        ]
        assert len(pg_dump_calls) == 0


# ============================================================================
# VALIDATION TESTS
# ============================================================================

class TestUpgradeProductionValidation:
    """Test production environment validation."""

    def test_validates_ho_prod_branch(self, release_manager_for_upgrade):
        """Test validates current branch is ho-prod."""
        release_mgr, mock_repo, _, _, _ = release_manager_for_upgrade

        # Change to wrong branch
        mock_repo.hgit.branch = "ho-patch/456-test"

        # Should fail validation
        with pytest.raises(ReleaseManagerError, match="Must be on ho-prod"):
            release_mgr.upgrade_production(skip_backup=True)

    def test_validates_clean_repository(self, release_manager_for_upgrade):
        """Test validates repository has no uncommitted changes."""
        release_mgr, mock_repo, _, _, _ = release_manager_for_upgrade

        # Make repository dirty
        mock_repo.hgit.repos_is_clean.return_value = False

        # Should fail validation
        with pytest.raises(ReleaseManagerError, match="uncommitted changes"):
            release_mgr.upgrade_production(skip_backup=True)


# ============================================================================
# SINGLE VERSION UPGRADE TESTS
# ============================================================================

class TestUpgradeProductionSingleVersion:
    """Test single version upgrade."""

    def test_upgrades_single_version(self, release_manager_for_upgrade):
        """Test upgrades from 1.3.5 to 1.3.6."""
        release_mgr, mock_repo, tmp_path, _, _ = release_manager_for_upgrade

        # Remove 1.3.7 to have only one upgrade
        (tmp_path / "releases" / "1.3.7.txt").unlink()

        # Update tags to only have v1.3.6
        mock_tag = Mock()
        mock_tag.name = "v1.3.6"  # String, pas Mock()
        mock_repo.hgit._HGit__git_repo.tags = [mock_tag]

        # Execute upgrade
        result = release_mgr.upgrade_production(skip_backup=True)

        # Should upgrade to 1.3.6
        assert result['status'] == 'success'
        assert result['current_version'] == '1.3.5'
        assert result['releases_applied'] == ['1.3.6']
        assert result['final_version'] == '1.3.6'

    def test_applies_patches_in_order(self, release_manager_for_upgrade):
        """Test patches applied in correct order."""
        release_mgr, mock_repo, tmp_path, _, _ = release_manager_for_upgrade

        # Single version
        (tmp_path / "releases" / "1.3.7.txt").unlink()

        mock_tag = Mock()
        mock_tag.name = "v1.3.6"
        mock_repo.hgit._HGit__git_repo.tags = [mock_tag]

        # Execute upgrade
        result = release_mgr.upgrade_production(skip_backup=True)

        # Should apply patches in order
        assert result['patches_applied'] == {
            '1.3.6': ['456-user-auth', '789-security']
        }

        # Verify apply_patch_files called for each patch
        assert mock_repo.patch_manager.apply_patch_files.call_count == 2
        calls = mock_repo.patch_manager.apply_patch_files.call_args_list
        assert calls[0][0][0] == '456-user-auth'
        assert calls[1][0][0] == '789-security'

    def test_updates_database_version(self, release_manager_for_upgrade):
        """Test database version updated after release."""
        release_mgr, mock_repo, tmp_path, _, _ = release_manager_for_upgrade

        # Single version
        (tmp_path / "releases" / "1.3.7.txt").unlink()

        mock_tag = Mock()
        mock_tag.name = "v1.3.6"
        mock_repo.hgit._HGit__git_repo.tags = [mock_tag]

        # Execute upgrade
        release_mgr.upgrade_production(skip_backup=True)

        # Should update version to 1.3.6
        mock_repo.database.register_release.assert_called_once_with(1, 3, 6)


# ============================================================================
# UP-TO-DATE SCENARIO TESTS
# ============================================================================

class TestUpgradeProductionUpToDate:
    """Test already up-to-date scenario."""

    def test_already_up_to_date(self, release_manager_for_upgrade):
        """Test when production is already at latest version."""
        release_mgr, mock_repo, _, _, _ = release_manager_for_upgrade

        # Set database to latest version
        mock_repo.database.last_release_s = "1.3.7"

        # Execute upgrade
        result = release_mgr.upgrade_production(skip_backup=True)

        # Should report up to date
        assert result['status'] == 'success'
        assert result['releases_applied'] == []
        assert 'already at latest' in result['message'].lower()

    def test_up_to_date_still_creates_backup(self, release_manager_for_upgrade):
        """Test backup created even when up-to-date (unless skipped)."""
        release_mgr, mock_repo, _, _, backups_dir = release_manager_for_upgrade

        # Set database to latest version
        mock_repo.database.last_release_s = "1.3.7"

        # Execute upgrade (with backup)
        result = release_mgr.upgrade_production()

        # Backup should still be created
        assert result['backup_created'] is not None
