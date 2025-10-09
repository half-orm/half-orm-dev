"""
Tests for PatchManager.apply_patch_complete_workflow() with release context.

Focused on testing:
- Release context detection and application
- Patch ordering (in release vs. not in release)
- RC + stage sequential application
- No release context (backward compatibility)
- Error handling with release context
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, call

from half_orm_dev.patch_manager import PatchManager, PatchManagerError
from half_orm_dev.release_manager import ReleaseManager


@pytest.fixture
def mock_workflow_with_release_context(patch_manager):
    """
    Setup complete mock environment for release context workflow tests.

    Provides:
    - patch_manager with temp directories
    - mock Model with disconnect/ping
    - mock Database.execute_pg_command
    - mock modules.generate
    - mock ReleaseManager
    - releases/ directory for release files

    Returns:
        Tuple of (patch_mgr, repo, schema_file, mock_model, mock_execute,
                  mock_generate, mock_release_mgr, releases_dir)
    """
    patch_mgr, repo, temp_dir, patches_dir = patch_manager

    # Create model/schema.sql
    model_dir = Path(temp_dir) / "model"
    model_dir.mkdir()
    schema_file = model_dir / "schema.sql"
    schema_file.write_text("CREATE TABLE users (id SERIAL PRIMARY KEY);")

    # Create releases/ directory
    releases_dir = Path(temp_dir) / "releases"
    releases_dir.mkdir()

    # Mock Model
    mock_model = Mock()
    mock_model.disconnect = Mock()
    mock_model.ping = Mock()
    mock_model.execute_query = Mock()
    repo.model = mock_model

    # Mock Database.execute_pg_command
    mock_execute = Mock()
    repo.database.execute_pg_command = mock_execute

    # Mock modules.generate
    mock_generate = Mock()

    # Create real ReleaseManager with mocked production version
    release_mgr = ReleaseManager(repo)
    release_mgr._get_production_version = Mock(return_value="1.3.5")
    repo.release_manager = release_mgr

    return (patch_mgr, repo, schema_file, mock_model, mock_execute,
            mock_generate, release_mgr, releases_dir)


def create_patch_directory(patches_dir: Path, patch_id: str, num_files: int = 2):
    """Helper to create patch directory with SQL files."""
    patch_path = patches_dir / patch_id
    patch_path.mkdir()
    for i in range(1, num_files + 1):
        sql_file = patch_path / f"{i:02d}_file.sql"
        sql_file.write_text(f"-- SQL for {patch_id} file {i}")
    return patch_path


def create_release_file(releases_dir: Path, filename: str, patch_ids: list):
    """Helper to create release file with patch IDs."""
    file_path = releases_dir / filename
    content = "\n".join(patch_ids)
    file_path.write_text(content)
    return file_path


class TestReleaseManagerGetAllReleaseContextPatches:
    """Test ReleaseManager.get_all_release_context_patches() method."""

    def test_no_release_files_returns_empty(self, mock_workflow_with_release_context):
        """Test returns empty list when no release files exist."""
        (patch_mgr, repo, schema_file, mock_model, mock_execute,
         mock_generate, release_mgr, releases_dir) = mock_workflow_with_release_context

        patches = release_mgr.get_all_release_context_patches()

        assert patches == []

    def test_single_stage_file(self, mock_workflow_with_release_context):
        """Test with single stage file."""
        (patch_mgr, repo, schema_file, mock_model, mock_execute,
         mock_generate, release_mgr, releases_dir) = mock_workflow_with_release_context

        # Create 1.3.6-stage.txt
        create_release_file(releases_dir, "1.3.6-stage.txt", ["123", "456", "789"])

        patches = release_mgr.get_all_release_context_patches()

        assert patches == ["123", "456", "789"]

    def test_single_rc_file(self, mock_workflow_with_release_context):
        """Test with single RC file."""
        (patch_mgr, repo, schema_file, mock_model, mock_execute,
         mock_generate, release_mgr, releases_dir) = mock_workflow_with_release_context

        # Create 1.3.6-rc1.txt
        create_release_file(releases_dir, "1.3.6-rc1.txt", ["123", "456"])

        patches = release_mgr.get_all_release_context_patches()

        assert patches == ["123", "456"]

    def test_multiple_rc_files_sequential(self, mock_workflow_with_release_context):
        """Test with multiple RC files (incremental)."""
        (patch_mgr, repo, schema_file, mock_model, mock_execute,
         mock_generate, release_mgr, releases_dir) = mock_workflow_with_release_context

        # Create incremental RC files
        create_release_file(releases_dir, "1.3.6-rc1.txt", ["123", "456", "789"])
        create_release_file(releases_dir, "1.3.6-rc2.txt", ["999"])  # New patch only
        create_release_file(releases_dir, "1.3.6-rc3.txt", ["888", "777"])  # New patches

        patches = release_mgr.get_all_release_context_patches()

        # Should preserve sequential order
        assert patches == ["123", "456", "789", "999", "888", "777"]

    def test_rc_plus_stage(self, mock_workflow_with_release_context):
        """Test with RC files + stage file."""
        (patch_mgr, repo, schema_file, mock_model, mock_execute,
         mock_generate, release_mgr, releases_dir) = mock_workflow_with_release_context

        # Create RC and stage
        create_release_file(releases_dir, "1.3.6-rc1.txt", ["123", "456"])
        create_release_file(releases_dir, "1.3.6-rc2.txt", ["789"])
        create_release_file(releases_dir, "1.3.6-stage.txt", ["234", "567"])

        patches = release_mgr.get_all_release_context_patches()

        # RC first, then stage
        assert patches == ["123", "456", "789", "234", "567"]

    def test_ignores_comments_and_empty_lines(self, mock_workflow_with_release_context):
        """Test that comments and empty lines are ignored."""
        (patch_mgr, repo, schema_file, mock_model, mock_execute,
         mock_generate, release_mgr, releases_dir) = mock_workflow_with_release_context

        # Create file with comments and empty lines
        file_path = releases_dir / "1.3.6-stage.txt"
        file_path.write_text("""# Comment line
