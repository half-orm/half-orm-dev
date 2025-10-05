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
    Create a complete halfORM development project via CLI.
    
    Depends on initialized_database fixture (DB with half_orm metadata).
    
    Executes:
        half_orm dev init-project <db_name> --git-origin=<url>
    
    Yields:
        tuple: (project_dir: Path, database_name: str)
            - project_dir: Path to created project directory
            - database_name: Name of the database used
    
    Cleanup:
        - Removes project directory
        - Removes .hop/config if exists
        - Database cleanup handled by initialized_database fixture
    
    Example:
        def test_something(devel_project):
            project_dir, db_name = devel_project
            assert (project_dir / ".git").exists()
            assert (project_dir / "Patches").exists()
    """
    database_name = initialized_database
    
    # Use database name as project name for simplicity
    project_name = database_name
    
    # Create project in temporary directory
    project_dir = tmp_path / project_name
    
    # Prepare git-origin to avoid interactive prompt
    git_origin = f"https://github.com/test/{project_name}.git"
    
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
    yield project_dir, database_name
    
    # === Cleanup ===
    
    # Remove project directory
    if project_dir.exists():
        shutil.rmtree(project_dir)
    
    # Remove .hop/config if exists (created inside project_dir, already removed)
    # Note: .hop/config is inside project_dir, so already cleaned up
    
    # Database cleanup is handled by initialized_database fixture
