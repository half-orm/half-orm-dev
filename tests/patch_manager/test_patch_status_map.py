"""
Tests for patch status map and directory organization.

Tests the _patch_status_map cache and get_patch_directory_path with status parameter.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock

from half_orm_dev.patch_manager import PatchManager
from half_orm_dev.release_file import ReleaseFile


@pytest.fixture
def patch_manager_with_releases(tmp_path):
    """Create PatchManager with releases directory structure."""
    # Create directory structure
    patches_dir = tmp_path / "Patches"
    patches_dir.mkdir()

    releases_dir = tmp_path / ".hop" / "releases"
    releases_dir.mkdir(parents=True)

    # Create mock repo
    repo = Mock()
    repo.base_dir = str(tmp_path)
    repo.releases_dir = str(releases_dir)
    repo.devel = True
    repo.name = "test_db"
    repo.hgit = Mock()

    patch_mgr = PatchManager(repo)

    return patch_mgr, repo, tmp_path, patches_dir, releases_dir


class TestGetPatchStatusMap:
    """Test get_patch_status_map() method."""

    def test_empty_status_map(self, patch_manager_with_releases):
        """Test status map is empty when no releases exist."""
        patch_mgr, repo, tmp_path, patches_dir, releases_dir = patch_manager_with_releases

        status_map = patch_mgr.get_patch_status_map()

        assert status_map == {}

    def test_status_map_from_toml(self, patch_manager_with_releases):
        """Test status map reads from TOML files."""
        patch_mgr, repo, tmp_path, patches_dir, releases_dir = patch_manager_with_releases

        # Create TOML file with patches
        release_file = ReleaseFile("0.1.0", releases_dir)
        release_file.create_empty()
        release_file.add_patch("1-auth")
        release_file.move_to_staged("1-auth", "abc123")
        release_file.add_patch("2-api")

        # Clear cache to force rebuild
        patch_mgr._patch_status_map = None
        status_map = patch_mgr.get_patch_status_map()

        assert "1-auth" in status_map
        assert status_map["1-auth"]["status"] == "staged"
        assert status_map["1-auth"]["merge_commit"] == "abc123"

        assert "2-api" in status_map
        assert status_map["2-api"]["status"] == "candidate"

    def test_status_map_cached(self, patch_manager_with_releases):
        """Test status map is cached after first access."""
        patch_mgr, repo, tmp_path, patches_dir, releases_dir = patch_manager_with_releases

        # First access
        status_map1 = patch_mgr.get_patch_status_map()
        # Second access
        status_map2 = patch_mgr.get_patch_status_map()

        # Should be the same object (cached)
        assert status_map1 is status_map2

    def test_status_map_from_staged_directory(self, patch_manager_with_releases):
        """Test status map reads patches from staged/ directory."""
        patch_mgr, repo, tmp_path, patches_dir, releases_dir = patch_manager_with_releases

        # Create staged directory with a patch
        staged_dir = patches_dir / "staged"
        staged_dir.mkdir()
        staged_patch = staged_dir / "1-old-patch"
        staged_patch.mkdir()
        (staged_patch / "README.md").write_text("# Old patch")

        # Clear cache
        patch_mgr._patch_status_map = None
        status_map = patch_mgr.get_patch_status_map()

        assert "1-old-patch" in status_map
        assert status_map["1-old-patch"]["status"] == "staged"

    def test_status_map_from_orphaned_directory(self, patch_manager_with_releases):
        """Test status map reads patches from orphaned/ directory."""
        patch_mgr, repo, tmp_path, patches_dir, releases_dir = patch_manager_with_releases

        # Create orphaned directory with a patch
        orphaned_dir = patches_dir / "orphaned"
        orphaned_dir.mkdir()
        orphaned_patch = orphaned_dir / "1-abandoned"
        orphaned_patch.mkdir()
        (orphaned_patch / "README.md").write_text("# Abandoned")

        # Clear cache
        patch_mgr._patch_status_map = None
        status_map = patch_mgr.get_patch_status_map()

        assert "1-abandoned" in status_map
        assert status_map["1-abandoned"]["status"] == "orphaned"


class TestAddPatchToStatusCache:
    """Test _add_patch_to_status_cache() method."""

    def test_add_patch_to_cache(self, patch_manager_with_releases):
        """Test adding a patch to the cache."""
        patch_mgr, repo, tmp_path, patches_dir, releases_dir = patch_manager_with_releases

        patch_mgr._add_patch_to_status_cache("1-new", "candidate", "0.1.0")

        status_map = patch_mgr.get_patch_status_map()
        assert "1-new" in status_map
        assert status_map["1-new"]["status"] == "candidate"
        assert status_map["1-new"]["version"] == "0.1.0"

    def test_add_patch_initializes_cache(self, patch_manager_with_releases):
        """Test adding patch initializes cache if None."""
        patch_mgr, repo, tmp_path, patches_dir, releases_dir = patch_manager_with_releases

        # Ensure cache is None
        patch_mgr._patch_status_map = None

        patch_mgr._add_patch_to_status_cache("1-new", "candidate", "0.1.0")

        assert patch_mgr._patch_status_map is not None
        assert "1-new" in patch_mgr._patch_status_map


class TestUpdatePatchStatusCache:
    """Test _update_patch_status_cache() method."""

    def test_update_status(self, patch_manager_with_releases):
        """Test updating patch status in cache."""
        patch_mgr, repo, tmp_path, patches_dir, releases_dir = patch_manager_with_releases

        # Add initial patch
        patch_mgr._add_patch_to_status_cache("1-test", "candidate", "0.1.0")

        # Update to staged
        patch_mgr._update_patch_status_cache("1-test", "staged", "def456")

        status_map = patch_mgr.get_patch_status_map()
        assert status_map["1-test"]["status"] == "staged"
        assert status_map["1-test"]["merge_commit"] == "def456"

    def test_update_nonexistent_patch(self, patch_manager_with_releases):
        """Test updating nonexistent patch does nothing."""
        patch_mgr, repo, tmp_path, patches_dir, releases_dir = patch_manager_with_releases

        # Clear and try to update nonexistent patch
        patch_mgr._patch_status_map = {}
        patch_mgr._update_patch_status_cache("nonexistent", "staged", "abc123")

        # Should not raise, just do nothing
        assert "nonexistent" not in patch_mgr._patch_status_map


class TestGetPatchDirectoryPathWithStatus:
    """Test get_patch_directory_path() with status parameter."""

    def test_path_default_candidate(self, patch_manager_with_releases):
        """Test default path is at root (candidate)."""
        patch_mgr, repo, tmp_path, patches_dir, releases_dir = patch_manager_with_releases

        path = patch_mgr.get_patch_directory_path("1-test")

        assert path == patches_dir / "1-test"

    def test_path_explicit_candidate(self, patch_manager_with_releases):
        """Test explicit candidate status returns root path."""
        patch_mgr, repo, tmp_path, patches_dir, releases_dir = patch_manager_with_releases

        path = patch_mgr.get_patch_directory_path("1-test", "candidate")

        assert path == patches_dir / "1-test"

    def test_path_explicit_staged(self, patch_manager_with_releases):
        """Test explicit staged status returns staged/ path."""
        patch_mgr, repo, tmp_path, patches_dir, releases_dir = patch_manager_with_releases

        path = patch_mgr.get_patch_directory_path("1-test", "staged")

        assert path == patches_dir / "staged" / "1-test"

    def test_path_explicit_orphaned(self, patch_manager_with_releases):
        """Test explicit orphaned status returns orphaned/ path."""
        patch_mgr, repo, tmp_path, patches_dir, releases_dir = patch_manager_with_releases

        path = patch_mgr.get_patch_directory_path("1-test", "orphaned")

        assert path == patches_dir / "orphaned" / "1-test"

    def test_path_from_cache(self, patch_manager_with_releases):
        """Test path uses cache when no status provided."""
        patch_mgr, repo, tmp_path, patches_dir, releases_dir = patch_manager_with_releases

        # Add patch as staged to cache
        patch_mgr._add_patch_to_status_cache("1-cached", "staged", "0.1.0")

        path = patch_mgr.get_patch_directory_path("1-cached")

        # Should return staged path based on cache
        assert path == patches_dir / "staged" / "1-cached"

    def test_path_override_cache(self, patch_manager_with_releases):
        """Test explicit status overrides cache."""
        patch_mgr, repo, tmp_path, patches_dir, releases_dir = patch_manager_with_releases

        # Add patch as staged to cache
        patch_mgr._add_patch_to_status_cache("1-override", "staged", "0.1.0")

        # Request candidate path explicitly
        path = patch_mgr.get_patch_directory_path("1-override", "candidate")

        # Should return candidate path despite cache saying staged
        assert path == patches_dir / "1-override"


class TestBuildPatchStatusMap:
    """Test _build_patch_status_map() method."""

    def test_build_from_multiple_toml_files(self, patch_manager_with_releases):
        """Test building map from multiple TOML files."""
        patch_mgr, repo, tmp_path, patches_dir, releases_dir = patch_manager_with_releases

        # Create first release
        rf1 = ReleaseFile("0.1.0", releases_dir)
        rf1.create_empty()
        rf1.add_patch("1-auth")

        # Create second release
        rf2 = ReleaseFile("0.2.0", releases_dir)
        rf2.create_empty()
        rf2.add_patch("2-api")

        patch_mgr._patch_status_map = None
        status_map = patch_mgr.get_patch_status_map()

        assert "1-auth" in status_map
        assert status_map["1-auth"]["version"] == "0.1.0"
        assert "2-api" in status_map
        assert status_map["2-api"]["version"] == "0.2.0"

    def test_toml_takes_precedence_over_filesystem(self, patch_manager_with_releases):
        """Test TOML files take precedence over filesystem scan."""
        patch_mgr, repo, tmp_path, patches_dir, releases_dir = patch_manager_with_releases

        # Create TOML with staged patch
        rf = ReleaseFile("0.1.0", releases_dir)
        rf.create_empty()
        rf.add_patch("1-test")
        rf.move_to_staged("1-test", "abc123")

        # Also create the patch in staged/ directory
        staged_dir = patches_dir / "staged"
        staged_dir.mkdir()
        (staged_dir / "1-test").mkdir()

        patch_mgr._patch_status_map = None
        status_map = patch_mgr.get_patch_status_map()

        # Should get info from TOML (has merge_commit)
        assert status_map["1-test"]["merge_commit"] == "abc123"