123

456
# Another comment

789
""")

        patches = release_mgr.get_all_release_context_patches()

        assert patches == ["123", "456", "789"]

    def test_prefers_patch_over_minor_over_major(self, mock_workflow_with_release_context):
        """Test that patch increment is preferred over minor and major."""
        (patch_mgr, repo, schema_file, mock_model, mock_execute,
         mock_generate, release_mgr, releases_dir) = mock_workflow_with_release_context

        # Create multiple versions
        create_release_file(releases_dir, "1.3.6-stage.txt", ["patch-123"])
        create_release_file(releases_dir, "1.4.0-stage.txt", ["minor-456"])
        create_release_file(releases_dir, "2.0.0-stage.txt", ["major-789"])

        patches = release_mgr.get_all_release_context_patches()

        # Should use patch version (1.3.6)
        assert patches == ["patch-123"]


class TestApplyPatchWithReleaseContext:
    """Test apply_patch_complete_workflow() with release context."""

    def test_no_release_context_backward_compatibility(self, mock_workflow_with_release_context):
        """Test backward compatibility when no release context exists."""
        (patch_mgr, repo, schema_file, mock_model, mock_execute,
         mock_generate, release_mgr, releases_dir) = mock_workflow_with_release_context

        patches_dir = Path(repo.base_dir) / "Patches"

        # Create single patch (not in any release)
        create_patch_directory(patches_dir, "789", num_files=2)

        # Track execution order
        execution_order = []

        def track_apply(patch_id, model):
            execution_order.append(patch_id)
            return [f"{patch_id}_01.sql", f"{patch_id}_02.sql"]

        with patch.object(patch_mgr, 'apply_patch_files', side_effect=track_apply):
            with patch('half_orm_dev.modules.generate', mock_generate):
                result = patch_mgr.apply_patch_complete_workflow("789")

        # Should apply only current patch
        assert execution_order == ["789"]
        assert result['patch_was_in_release'] is False
        assert result['release_patches'] == []

    def test_patch_in_release_applied_in_order(self, mock_workflow_with_release_context):
        """Test patch in release is applied in correct order."""
        (patch_mgr, repo, schema_file, mock_model, mock_execute,
         mock_generate, release_mgr, releases_dir) = mock_workflow_with_release_context

        patches_dir = Path(repo.base_dir) / "Patches"

        # Create release context
        create_release_file(releases_dir, "1.3.6-stage.txt", ["123", "456", "789", "234"])

        # Create patches
        for patch_id in ["123", "456", "789", "234"]:
            create_patch_directory(patches_dir, patch_id)

        # Track execution order
        execution_order = []

        def track_apply(patch_id, model):
            execution_order.append(patch_id)
            return [f"{patch_id}.sql"]

        with patch.object(patch_mgr, 'apply_patch_files', side_effect=track_apply):
            with patch('half_orm_dev.modules.generate', mock_generate):
                result = patch_mgr.apply_patch_complete_workflow("789")

        # Patch 789 should be applied in order (3rd position)
        assert execution_order == ["123", "456", "789", "234"]
        assert result['patch_was_in_release'] is True
        assert result['release_patches'] == ["123", "456", "234"]  # Excludes current

    def test_patch_not_in_release_applied_at_end(self, mock_workflow_with_release_context):
        """Test patch not in release is applied at the end."""
        (patch_mgr, repo, schema_file, mock_model, mock_execute,
         mock_generate, release_mgr, releases_dir) = mock_workflow_with_release_context

        patches_dir = Path(repo.base_dir) / "Patches"

        # Create release context (without 999)
        create_release_file(releases_dir, "1.3.6-stage.txt", ["123", "456", "789"])

        # Create patches
        for patch_id in ["123", "456", "789", "999"]:
            create_patch_directory(patches_dir, patch_id)

        # Track execution order
        execution_order = []

        def track_apply(patch_id, model):
            execution_order.append(patch_id)
            return [f"{patch_id}.sql"]

        with patch.object(patch_mgr, 'apply_patch_files', side_effect=track_apply):
            with patch('half_orm_dev.modules.generate', mock_generate):
                result = patch_mgr.apply_patch_complete_workflow("999")

        # Patch 999 should be applied AFTER all release patches
        assert execution_order == ["123", "456", "789", "999"]
        assert result['patch_was_in_release'] is False
        assert result['release_patches'] == ["123", "456", "789"]

    def test_patch_first_in_release(self, mock_workflow_with_release_context):
        """Test patch at first position in release."""
        (patch_mgr, repo, schema_file, mock_model, mock_execute,
         mock_generate, release_mgr, releases_dir) = mock_workflow_with_release_context

        patches_dir = Path(repo.base_dir) / "Patches"

        # Create release with patch at start
        create_release_file(releases_dir, "1.3.6-stage.txt", ["789", "123", "456"])

        for patch_id in ["789", "123", "456"]:
            create_patch_directory(patches_dir, patch_id)

        execution_order = []

        def track_apply(patch_id, model):
            execution_order.append(patch_id)
            return [f"{patch_id}.sql"]

        with patch.object(patch_mgr, 'apply_patch_files', side_effect=track_apply):
            with patch('half_orm_dev.modules.generate', mock_generate):
                result = patch_mgr.apply_patch_complete_workflow("789")

        # Should be applied first
        assert execution_order == ["789", "123", "456"]
        assert result['patch_was_in_release'] is True

    def test_patch_last_in_release(self, mock_workflow_with_release_context):
        """Test patch at last position in release."""
        (patch_mgr, repo, schema_file, mock_model, mock_execute,
         mock_generate, release_mgr, releases_dir) = mock_workflow_with_release_context

        patches_dir = Path(repo.base_dir) / "Patches"

        # Create release with patch at end
        create_release_file(releases_dir, "1.3.6-stage.txt", ["123", "456", "789"])

        for patch_id in ["123", "456", "789"]:
            create_patch_directory(patches_dir, patch_id)

        execution_order = []

        def track_apply(patch_id, model):
            execution_order.append(patch_id)
            return [f"{patch_id}.sql"]

        with patch.object(patch_mgr, 'apply_patch_files', side_effect=track_apply):
            with patch('half_orm_dev.modules.generate', mock_generate):
                result = patch_mgr.apply_patch_complete_workflow("789")

        # Should be applied last
        assert execution_order == ["123", "456", "789"]
        assert result['patch_was_in_release'] is True

    def test_rc_sequence_applied_before_stage(self, mock_workflow_with_release_context):
        """Test RC files applied before stage file."""
        (patch_mgr, repo, schema_file, mock_model, mock_execute,
         mock_generate, release_mgr, releases_dir) = mock_workflow_with_release_context

        patches_dir = Path(repo.base_dir) / "Patches"

        # Create RC sequence + stage
        create_release_file(releases_dir, "1.3.6-rc1.txt", ["123", "456"])
        create_release_file(releases_dir, "1.3.6-rc2.txt", ["789"])
        create_release_file(releases_dir, "1.3.6-stage.txt", ["234"])

        for patch_id in ["123", "456", "789", "234", "999"]:
            create_patch_directory(patches_dir, patch_id)

        execution_order = []

        def track_apply(patch_id, model):
            execution_order.append(patch_id)
            return [f"{patch_id}.sql"]

        with patch.object(patch_mgr, 'apply_patch_files', side_effect=track_apply):
            with patch('half_orm_dev.modules.generate', mock_generate):
                result = patch_mgr.apply_patch_complete_workflow("999")

        # Order: rc1 → rc2 → stage → current
        assert execution_order == ["123", "456", "789", "234", "999"]
        assert result['patch_was_in_release'] is False

    def test_return_structure_with_release_context(self, mock_workflow_with_release_context):
        """Test return structure includes release context info."""
        (patch_mgr, repo, schema_file, mock_model, mock_execute,
         mock_generate, release_mgr, releases_dir) = mock_workflow_with_release_context

        patches_dir = Path(repo.base_dir) / "Patches"

        create_release_file(releases_dir, "1.3.6-stage.txt", ["123", "456"])

        for patch_id in ["123", "456", "789"]:
            create_patch_directory(patches_dir, patch_id)

        def mock_apply(patch_id, model):
            return [f"{patch_id}.sql"]

        with patch.object(patch_mgr, 'apply_patch_files', side_effect=mock_apply):
            with patch('half_orm_dev.modules.generate', mock_generate):
                result = patch_mgr.apply_patch_complete_workflow("789")

        # Verify new return keys
        assert 'release_patches' in result
        assert 'applied_release_files' in result
        assert 'applied_current_files' in result
        assert 'patch_was_in_release' in result

        assert result['release_patches'] == ["123", "456"]
        assert result['patch_was_in_release'] is False


class TestApplyPatchErrorHandlingWithReleaseContext:
    """Test error handling with release context."""

    def test_rollback_on_release_patch_failure(self, mock_workflow_with_release_context):
        """Test rollback when a release patch fails."""
        (patch_mgr, repo, schema_file, mock_model, mock_execute,
         mock_generate, release_mgr, releases_dir) = mock_workflow_with_release_context

        patches_dir = Path(repo.base_dir) / "Patches"

        create_release_file(releases_dir, "1.3.6-stage.txt", ["123", "456", "789"])

        for patch_id in ["123", "456", "789", "999"]:
            create_patch_directory(patches_dir, patch_id)

        # Mock failure on patch 456
        def mock_apply(patch_id, model):
            if patch_id == "456":
                raise PatchManagerError(f"Failed to apply patch {patch_id}")
            return [f"{patch_id}.sql"]

        with patch.object(patch_mgr, 'apply_patch_files', side_effect=mock_apply):
            with patch('half_orm_dev.modules.generate', mock_generate):
                with pytest.raises(PatchManagerError, match="Failed to apply patch 456"):
                    patch_mgr.apply_patch_complete_workflow("999")

        # Code generation should not be called
        mock_generate.assert_not_called()

    def test_rollback_on_current_patch_failure(self, mock_workflow_with_release_context):
        """Test rollback when current patch fails."""
        (patch_mgr, repo, schema_file, mock_model, mock_execute,
         mock_generate, release_mgr, releases_dir) = mock_workflow_with_release_context

        patches_dir = Path(repo.base_dir) / "Patches"

        create_release_file(releases_dir, "1.3.6-stage.txt", ["123", "456"])

        for patch_id in ["123", "456", "789"]:
            create_patch_directory(patches_dir, patch_id)

        # Mock failure on current patch
        def mock_apply(patch_id, model):
            if patch_id == "789":
                raise PatchManagerError(f"Failed to apply current patch {patch_id}")
            return [f"{patch_id}.sql"]

        with patch.object(patch_mgr, 'apply_patch_files', side_effect=mock_apply):
            with patch('half_orm_dev.modules.generate', mock_generate):
                with pytest.raises(PatchManagerError, match="Failed to apply current patch 789"):
                    patch_mgr.apply_patch_complete_workflow("789")

        # Code generation should not be called
        mock_generate.assert_not_called()
