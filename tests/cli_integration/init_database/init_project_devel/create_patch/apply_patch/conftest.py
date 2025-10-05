"""
Pytest fixtures for apply-patch CLI integration tests.

Provides:
- applied_patch: Creates and applies first patch via CLI
"""

import pytest
import subprocess
from pathlib import Path


@pytest.fixture
def applied_patch(first_patch):
    """
    Create and apply first patch on halfORM project via CLI.
    
    Depends on first_patch fixture (patch branch created, on ho-patch/1-first-patch).
    
    Creates:
        - 01_create_table.sql in Patches/1-first-patch/
        - Simple test table: test_users(id, name)
    
    Executes:
        half_orm dev apply-patch
    
    Yields:
        tuple: (project_dir: Path, database_name: str, patch_id: str, sql_file: Path, remote_repo: Path)
            - project_dir: Path to project directory
            - database_name: Name of the database
            - patch_id: ID of the patch ("1-first-patch")
            - sql_file: Path to created SQL file
            - remote_repo: Path to bare Git repository (remote)
    
    Cleanup:
        - All cleanup handled by first_patch fixture
    
    Example:
        def test_something(applied_patch):
            project_dir, db_name, patch_id, sql_file, _ = applied_patch
            # Verify table exists in database
    """
    project_dir, database_name, patch_id, remote_repo = first_patch
    
    # Create Patches/<patch_id>/ directory (should exist from first_patch)
    patch_dir = project_dir / "Patches" / patch_id
    assert patch_dir.exists(), f"Patches/{patch_id}/ should exist from first_patch"
    
    # Create simple SQL file for testing
    sql_file = patch_dir / "01_create_table.sql"
    sql_content = """-- Create test table for integration testing
CREATE TABLE test_users (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL
);
"""
    sql_file.write_text(sql_content)
    
    # Execute apply-patch CLI command
    cmd = ["half_orm", "dev", "apply-patch"]
    
    result = subprocess.run(
        cmd,
        cwd=str(project_dir),
        capture_output=True,
        text=True
    )
    
    # Verify command succeeded
    assert result.returncode == 0, (
        f"apply-patch command failed:\n"
        f"STDOUT: {result.stdout}\n"
        f"STDERR: {result.stderr}"
    )
    
    # Yield patch application info to tests
    yield project_dir, database_name, patch_id, sql_file, remote_repo
    
    # === Cleanup ===
    # All cleanup handled by first_patch fixture
    # (database, branches, project directory)
