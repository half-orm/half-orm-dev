"""
Tests for ReleaseFile class - TOML-based release tracking.

This module tests the core functionality of the ReleaseFile class which manages
patch tracking in TOML format with candidate and staged sections.

Test coverage:
- File creation and validation
- Adding patches (candidates)
- Moving patches to staged (with merge_commit)
- Removing patches
- Getting patches by status
- Getting merge_commit
- Order preservation
- Error handling
"""

import pytest
from pathlib import Path
import sys

# Import tomli based on Python version (same logic as release_file.py)
if sys.version_info >= (3, 11):
    import tomllib as tomli
else:
    import tomli

from half_orm_dev.release_file import ReleaseFile, ReleaseFileError


class TestReleaseFileCreation:
    """Test ReleaseFile initialization and file creation."""

    def test_create_empty_toml_file(self, tmp_path):
        """Test creating an empty TOML patches file."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.6", releases_dir)
        release_file.create_empty()

        # Verify file exists
        toml_path = releases_dir / "1.3.6-patches.toml"
        assert toml_path.exists()

        # Verify structure
        with open(toml_path, "rb") as f:
            data = tomli.load(f)

        assert "patches" in data
        assert data["patches"] == {}

    def test_file_path_property(self, tmp_path):
        """Test file_path property returns correct path."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.6", releases_dir)

        expected_path = releases_dir / "1.3.6-patches.toml"
        assert release_file.file_path == expected_path

    def test_create_empty_idempotent(self, tmp_path):
        """Test create_empty() can be called multiple times safely."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.6", releases_dir)
        release_file.create_empty()
        release_file.create_empty()  # Should not error

        # Verify file still valid
        toml_path = releases_dir / "1.3.6-patches.toml"
        assert toml_path.exists()

    def test_version_in_filename(self, tmp_path):
        """Test version is correctly used in filename."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        for version in ["0.1.0", "1.3.6", "2.0.0-rc1"]:
            release_file = ReleaseFile(version, releases_dir)
            expected = releases_dir / f"{version}-patches.toml"
            assert release_file.file_path == expected


