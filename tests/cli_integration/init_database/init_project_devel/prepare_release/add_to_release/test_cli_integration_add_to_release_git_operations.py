"""
Integration tests for add-to-release: Git operations.

Tests Git commits, branch state, and push operations.
"""

import pytest
import subprocess


@pytest.mark.integration
class TestAddToReleaseGitOperations:
    """Test Git operations after add-to-release."""

    def test_creates_commit_on_ho_prod(self, release_with_first_patch):
        """Test that add-to-release creates commit on ho-prod branch."""
        project_dir, db_name, patch_id, version, stage_file, _ = release_with_first_patch

        # Verify still on ho-prod branch
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "ho-prod", "Should be on ho-prod branch"

        # Verify commit exists
        result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        commit_message = result.stdout.strip()

        # Commit message should mention patch and version
        assert patch_id in commit_message, f"Commit should mention patch {patch_id}"
        assert version in commit_message, f"Commit should mention version {version}"

    def test_commit_includes_stage_file(self, release_with_first_patch):
        """Test that stage file change is included in commit."""
        project_dir, db_name, patch_id, version, stage_file, _ = release_with_first_patch

        # Verify stage file is in last commit
        result = subprocess.run(
            ["git", "show", "--name-only", "--format=", "HEAD"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0

        committed_files = result.stdout.strip().split('\n')
        stage_file_relative = f"releases/{version}-stage.txt"

        assert stage_file_relative in committed_files, (
            f"Stage file {stage_file_relative} should be in commit"
        )

    def test_only_stage_file_in_commit(self, release_with_first_patch):
        """Test that commit only contains stage file (no patch code)."""
        project_dir, db_name, patch_id, version, stage_file, _ = release_with_first_patch

        # Get files in last commit
        result = subprocess.run(
            ["git", "show", "--name-only", "--format=", "HEAD"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0

        committed_files = result.stdout.strip().split('\n')

        # Should only have the stage file
        assert len(committed_files) == 1, "Commit should only contain stage file"
        assert committed_files[0].endswith('-stage.txt'), "File should be stage file"

        # Should NOT have patch files (Patches/ directory not in commit)
        for file in committed_files:
            assert not file.startswith('Patches/'), (
                "Commit should not contain patch code directly"
            )

    def test_repository_is_clean_after(self, release_with_first_patch):
        """Test that repository is clean after add-to-release."""
        project_dir, db_name, patch_id, version, stage_file, _ = release_with_first_patch

        # Check git status
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0

        # Should have no uncommitted changes
        assert result.stdout.strip() == "", "Repository should be clean after add-to-release"
