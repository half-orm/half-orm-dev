"""
Pytest fixtures for prepare-release CLI integration tests.

Provides:
- prepared_release: Creates release stage file via CLI from devel project
"""

import pytest
import subprocess
from pathlib import Path


@pytest.fixture
def prepared_release(devel_project):
    """
    Create release stage file via CLI on initialized halfORM project.

    Depends on devel_project fixture (initialized project on ho-prod branch).

    Executes:
        half_orm dev prepare-release patch

    Yields:
        tuple: (project_dir: Path, database_name: str, version: str, 
                stage_file: Path, remote_repo: Path)
            - project_dir: Path to project directory
            - database_name: Name of the database
            - version: Release version created (e.g., "0.0.1")
            - stage_file: Path to created stage file
            - remote_repo: Path to bare Git repository (remote)

    Cleanup:
        - Removes stage file (if exists)
        - Resets ho-prod to before prepare-release commit
        - Project cleanup handled by devel_project fixture

    Example:
        def test_something(prepared_release):
            project_dir, db_name, version, stage_file, remote = prepared_release
            assert stage_file.exists()
    """
    project_dir, database_name, remote_repo = devel_project

    # Execute prepare-release CLI command (patch increment from 0.0.0)
    cmd = [
        "half_orm", "dev", "prepare-release",
        "patch"
    ]

    result = subprocess.run(
        cmd,
        cwd=str(project_dir),
        capture_output=True,
        text=True
    )

    # Verify command succeeded
    assert result.returncode == 0, (
        f"prepare-release command failed:\n"
        f"STDOUT: {result.stdout}\n"
        f"STDERR: {result.stderr}"
    )

    # Expected version: 0.0.1 (patch increment from 0.0.0 in model/schema-0.0.0.sql)
    version = "0.0.1"
    stage_file = project_dir / "releases" / f"{version}-stage.txt"

    # Verify stage file was created
    assert stage_file.exists(), (
        f"Stage file {stage_file} should be created"
    )

    # Verify we're still on ho-prod branch
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=str(project_dir),
        capture_output=True,
        text=True
    )
    assert result.stdout.strip() == "ho-prod", (
        f"Should still be on ho-prod after prepare-release"
    )

    # Yield release info to tests
    yield project_dir, database_name, version, stage_file, remote_repo

    # === Cleanup ===

    # Remove stage file (if still exists)
    if stage_file.exists():
        stage_file.unlink()

    # Reset ho-prod to before prepare-release commit
    # This undoes the "Prepare release X.Y.Z-stage" commit
    subprocess.run(
        ["git", "reset", "--hard", "HEAD~1"],
        cwd=str(project_dir),
        capture_output=True,
        text=True
    )

    # Project cleanup is handled by devel_project fixture