class TestAddPatch:
    """Test adding patches as candidates."""

    def test_add_single_patch(self, tmp_path):
        """Test adding a single patch as candidate."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.6", releases_dir)
        release_file.create_empty()
        release_file.add_patch("001-feature")

        # Verify patch added as candidate
        assert "001-feature" in release_file.get_patches()
        assert release_file.get_patch_status("001-feature") == "candidate"

    def test_add_multiple_patches(self, tmp_path):
        """Test adding multiple patches."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.6", releases_dir)
        release_file.create_empty()

        for patch_id in ["001-first", "002-second", "003-third"]:
            release_file.add_patch(patch_id)

        patches = release_file.get_patches()
        assert len(patches) == 3
        for patch_id in patches:
            assert release_file.get_patch_status(patch_id) == "candidate"

    def test_add_patch_preserves_order(self, tmp_path):
        """Test patches maintain insertion order."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.6", releases_dir)
        release_file.create_empty()

        patch_order = ["003-third", "001-first", "002-second"]
        for patch_id in patch_order:
            release_file.add_patch(patch_id)

        # Get patches (should maintain order)
        patches = release_file.get_patches()
        assert patches == patch_order

    def test_add_duplicate_patch_error(self, tmp_path):
        """Test adding duplicate patch raises error."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.6", releases_dir)
        release_file.create_empty()
        release_file.add_patch("001-feature")

        with pytest.raises(ReleaseFileError, match="Patch 001-feature already exists"):
            release_file.add_patch("001-feature")

    def test_add_patch_to_nonexistent_file_error(self, tmp_path):
        """Test adding patch to non-existent file raises error."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.6", releases_dir)
        # Don't create file

        with pytest.raises(ReleaseFileError, match="Release file not found"):
            release_file.add_patch("001-feature")


class TestMoveToStaged:
    """Test moving patches from candidate to staged."""

    def test_move_single_patch_to_staged(self, tmp_path):
        """Test moving a candidate patch to staged."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.6", releases_dir)
        release_file.create_empty()
        release_file.add_patch("001-feature")
        release_file.move_to_staged("001-feature", "abc12345")

        # Verify patch is now staged
        assert release_file.get_patch_status("001-feature") == "staged"
        assert release_file.get_merge_commit("001-feature") == "abc12345"

    def test_move_multiple_patches_to_staged(self, tmp_path):
        """Test moving multiple patches to staged."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.6", releases_dir)
        release_file.create_empty()

        # Add three candidates
        for patch_id in ["001-first", "002-second", "003-third"]:
            release_file.add_patch(patch_id)

        # Move first two to staged
        release_file.move_to_staged("001-first", "commit001")
        release_file.move_to_staged("002-second", "commit002")

        assert release_file.get_patch_status("001-first") == "staged"
        assert release_file.get_patch_status("002-second") == "staged"
        assert release_file.get_patch_status("003-third") == "candidate"

        assert release_file.get_merge_commit("001-first") == "commit001"
        assert release_file.get_merge_commit("002-second") == "commit002"
        assert release_file.get_merge_commit("003-third") is None

    def test_move_to_staged_preserves_order(self, tmp_path):
        """Test moving to staged maintains insertion order."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.6", releases_dir)
        release_file.create_empty()

        # Add in specific order
        patch_order = ["003-third", "001-first", "002-second"]
        for patch_id in patch_order:
            release_file.add_patch(patch_id)

        # Move all to staged
        for i, patch_id in enumerate(patch_order):
            release_file.move_to_staged(patch_id, f"commit{i}")

        patches = release_file.get_patches()
        assert patches == patch_order

    def test_move_nonexistent_patch_error(self, tmp_path):
        """Test moving non-existent patch raises error."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.6", releases_dir)
        release_file.create_empty()

        with pytest.raises(ReleaseFileError, match="Patch 999-missing not found"):
            release_file.move_to_staged("999-missing", "commit123")

    def test_move_already_staged_patch_raises_error(self, tmp_path):
        """Test moving already staged patch raises error."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.6", releases_dir)
        release_file.create_empty()
        release_file.add_patch("001-feature")
        release_file.move_to_staged("001-feature", "commit123")

        # Second move should raise error
        with pytest.raises(ReleaseFileError, match="already staged"):
            release_file.move_to_staged("001-feature", "commit456")


class TestRemovePatch:
    """Test removing patches from file."""

    def test_remove_candidate_patch(self, tmp_path):
        """Test removing a candidate patch."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.6", releases_dir)
        release_file.create_empty()
        release_file.add_patch("001-feature")
        release_file.remove_patch("001-feature")

        assert "001-feature" not in release_file.get_patches()

    def test_remove_staged_patch(self, tmp_path):
        """Test removing a staged patch."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.6", releases_dir)
        release_file.create_empty()
        release_file.add_patch("001-feature")
        release_file.move_to_staged("001-feature", "commit123")
        release_file.remove_patch("001-feature")

        assert "001-feature" not in release_file.get_patches()

    def test_remove_nonexistent_patch_error(self, tmp_path):
        """Test removing non-existent patch raises error."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.6", releases_dir)
        release_file.create_empty()

        with pytest.raises(ReleaseFileError, match="Patch 999-missing not found"):
            release_file.remove_patch("999-missing")

    def test_remove_middle_patch_preserves_order(self, tmp_path):
        """Test removing patch from middle preserves order."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.6", releases_dir)
        release_file.create_empty()

        for patch_id in ["001-first", "002-second", "003-third"]:
            release_file.add_patch(patch_id)

        release_file.remove_patch("002-second")

        patches = release_file.get_patches()
        assert patches == ["001-first", "003-third"]


