"""
Pytest fixtures for init-project CLI integration tests (development mode).

Provides:
- devel_project: Creates a complete halfORM project via CLI with development mode
"""

import pytest
import subprocess
import shutil
from pathlib import Path


@pytest.fixture
def devel_project(initialized_database, tmp_path):
    """
    Create a complete halfORM development project via CLI with local Git remote.

    Depends on initialized_database fixture (DB with half_orm metadata).

    Creates:
        - Local bare Git repository as remote (remote_repo.git)
        - halfORM project initialized with real Git remote

    Executes:
        half_orm dev init-project <db_name> --git-origin=file:///.../remote_repo.git

    Yields:
        tuple: (project_dir: Path, database_name: str, remote_repo: Path)
            - project_dir: Path to created project directory
            - database_name: Name of the database used
            - remote_repo: Path to bare Git repository (remote)

    Cleanup:
        - Removes project directory
        - Removes remote repository
        - Database cleanup handled by initialized_database fixture

    Example:
        def test_something(devel_project):
            project_dir, db_name, remote_repo = devel_project
            assert (project_dir / ".git").exists()
            assert remote_repo.exists()
    """
    database_name = initialized_database[1]

    # Use database name as project name for simplicity
    project_name = database_name

    # Create local bare Git repository to serve as remote
    remote_repo = tmp_path / "remote_repo.git"
    remote_repo.mkdir()

    # Initialize bare repository
    result = subprocess.run(
        ["git", "init", "--bare"],
        cwd=str(remote_repo),
        capture_output=True,
        text=True
    )
    assert result.returncode == 0, f"Failed to create bare repository: {result.stderr}"

    # Create project in temporary directory
    project_dir = tmp_path / project_name

    # Use local bare repository as git-origin (file:// protocol)
    git_origin = f"file://{remote_repo.absolute()}"

    # Execute init-project CLI command
    cmd = [
        "half_orm", "dev", "init-project",
        project_name,
        "--git-origin", git_origin
    ]

    result = subprocess.run(
        cmd,
        cwd=str(tmp_path),
        capture_output=True,
        text=True
    )

    # Verify command succeeded
    assert result.returncode == 0, (
        f"init-project command failed:\n"
        f"STDOUT: {result.stdout}\n"
        f"STDERR: {result.stderr}"
    )

    # Verify project directory was created
    assert project_dir.exists(), f"Project directory {project_dir} was not created"

    # Yield project info to tests
    yield project_dir, database_name, remote_repo

    # === Cleanup ===

    # Remove project directory
    if project_dir.exists():
        shutil.rmtree(project_dir)

    # Remove remote repository
    if remote_repo.exists():
        shutil.rmtree(remote_repo)

    # Database cleanup is handled by initialized_database fixture
