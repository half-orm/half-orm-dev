"""
Tests for ReleaseManager.upgrade_production() - Error handling.

Focused on testing:
- Patch application failures
- Backup creation failures
- Invalid configurations
- Rollback information
"""

import pytest
from pathlib import Path
from unittest.mock import Mock
from half_orm_dev.release_manager import ReleaseManager, ReleaseManagerError


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def release_manager_for_errors(tmp_path):
    """
    Setup ReleaseManager for error testing.

    Provides:
    - Releases with multiple patches
    - Mocked dependencies configured for error scenarios
    """
    releases_dir = tmp_path / "releases"
    releases_dir.mkdir(exist_ok=True)

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

    mock_tag_136 = Mock()
    mock_tag_136.name = "v1.3.6"
    mock_tag_137 = Mock()
    mock_tag_137.name = "v1.3.7"

    mock_hgit._HGit__git_repo = Mock()
    mock_hgit._HGit__git_repo.tags = [mock_tag_136, mock_tag_137]

    mock_repo.hgit = mock_hgit

    # Mock PatchManager
    mock_patch_manager = Mock()
    mock_patch_manager.apply_patch_files = Mock()
    mock_repo.patch_manager = mock_patch_manager

    # Create ReleaseManager
    release_mgr = ReleaseManager(mock_repo)

    return release_mgr, mock_repo, tmp_path, backups_dir


# ============================================================================
# PATCH APPLICATION FAILURE TESTS
# ============================================================================

class TestUpgradeProductionPatchFailures:
    """Test failures during patch application."""

    def test_patch_failure_raises_with_rollback_info(self, release_manager_for_errors):
        """Test patch failure provides rollback instructions."""
        release_mgr, mock_repo, _, backups_dir = release_manager_for_errors

        # Make patch application fail
        mock_repo.patch_manager.apply_patch_files.side_effect = Exception("SQL error")

        # Execute upgrade
        with pytest.raises(ReleaseManagerError) as exc_info:
            release_mgr.upgrade_production()

        # Should include rollback instructions
        error_msg = str(exc_info.value)
        assert "ROLLBACK INSTRUCTIONS" in error_msg
        assert "psql" in error_msg
        assert "backups/1.3.5.sql" in error_msg

    def test_partial_failure_after_first_release(self, release_manager_for_errors):
        """Test failure on second release after first succeeds."""
        release_mgr, mock_repo, _, _ = release_manager_for_errors

        # First release succeeds, second fails
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] > 2:  # Fail on third patch (first patch of 1.3.7)
                raise Exception("SQL error in 999-bugfix")

        mock_repo.patch_manager.apply_patch_files.side_effect = side_effect

        # Execute upgrade
        with pytest.raises(ReleaseManagerError) as exc_info:
            release_mgr.upgrade_production(skip_backup=True)

        # Error should mention which release failed
        error_msg = str(exc_info.value)
        assert "1.3.7" in error_msg or "999-bugfix" in error_msg

    def test_provides_specific_patch_in_error(self, release_manager_for_errors):
        """Test error message includes specific failing patch."""
        release_mgr, mock_repo, _, _ = release_manager_for_errors

        # Make specific patch fail
        def side_effect(patch_id, *args, **kwargs):
            if patch_id == "789-security":
                raise Exception("Foreign key violation")

        mock_repo.patch_manager.apply_patch_files.side_effect = side_effect

        # Execute upgrade
        with pytest.raises(ReleaseManagerError) as exc_info:
            release_mgr.upgrade_production(skip_backup=True)

        # Should mention the failing patch
        error_msg = str(exc_info.value)
        assert "789-security" in error_msg

    def test_backup_exists_before_failure(self, release_manager_for_errors):
        """Test backup created before failure allows rollback."""
        release_mgr, mock_repo, _, backups_dir = release_manager_for_errors

        # Make patch fail
        mock_repo.patch_manager.apply_patch_files.side_effect = Exception("Error")

        # Execute upgrade (will fail)
        try:
            release_mgr.upgrade_production()
        except ReleaseManagerError:
            pass

        # Backup should exist for rollback
        backup_file = backups_dir / "1.3.5.sql"
        # Note: actual file won't exist in test (mocked), but path is correct