class TestGetPatches:
    """Test retrieving patches with various filters."""

    def test_get_patches_returns_all_patch_ids(self, tmp_path):
        """Test get_patches() returns all patch IDs regardless of status."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.6", releases_dir)
        release_file.create_empty()

        release_file.add_patch("001-candidate")
        release_file.add_patch("002-staged")
        release_file.move_to_staged("002-staged", "commit123")

        patches = release_file.get_patches()
        assert set(patches) == {"001-candidate", "002-staged"}

    def test_get_candidates(self, tmp_path):
        """Test getting only candidate patches."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.6", releases_dir)
        release_file.create_empty()

        release_file.add_patch("001-candidate")
        release_file.add_patch("002-candidate2")
        release_file.add_patch("003-staged")
        release_file.move_to_staged("003-staged", "commit123")

        candidates = release_file.get_patches(status="candidate")
        assert set(candidates) == {"001-candidate", "002-candidate2"}

    def test_get_staged(self, tmp_path):
        """Test getting only staged patches."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.6", releases_dir)
        release_file.create_empty()

        release_file.add_patch("001-candidate")
        release_file.add_patch("002-staged")
        release_file.add_patch("003-staged2")
        release_file.move_to_staged("002-staged", "commit002")
        release_file.move_to_staged("003-staged2", "commit003")

        staged = release_file.get_patches(status="staged")
        assert set(staged) == {"002-staged", "003-staged2"}

    def test_get_empty_lists(self, tmp_path):
        """Test getting patches from empty file."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.6", releases_dir)
        release_file.create_empty()

        assert release_file.get_patches() == []
        assert release_file.get_patches(status="candidate") == []
        assert release_file.get_patches(status="staged") == []

    def test_get_patches_maintains_order(self, tmp_path):
        """Test get_patches() maintains insertion order."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.6", releases_dir)
        release_file.create_empty()

        patch_order = ["003-third", "001-first", "002-second"]
        for patch_id in patch_order:
            release_file.add_patch(patch_id)

        patches = release_file.get_patches()
        assert patches == patch_order


class TestGetMergeCommit:
    """Test getting merge commit hash."""

    def test_get_merge_commit_for_staged_patch(self, tmp_path):
        """Test getting merge commit for a staged patch."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.6", releases_dir)
        release_file.create_empty()
        release_file.add_patch("001-feature")
        release_file.move_to_staged("001-feature", "abc12345")

        assert release_file.get_merge_commit("001-feature") == "abc12345"

    def test_get_merge_commit_for_candidate_returns_none(self, tmp_path):
        """Test getting merge commit for a candidate patch returns None."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.6", releases_dir)
        release_file.create_empty()
        release_file.add_patch("001-feature")

        assert release_file.get_merge_commit("001-feature") is None

    def test_get_merge_commit_for_nonexistent_patch_returns_none(self, tmp_path):
        """Test getting merge commit for non-existent patch returns None."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.6", releases_dir)
        release_file.create_empty()

        assert release_file.get_merge_commit("999-missing") is None


class TestOrderPreservation:
    """Test that patch order is always preserved."""

    def test_mixed_candidates_and_staged_preserve_order(self, tmp_path):
        """Test mixed operations preserve insertion order."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.6", releases_dir)
        release_file.create_empty()

        # Add patches in specific order
        release_file.add_patch("003-third")
        release_file.add_patch("001-first")
        release_file.add_patch("002-second")
        release_file.add_patch("004-fourth")

        # Move some to staged (not in order)
        release_file.move_to_staged("001-first", "commit001")
        release_file.move_to_staged("004-fourth", "commit004")

        # Order should be preserved
        patches = release_file.get_patches()
        assert patches == ["003-third", "001-first", "002-second", "004-fourth"]

    def test_order_preserved_across_file_reload(self, tmp_path):
        """Test order is preserved when reloading file."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file1 = ReleaseFile("1.3.6", releases_dir)
        release_file1.create_empty()

        patch_order = ["003-third", "001-first", "002-second"]
        for patch_id in patch_order:
            release_file1.add_patch(patch_id)

        # Reload from disk
        release_file2 = ReleaseFile("1.3.6", releases_dir)
        patches = release_file2.get_patches()

        assert patches == patch_order


