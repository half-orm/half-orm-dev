"""
Integration tests for promote-to rc CLI command.

Tests the complete workflow:
- File rename: X.Y.Z-stage.txt → X.Y.Z-rc1.txt
- Code merge: ho-release/X.Y.Z/* → ho-prod (CRITICAL OPERATION)
- Branch cleanup: ho-patch/* deleted
- RC number increment: rc1, rc2, rc3
"""

import pytest
import subprocess
from pathlib import Path


@pytest.mark.integration
class TestPromoteToRcBasicWorkflow:
    """Test basic promote-to rc workflow."""

    def test_rc_file_contains_same_patches(self, release_with_rc):
        """Test that RC file contains same patches as stage."""
        project_dir, db_name, patch_id, version, rc_file, _ = release_with_rc

        # Read RC file content
        rc_content = rc_file.read_text().strip()

        # Should contain the patch
        assert patch_id in rc_content, f"RC file should contain patch {patch_id}"

    def test_creates_commit_on_ho_prod(self, release_with_rc):
        """Test that promote-to rc creates commit on ho-prod."""
        project_dir, db_name, patch_id, version, rc_file, _ = release_with_rc

        # Verify still on ho-prod
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "ho-prod"

        # Verify commit exists
        result = subprocess.run(
            ["git", "log", "--oneline", "-2"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        commit_message = result.stdout.strip()

        # Commit should mention promotion
        assert "promote" in commit_message.lower() or "rc" in commit_message.lower()
        assert version in commit_message
        result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        commit_message = result.stdout.strip()

        # Commit should mention promotion
        assert "create new empty stage" in commit_message.lower()
        assert version in commit_message

    def test_commit_includes_rc_file(self, release_with_rc):
        """Test that RC file is in the commit."""
        project_dir, db_name, patch_id, version, rc_file, _ = release_with_rc

        # Get files in last commit
        result = subprocess.run(
            ["git", "show", "--name-only", "--format=", "HEAD", "-2"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0

        committed_files = result.stdout.strip().split('\n')
        rc_file_relative = f"releases/{version}-rc1.txt"

        assert rc_file_relative in committed_files, (
            f"RC file {rc_file_relative} should be in commit"
        )


@pytest.mark.integration
class TestPromoteToRcCodeMerge:
    """Test code merge operation (CRITICAL: code enters ho-prod here)."""

    def test_code_merged_to_ho_prod(self, release_with_rc):
        """Test that patch code is merged into ho-prod."""
        project_dir, db_name, patch_id, version, rc_file, _ = release_with_rc

        # Check that Patches/ directory exists in ho-prod
        patches_dir = project_dir / "Patches" / patch_id
        assert patches_dir.exists(), f"Patches/{patch_id}/ should exist in ho-prod"

        # Verify specific patch files exist
        readme = patches_dir / "README.md"
        assert readme.exists(), "README.md should exist in merged code"

    def test_commit_includes_patch_code(self, release_with_rc):
        """Test that merge commits include patch code files."""
        project_dir, db_name, patch_id, version, rc_file, _ = release_with_rc

        # Get recent commits (not just HEAD, but several commits)
        result = subprocess.run(
            ["git", "log", "--name-only", "--format=%H", "-5"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0

        all_files = result.stdout

        # Should include patch files in one of the recent commits
        has_patch_files = f"Patches/{patch_id}/" in all_files
        assert has_patch_files, (
            f"Recent commits should include Patches/{patch_id}/ files "
            f"(check merge commits, not just promotion commit)"
        )

    def test_git_log_shows_merge_commit(self, release_with_rc):
        """Test that git log shows merge commit for patch integration."""
        project_dir, db_name, patch_id, version, rc_file, _ = release_with_rc

        # Get recent commits
        result = subprocess.run(
            ["git", "log", "--oneline", "-10"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0

        log_output = result.stdout

        # Should show merge commit for patch
        assert "Integrate" in log_output or "Merge" in log_output, (
            "Git log should show merge commit for patch integration"
        )


@pytest.mark.integration
class TestPromoteToRcBranchCleanup:
    """Test automatic branch cleanup after promotion."""

    def test_patch_branch_deleted_locally(self, release_with_rc):
        """Test that ho-patch branch is deleted locally."""
        project_dir, db_name, patch_id, version, rc_file, _ = release_with_rc

        patch_branch = f"ho-patch/{patch_id}"

        # Verify local branch does NOT exist
        result = subprocess.run(
            ["git", "show-ref", "--verify", f"refs/heads/{patch_branch}"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode != 0, f"Local branch {patch_branch} should be deleted"

    def test_patch_branch_deleted_remote(self, release_with_rc):
        """Test that ho-patch branch is deleted from remote."""
        project_dir, db_name, patch_id, version, rc_file, _ = release_with_rc

        patch_branch = f"ho-patch/{patch_id}"

        # Verify remote branch does NOT exist
        result = subprocess.run(
            ["git", "ls-remote", "--heads", "origin", patch_branch],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert patch_branch not in result.stdout, (
            f"Remote branch {patch_branch} should be deleted"
        )

    def test_archived_branch_still_exists(self, release_with_rc):
        """Test that ho-release archived branch still exists after promotion."""
        project_dir, db_name, patch_id, version, rc_file, _ = release_with_rc

        archived_branch = f"ho-release/{version}/{patch_id}"

        # Archived branch should still exist (not deleted by promote)
        result = subprocess.run(
            ["git", "show-ref", "--verify", f"refs/heads/{archived_branch}"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, (
            f"Archived branch {archived_branch} should still exist"
        )


@pytest.mark.integration
class TestPromoteToRcNumbering:
    """Test RC numbering (rc1, rc2, rc3, etc.)."""

    def test_first_promotion_creates_rc1(self, release_with_rc):
        """Test that first promotion creates rc1."""
        project_dir, db_name, patch_id, version, rc_file, _ = release_with_rc

        # Should be rc1
        assert rc_file.name == f"{version}-rc1.txt", (
            "First promotion should create rc1"
        )

    def test_second_promotion_creates_rc2(self, release_with_rc2):
        """Test that second promotion of same version creates rc2."""
        (project_dir, db_name, first_patch, second_patch,
         version, rc2_file, rc1_file, _) = release_with_rc2

        # RC1 should still exist
        assert rc1_file.exists(), "RC1 should still exist"

        # RC2 should be created
        assert rc2_file.exists(), "RC2 should be created"
        assert rc2_file.name == f"{version}-rc2.txt"

    def test_rc2_contains_new_patch(self, release_with_rc2):
        """Test that rc2 contains the new patch."""
        (project_dir, db_name, first_patch, second_patch,
         version, rc2_file, rc1_file, _) = release_with_rc2

        # RC2 should contain second patch
        rc2_content = rc2_file.read_text()
        assert second_patch in rc2_content, (
            f"RC2 should contain second patch {second_patch}"
        )

    def test_rc1_unchanged(self, release_with_rc2):
        """Test that rc1 remains unchanged when rc2 is created."""
        (project_dir, db_name, first_patch, second_patch,
         version, rc2_file, rc1_file, _) = release_with_rc2

        # RC1 should only contain first patch
        rc1_content = rc1_file.read_text()
        assert first_patch in rc1_content
        assert second_patch not in rc1_content, (
            "RC1 should not be modified when RC2 is created"
        )


@pytest.mark.integration
class TestPromoteToRcErrorHandling:
    """Test error handling and validation."""

    def test_error_if_not_on_ho_prod(self, release_with_first_patch):
        """Test error when not on ho-prod branch."""
        project_dir, db_name, patch_id, version, stage_file, _ = release_with_first_patch

        # Checkout to patch branch
        result = subprocess.run(
            ["git", "checkout", "-b", "test-branch"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0

        # Try promote-to rc
        result = subprocess.run(
            ["half_orm", "dev", "promote-to", "rc"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )

        # Should fail
        assert result.returncode != 0, "Should fail when not on ho-prod"
        assert "ho-prod" in result.stderr.lower(), (
            "Error should mention ho-prod branch requirement"
        )

        # Cleanup: return to ho-prod
        subprocess.run(
            ["git", "checkout", "ho-prod"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        subprocess.run(
            ["git", "branch", "-D", "test-branch"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )

    def test_error_if_no_stage_files(self, devel_project):
        """Test error when no stage files exist."""
        project_dir, db_name, _ = devel_project

        # Ensure no stage files
        releases_dir = project_dir / "releases"
        stage_files = list(releases_dir.glob("*-stage.txt"))
        for f in stage_files:
            f.unlink()

        # Try promote-to rc
        result = subprocess.run(
            ["half_orm", "dev", "promote-to", "rc"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )

        # Should fail
        assert result.returncode != 0, "Should fail when no stage files exist"
        assert "stage" in result.stderr.lower(), (
            "Error should mention missing stage files"
        )

    def test_error_if_repository_not_clean(self, release_with_first_patch):
        """Test error when repository has uncommitted changes."""
        project_dir, db_name, patch_id, version, stage_file, _ = release_with_first_patch

        # Create uncommitted change
        test_file = project_dir / "test_uncommitted.txt"
        test_file.write_text("uncommitted change")

        # Try promote-to rc
        result = subprocess.run(
            ["half_orm", "dev", "promote-to", "rc"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )

        # Should fail
        assert result.returncode != 0, "Should fail with uncommitted changes"
        assert "clean" in result.stderr.lower() or "uncommitted" in result.stderr.lower(), (
            "Error should mention uncommitted changes"
        )

        # Cleanup
        test_file.unlink()
