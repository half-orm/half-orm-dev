"""
Integration tests for add-to-release: Branch archiving.

Tests that patch branches are archived to ho-release/{version}/ namespace.
"""

import pytest
import subprocess


@pytest.mark.integration
class TestAddToReleaseBranchArchiving:
    """Test branch archiving after add-to-release."""

    def test_archives_patch_branch(self, release_with_first_patch):
        """Test that patch branch is archived to ho-archive/{version}/ namespace."""
        project_dir, db_name, patch_id, version, stage_file, _ = release_with_first_patch

        # Expected archived branch name
        archived_branch = f"ho-archive/{version}/{patch_id}"

        # Verify archived branch exists
        result = subprocess.run(
            ["git", "show-ref", "--verify", f"refs/heads/{archived_branch}"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Archived branch {archived_branch} should exist"

    def test_original_patch_branch_deleted(self, release_with_first_patch):
        """Test that original ho-patch branch is deleted after archiving."""
        project_dir, db_name, patch_id, version, stage_file, _ = release_with_first_patch

        # Original branch name
        original_branch = f"ho-patch/{patch_id}"

        # Verify original branch does NOT exist
        result = subprocess.run(
            ["git", "show-ref", "--verify", f"refs/heads/{original_branch}"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode != 0, f"Original branch {original_branch} should be deleted"

    def test_archived_branch_points_to_patch_commit(self, release_with_first_patch):
        """Test that archived branch points to the correct commit (with patch code)."""
        project_dir, db_name, patch_id, version, stage_file, _ = release_with_first_patch

        archived_branch = f"ho-release/{version}/{patch_id}"

        # Verify Patches/ directory exists in archived branch
        result = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", archived_branch],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0

        files_in_branch = result.stdout.strip().split('\n')

        # Should contain Patches/{patch_id}/ directory
        patches_dir = f"Patches/{patch_id}/"
        has_patches = any(f.startswith(patches_dir) for f in files_in_branch)
        assert has_patches, f"Archived branch should contain {patches_dir}"

    def test_multiple_patches_archived_separately(self, release_with_second_patch):
        """Test that multiple patches are archived in separate branches."""
        (project_dir, db_name, second_patch_id, version,
         stage_file, _, first_patch_id) = release_with_second_patch

        # Both patches should be archived
        first_archived = f"ho-release/{version}/{first_patch_id}"
        second_archived = f"ho-release/{version}/{second_patch_id}"

        # Verify both archived branches exist
        result1 = subprocess.run(
            ["git", "show-ref", "--verify", f"refs/heads/{first_archived}"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result1.returncode == 0, f"First archived branch {first_archived} should exist"

        result2 = subprocess.run(
            ["git", "show-ref", "--verify", f"refs/heads/{second_archived}"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result2.returncode == 0, f"Second archived branch {second_archived} should exist"

        # Both original branches should be deleted
        result3 = subprocess.run(
            ["git", "show-ref", "--verify", f"refs/heads/ho-patch/{first_patch_id}"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result3.returncode != 0, "First original branch should be deleted"

        result4 = subprocess.run(
            ["git", "show-ref", "--verify", f"refs/heads/ho-patch/{second_patch_id}"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result4.returncode != 0, "Second original branch should be deleted"