class TestFileExistence:
    """Test file existence checks."""

    def test_exists_returns_false_for_nonexistent_file(self, tmp_path):
        """Test exists() returns False for non-existent file."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.6", releases_dir)
        assert not release_file.exists()

    def test_exists_returns_true_after_creation(self, tmp_path):
        """Test exists() returns True after file creation."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.6", releases_dir)
        release_file.create_empty()
        assert release_file.exists()


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_patch_id_with_special_characters(self, tmp_path):
        """Test patch IDs with special characters."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.6", releases_dir)
        release_file.create_empty()

        # These should all work
        special_ids = [
            "001-feature_name",
            "002-bug-fix",
            "003-with.dots",
            "004-UPPERCASE"
        ]

        for patch_id in special_ids:
            release_file.add_patch(patch_id)

        patches = release_file.get_patches()
        assert set(patches) == set(special_ids)

    def test_empty_operations_dont_corrupt_file(self, tmp_path):
        """Test that operations on empty file don't corrupt it."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.6", releases_dir)
        release_file.create_empty()

        # These should all be safe
        assert release_file.get_patches() == []
        assert release_file.get_patches(status="candidate") == []
        assert release_file.get_patches(status="staged") == []

        # File should still be valid TOML
        with open(release_file.file_path, "rb") as f:
            data = tomli.load(f)
        assert "patches" in data

    def test_concurrent_modifications(self, tmp_path):
        """Test multiple ReleaseFile instances modifying same file."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        # Create file with first instance
        rf1 = ReleaseFile("1.3.6", releases_dir)
        rf1.create_empty()
        rf1.add_patch("001-first")

        # Modify with second instance
        rf2 = ReleaseFile("1.3.6", releases_dir)
        rf2.add_patch("002-second")

        # Both should see all patches
        assert set(rf1.get_patches()) == {"001-first", "002-second"}
        assert set(rf2.get_patches()) == {"001-first", "002-second"}


class TestIntegrationScenarios:
    """Test realistic usage scenarios."""

    def test_typical_release_workflow(self, tmp_path):
        """Test typical workflow: add candidates, merge some to staged."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.6", releases_dir)
        release_file.create_empty()

        # Add three patch candidates
        for patch_id in ["001-auth", "002-api", "003-ui"]:
            release_file.add_patch(patch_id)

        # Merge first two
        release_file.move_to_staged("001-auth", "commit001")
        release_file.move_to_staged("002-api", "commit002")

        # Verify state
        candidates = release_file.get_patches(status="candidate")
        staged = release_file.get_patches(status="staged")

        assert candidates == ["003-ui"]
        assert staged == ["001-auth", "002-api"]

        # Verify merge commits
        assert release_file.get_merge_commit("001-auth") == "commit001"
        assert release_file.get_merge_commit("002-api") == "commit002"

    def test_hotfix_workflow(self, tmp_path):
        """Test hotfix workflow: create empty, add patch, stage it."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.5", releases_dir)
        release_file.create_empty()

        # Add hotfix patch
        release_file.add_patch("hotfix-001-security")
        release_file.move_to_staged("hotfix-001-security", "hotfix_commit")

        # Verify
        patches = release_file.get_patches(status="staged")
        assert patches == ["hotfix-001-security"]
        assert release_file.get_merge_commit("hotfix-001-security") == "hotfix_commit"

    def test_rc_promotion_workflow(self, tmp_path):
        """Test RC promotion: verify patches before promotion."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.4.0", releases_dir)
        release_file.create_empty()

        # Add and stage patches
        for i, patch_id in enumerate(["001-feat1", "002-feat2", "003-feat3"]):
            release_file.add_patch(patch_id)
            release_file.move_to_staged(patch_id, f"commit{i}")

        # Before RC: verify no candidates remain
        assert release_file.get_patches(status="candidate") == []
        assert len(release_file.get_patches(status="staged")) == 3


class TestTomlFileFormat:
    """Test the TOML file format directly."""

    def test_toml_file_format_for_candidate(self, tmp_path):
        """Test TOML file contains correct dict format for candidate."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.6", releases_dir)
        release_file.create_empty()
        release_file.add_patch("001-feature")

        # Read raw TOML
        with open(release_file.file_path, "rb") as f:
            data = tomli.load(f)

        assert data["patches"]["001-feature"] == {"status": "candidate"}

    def test_toml_file_format_for_staged(self, tmp_path):
        """Test TOML file contains correct dict format for staged with merge_commit."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()

        release_file = ReleaseFile("1.3.6", releases_dir)
        release_file.create_empty()
        release_file.add_patch("001-feature")
        release_file.move_to_staged("001-feature", "abc12345")

        # Read raw TOML
        with open(release_file.file_path, "rb") as f:
            data = tomli.load(f)

        assert data["patches"]["001-feature"] == {
            "status": "staged",
            "merge_commit": "abc12345"
        }