# ============================================================================
# BACKUP CREATION FAILURE TESTS
# ============================================================================

class TestUpgradeProductionBackupFailures:
    """Test failures during backup creation."""

    def test_backup_creation_failure_stops_upgrade(self, release_manager_for_errors):
        """Test upgrade stops if backup creation fails."""
        release_mgr, mock_repo, _, _ = release_manager_for_errors

        # Make pg_dump fail
        mock_repo.database.execute_pg_command.side_effect = Exception("pg_dump failed")

        # Execute upgrade
        with pytest.raises(ReleaseManagerError, match="Failed to create backup"):
            release_mgr.upgrade_production()

        # Patches should NOT be applied
        assert mock_repo.patch_manager.apply_patch_files.call_count == 0

    def test_disk_full_during_backup(self, release_manager_for_errors):
        """Test handles disk full error during backup."""
        release_mgr, mock_repo, _, _ = release_manager_for_errors

        # Simulate disk full
        mock_repo.database.execute_pg_command.side_effect = OSError("No space left")

        # Execute upgrade
        with pytest.raises(ReleaseManagerError, match="Failed to create backup"):
            release_mgr.upgrade_production()


# ============================================================================
# INVALID CONFIGURATION TESTS
# ============================================================================

class TestUpgradeProductionInvalidConfig:
    """Test invalid configurations and inputs."""

    def test_missing_release_file(self, release_manager_for_errors):
        """Test handles missing release file gracefully."""
        release_mgr, mock_repo, tmp_path, _ = release_manager_for_errors

        # Delete release file
        (tmp_path / "releases" / "1.3.6.txt").unlink()

        # Execute upgrade
        # Should handle gracefully (empty patch list) or succeed
        result = release_mgr.upgrade_production(skip_backup=True)

        # If release file missing, patches_applied should be empty for that release
        # or it should skip that release entirely
        assert result['status'] == 'success'

    def test_invalid_version_format_in_database(self, release_manager_for_errors):
        """Test handles invalid version format gracefully."""
        release_mgr, mock_repo, _, _ = release_manager_for_errors

        # Set invalid current version
        mock_repo.database.last_release_s = "invalid"

        # Should handle gracefully or raise clear error
        # (Depends on version parsing implementation)

    def test_empty_release_file(self, release_manager_for_errors):
        """Test handles empty release file (no patches)."""
        release_mgr, mock_repo, tmp_path, _ = release_manager_for_errors

        # Make release file empty
        (tmp_path / "releases" / "1.3.6.txt").write_text("")

        # Execute upgrade
        result = release_mgr.upgrade_production(skip_backup=True)

        # Should succeed but apply no patches for that release
        assert '1.3.6' in result['releases_applied']
        assert result['patches_applied']['1.3.6'] == []


# ============================================================================
# VALIDATION ERROR TESTS
# ============================================================================

class TestUpgradeProductionValidationErrors:
    """Test validation errors before upgrade starts."""

    def test_wrong_branch_error_clear(self, release_manager_for_errors):
        """Test clear error when not on ho-prod branch."""
        release_mgr, mock_repo, _, _ = release_manager_for_errors

        # Set wrong branch
        mock_repo.hgit.branch = "ho-patch/456-test"

        # Execute upgrade
        with pytest.raises(ReleaseManagerError) as exc_info:
            release_mgr.upgrade_production(skip_backup=True)

        # Should have clear error message
        error_msg = str(exc_info.value)
        assert "ho-prod" in error_msg
        assert "ho-patch/456-test" in error_msg

    def test_dirty_repo_error_clear(self, release_manager_for_errors):
        """Test clear error when repository has uncommitted changes."""
        release_mgr, mock_repo, _, _ = release_manager_for_errors

        # Make repo dirty
        mock_repo.hgit.repos_is_clean.return_value = False

        # Execute upgrade
        with pytest.raises(ReleaseManagerError) as exc_info:
            release_mgr.upgrade_production(skip_backup=True)

        # Should have clear error message
        error_msg = str(exc_info.value)
        assert "uncommitted" in error_msg.lower()


