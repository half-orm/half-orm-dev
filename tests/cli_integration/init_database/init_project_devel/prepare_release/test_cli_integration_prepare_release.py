"""
Integration tests for 'half_orm dev prepare-release' CLI command.

Tests end-to-end release preparation via subprocess with real database.
Verifies stage file creation, Git operations, version calculation, and error handling.
"""

import pytest
import subprocess
import re
from pathlib import Path


@pytest.mark.integration
class TestPrepareReleaseGitStructure:
    """Test Git repository state after prepare-release."""

    def test_prepare_release_creates_stage_file(self, prepared_release):
        """Test that prepare-release creates stage file in releases/ directory."""
        project_dir, db_name, version, stage_file, _ = prepared_release

        # Verify stage file exists
        assert stage_file.exists(), f"Stage file {stage_file} should exist"
        assert stage_file.is_file(), "Stage file should be a regular file"

        # Verify file is in releases/ directory
        assert stage_file.parent.name == "releases", "Stage file should be in releases/ directory"

        # Verify filename format (X.Y.Z-stage.txt)
        assert stage_file.name == f"{version}-stage.txt", f"Filename should be {version}-stage.txt"

    def test_prepare_release_commits_to_ho_prod(self, prepared_release):
        """Test that prepare-release creates commit on ho-prod branch."""
        project_dir, db_name, version, stage_file, _ = prepared_release

        # Verify still on ho-prod branch
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "ho-prod", "Should be on ho-prod branch"

        # Verify commit exists with stage file
        result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        commit_message = result.stdout.strip()

        # Commit message should mention version and stage
        assert version in commit_message, f"Commit should mention version {version}"
        assert "stage" in commit_message.lower(), "Commit should mention 'stage'"

    def test_prepare_release_stages_file_in_commit(self, prepared_release):
        """Test that stage file is included in the commit."""
        project_dir, db_name, version, stage_file, _ = prepared_release

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


@pytest.mark.integration
class TestPrepareReleaseStageFileContent:
    """Test stage file content and format."""

    def test_stage_file_is_empty(self, prepared_release):
        """Test that newly created stage file is empty (ready for patches)."""
        project_dir, db_name, version, stage_file, _ = prepared_release

        # Read stage file content
        content = stage_file.read_text()

        # Should be empty (no patches yet)
        assert content == "", "Stage file should be empty initially"

    def test_stage_file_has_correct_format(self, prepared_release):
        """Test stage file naming follows X.Y.Z-stage.txt format."""
        project_dir, db_name, version, stage_file, _ = prepared_release

        # Verify filename matches pattern
        pattern = r'^\d+\.\d+\.\d+-stage\.txt$'
        assert re.match(pattern, stage_file.name), (
            f"Filename {stage_file.name} should match pattern X.Y.Z-stage.txt"
        )


