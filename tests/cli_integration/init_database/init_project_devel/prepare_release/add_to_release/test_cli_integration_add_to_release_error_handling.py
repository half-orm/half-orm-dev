"""
Integration tests for add-to-release: Error handling.

Tests validation and error cases.
"""

import pytest
import subprocess


@pytest.mark.integration
class TestAddToReleaseErrorHandling:
    """Test error handling and validation."""

    def test_error_if_patch_does_not_exist(self, prepared_release):
        """Test error when trying to add non-existent patch."""
        project_dir, db_name, version, stage_file, _ = prepared_release

        # Ensure on ho-prod
        subprocess.run(
            ["git", "checkout", "ho-prod"],
            cwd=str(project_dir),
            capture_output=True
        )

        # Try to add non-existent patch
        result = subprocess.run(
            ["half_orm", "dev", "add-to-release", "999-nonexistent"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )

        # Should fail
        assert result.returncode != 0, "Should fail when patch doesn't exist"
        assert "not found" in result.stderr.lower() or "doesn't exist" in result.stderr.lower(), (
            "Error message should indicate patch not found"
        )

    def test_error_if_not_on_ho_prod(self, prepared_release, first_patch):
        """Test error when not on ho-prod branch."""
        project_dir_release, db_name, version, stage_file, _ = prepared_release
        project_dir_patch, _, patch_id, _ = first_patch

        # Checkout to patch branch
        result = subprocess.run(
            ["git", "checkout", f"ho-patch/{patch_id}"],
            cwd=str(project_dir_release),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0

        try:
            # Try to add-to-release from wrong branch
            result = subprocess.run(
                ["half_orm", "dev", "add-to-release", patch_id],
                cwd=str(project_dir_release),
                capture_output=True,
                text=True
            )

            # Should fail
            assert result.returncode != 0, "Should fail when not on ho-prod branch"
            assert "ho-prod" in result.stderr.lower(), (
                "Error message should mention ho-prod branch requirement"
            )

        finally:
            # Cleanup: return to ho-prod
            subprocess.run(
                ["git", "checkout", "ho-prod"],
                cwd=str(project_dir_release),
                capture_output=True
            )

    def test_error_if_no_stage_release(self, devel_project):
        """Test error when no stage release exists."""
        project_dir, db_name, _ = devel_project

        # Create a patch without prepared_release (no stage file)
        patch_id = "999-test-patch"
        
        # Ensure on ho-prod
        subprocess.run(
            ["git", "checkout", "ho-prod"],
            cwd=str(project_dir),
            capture_output=True
        )

        # Create patch
        result = subprocess.run(
            ["half_orm", "dev", "create-patch", patch_id],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0

        # Go back to ho-prod
        subprocess.run(
            ["git", "checkout", "ho-prod"],
            cwd=str(project_dir),
            capture_output=True
        )

        try:
            # Try to add-to-release without stage
            result = subprocess.run(
                ["half_orm", "dev", "add-to-release", patch_id],
                cwd=str(project_dir),
                capture_output=True,
                text=True
            )

            # Should fail
            assert result.returncode != 0, "Should fail when no stage release exists"
            assert "no stage" in result.stderr.lower() or "prepare-release" in result.stderr.lower(), (
                "Error message should indicate missing stage release"
            )

        finally:
            # Cleanup: delete patch branch
            subprocess.run(
                ["git", "branch", "-D", f"ho-patch/{patch_id}"],
                cwd=str(project_dir),
                capture_output=True
            )
            subprocess.run(
                ["git", "push", "origin", "--delete", f"ho-patch/{patch_id}"],
                cwd=str(project_dir),
                capture_output=True
            )

    def test_error_if_repository_not_clean(self, prepared_release, first_patch):
        """Test error when repository has uncommitted changes."""
        project_dir_release, db_name, version, stage_file, _ = prepared_release
        project_dir_patch, _, patch_id, _ = first_patch

        # Ensure on ho-prod
        subprocess.run(
            ["git", "checkout", "ho-prod"],
            cwd=str(project_dir_release),
            capture_output=True
        )

        # Create uncommitted change
        dirty_file = project_dir_release / "dirty_file.txt"
        dirty_file.write_text("dirty content")

        try:
            # Try to add-to-release with dirty repo
            result = subprocess.run(
                ["half_orm", "dev", "add-to-release", patch_id],
                cwd=str(project_dir_release),
                capture_output=True,
                text=True
            )

            # Should fail
            assert result.returncode != 0, "Should fail when repository is not clean"
            assert "uncommitted" in result.stderr.lower() or "clean" in result.stderr.lower(), (
                "Error message should mention uncommitted changes"
            )

        finally:
            # Cleanup
            if dirty_file.exists():
                dirty_file.unlink()

    def test_error_if_patch_already_in_release(self, release_with_first_patch):
        """Test error when trying to add patch that's already in release."""
        project_dir, db_name, patch_id, version, stage_file, _ = release_with_first_patch

        # Patch already in stage file
        content = stage_file.read_text()
        assert patch_id in content

        # Patch branch was archived, need to recreate it temporarily for this test
        archived_branch = f"ho-release/{version}/{patch_id}"
        original_branch = f"ho-patch/{patch_id}"
        
        # Recreate the patch branch from archived location
        result = subprocess.run(
            ["git", "branch", original_branch, archived_branch],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, "Failed to recreate patch branch for test"

        # Checkout to recreated patch branch
        subprocess.run(
            ["git", "checkout", original_branch],
            cwd=str(project_dir),
            capture_output=True
        )

        # Checkout back to ho-prod
        subprocess.run(
            ["git", "checkout", "ho-prod"],
            cwd=str(project_dir),
            capture_output=True
        )

        try:
            # Try to add same patch again
            result = subprocess.run(
                ["half_orm", "dev", "add-to-release", patch_id],
                cwd=str(project_dir),
                capture_output=True,
                text=True
            )

            # Should fail
            assert result.returncode != 0, "Should fail when patch already in release"
            assert "already" in result.stderr.lower() or "already in release" in result.stdout.lower(), (
                f"Error message should indicate patch already in release.\n"
                f"Got stderr: {result.stderr}\n"
                f"Got stdout: {result.stdout}"
            )

        finally:
            # Cleanup: delete recreated branch
            subprocess.run(
                ["git", "checkout", "ho-prod"],
                cwd=str(project_dir),
                capture_output=True
            )
            subprocess.run(
                ["git", "branch", "-D", original_branch],
                cwd=str(project_dir),
                capture_output=True
            )
