"""
Pytest fixtures for create-patch CLI integration tests.

Provides:
- first_patch: Creates first patch on initialized project via CLI
"""

import pytest
import subprocess
from pathlib import Path


@pytest.fixture
def first_patch(devel_project):
    """
    Create first patch on initialized halfORM project via CLI.

    Depends on devel_project fixture (initialized project on ho-prod branch).

    Executes:
        half_orm dev create-patch "1-first-patch"

    Yields:
        tuple: (project_dir: Path, database_name: str, patch_id: str, remote_repo: Path)
            - project_dir: Path to project directory
            - database_name: Name of the database
            - patch_id: ID of created patch ("1-first-patch")
            - remote_repo: Path to bare Git repository (remote)

    Cleanup:
        - Switch back to ho-prod branch
        - Delete local ho-patch/1-first-patch branch
        - Delete remote branch (if exists)
        - Project cleanup handled by devel_project fixture

    Example:
        def test_something(first_patch):
            project_dir, db_name, patch_id, remote_repo = first_patch
            assert (project_dir / "Patches" / patch_id).exists()
    """
    project_dir, database_name, remote_repo = devel_project

    patch_id = "1-first-patch"
    branch_name = f"ho-patch/{patch_id}"

    # Execute create-patch CLI command
    cmd = [
        "half_orm", "dev", "create-patch",
        patch_id
    ]

    result = subprocess.run(
        cmd,
        cwd=str(project_dir),
        capture_output=True,
        text=True
    )

    # Verify command succeeded
    assert result.returncode == 0, (
        f"create-patch command failed:\n"
        f"STDOUT: {result.stdout}\n"
        f"STDERR: {result.stderr}"
    )

    # Verify we're on the new patch branch
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=str(project_dir),
        capture_output=True,
        text=True
    )
    assert result.stdout.strip() == branch_name, (
        f"Should be on {branch_name}, but on {result.stdout.strip()}"
    )

    # Yield patch info to tests
    yield project_dir, database_name, patch_id, remote_repo

    # === Cleanup ===

    # Switch back to ho-prod
    subprocess.run(
        ["git", "checkout", "ho-prod"],
        cwd=str(project_dir),
        capture_output=True,
        text=True
    )

    # Delete local patch branch
    subprocess.run(
        ["git", "branch", "-D", branch_name],
        cwd=str(project_dir),
        capture_output=True,
        text=True
    )

    # Delete remote branch if exists
    subprocess.run(
        ["git", "push", "origin", "--delete", branch_name],
        cwd=str(project_dir),
        capture_output=True,
        text=True
    )

    # Project cleanup is handled by devel_project fixture
