"""
Pytest fixtures for apply-patch CLI integration tests.

Provides autonomous fixture that doesn't depend on other integration fixtures.
Creates complete environment from scratch for each test.
"""

import pytest
import subprocess
import shutil
import os
from pathlib import Path


@pytest.fixture(scope="function")
def standalone_applied_patch(tmp_path):
    """
    Autonomous fixture for apply-patch integration tests.

    Creates complete test environment from scratch:
    - Unique temporary database with half_orm metadata
    - Git repository with remote
    - halfORM project initialized
    - Patch branch created
    - SQL file added
    - Patch applied

    Does NOT depend on initialized_database, devel_project, or first_patch fixtures.
    Complete isolation for each test.

    Yields:
        tuple: (project_dir: Path, db_name: str, patch_id: str)

    Cleanup:
        - Drops database (with --force)
        - Removes project directory
        - Removes remote repository

    Example:
        def test_something(standalone_applied_patch):
            project_dir, db_name, patch_id = standalone_applied_patch
            # Test with fully applied patch
    """
    # Generate unique database name
    db_name = f"hop_test_apply_{os.getpid()}_{id(tmp_path)}"
    patch_id = "1-test-patch"
    project_dir = tmp_path / db_name
    remote_repo = tmp_path / "remote.git"

    try:
        # === 1. Create database with metadata ===

        # Install half_orm metadata
        # Use half_orm dev init-database to install metadata
        result = subprocess.run(
            [
                "half_orm", "dev", "init-database", db_name,
                "--create-db",
                "--user", "halftest",
                "--password", "halftest",
                "--host", "localhost",
                "--port", "5432"
            ],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"init-database failed: {result.stderr}"

        # === 2. Create bare Git repository (remote) ===

        remote_repo.mkdir()
        result = subprocess.run(
            ["git", "init", "--bare"],
            cwd=str(remote_repo),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"git init --bare failed: {result.stderr}"

        # === 3. Initialize halfORM project ===

        git_origin = f"file://{remote_repo.absolute()}"
        result = subprocess.run(
            [
                "half_orm", "dev", "init-project",
                db_name,
                "--git-origin", git_origin
            ],
            cwd=str(tmp_path),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"init-project failed: {result.stderr}"
        assert project_dir.exists(), f"Project directory {project_dir} not created"

        # === 4. Create patch branch ===

        result = subprocess.run(
            ["half_orm", "dev", "create-patch", patch_id],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"create-patch failed: {result.stderr}"

        # === 5. Add SQL file to patch ===

        patch_dir = project_dir / "Patches" / patch_id
        assert patch_dir.exists(), f"Patch directory {patch_dir} not created"

        sql_file = patch_dir / "01_create_table.sql"
        sql_content = """-- Test table for apply-patch integration tests
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL
);
"""
        sql_file.write_text(sql_content)

        # === 6. Apply patch ===

        result = subprocess.run(
            ["half_orm", "dev", "apply-patch"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, (
            f"apply-patch failed:\n"
            f"STDOUT: {result.stdout}\n"
            f"STDERR: {result.stderr}"
        )

        # === Yield to test ===

        yield project_dir, db_name, patch_id

    finally:
        # === Cleanup ===

        # Drop database with --force (terminates connections)
        subprocess.run(
            ["dropdb", "--force", db_name],
            capture_output=True,
            text=True
        )

        # Remove project directory
        if project_dir.exists():
            shutil.rmtree(project_dir)

        # Remove remote repository
        if remote_repo.exists():
            shutil.rmtree(remote_repo)