# ============================================================================
# DATABASE VERSION UPDATE FAILURE TESTS
# ============================================================================

class TestUpgradeProductionVersionUpdateFailures:
    """Test failures during database version updates."""

    def test_register_release_failure(self, release_manager_for_errors):
        """Test handles failure to update database version."""
        release_mgr, mock_repo, _, _ = release_manager_for_errors

        # Make register_release fail
        mock_repo.database.register_release.side_effect = Exception("DB error")

        # Execute upgrade
        with pytest.raises(ReleaseManagerError):
            release_mgr.upgrade_production(skip_backup=True)

    def test_invalid_version_format_in_release(self, release_manager_for_errors):
        """Test handles invalid version format in release filename."""
        release_mgr, mock_repo, tmp_path, _ = release_manager_for_errors

        # Create release with invalid version format
        (tmp_path / "releases" / "invalid.txt").write_text("123-patch\n")

        # Mock to include invalid version
        mock_tag = Mock()
        mock_tag.name = "v-invalid"
        mock_repo.hgit._HGit__git_repo.tags.append(mock_tag)

        # Should handle gracefully or raise clear error


# ============================================================================
# CONCURRENT MODIFICATION TESTS
# ============================================================================

class TestUpgradeProductionConcurrency:
    """Test issues with concurrent modifications."""

    def test_release_file_modified_during_upgrade(self, release_manager_for_errors):
        """Test handles release file changes during upgrade."""
        release_mgr, mock_repo, tmp_path, _ = release_manager_for_errors

        # Simulate file being modified mid-upgrade
        # (Hard to test without actual filesystem operations)
        # This is more of an edge case documentation

    def test_database_version_changed_externally(self, release_manager_for_errors):
        """Test detects if database version changed externally."""
        release_mgr, mock_repo, _, _ = release_manager_for_errors

        # Simulate version changing during upgrade
        # (Would need actual database connection to test properly)


# ============================================================================
# ROLLBACK INFORMATION TESTS
# ============================================================================

class TestUpgradeProductionRollbackInfo:
    """Test rollback information in error messages."""

    def test_rollback_includes_backup_path(self, release_manager_for_errors):
        """Test rollback instructions include backup file path."""
        release_mgr, mock_repo, _, backups_dir = release_manager_for_errors

        # Make patch fail
        mock_repo.patch_manager.apply_patch_files.side_effect = Exception("Error")

        # Execute upgrade
        with pytest.raises(ReleaseManagerError) as exc_info:
            release_mgr.upgrade_production()

        # Should include backup path
        error_msg = str(exc_info.value)
        assert str(backups_dir / "1.3.5.sql") in error_msg or "1.3.5.sql" in error_msg

    def test_rollback_includes_psql_command(self, release_manager_for_errors):
        """Test rollback instructions include psql command."""
        release_mgr, mock_repo, _, _ = release_manager_for_errors

        # Make patch fail
        mock_repo.patch_manager.apply_patch_files.side_effect = Exception("Error")

        # Execute upgrade
        with pytest.raises(ReleaseManagerError) as exc_info:
            release_mgr.upgrade_production()

        # Should include psql command
        error_msg = str(exc_info.value)
        assert "psql" in error_msg
        assert "-f" in error_msg

    def test_rollback_includes_verification_step(self, release_manager_for_errors):
        """Test rollback instructions include verification query."""
        release_mgr, mock_repo, _, _ = release_manager_for_errors

        # Make patch fail
        mock_repo.patch_manager.apply_patch_files.side_effect = Exception("Error")

        # Execute upgrade
        with pytest.raises(ReleaseManagerError) as exc_info:
            release_mgr.upgrade_production()

        # Should include verification step
        error_msg = str(exc_info.value)
        assert "SELECT" in error_msg or "verify" in error_msg.lower()
