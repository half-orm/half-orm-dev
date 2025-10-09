"""
Integration tests for 'half_orm dev create-patch' CLI command (nominal case).

Tests end-to-end patch creation via subprocess with real Git repository.
Verifies branch creation, directory structure, commits, and remote operations.
"""

import pytest
import subprocess
from pathlib import Path


@pytest.mark.integration
class TestCreatePatchBranch:
    """Test Git branch creation."""

    def test_create_patch_creates_branch(self, first_patch):
        """Test that create-patch creates ho-patch/1-first-patch branch."""
        project_dir, db_name, patch_id, _ = first_patch

        # Verify branch exists locally
        result = subprocess.run(
            ["git", "branch", "--list", f"ho-patch/{patch_id}"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert f"ho-patch/{patch_id}" in result.stdout, "Branch not created locally"


@pytest.mark.integration
class TestCreatePatchDirectory:
    """Test Patches/ directory structure creation."""

    def test_create_patch_creates_directory(self, first_patch):
        """Test that Patches/1-first-patch/ directory is created with README.md."""
        project_dir, db_name, patch_id, _ = first_patch

        # Verify Patches/<patch_id>/ directory exists
        patch_dir = project_dir / "Patches" / patch_id
        assert patch_dir.exists(), f"Patches/{patch_id}/ directory not created"
        assert patch_dir.is_dir(), f"Patches/{patch_id}/ should be a directory"

        # Verify README.md exists
        readme = patch_dir / "README.md"
        assert readme.exists(), f"Patches/{patch_id}/README.md not created"
        assert readme.is_file(), "README.md should be a file"

        # Verify README has patch ID
        readme_content = readme.read_text()
        assert patch_id in readme_content, "README.md should contain patch ID"


@pytest.mark.integration
class TestCreatePatchCheckout:
    """Test automatic checkout to new patch branch."""

    def test_create_patch_switches_to_branch(self, first_patch):
        """Test that create-patch automatically checks out to new branch."""
        project_dir, db_name, patch_id, _ = first_patch

        # Verify current branch is the patch branch
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert result.stdout.strip() == f"ho-patch/{patch_id}", (
            f"Should be on ho-patch/{patch_id} branch"
        )


@pytest.mark.integration
class TestCreatePatchCommit:
    """Test Git commit for Patches/ directory."""

    def test_create_patch_commits_directory(self, first_patch):
        """Test that Patches/1-first-patch/ is committed to Git."""
        project_dir, db_name, patch_id, _ = first_patch

        # Verify latest commit message
        result = subprocess.run(
            ["git", "log", "-1", "--pretty=%s"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        commit_message = result.stdout.strip()

        # Should contain patch directory reference
        assert f"Patches/{patch_id}" in commit_message, (
            f"Commit message should reference Patches/{patch_id}"
        )

        # Verify Patches/<patch_id>/ is in the commit
        result = subprocess.run(
            ["git", "ls-tree", "-r", "HEAD", "--name-only"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        committed_files = result.stdout.strip().split('\n')

        assert f"Patches/{patch_id}/README.md" in committed_files, (
            f"Patches/{patch_id}/README.md should be committed"
        )


@pytest.mark.integration
class TestCreatePatchRemote:
    """Test remote Git operations (push branch and tag)."""

    def test_create_patch_pushes_to_remote(self, first_patch):
        """Test that branch and reservation tag are pushed to remote repository."""
        project_dir, db_name, patch_id, remote_repo = first_patch

        # Extract numeric ID from patch_id (e.g., "1-first-patch" -> "1")
        numeric_id = patch_id.split('-')[0]
        tag_name = f"ho-patch/{numeric_id}"

        # Verify remote branch exists
        result = subprocess.run(
            ["git", "ls-remote", "--heads", "origin", f"ho-patch/{patch_id}"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert f"ho-patch/{patch_id}" in result.stdout, (
            f"Remote branch ho-patch/{patch_id} not found"
        )

        # Verify reservation tag exists with numeric ID only
        result = subprocess.run(
            ["git", "ls-remote", "--tags", "origin"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert tag_name in result.stdout, (
            f"Reservation tag {tag_name} not found on remote"
        )

        # Extract tag commit SHA from ls-remote output
        tag_line = [line for line in result.stdout.split('\n') if tag_name in line][0]
        tag_commit_sha = tag_line.split()[0]

        # Verify tag points to commit containing Patches/<patch_id>/
        result = subprocess.run(
            ["git", "ls-tree", "-r", tag_commit_sha, "--name-only"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        committed_files = result.stdout.strip().split('\n')

        assert f"Patches/{patch_id}/README.md" in committed_files, (
            f"Tag {tag_name} should point to commit with Patches/{patch_id}/README.md"
        )