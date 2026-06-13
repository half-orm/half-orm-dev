"""
Tests for release ordering constraint during patch merge.

Verifies that patches cannot be merged in higher releases while lower
releases have unmerged patches (candidate or staged status).
"""

import pytest
from pathlib import Path
from half_orm_dev.patch_manager import PatchManager, PatchManagerError
from half_orm_dev.release_file import ReleaseFile

try:
    import tomli_w
except ImportError:
    raise ImportError("tomli_w is required for tests")

import sys
if sys.version_info >= (3, 11):
    import tomllib as tomli
else:
    import tomli


def add_patch_with_status(release_file: ReleaseFile, patch_id: str, status: str) -> None:
    """Helper to add a patch with specific status (candidate or staged)."""
    # Read current data
    with release_file.file_path.open('rb') as f:
        data = tomli.load(f)

    # Add patch with specified status
    if "patches" not in data:
        data["patches"] = {}

    data["patches"][patch_id] = {"status": status}

    # Write back
    with release_file.file_path.open('wb') as f:
        tomli_w.dump(data, f)


class TestReleaseOrderingConstraint:
    """Test _check_lower_releases_with_unmerged_patches() method."""

    def test_no_blocking_releases_when_all_empty(self, temp_repo):
        """No blocking when all lower releases have no patches."""
        repo, temp_dir, patches_dir = temp_repo
        releases_dir = Path(repo.releases_dir)

        # Create releases: 0.0.1, 0.0.2, 0.1.0 (all empty)
        for version in ["0.0.1", "0.0.2", "0.1.0"]:
            release_file = ReleaseFile(version, releases_dir)
            release_file.create_empty()

        # Check 0.1.0 - should find no blocking releases
        pm = PatchManager(repo)
        blocking = pm._check_lower_releases_with_unmerged_patches("0.1.0")

        assert blocking == []

    def test_blocking_when_lower_has_candidate(self, temp_repo):
        """Blocking when lower release has candidate patches."""
        repo, temp_dir, patches_dir = temp_repo
        releases_dir = Path(repo.releases_dir)

        # Create 0.0.2 with candidate patch
        rf_002 = ReleaseFile("0.0.2", releases_dir)
        rf_002.create_empty()
        add_patch_with_status(rf_002, "123-fix", "candidate")

        # Create 0.1.0 (empty)
        rf_010 = ReleaseFile("0.1.0", releases_dir)
        rf_010.create_empty()

        # Check 0.1.0 - should be blocked by 0.0.2
        pm = PatchManager(repo)
        blocking = pm._check_lower_releases_with_unmerged_patches("0.1.0")

        assert blocking == ["0.0.2"]

    def test_blocking_when_lower_has_staged(self, temp_repo):
        """Blocking when lower release has staged patches."""
        repo, temp_dir, patches_dir = temp_repo
        releases_dir = Path(repo.releases_dir)

        # Create 0.0.2 with staged patch
        rf_002 = ReleaseFile("0.0.2", releases_dir)
        rf_002.create_empty()
        add_patch_with_status(rf_002, "123-fix", "staged")

        # Create 0.1.0 (empty)
        rf_010 = ReleaseFile("0.1.0", releases_dir)
        rf_010.create_empty()

        # Check 0.1.0 - should be blocked by 0.0.2
        pm = PatchManager(repo)
        blocking = pm._check_lower_releases_with_unmerged_patches("0.1.0")

        assert blocking == ["0.0.2"]

    def test_blocking_when_lower_has_both_candidate_and_staged(self, temp_repo):
        """Blocking when lower release has both candidate and staged patches."""
        repo, temp_dir, patches_dir = temp_repo
        releases_dir = Path(repo.releases_dir)

        # Create 0.0.2 with candidate and staged patches
        rf_002 = ReleaseFile("0.0.2", releases_dir)
        rf_002.create_empty()
        add_patch_with_status(rf_002, "123-fix", "candidate")
        add_patch_with_status(rf_002, "124-feature", "staged")

        # Create 0.1.0 (empty)
        rf_010 = ReleaseFile("0.1.0", releases_dir)
        rf_010.create_empty()

        # Check 0.1.0 - should be blocked by 0.0.2
        pm = PatchManager(repo)
        blocking = pm._check_lower_releases_with_unmerged_patches("0.1.0")

        assert blocking == ["0.0.2"]

    def test_multiple_blocking_releases(self, temp_repo):
        """Multiple lower releases with unmerged patches."""
        repo, temp_dir, patches_dir = temp_repo
        releases_dir = Path(repo.releases_dir)

        # Create 0.0.1 with candidate
        rf_001 = ReleaseFile("0.0.1", releases_dir)
        rf_001.create_empty()
        add_patch_with_status(rf_001, "100-init", "candidate")

        # Create 0.0.2 with staged
        rf_002 = ReleaseFile("0.0.2", releases_dir)
        rf_002.create_empty()
        add_patch_with_status(rf_002, "123-fix", "staged")

        # Create 0.1.0 (empty)
        rf_010 = ReleaseFile("0.1.0", releases_dir)
        rf_010.create_empty()

        # Check 0.1.0 - should be blocked by both
        pm = PatchManager(repo)
        blocking = pm._check_lower_releases_with_unmerged_patches("0.1.0")

        # Should return both, sorted by version
        assert blocking == ["0.0.1", "0.0.2"]

    def test_no_blocking_when_lower_released_to_production(self, temp_repo):
        """No blocking when lower release is already in production (txt file)."""
        repo, temp_dir, patches_dir = temp_repo
        releases_dir = Path(repo.releases_dir)

        # Create 0.0.2 production release (txt file, no toml)
        txt_file = releases_dir / "0.0.2.txt"
        txt_file.write_text("123-fix\n124-feature\n")

        # Create 0.1.0 with candidate
        rf_010 = ReleaseFile("0.1.0", releases_dir)
        rf_010.create_empty()
        add_patch_with_status(rf_010, "200-new", "candidate")

        # Check 0.1.0 - should NOT be blocked (0.0.2 is in production)
        pm = PatchManager(repo)
        blocking = pm._check_lower_releases_with_unmerged_patches("0.1.0")

        assert blocking == []

    def test_same_version_not_blocking(self, temp_repo):
        """Same version release doesn't block itself."""
        repo, temp_dir, patches_dir = temp_repo
        releases_dir = Path(repo.releases_dir)

        # Create 0.1.0 with candidate and staged
        rf_010 = ReleaseFile("0.1.0", releases_dir)
        rf_010.create_empty()
        add_patch_with_status(rf_010, "123-feature", "candidate")
        add_patch_with_status(rf_010, "124-fix", "staged")

        # Check 0.1.0 against itself
        pm = PatchManager(repo)
        blocking = pm._check_lower_releases_with_unmerged_patches("0.1.0")

        assert blocking == []

    def test_higher_version_not_blocking(self, temp_repo):
        """Higher version releases don't block lower ones."""
        repo, temp_dir, patches_dir = temp_repo
        releases_dir = Path(repo.releases_dir)

        # Create 0.0.2 (empty)
        rf_002 = ReleaseFile("0.0.2", releases_dir)
        rf_002.create_empty()

        # Create 0.1.0 with candidate
        rf_010 = ReleaseFile("0.1.0", releases_dir)
        rf_010.create_empty()
        add_patch_with_status(rf_010, "200-new", "candidate")

        # Check 0.0.2 - should NOT be blocked by higher 0.1.0
        pm = PatchManager(repo)
        blocking = pm._check_lower_releases_with_unmerged_patches("0.0.2")

        assert blocking == []

    def test_complex_scenario_multiple_versions(self, temp_repo):
        """Complex scenario with multiple releases at different levels."""
        repo, temp_dir, patches_dir = temp_repo
        releases_dir = Path(repo.releases_dir)

        # 0.0.1 - production (txt only)
        (releases_dir / "0.0.1.txt").write_text("100-init\n")

        # 0.0.2 - has candidate
        rf_002 = ReleaseFile("0.0.2", releases_dir)
        rf_002.create_empty()
        add_patch_with_status(rf_002, "101-fix", "candidate")

        # 0.0.3 - empty
        rf_003 = ReleaseFile("0.0.3", releases_dir)
        rf_003.create_empty()

        # 0.1.0 - has staged
        rf_010 = ReleaseFile("0.1.0", releases_dir)
        rf_010.create_empty()
        add_patch_with_status(rf_010, "200-feature", "staged")

        # 0.2.0 - empty
        rf_020 = ReleaseFile("0.2.0", releases_dir)
        rf_020.create_empty()

        # Check 0.2.0 - should be blocked by 0.0.2 and 0.1.0
        pm = PatchManager(repo)
        blocking = pm._check_lower_releases_with_unmerged_patches("0.2.0")

        assert blocking == ["0.0.2", "0.1.0"]

    def test_version_sorting(self, temp_repo):
        """Blocking releases are returned sorted by version."""
        repo, temp_dir, patches_dir = temp_repo
        releases_dir = Path(repo.releases_dir)

        # Create releases in non-sorted order with patches
        for version in ["0.1.0", "0.0.2", "0.0.10", "0.0.3"]:
            rf = ReleaseFile(version, releases_dir)
            rf.create_empty()
            add_patch_with_status(rf, f"patch-{version}", "candidate")

        # Create target release
        rf_target = ReleaseFile("0.2.0", releases_dir)
        rf_target.create_empty()

        # Check 0.2.0
        pm = PatchManager(repo)
        blocking = pm._check_lower_releases_with_unmerged_patches("0.2.0")

        # Should be sorted properly (0.0.2 < 0.0.3 < 0.0.10 < 0.1.0)
        assert blocking == ["0.0.2", "0.0.3", "0.0.10", "0.1.0"]


