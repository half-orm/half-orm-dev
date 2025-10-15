"""
Pytest fixtures for promote-to-rc CLI integration tests.

Provides:
- release_with_rc: Stage release promoted to RC via CLI
"""

import pytest
import subprocess
from pathlib import Path


@pytest.fixture
def release_with_rc(release_with_first_patch):
    """
    Promote stage release to RC via CLI.

    Depends on:
        - release_with_first_patch: Stage release with one patch

    Executes:
        git checkout ho-prod
        half_orm dev promote-to-rc

    Yields:
        tuple: (project_dir: Path, database_name: str, patch_id: str,
                version: str, rc_file: Path, remote_repo: Path)

    Cleanup:
        - Rename RC file back to stage
        - Reset ho-prod to before promote commit
        - Restore archived patch branch
        - Remove code merge from ho-prod

    Note:
        This is the CRITICAL operation where code enters ho-prod.
        Tests verify:
        - File rename: 1.3.5-stage.txt → 1.3.5-rc1.txt
        - Code merge: ho-release/1.3.5/* → ho-prod
        - Branch cleanup: ho-patch/* deleted
    """
    project_dir, db_name, patch_id, version, stage_file, remote_repo = release_with_first_patch

    # Ensure we're on ho-prod branch
    subprocess.run(
        ["git", "checkout", "ho-prod"],
        cwd=str(project_dir),
        capture_output=True,
        text=True
    )

    # Execute promote-to-rc CLI command
    result = subprocess.run(
        ["half_orm", "dev", "promote-to-rc"],
        cwd=str(project_dir),
        capture_output=True,
        text=True
    )

    assert result.returncode == 0, (
        f"promote-to-rc command failed:\n"
        f"STDOUT: {result.stdout}\n"
        f"STDERR: {result.stderr}"
    )

    # RC file should now exist
    rc_file = project_dir / "releases" / f"{version}-rc1.txt"
    assert rc_file.exists(), f"RC file {rc_file} should exist after promotion"

    # Yield RC info to tests
    yield project_dir, db_name, patch_id, version, rc_file, remote_repo

    # === Cleanup ===

    # 1. Rename RC file back to stage
    if rc_file.exists():
        rc_file.rename(stage_file)

    # 2. Reset ho-prod to before promote commit
    # The promote creates one commit, so HEAD~1
    subprocess.run(
        ["git", "reset", "--hard", "HEAD~1"],
        cwd=str(project_dir),
        capture_output=True,
        text=True
    )

    # 3. Restore archived patch branch (was deleted by promote-to-rc)
    _restore_archived_branch(project_dir, version, patch_id)


@pytest.fixture
def release_with_rc2(release_with_rc, second_patch):
    """
    Promote second RC (rc2) after adding another patch to stage.

    Workflow:
        1. Start with release_with_rc (already have rc1)
        2. Prepare NEW stage file (same version)
        3. Add second patch to stage (via add-to-release)
        4. Promote stage to rc2
    """
    project_dir_rc, db_name_rc, first_patch_id, version, rc1_file, remote_repo = release_with_rc
    project_dir_patch, db_name_patch, second_patch_id, _ = second_patch

    # Verify same project
    assert project_dir_rc == project_dir_patch
    project_dir = project_dir_rc

    # Ensure on ho-prod
    subprocess.run(
        ["git", "checkout", "ho-prod"],
        cwd=str(project_dir),
        capture_output=True,
        text=True
    )

    # NOUVELLE ÉTAPE : Recréer le stage file (car il a été renommé en rc1)
    # Use prepare-release to create new stage file
    result = subprocess.run(
        ["half_orm", "dev", "prepare-release", "patch"],
        cwd=str(project_dir),
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0, (
        f"prepare-release failed:\n{result.stderr}"
    )

    # Verify stage file was created
    stage_file = project_dir / "releases" / f"{version}-stage.txt"
    assert stage_file.exists(), "Stage file should be created by prepare-release"

    # Add second patch to stage release via add-to-release
    result = subprocess.run(
        ["half_orm", "dev", "add-to-release", second_patch_id],
        cwd=str(project_dir),
        capture_output=True,
        text=True
    )

    assert result.returncode == 0, (
        f"add-to-release failed for second patch:\n{result.stderr}"
    )

    # Promote stage to rc2
    result = subprocess.run(
        ["half_orm", "dev", "promote-to-rc"],
        cwd=str(project_dir),
        capture_output=True,
        text=True
    )

    assert result.returncode == 0, (
        f"promote-to-rc for rc2 failed:\n{result.stderr}"
    )

    # RC2 file should now exist
    rc2_file = project_dir / "releases" / f"{version}-rc2.txt"
    assert rc2_file.exists(), f"RC2 file should exist"

    # Yield info to tests
    yield (project_dir, db_name_rc, first_patch_id, second_patch_id, 
           version, rc2_file, rc1_file, remote_repo)

    # === Cleanup ===

    # Remove rc2 file
    if rc2_file.exists():
        rc2_file.unlink()

    # Reset commits (prepare-release + add-to-release + promote-to-rc = 3 commits)
    subprocess.run(
        ["git", "reset", "--hard", "HEAD~3"],
        cwd=str(project_dir),
        capture_output=True,
        text=True
    )

    # Restore second patch branch
    _restore_archived_branch(project_dir, version, second_patch_id)


def _restore_archived_branch(project_dir: Path, version: str, patch_id: str) -> None:
    """
    Restore ho-patch branch if it was archived to ho-release/.

    Helper function for cleanup in fixtures.

    Args:
        project_dir: Project directory path
        version: Version string (e.g., "0.0.1")
        patch_id: Patch identifier (e.g., "1-first-patch")
    """
    archived_branch = f"ho-release/{version}/{patch_id}"
    patch_branch = f"ho-patch/{patch_id}"

    # Check if archived branch exists
    result = subprocess.run(
        ["git", "show-ref", "--verify", f"refs/heads/{archived_branch}"],
        cwd=str(project_dir),
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        # Archived branch exists, restore it to ho-patch
        subprocess.run(
            ["git", "branch", "-m", archived_branch, patch_branch],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )

        # Push restored branch to remote
        subprocess.run(
            ["git", "push", "origin", patch_branch],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )

        # Delete archived branch from remote
        subprocess.run(
            ["git", "push", "origin", "--delete", archived_branch],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
