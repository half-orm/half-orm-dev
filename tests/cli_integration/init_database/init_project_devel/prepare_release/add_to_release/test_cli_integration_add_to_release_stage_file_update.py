"""
Integration tests for add-to-release: Stage file updates.

Tests that patches are correctly added to stage file with proper formatting.
"""

import pytest


@pytest.mark.integration
class TestAddToReleaseStageFileUpdate:
    """Test stage file content after add-to-release."""

    def test_adds_patch_to_empty_stage(self, release_with_first_patch):
        """Test adding first patch to empty stage file."""
        project_dir, db_name, patch_id, version, stage_file, _ = release_with_first_patch

        # Read stage file content
        content = stage_file.read_text()

        # Should contain patch ID
        assert patch_id in content, f"Stage file should contain {patch_id}"

        # Should be on its own line
        lines = content.strip().split('\n')
        assert patch_id in lines, f"Patch should be on its own line"

    def test_appends_patch_to_existing_stage(self, release_with_second_patch):
        """Test adding second patch preserves first patch."""
        (project_dir, db_name, second_patch_id, version, 
         stage_file, _, first_patch_id) = release_with_second_patch

        # Read stage file content
        content = stage_file.read_text()
        lines = content.strip().split('\n')

        # Should contain both patches
        assert first_patch_id in lines, f"Should still contain first patch {first_patch_id}"
        assert second_patch_id in lines, f"Should contain second patch {second_patch_id}"

        # Should have exactly 2 lines
        assert len(lines) == 2, "Stage file should have exactly 2 patches"

    def test_preserves_patch_order(self, release_with_second_patch):
        """Test patches are in correct order (first added first)."""
        (project_dir, db_name, second_patch_id, version, 
         stage_file, _, first_patch_id) = release_with_second_patch

        # Read stage file content
        content = stage_file.read_text()
        lines = content.strip().split('\n')

        # First patch should be first, second patch should be second
        assert lines[0] == first_patch_id, "First patch should be on line 1"
        assert lines[1] == second_patch_id, "Second patch should be on line 2"

    def test_stage_file_format_valid(self, release_with_first_patch):
        """Test stage file has valid format (one patch per line, no empty lines)."""
        project_dir, db_name, patch_id, version, stage_file, _ = release_with_first_patch

        # Read stage file content
        content = stage_file.read_text()

        # Should end with newline
        assert content.endswith('\n'), "Stage file should end with newline"

        # No empty lines (except potentially at end)
        lines = content.strip().split('\n')
        for line in lines:
            assert line.strip() != '', "Should not have empty lines"

        # Each line should be a valid patch ID
        for line in lines:
            assert '-' in line, f"Line '{line}' should be a valid patch ID (contains hyphen)"
