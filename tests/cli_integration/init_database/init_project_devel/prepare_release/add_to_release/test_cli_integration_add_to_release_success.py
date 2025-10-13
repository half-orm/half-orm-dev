"""
Integration tests for add-to-release: Success scenarios.

Tests successful workflow completion and exit codes.
"""

import pytest
import subprocess


@pytest.mark.integration
class TestAddToReleaseSuccessWorkflow:
    """Test successful add-to-release workflow."""

    def test_add_to_release_success_exit_code(self, release_with_first_patch):
        """Test that add-to-release completes successfully with exit code 0."""
        # Fixture already verified returncode == 0
        # This test documents the expected behavior
        project_dir, db_name, patch_id, version, stage_file, _ = release_with_first_patch

        # Verify patch in stage file (proof of success)
        content = stage_file.read_text()
        assert patch_id in content, "Patch should be in stage file after successful add-to-release"

        # Verify commit was created
        result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert patch_id in result.stdout, f"Latest commit should mention patch {patch_id}"

    def test_complete_workflow_with_output_messages(self, prepared_release, first_patch):
        """Test complete workflow produces informative output messages."""
        project_dir_release, db_name, version, stage_file, _ = prepared_release
        project_dir_patch, _, patch_id, _ = first_patch

        # Ensure on ho-prod
        subprocess.run(
            ["git", "checkout", "ho-prod"],
            cwd=str(project_dir_release),
            capture_output=True
        )

        # Execute add-to-release and capture output
        result = subprocess.run(
            ["half_orm", "dev", "add-to-release", patch_id],
            cwd=str(project_dir_release),
            capture_output=True,
            text=True
        )

        # Should succeed
        assert result.returncode == 0, f"Command should succeed: {result.stderr}"

        # Output should contain success indicators
        output = result.stdout.lower()
        assert any(word in output for word in ['success', 'added', 'complete', '✓']), (
            "Output should indicate success"
        )

        # Output should mention patch ID
        assert patch_id in result.stdout, "Output should mention patch ID"

        # Output should mention version
        assert version in result.stdout, "Output should mention version"

        # Cleanup
        stage_file.write_text("")
        subprocess.run(
            ["git", "reset", "--hard", "HEAD~1"],
            cwd=str(project_dir_release),
            capture_output=True
        )
