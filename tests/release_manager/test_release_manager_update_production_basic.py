"""
Tests for ReleaseManager.update_production() - Basic functionality.

Focused on testing:
- Fetch tags from origin
- Read current version from database (hop_last_release)
- List available tags
- No updates scenario
- Error handling
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, call
from git.exc import GitCommandError

from half_orm_dev.release_manager import ReleaseManager, ReleaseManagerError


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def release_manager_for_update(tmp_path):
    """
    Setup ReleaseManager for update_production() tests.
    
    Provides:
    - Temporary releases directory
    - Mocked Repo with database
    - Mocked HGit for tag operations
    - Default current production version: 1.3.5
    """
    # Create releases directory structure
    releases_dir = tmp_path / "releases"
    releases_dir.mkdir()
    
    # Mock Repo
    mock_repo = Mock()
    mock_repo.name = "test_repo"
    mock_repo.base_dir = tmp_path
    
    # Mock Database with last_release_s property
    mock_database = Mock()
    mock_database.last_release_s = "1.3.5"  # Current production version
    mock_repo.database = mock_database
    
    # Mock HGit for tag operations
    mock_hgit = Mock()
    mock_hgit.fetch_tags = Mock()
    mock_repo.hgit = mock_hgit
    
    # Create ReleaseManager
    release_mgr = ReleaseManager(mock_repo)
    
    return release_mgr, mock_repo, mock_hgit, releases_dir


# ============================================================================
# BASIC FUNCTIONALITY TESTS
# ============================================================================

class TestUpdateProductionBasic:
    """Test basic functionality of update_production()."""
    
    @pytest.mark.skip(reason="Fetch tags logic not implemented yet")
    def test_fetches_tags_from_origin(self, release_manager_for_update):
        """Test that update_production() fetches tags from origin."""
        release_mgr, mock_repo, mock_hgit, _ = release_manager_for_update
        
        # Mock available tags (empty for this test)
        mock_hgit._HGit__git_repo = Mock()
        mock_hgit._HGit__git_repo.tags = []
        
        # Call update_production
        result = release_mgr.update_production()
        
        # Should have called fetch_tags
        mock_hgit.fetch_tags.assert_called_once()
    
    @pytest.mark.skip(reason="Database version reading not implemented yet")
    def test_reads_current_version_from_database(self, release_manager_for_update):
        """Test reads production version from database.last_release_s."""
        release_mgr, mock_repo, mock_hgit, _ = release_manager_for_update
        
        # Mock tags (empty)
        mock_hgit._HGit__git_repo = Mock()
        mock_hgit._HGit__git_repo.tags = []
        
        # Call update_production
        result = release_mgr.update_production()
        
        # Should have read version from database
        assert result['current_version'] == "1.3.5"
        
        # Verify database.last_release_s was accessed
        assert mock_repo.database.last_release_s == "1.3.5"
    
    @pytest.mark.skip(reason="Tag listing not implemented yet")
    def test_lists_available_production_tags(self, release_manager_for_update):
        """Test lists only production tags (no RC by default)."""
        release_mgr, mock_repo, mock_hgit, _ = release_manager_for_update
        
        # Mock available tags (mix of production and RC)
        mock_tag_v136 = Mock()
        mock_tag_v136.name = "v1.3.6"
        mock_tag_v136_rc1 = Mock()
        mock_tag_v136_rc1.name = "v1.3.6-rc1"
        mock_tag_v140 = Mock()
        mock_tag_v140.name = "v1.4.0"
        
        mock_hgit._HGit__git_repo = Mock()
        mock_hgit._HGit__git_repo.tags = [mock_tag_v136_rc1, mock_tag_v136, mock_tag_v140]
        
        # Call update_production (allow_rc=False by default)
        result = release_mgr.update_production()
        
        # Should only include production tags (not RC)
        versions = [rel['version'] for rel in result['available_releases']]
        assert "1.3.6" in versions
        assert "1.4.0" in versions
        assert "1.3.6-rc1" not in versions
    
    @pytest.mark.skip(reason="No updates scenario not implemented yet")
    def test_no_updates_available(self, release_manager_for_update):
        """Test when no new releases available."""
        release_mgr, mock_repo, mock_hgit, _ = release_manager_for_update
        
        # Current version is 1.3.5
        # Only tags <= 1.3.5 available
        mock_tag_v135 = Mock()
        mock_tag_v135.name = "v1.3.5"
        mock_tag_v134 = Mock()
        mock_tag_v134.name = "v1.3.4"
        
        mock_hgit._HGit__git_repo = Mock()
        mock_hgit._HGit__git_repo.tags = [mock_tag_v135, mock_tag_v134]
        
        # Call update_production
        result = release_mgr.update_production()
        
        # Should indicate no updates
        assert result['has_updates'] is False
        assert result['available_releases'] == []
        assert result['upgrade_path'] == []
    
    @pytest.mark.skip(reason="RC filtering not implemented yet")
    def test_includes_rc_when_allow_rc_true(self, release_manager_for_update):
        """Test RC tags included when allow_rc=True."""
        release_mgr, mock_repo, mock_hgit, _ = release_manager_for_update
        
        # Mock tags with RC
        mock_tag_v136_rc1 = Mock()
        mock_tag_v136_rc1.name = "v1.3.6-rc1"
        mock_tag_v136 = Mock()
        mock_tag_v136.name = "v1.3.6"
        
        mock_hgit._HGit__git_repo = Mock()
        mock_hgit._HGit__git_repo.tags = [mock_tag_v136_rc1, mock_tag_v136]
        
        # Call with allow_rc=True
        result = release_mgr.update_production(allow_rc=True)
        
        # Should include RC tags
        versions = [rel['version'] for rel in result['available_releases']]
        assert "1.3.6-rc1" in versions
        assert "1.3.6" in versions


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

class TestUpdateProductionErrors:
    """Test error handling in update_production()."""
    
    @pytest.mark.skip(reason="Error handling not implemented yet")
    def test_raises_error_on_fetch_failure(self, release_manager_for_update):
        """Test raises ReleaseManagerError when fetch fails."""
        release_mgr, mock_repo, mock_hgit, _ = release_manager_for_update
        
        # Mock fetch_tags to raise error
        mock_hgit.fetch_tags.side_effect = GitCommandError(
            "git fetch --tags", 1, stderr="Network error"
        )
        
        # Should raise ReleaseManagerError
        with pytest.raises(ReleaseManagerError, match="Failed to fetch tags|Network error"):
            release_mgr.update_production()
    
    @pytest.mark.skip(reason="Error handling not implemented yet")
    def test_raises_error_on_database_version_unavailable(self, release_manager_for_update):
        """Test raises error when cannot read database version."""
        release_mgr, mock_repo, mock_hgit, _ = release_manager_for_update
        
        # Mock database.last_release_s to raise error
        type(mock_repo.database).last_release_s = property(
            lambda self: (_ for _ in ()).throw(Exception("Database connection lost"))
        )
        
        # Should raise ReleaseManagerError
        with pytest.raises(ReleaseManagerError, match="Cannot read.*version|Database"):
            release_mgr.update_production()
    
    @pytest.mark.skip(reason="Result structure validation not implemented yet")
    def test_returns_correct_structure(self, release_manager_for_update):
        """Test returns dict with correct structure."""
        release_mgr, mock_repo, mock_hgit, _ = release_manager_for_update
        
        # Mock single available tag
        mock_tag = Mock()
        mock_tag.name = "v1.3.6"
        mock_hgit._HGit__git_repo = Mock()
        mock_hgit._HGit__git_repo.tags = [mock_tag]
        
        # Call update_production
        result = release_mgr.update_production()
        
        # Verify structure
        assert 'current_version' in result
        assert 'available_releases' in result
        assert 'upgrade_path' in result
        assert 'has_updates' in result
        
        # Verify types
        assert isinstance(result['current_version'], str)
        assert isinstance(result['available_releases'], list)
        assert isinstance(result['upgrade_path'], list)
        assert isinstance(result['has_updates'], bool)
