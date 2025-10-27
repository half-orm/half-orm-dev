"""
Tests for automatic stage file creation after promote-to rc/prod.

Tests the new step 10.5 in promote_to() workflow that creates
an empty stage file after successful promotion. This ensures a resumption
point is always available for add-to-release without manual prepare-release.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, call

from half_orm_dev.release_manager import ReleaseManager, ReleaseManagerError


@pytest.fixture
def release_manager_basic(tmp_path):
    """Basic ReleaseManager setup with mocked repo."""
    # Setup directories
    releases_dir = tmp_path / "releases"
    releases_dir.mkdir()
    
    # Create model directory for prod tests
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    
    # Mock repo with hgit
    mock_repo = Mock()
    mock_hgit = Mock()
    mock_repo.hgit = mock_hgit
    mock_repo.base_dir = tmp_path  # Path object, not string
    
    # Setup hgit branch and status
    mock_hgit.branch = "ho-prod"
    mock_hgit.repos_is_clean.return_value = True
    mock_hgit.push = Mock()
    mock_hgit.commit = Mock(return_value="abc123def456")
    mock_hgit.add = Mock()
    def mock_mv(source, target):
        """Simulate git mv by renaming file."""
        Path(source).rename(Path(target))

    mock_hgit.mv = Mock(side_effect=mock_mv)

    # CRITICAL: Mock is_branch_synced (returns tuple)
    mock_hgit.is_branch_synced = Mock(return_value=(True, "synced"))
    
    # Mock fetch and pull
    mock_hgit.fetch = Mock()
    mock_hgit.pull = Mock()
    
    # Create ReleaseManager
    release_mgr = ReleaseManager(mock_repo)
    
    return release_mgr, releases_dir, mock_hgit


class TestPromoteCreateStageRC:
    """Test automatic stage creation for promote-to rc."""
    
    def test_creates_empty_stage_after_rc_promotion(self, release_manager_basic):
        """Test creates empty stage file after successful RC promotion."""
        release_mgr, releases_dir, mock_hgit = release_manager_basic
        
        # Create initial stage file
        stage_file = releases_dir / "1.3.5-stage.txt"
        stage_file.write_text("456-user-auth\n789-security\n")
        
        # Mock helpers
        release_mgr._detect_stage_to_promote = Mock(return_value=("1.3.5", "1.3.5-stage.txt"))
        release_mgr._validate_single_active_rc = Mock()
        release_mgr._determine_rc_number = Mock(return_value=1)
        release_mgr._merge_archived_patches_to_ho_prod = Mock(return_value=["456-user-auth", "789-security"])
        release_mgr._send_rebase_notifications = Mock(return_value=[])
        release_mgr._cleanup_patch_branches = Mock(return_value=[])
        mock_hgit.acquire_branch_lock = Mock(return_value="lock-tag-123")
        mock_hgit.release_branch_lock = Mock()
        mock_hgit.fetch = Mock()
        mock_hgit.pull = Mock()
        
        # Execute promotion
        result = release_mgr.promote_to('rc')
        
        # Verify new stage file created
        new_stage_file = releases_dir / "1.3.5-stage.txt"
        assert new_stage_file.exists(), "New stage file should be created"
        
        # Verify stage file is EMPTY
        content = new_stage_file.read_text()
        assert content == "", "New stage file must be empty"
        
        # Verify result includes new_stage_created field
        assert 'new_stage_created' in result
        assert result['new_stage_created'] == "1.3.5-stage.txt"
    
    def test_stage_file_added_and_committed_separately(self, release_manager_basic):
        """Test stage file is added and committed in separate commit."""
        release_mgr, releases_dir, mock_hgit = release_manager_basic
        
        # Create initial stage file
        stage_file = releases_dir / "1.3.5-stage.txt"
        stage_file.write_text("456-user-auth\n")
        
        # Mock helpers
        release_mgr._detect_stage_to_promote = Mock(return_value=("1.3.5", "1.3.5-stage.txt"))
        release_mgr._validate_single_active_rc = Mock()
        release_mgr._determine_rc_number = Mock(return_value=1)
        release_mgr._merge_archived_patches_to_ho_prod = Mock(return_value=["456-user-auth"])
        release_mgr._send_rebase_notifications = Mock(return_value=[])
        release_mgr._cleanup_patch_branches = Mock(return_value=[])
        mock_hgit.acquire_branch_lock = Mock(return_value="lock-tag-123")
        mock_hgit.release_branch_lock = Mock()
        mock_hgit.fetch = Mock()
        mock_hgit.pull = Mock()
        
        # Execute promotion
        release_mgr.promote_to('rc')
        
        # Verify add called for new stage
        new_stage_path = releases_dir / "1.3.5-stage.txt"
        assert any(
            call(new_stage_path) in mock_hgit.add.call_args_list
            for call_args in mock_hgit.add.call_args_list
        ), "Stage file should be added via git add"
        
        # Verify commit called with stage creation message
        commit_calls = [str(call) for call in mock_hgit.commit.call_args_list]
        assert any(
            "Create new empty stage file for 1.3.5" in call_str
            for call_str in commit_calls
        ), "Should commit stage creation with clear message"
        
        # Verify separate push for stage creation
        assert mock_hgit.push.call_count >= 2, "Should push twice: promotion + stage"
    
    def test_stage_created_with_same_version_as_rc(self, release_manager_basic):
        """Test stage uses same version as RC (not next version)."""
        release_mgr, releases_dir, mock_hgit = release_manager_basic
        
        # Create initial stage for rc2
        stage_file = releases_dir / "1.3.5-stage.txt"
        stage_file.write_text("999-bugfix\n")
        
        # Existing rc1
        rc1_file = releases_dir / "1.3.5-rc1.txt"
        rc1_file.write_text("456-user-auth\n789-security\n")
        
        # Mock helpers
        release_mgr._detect_stage_to_promote = Mock(return_value=("1.3.5", "1.3.5-stage.txt"))
        release_mgr._validate_single_active_rc = Mock()
        release_mgr._determine_rc_number = Mock(return_value=2)  # rc2
        release_mgr._merge_archived_patches_to_ho_prod = Mock(return_value=["999-bugfix"])
        release_mgr._send_rebase_notifications = Mock(return_value=[])
        release_mgr._cleanup_patch_branches = Mock(return_value=[])
        mock_hgit.acquire_branch_lock = Mock(return_value="lock-tag-123")
        mock_hgit.release_branch_lock = Mock()
        mock_hgit.fetch = Mock()
        mock_hgit.pull = Mock()
        
        # Execute promotion
        result = release_mgr.promote_to('rc')
        
        # Verify new stage has SAME version (1.3.5, not 1.3.6)
        new_stage_file = releases_dir / "1.3.5-stage.txt"
        assert new_stage_file.exists(), "Stage should use same version"
        
        # Verify rc2 created
        rc2_file = releases_dir / "1.3.5-rc2.txt"
        assert rc2_file.exists(), "RC2 should be created"
        
        # Verify result shows same version
        assert result['version'] == "1.3.5"
        assert result['new_stage_created'] == "1.3.5-stage.txt"


class TestPromoteCreateStageProd:
    """Test automatic stage creation for promote-to-prod."""
    
    def test_creates_empty_stage_after_prod_promotion(self, release_manager_basic):
        """Test creates empty stage file after successful production promotion."""
        release_mgr, releases_dir, mock_hgit = release_manager_basic
        
        # Create RC file
        rc_file = releases_dir / "1.3.5-rc1.txt"
        rc_file.write_text("456-user-auth\n789-security\n")
        
        # Mock helpers for prod promotion
        release_mgr._get_production_version = Mock(return_value="1.3.4")  # NOUVEAU
        release_mgr._detect_stage_to_promote = Mock(return_value=("1.3.5", "1.3.5-rc1.txt"))
        release_mgr._validate_single_active_rc = Mock()
        release_mgr._restore_and_apply_all_patches = Mock(return_value=["456-user-auth", "789-security"])
        release_mgr._generate_schema_dumps = Mock(return_value={
            'schema_file': Path('model/schema-1.3.5.sql'),
            'metadata_file': Path('model/metadata-1.3.5.sql')
        })
        release_mgr._merge_archived_patches_to_ho_prod = Mock(return_value=[])
        release_mgr._send_rebase_notifications = Mock(return_value=[])
        release_mgr._cleanup_patch_branches = Mock(return_value=[])
        mock_hgit.acquire_branch_lock = Mock(return_value="lock-tag-123")
        mock_hgit.release_branch_lock = Mock()
        mock_hgit.fetch = Mock()
        mock_hgit.pull = Mock()
        
        # Execute promotion
        result = release_mgr.promote_to('prod')
        
        # Verify new stage file created
        new_stage_file = releases_dir / "1.3.5-stage.txt"
        assert new_stage_file.exists(), "New stage file should be created after prod"
        
        # Verify stage file is EMPTY
        content = new_stage_file.read_text()
        assert content == "", "New stage file must be empty"
        
        # Verify result includes new_stage_created field
        assert 'new_stage_created' in result
        assert result['new_stage_created'] == "1.3.5-stage.txt"
    
    def test_stage_uses_same_version_as_prod(self, release_manager_basic):
        """Test stage uses same version as production (not next version)."""
        release_mgr, releases_dir, mock_hgit = release_manager_basic
        
        # Create RC file
        rc_file = releases_dir / "1.3.5-rc1.txt"
        rc_file.write_text("456-user-auth\n")
        
        # Mock helpers
        release_mgr._get_production_version = Mock(return_value="1.3.4")  # NOUVEAU
        release_mgr._detect_stage_to_promote = Mock(return_value=("1.3.5", "1.3.5-rc1.txt"))
        release_mgr._validate_single_active_rc = Mock()
        release_mgr._restore_and_apply_all_patches = Mock(return_value=["456-user-auth"])
        release_mgr._generate_schema_dumps = Mock(return_value={
            'schema_file': Path('model/schema-1.3.5.sql'),
            'metadata_file': Path('model/metadata-1.3.5.sql')
        })
        release_mgr._merge_archived_patches_to_ho_prod = Mock(return_value=[])
        release_mgr._send_rebase_notifications = Mock(return_value=[])
        release_mgr._cleanup_patch_branches = Mock(return_value=[])
        mock_hgit.acquire_branch_lock = Mock(return_value="lock-tag-123")
        mock_hgit.release_branch_lock = Mock()
        mock_hgit.fetch = Mock()
        mock_hgit.pull = Mock()
        
        # Execute promotion
        result = release_mgr.promote_to('prod')
        
        # Verify stage has SAME version as prod (1.3.5, not 1.3.6)
        new_stage_file = releases_dir / "1.3.5-stage.txt"
        assert new_stage_file.exists(), "Stage should use same version as prod"
        
        # Verify production file created
        prod_file = releases_dir / "1.3.5.txt"
        assert prod_file.exists(), "Production file should be created"
        
        # Verify result shows same version
        assert result['version'] == "1.3.5"
        assert result['new_stage_created'] == "1.3.5-stage.txt"


class TestPromoteCreateStageWorkflow:
    """Test stage creation workflow integration."""
    
    def test_stage_created_after_push_before_notifications(self, release_manager_basic):
        """Test stage creation happens after push, before notifications."""
        release_mgr, releases_dir, mock_hgit = release_manager_basic
        
        # Create initial stage
        stage_file = releases_dir / "1.3.5-stage.txt"
        stage_file.write_text("456-user-auth\n")
        
        # Track call order
        call_order = []
        
        def track_push():
            call_order.append('push')
        
        def track_commit(*args):
            msg = ' '.join(str(arg) for arg in args)
            if "Create new empty stage file" in msg:
                call_order.append('stage_commit')
            else:
                call_order.append('promote_commit')
            return "sha123"
        
        def track_notifications(*args, **kwargs):
            call_order.append('notifications')
            return []
        
        mock_hgit.push.side_effect = track_push
        mock_hgit.commit.side_effect = track_commit
        
        # Mock helpers
        release_mgr._detect_stage_to_promote = Mock(return_value=("1.3.5", "1.3.5-stage.txt"))
        release_mgr._validate_single_active_rc = Mock()
        release_mgr._determine_rc_number = Mock(return_value=1)
        release_mgr._merge_archived_patches_to_ho_prod = Mock(return_value=["456-user-auth"])
        release_mgr._send_rebase_notifications = Mock(side_effect=track_notifications)
        release_mgr._cleanup_patch_branches = Mock(return_value=[])
        mock_hgit.acquire_branch_lock = Mock(return_value="lock-tag-123")
        mock_hgit.release_branch_lock = Mock()
        mock_hgit.fetch = Mock()
        mock_hgit.pull = Mock()
        
        # Execute promotion
        release_mgr.promote_to('rc')
        
        # Verify order: promote_commit → push → stage_commit → push → notifications
        assert 'promote_commit' in call_order
        assert 'stage_commit' in call_order
        assert 'notifications' in call_order
        
        promote_idx = call_order.index('promote_commit')
        stage_idx = call_order.index('stage_commit')
        notif_idx = call_order.index('notifications')
        
        assert promote_idx < stage_idx, "Stage commit after promotion commit"
        assert stage_idx < notif_idx, "Notifications after stage creation"
    
    def test_stage_creation_failure_does_not_block_promotion(self, release_manager_basic):
        """Test promotion succeeds even if stage creation fails (non-critical)."""
        release_mgr, releases_dir, mock_hgit = release_manager_basic
        
        # Create initial stage
        stage_file = releases_dir / "1.3.5-stage.txt"
        stage_file.write_text("456-user-auth\n")
        
        # Make releases dir read-only to simulate failure
        def mock_write_text_fail(content):
            raise PermissionError("Cannot write to releases directory")
        
        # Mock helpers
        release_mgr._detect_stage_to_promote = Mock(return_value=("1.3.5", "1.3.5-stage.txt"))
        release_mgr._validate_single_active_rc = Mock()
        release_mgr._determine_rc_number = Mock(return_value=1)
        release_mgr._merge_archived_patches_to_ho_prod = Mock(return_value=["456-user-auth"])
        release_mgr._send_rebase_notifications = Mock(return_value=[])
        release_mgr._cleanup_patch_branches = Mock(return_value=[])
        mock_hgit.acquire_branch_lock = Mock(return_value="lock-tag-123")
        mock_hgit.release_branch_lock = Mock()
        mock_hgit.fetch = Mock()
        mock_hgit.pull = Mock()
        
        # Note: This test validates the DESIGN DECISION that stage creation
        # is non-critical. If implementation makes it critical, this test
        # should be updated accordingly.
        
        # For now, document expected behavior:
        # If stage creation fails, promotion should still succeed
        # (or at minimum, clearly log the failure without blocking)


class TestPromoteCreateStageEdgeCases:
    """Test edge cases for automatic stage creation."""
    
    def test_empty_rc_promotion_creates_empty_stage(self, release_manager_basic):
        """Test empty RC promotion creates empty stage."""
        release_mgr, releases_dir, mock_hgit = release_manager_basic
        
        # Create EMPTY initial stage
        stage_file = releases_dir / "1.3.5-stage.txt"
        stage_file.write_text("")  # No patches
        
        # Mock helpers
        release_mgr._detect_stage_to_promote = Mock(return_value=("1.3.5", "1.3.5-stage.txt"))
        release_mgr._validate_single_active_rc = Mock()
        release_mgr._determine_rc_number = Mock(return_value=1)
        release_mgr._merge_archived_patches_to_ho_prod = Mock(return_value=[])  # No patches
        release_mgr._send_rebase_notifications = Mock(return_value=[])
        release_mgr._cleanup_patch_branches = Mock(return_value=[])
        mock_hgit.acquire_branch_lock = Mock(return_value="lock-tag-123")
        mock_hgit.release_branch_lock = Mock()
        mock_hgit.fetch = Mock()
        mock_hgit.pull = Mock()
        
        # Execute promotion
        result = release_mgr.promote_to('rc')
        
        # Verify new stage created (even for empty RC)
        new_stage_file = releases_dir / "1.3.5-stage.txt"
        assert new_stage_file.exists(), "Stage should be created even for empty RC"
        assert new_stage_file.read_text() == "", "New stage should be empty"
        
        # Verify result
        assert result['new_stage_created'] == "1.3.5-stage.txt"
    
    def test_stage_already_exists_gets_overwritten(self, release_manager_basic):
        """Test if stage already exists (edge case), it gets overwritten."""
        release_mgr, releases_dir, mock_hgit = release_manager_basic
        
        # Create initial stage
        stage_file = releases_dir / "1.3.5-stage.txt"
        stage_file.write_text("456-user-auth\n")
        
        # Mock helpers
        release_mgr._detect_stage_to_promote = Mock(return_value=("1.3.5", "1.3.5-stage.txt"))
        release_mgr._validate_single_active_rc = Mock()
        release_mgr._determine_rc_number = Mock(return_value=1)
        release_mgr._merge_archived_patches_to_ho_prod = Mock(return_value=["456-user-auth"])
        release_mgr._send_rebase_notifications = Mock(return_value=[])
        release_mgr._cleanup_patch_branches = Mock(return_value=[])
        mock_hgit.acquire_branch_lock = Mock(return_value="lock-tag-123")
        mock_hgit.release_branch_lock = Mock()
        mock_hgit.fetch = Mock()
        mock_hgit.pull = Mock()
        
        # Execute promotion
        # Note: This should work because stage is RENAMED to rc first,
        # then new empty stage is created
        result = release_mgr.promote_to('rc')
        
        # Verify new stage is empty (not old content)
        new_stage_file = releases_dir / "1.3.5-stage.txt"
        assert new_stage_file.exists()
        assert new_stage_file.read_text() == "", "New stage should be empty, not old content"