@pytest.mark.integration
class TestPrepareReleaseVersionCalculation:
    """Test version calculation from production version."""

    def test_patch_increment_from_production(self, devel_project):
        """Test patch increment calculates correct next version."""
        project_dir, db_name, remote_repo = devel_project

        # Production version is 0.0.0 (from model/schema-0.0.0.sql)
        # Patch increment should create 0.0.1

        # Execute prepare-release with patch increment
        result = subprocess.run(
            ["half_orm", "dev", "prepare-release", "patch"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )

        assert result.returncode == 0, f"Command should succeed: {result.stderr}"

        # Verify 0.0.1-stage.txt was created
        stage_file = project_dir / "releases" / "0.0.1-stage.txt"
        assert stage_file.exists(), "Should create 0.0.1-stage.txt (patch from 0.0.0)"

        # Cleanup
        stage_file.unlink()
        subprocess.run(
            ["git", "reset", "--hard", "HEAD~1"],
            cwd=str(project_dir),
            capture_output=True
        )

    def test_minor_increment_from_production(self, devel_project):
        """Test minor increment calculates correct next version."""
        project_dir, db_name, remote_repo = devel_project

        # Production version is 0.0.0
        # Minor increment should create 0.1.0

        # Execute prepare-release with minor increment
        result = subprocess.run(
            ["half_orm", "dev", "prepare-release", "minor"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )

        assert result.returncode == 0, f"Command should succeed: {result.stderr}"

        # Verify 0.1.0-stage.txt was created
        stage_file = project_dir / "releases" / "0.1.0-stage.txt"
        assert stage_file.exists(), "Should create 0.1.0-stage.txt (minor from 0.0.0)"

        # Cleanup
        stage_file.unlink()
        subprocess.run(
            ["git", "reset", "--hard", "HEAD~1"],
            cwd=str(project_dir),
            capture_output=True
        )

    def test_major_increment_from_production(self, devel_project):
        """Test major increment calculates correct next version."""
        project_dir, db_name, remote_repo = devel_project

        # Production version is 0.0.0
        # Major increment should create 1.0.0

        # Execute prepare-release with major increment
        result = subprocess.run(
            ["half_orm", "dev", "prepare-release", "major"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )

        assert result.returncode == 0, f"Command should succeed: {result.stderr}"

        # Verify 1.0.0-stage.txt was created
        stage_file = project_dir / "releases" / "1.0.0-stage.txt"
        assert stage_file.exists(), "Should create 1.0.0-stage.txt (major from 0.0.0)"

        # Cleanup
        stage_file.unlink()
        subprocess.run(
            ["git", "reset", "--hard", "HEAD~1"],
            cwd=str(project_dir),
            capture_output=True
        )


@pytest.mark.integration
class TestPrepareReleaseErrorHandling:
    """Test error handling and validation."""

    def test_error_if_stage_already_exists(self, prepared_release):
        """Test error when trying to prepare same version twice."""
        project_dir, db_name, version, stage_file, _ = prepared_release

        # Stage file already exists from fixture
        assert stage_file.exists()

        # Try to prepare same version again
        result = subprocess.run(
            ["half_orm", "dev", "prepare-release", "patch"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )

        # Should fail
        assert result.returncode != 0, "Should fail when stage file already exists"
        assert "already exists" in result.stderr.lower() or "exists" in result.stderr.lower(), (
            "Error message should mention file already exists"
        )

    def test_error_if_not_on_ho_prod(self, prepared_release):
        """Test error when not on ho-prod branch."""
        project_dir, db_name, version, stage_file, _ = prepared_release

        # Create and checkout to different branch
        subprocess.run(
            ["git", "checkout", "-b", "test-branch"],
            cwd=str(project_dir),
            capture_output=True
        )

        try:
            # Try to prepare release from wrong branch
            result = subprocess.run(
                ["half_orm", "dev", "prepare-release", "patch"],
                cwd=str(project_dir),
                capture_output=True,
                text=True
            )

            # Should fail
            assert result.returncode != 0, "Should fail when not on ho-prod branch"
            assert "ho-prod" in result.stderr.lower(), (
                "Error message should mention ho-prod branch requirement"
            )

        finally:
            # Cleanup: return to ho-prod
            subprocess.run(
                ["git", "checkout", "ho-prod"],
                cwd=str(project_dir),
                capture_output=True
            )
            subprocess.run(
                ["git", "branch", "-D", "test-branch"],
                cwd=str(project_dir),
                capture_output=True
            )


@pytest.mark.integration
class TestPrepareReleaseMultipleLevels:
    """Test multiple stage files for different increment levels."""

    def test_cannot_create_two_patches_same_level(self, prepared_release):
        """Test error when trying to create second patch-level stage."""
        project_dir, db_name, version, stage_file, _ = prepared_release

        # 0.0.1-stage.txt already exists (patch level)
        assert stage_file.exists()
        assert version == "0.0.1"

        # Try to prepare another patch-level release (would be 0.0.2)
        result = subprocess.run(
            ["half_orm", "dev", "prepare-release", "patch"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )

        # Should fail because 0.0.1-stage already exists
        assert result.returncode != 0, "Should fail when patch-level stage already exists"
        assert "already exists" in result.stderr.lower() or "exists" in result.stderr.lower(), (
            "Error message should indicate stage file already exists"
        )

    def test_can_prepare_different_levels_simultaneously(self, prepared_release):
        """Test that different increment levels can coexist (patch + minor + major)."""
        project_dir, db_name, version, stage_file, _ = prepared_release

        # 0.0.1-stage.txt already exists (patch level)
        assert stage_file.exists()
        assert version == "0.0.1"

        try:
            # Prepare minor-level release (should succeed, different level)
            result = subprocess.run(
                ["half_orm", "dev", "prepare-release", "minor"],
                cwd=str(project_dir),
                capture_output=True,
                text=True
            )

            assert result.returncode == 0, f"Minor release should succeed: {result.stderr}"

            # Verify 0.1.0-stage.txt was created
            minor_stage = project_dir / "releases" / "0.1.0-stage.txt"
            assert minor_stage.exists(), "Should create 0.1.0-stage.txt (minor level)"

            # Prepare major-level release (should succeed, different level)
            result = subprocess.run(
                ["half_orm", "dev", "prepare-release", "major"],
                cwd=str(project_dir),
                capture_output=True,
                text=True
            )

            assert result.returncode == 0, f"Major release should succeed: {result.stderr}"

            # Verify 1.0.0-stage.txt was created
            major_stage = project_dir / "releases" / "1.0.0-stage.txt"
            assert major_stage.exists(), "Should create 1.0.0-stage.txt (major level)"

            # All three levels should coexist
            assert stage_file.exists(), "Patch-level stage should still exist"
            assert minor_stage.exists(), "Minor-level stage should exist"
            assert major_stage.exists(), "Major-level stage should exist"

        finally:
            # Cleanup additional stages
            minor_stage = project_dir / "releases" / "0.1.0-stage.txt"
            major_stage = project_dir / "releases" / "1.0.0-stage.txt"

            if minor_stage.exists():
                minor_stage.unlink()
            if major_stage.exists():
                major_stage.unlink()

            # Reset commits (2 additional commits to remove)
            subprocess.run(
                ["git", "reset", "--hard", "HEAD~2"],
                cwd=str(project_dir),
                capture_output=True
            )


@pytest.mark.integration
class TestPrepareReleaseExitCode:
    """Test successful command exit code."""

    def test_prepare_release_success_exit_code(self, prepared_release):
        """Test that prepare-release completes successfully with exit code 0."""
        # Fixture already verified returncode == 0
        # This test documents the expected behavior
        project_dir, db_name, version, stage_file, _ = prepared_release

        # Verify stage file exists (proof of success)
        assert stage_file.exists(), "Stage file should exist after successful prepare-release"

        # Verify commit was created
        result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert version in result.stdout, f"Latest commit should mention version {version}"
