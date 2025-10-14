"""
Pytest fixtures for add-to-release CLI integration tests.

Provides:
- first_patch: Creates first patch on devel project
- second_patch: Creates second patch after first patch
- release_with_first_patch: Adds first patch to stage release
- release_with_second_patch: Adds second patch to stage release (depends on first)
"""

import pytest
import subprocess
from pathlib import Path


@pytest.fixture
def first_patch(prepared_release):
    """
    Create first patch on initialized halfORM project with prepared release.

    Depends on prepared_release fixture (project initialized + stage file created).

    Executes:
        git checkout ho-prod
        half_orm dev create-patch "1-first-patch"

    Yields:
        tuple: (project_dir: Path, database_name: str, patch_id: str, remote_repo: Path)

    Cleanup:
        - Switch back to ho-prod branch
        - Delete local ho-patch/1-first-patch branch
        - Delete remote branch (if exists)
    """
    project_dir, database_name, version, stage_file, remote_repo = prepared_release

    patch_id = "1-first-patch"
    branch_name = f"ho-patch/{patch_id}"

    # Checkout ho-prod first
    result = subprocess.run(
        ["git", "checkout", "ho-prod"],
        cwd=str(project_dir),
        capture_output=True,
        text=True
    )
    assert result.returncode == 0, f"Failed to checkout ho-prod: {result.stderr}"

    # Execute create-patch CLI command
    cmd = ["half_orm", "dev", "create-patch", patch_id]

    result = subprocess.run(
        cmd,
        cwd=str(project_dir),
        capture_output=True,
        text=True
    )

    assert result.returncode == 0, (
        f"create-patch command failed:\n"
        f"STDOUT: {result.stdout}\n"
        f"STDERR: {result.stderr}"
    )

    # Create mock patch with SQL + Python code + tests (without apply-patch)
    patch_dir = project_dir / "Patches" / patch_id

    # 1. Add SQL file
    sql_file = patch_dir / "01_create_table.sql"
    sql_file.write_text("CREATE TABLE test_table (id SERIAL PRIMARY KEY, name TEXT);")

    # 2. Create mock Python code (simulates generated code)
    db_package_dir = project_dir / database_name
    public_schema_dir = db_package_dir / "public"
    public_schema_dir.mkdir(parents=True, exist_ok=True)

    # Create __init__.py files
    (db_package_dir / "__init__.py").touch()
    (public_schema_dir / "__init__.py").touch()

    # Create mock model file
    model_file = public_schema_dir / "test_table.py"
    model_file.write_text('''"""Mock generated model for test_table."""

class TestTable:
    """Mock model class for test_table."""

    def __init__(self):
        self.id = None
        self.name = None
''')

    # 3. Create mock test file (minimal test that passes)
    tests_dir = project_dir / "tests"
    tests_dir.mkdir(exist_ok=True)
    (tests_dir / "__init__.py").touch()

    test_file = tests_dir / f"test_{patch_id.replace('-', '_')}.py"
    test_file.write_text(f'''"""Mock tests for patch {patch_id}."""

import pytest

def test_patch_{patch_id.replace('-', '_')}_basic():
    """Basic test that always passes."""
    assert True

def test_patch_{patch_id.replace('-', '_')}_table_exists():
    """Mock test for table existence."""
    # In real scenario, this would check database
    assert True
''')

    # 4. Commit all files (SQL + generated code + tests)
    subprocess.run(
        ["git", "add", "."],
        cwd=str(project_dir),
        capture_output=True,
        text=True
    )
    subprocess.run(
        ["git", "commit", "-m", f"Add mock patch {patch_id} with SQL, code, and tests"],
        cwd=str(project_dir),
        capture_output=True,
        text=True
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


@pytest.fixture
def second_patch(first_patch):
    """
    Create second patch on initialized halfORM project.

    Depends on first_patch fixture (first patch already created).

    Executes:
        git checkout ho-prod
        half_orm dev create-patch "2-second-patch"

    Yields:
        tuple: (project_dir: Path, database_name: str, patch_id: str, remote_repo: Path)

    Cleanup:
        - Switch back to ho-prod branch
        - Delete local ho-patch/2-second-patch branch
        - Delete remote branch (if exists)
    """
    project_dir, database_name, first_patch_id, remote_repo = first_patch

    patch_id = "2-second-patch"
    branch_name = f"ho-patch/{patch_id}"

    # Checkout ho-prod first
    result = subprocess.run(
        ["git", "checkout", "ho-prod"],
        cwd=str(project_dir),
        capture_output=True,
        text=True
    )
    assert result.returncode == 0, f"Failed to checkout ho-prod: {result.stderr}"

    # Execute create-patch CLI command
    cmd = ["half_orm", "dev", "create-patch", patch_id]

    result = subprocess.run(
        cmd,
        cwd=str(project_dir),
        capture_output=True,
        text=True
    )

    assert result.returncode == 0, (
        f"create-patch command failed:\n"
        f"STDOUT: {result.stdout}\n"
        f"STDERR: {result.stderr}"
    )

    # Create mock patch with SQL + Python code + tests (without apply-patch)
    patch_dir = project_dir / "Patches" / patch_id

    # 1. Add SQL file (different table to avoid conflict)
    sql_file = patch_dir / "01_create_table.sql"
    sql_file.write_text("CREATE TABLE test_table_2 (id SERIAL PRIMARY KEY, description TEXT);")

    # 2. Create mock Python code (simulates generated code)
    db_package_dir = project_dir / database_name
    public_schema_dir = db_package_dir / "public"
    public_schema_dir.mkdir(parents=True, exist_ok=True)

    # Create __init__.py files if not exist
    (db_package_dir / "__init__.py").touch()
    (public_schema_dir / "__init__.py").touch()

    # Create mock model file
    model_file = public_schema_dir / "test_table_2.py"
    model_file.write_text('''"""Mock generated model for test_table_2."""

class TestTable2:
    """Mock model class for test_table_2."""

    def __init__(self):
        self.id = None
        self.description = None
''')

    # 3. Create mock test file (minimal test that passes)
    tests_dir = project_dir / "tests"
    tests_dir.mkdir(exist_ok=True)
    (tests_dir / "__init__.py").touch()

    test_file = tests_dir / f"test_{patch_id.replace('-', '_')}.py"
    test_file.write_text(f'''"""Mock tests for patch {patch_id}."""

import pytest

def test_patch_{patch_id.replace('-', '_')}_basic():
    """Basic test that always passes."""
    assert True

def test_patch_{patch_id.replace('-', '_')}_table_2_exists():
    """Mock test for table_2 existence."""
    # In real scenario, this would check database
    assert True
''')

    # 4. Commit all files (SQL + generated code + tests)
    subprocess.run(
        ["git", "add", "."],
        cwd=str(project_dir),
        capture_output=True,
        text=True
    )
    subprocess.run(
        ["git", "commit", "-m", f"Add mock patch {patch_id} with SQL, code, and tests"],
        cwd=str(project_dir),
        capture_output=True,
        text=True
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


@pytest.fixture
def release_with_first_patch(prepared_release, first_patch):
    """
    Add first patch to stage release via CLI.

    Depends on:
    - prepared_release: Stage file created (0.0.1-stage.txt)
    - first_patch: First patch created (1-first-patch)

    Executes:
        git checkout ho-prod
        half_orm dev add-to-release "1-first-patch"

    Yields:
        tuple: (project_dir: Path, database_name: str, patch_id: str,
                version: str, stage_file: Path, remote_repo: Path)

    Cleanup:
        - Removes patch from stage file
        - Resets ho-prod to before add-to-release commit
        - Restores ho-patch branch (if archived)
    """
    project_dir_release, db_name, version, stage_file, remote_repo = prepared_release
    project_dir_patch, db_name_patch, patch_id, _ = first_patch

    # Verify same project
    assert project_dir_release == project_dir_patch

    project_dir = project_dir_release

    # Ensure we're on ho-prod branch
    subprocess.run(
        ["git", "checkout", "ho-prod"],
        cwd=str(project_dir),
        capture_output=True,
        text=True
    )

    # Execute add-to-release CLI command
    cmd = ["half_orm", "dev", "add-to-release", patch_id]

    result = subprocess.run(
        cmd,
        cwd=str(project_dir),
        capture_output=True,
        text=True
    )

    assert result.returncode == 0, (
        f"add-to-release command failed:\n"
        f"STDOUT: {result.stdout}\n"
        f"STDERR: {result.stderr}"
    )

    # Yield release info to tests
    yield project_dir, db_name, patch_id, version, stage_file, remote_repo

    # === Cleanup ===

    # Remove patch from stage file (restore to empty)
    stage_file.write_text("")

    # Reset ho-prod to before add-to-release commit
    subprocess.run(
        ["git", "reset", "--hard", "HEAD~1"],
        cwd=str(project_dir),
        capture_output=True,
        text=True
    )

    # Restore ho-patch branch if archived
    _restore_archived_branch(project_dir, version, patch_id)


@pytest.fixture
def release_with_second_patch(release_with_first_patch, second_patch):
    """
    Add second patch to stage release (already contains first patch).

    Depends on:
    - release_with_first_patch: First patch already in stage
    - second_patch: Second patch created

    Executes:
        git checkout ho-prod
        half_orm dev add-to-release "2-second-patch"

    Yields:
        tuple: (project_dir: Path, database_name: str, patch_id: str,
                version: str, stage_file: Path, remote_repo: Path, first_patch_id: str)

    Cleanup:
        - Removes second patch from stage file
        - Resets ho-prod to before second add-to-release commit
        - Restores ho-patch branch (if archived)
    """
    project_dir_release, db_name, first_patch_id, version, stage_file, remote_repo = release_with_first_patch
    project_dir_patch, db_name_patch, patch_id, _ = second_patch

    # Verify same project
    assert project_dir_release == project_dir_patch

    project_dir = project_dir_release

    # Ensure we're on ho-prod branch
    subprocess.run(
        ["git", "checkout", "ho-prod"],
        cwd=str(project_dir),
        capture_output=True,
        text=True
    )

    # Execute add-to-release CLI command for second patch
    cmd = ["half_orm", "dev", "add-to-release", patch_id]

    result = subprocess.run(
        cmd,
        cwd=str(project_dir),
        capture_output=True,
        text=True
    )

    assert result.returncode == 0, (
        f"add-to-release command failed:\n"
        f"STDOUT: {result.stdout}\n"
        f"STDERR: {result.stderr}"
    )

    # Yield release info to tests
    yield project_dir, db_name, patch_id, version, stage_file, remote_repo, first_patch_id

    # === Cleanup ===

    # Remove second patch from stage file (keep first patch)
    stage_file.write_text(f"{first_patch_id}\n")

    # Reset ho-prod to before second add-to-release commit
    subprocess.run(
        ["git", "reset", "--hard", "HEAD~1"],
        cwd=str(project_dir),
        capture_output=True,
        text=True
    )

    # Restore ho-patch branch if archived
    _restore_archived_branch(project_dir, version, patch_id)


def _restore_archived_branch(project_dir: Path, version: str, patch_id: str) -> None:
    """
    Restore ho-patch branch if it was archived to ho-release/.

    Helper function for cleanup in fixtures.
    """
    archived_branch = f"ho-release/{version}/{patch_id}"
    result = subprocess.run(
        ["git", "show-ref", "--verify", f"refs/heads/{archived_branch}"],
        cwd=str(project_dir),
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        # Archived branch exists, restore original ho-patch branch
        original_branch = f"ho-patch/{patch_id}"

        # Create branch at the archived location
        subprocess.run(
            ["git", "branch", original_branch, archived_branch],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )

        # Delete archived branch
        subprocess.run(
            ["git", "branch", "-D", archived_branch],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )