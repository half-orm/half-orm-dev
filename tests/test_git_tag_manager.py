#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TDD Tests for GitTagManager Module

Test-Driven Development for Git tag management in SchemaPatches.
These tests define the expected behavior BEFORE implementation.

Test Structure:
- Unit tests for core functionality
- Integration tests with real Git repositories
- Edge cases and error conditions
- Performance considerations

Run with: pytest test_git_tag_manager.py -v
"""

import os
import tempfile
import shutil
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import git
from git.exc import GitCommandError, InvalidGitRepositoryError

# Import the classes we're testing (will fail initially - that's TDD!)
from half_orm_dev.git_operations.git_tag_manager import (
    GitTagManager,
    VersionTag,
    GitTagManagerError,
    InvalidRepositoryError,
    TagCreationError,
    TagParsingError,
    VersionExistsError
)


@pytest.fixture
def temp_git_repo():
    """Create a temporary Git repository for testing"""
    temp_dir = tempfile.mkdtemp()
    repo = git.Repo.init(temp_dir)
    
    # Create initial commit
    test_file = os.path.join(temp_dir, "README.md")
    with open(test_file, 'w') as f:
        f.write("Test repository")
    repo.index.add([test_file])
    repo.index.commit("Initial commit")
    
    yield temp_dir, repo
    
    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.fixture
def sample_version_tag():
    """Sample VersionTag for testing"""
    return VersionTag(
        raw_tag="v1.3.4",
        major=1,
        minor=3,
        patch=4
    )


@pytest.fixture
def prerelease_version_tag():
    """Sample pre-release VersionTag for testing"""
    return VersionTag(
        raw_tag="v1.3.4-alpha1",
        major=1,
        minor=3,
        patch=4,
        pre_release="alpha1",
        is_pre_release=True
    )


@pytest.fixture
def tag_manager_with_tags(temp_git_repo):
    """GitTagManager with pre-created tags for testing"""
    temp_dir, repo = temp_git_repo
    
    # Create version tags
    tags_to_create = [
        "v1.3.1", "v1.3.3", "v1.3.8",  # 1.3.x line with gaps
        "v1.4.1", "v1.4.2", "v1.4.3",  # 1.4.x line without gaps
        "v2.0.1",                       # 2.0.x line
        "v1.3.4-alpha1"                 # Pre-release
    ]
    
    for tag_name in tags_to_create:
        repo.create_tag(tag_name, message=f"Release {tag_name}")
    
    manager = GitTagManager(temp_dir)
    yield manager


class TestVersionTag:
    """Test VersionTag dataclass"""
    
    def test_version_tag_creation_basic(self, sample_version_tag):
        """Should create VersionTag with basic version info"""
        tag = sample_version_tag
        
        assert tag.raw_tag == "v1.3.4"
        assert tag.major == 1
        assert tag.minor == 3
        assert tag.patch == 4
        assert tag.pre_release is None
        assert tag.is_pre_release is False
    
    def test_version_tag_prerelease(self, prerelease_version_tag):
        """Should handle pre-release versions correctly"""
        tag = prerelease_version_tag
        
        assert tag.raw_tag == "v1.3.4-alpha1"
        assert tag.major == 1
        assert tag.minor == 3
        assert tag.patch == 4
        assert tag.pre_release == "alpha1"
        assert tag.is_pre_release is True
    
    def test_version_tag_maintenance_line_property(self):
        """Should generate correct maintenance line identifier"""
        tag = VersionTag(raw_tag="v1.3.4", major=1, minor=3, patch=4)
        assert tag.maintenance_line == "1.3.x"
        
        tag2 = VersionTag(raw_tag="v10.25.100", major=10, minor=25, patch=100)
        assert tag2.maintenance_line == "10.25.x"
    
    def test_version_tag_version_string_property(self):
        """Should generate version string without 'v' prefix"""
        tag = VersionTag(raw_tag="v1.3.4", major=1, minor=3, patch=4)
        assert tag.version_string == "1.3.4"
        
        # With pre-release
        tag_pre = VersionTag(
            raw_tag="v1.3.4-alpha1", major=1, minor=3, patch=4,
            pre_release="alpha1", is_pre_release=True
        )
        assert tag_pre.version_string == "1.3.4-alpha1"
    
    def test_version_tag_string_representation(self):
        """Should return raw tag as string representation"""
        tag = VersionTag(raw_tag="v1.3.4", major=1, minor=3, patch=4)
        assert str(tag) == "v1.3.4"
    
    def test_version_tag_frozen_dataclass(self):
        """Should be immutable (frozen dataclass)"""
        tag = VersionTag(raw_tag="v1.3.4", major=1, minor=3, patch=4)
        
        with pytest.raises(AttributeError):
            tag.major = 2  # Should raise because dataclass is frozen


class TestGitTagManagerInitialization:
    """Test GitTagManager initialization and basic setup"""
    
    def test_init_with_valid_repo(self, temp_git_repo):
        """Should initialize successfully with valid Git repository"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(temp_dir)
        
        assert manager is not None
        assert str(manager.repo_path) == str(Path(temp_dir).resolve())
    
    def test_init_with_current_directory(self):
        """Should initialize with current directory as default"""
        with patch('git.Repo') as mock_repo:
            manager = GitTagManager()
            mock_repo.assert_called_once()
    
    def test_init_with_invalid_repo(self):
        """Should raise InvalidRepositoryError for non-Git directory"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # temp_dir is not a Git repository
            with pytest.raises(InvalidRepositoryError) as exc_info:
                GitTagManager(temp_dir)
            
            assert "Invalid Git repository" in str(exc_info.value)
    
    def test_init_with_nonexistent_path(self):
        """Should raise InvalidRepositoryError for non-existent path"""
        with pytest.raises(InvalidRepositoryError):
            GitTagManager("/path/that/does/not/exist")


class TestTagParsing:
    """Test version tag parsing functionality"""
    
    def test_parse_version_tag_basic_v_prefix(self, temp_git_repo):
        """Should parse version tag with 'v' prefix correctly"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(temp_dir)
        
        tag = manager._parse_version_tag("v1.3.4")
        
        assert tag.raw_tag == "v1.3.4"
        assert tag.major == 1
        assert tag.minor == 3
        assert tag.patch == 4
        assert tag.pre_release is None
        assert tag.is_pre_release is False
    
    def test_parse_version_tag_basic_no_prefix(self, temp_git_repo):
        """Should parse version tag without 'v' prefix correctly"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(temp_dir)
        
        tag = manager._parse_version_tag("1.3.4")
        
        assert tag.raw_tag == "1.3.4"
        assert tag.major == 1
        assert tag.minor == 3
        assert tag.patch == 4
    
    def test_parse_version_tag_with_prerelease(self, temp_git_repo):
        """Should parse version tag with pre-release identifier"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(temp_dir)
        
        test_cases = [
            ("v1.3.4-alpha1", "alpha1"),
            ("1.3.4-beta", "beta"),
            ("v2.0.0-rc2", "rc2"),
            ("1.5.0-dev", "dev")
        ]
        
        for tag_name, expected_prerelease in test_cases:
            tag = manager._parse_version_tag(tag_name)
            assert tag.pre_release == expected_prerelease
            assert tag.is_pre_release is True
    
    def test_parse_version_tag_large_numbers(self, temp_git_repo):
        """Should handle large version numbers correctly"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(temp_dir)
        
        tag = manager._parse_version_tag("v10.25.100")
        
        assert tag.major == 10
        assert tag.minor == 25
        assert tag.patch == 100
    
    def test_parse_version_tag_zero_versions(self, temp_git_repo):
        """Should handle zero version numbers correctly"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(temp_dir)
        
        tag = manager._parse_version_tag("v0.0.1")
        
        assert tag.major == 0
        assert tag.minor == 0
        assert tag.patch == 1
    
    def test_parse_version_tag_invalid_format(self, temp_git_repo):
        """Should raise TagParsingError for invalid tag formats"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(temp_dir)
        
        invalid_tags = [
            "invalid",
            "v1.3",
            "v1.3.4.5",
            "1.3.4-",
            "v1.3.4-invalid_prerelease",
            "release-1.3.4",
            ""
        ]
        
        for invalid_tag in invalid_tags:
            with pytest.raises(TagParsingError):
                manager._parse_version_tag(invalid_tag)


class TestPrereleaseValidation:
    """Test pre-release identifier validation"""
    
    def test_validate_prerelease_valid_identifiers(self, temp_git_repo):
        """Should validate correct pre-release identifiers"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(temp_dir)
        
        valid_prereleases = [
            "alpha", "alpha1", "alpha10",
            "beta", "beta1", "beta5",
            "rc", "rc1", "rc2",
            "dev", "dev1", "dev3"
        ]
        
        for prerelease in valid_prereleases:
            assert manager._validate_prerelease(prerelease) is True
    
    def test_validate_prerelease_invalid_identifiers(self, temp_git_repo):
        """Should reject invalid pre-release identifiers"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(temp_dir)
        
        invalid_prereleases = [
            "invalid", "gamma", "stable",
            "alpha0", "beta-1", "rc_1",
            "", "alpha.1", "beta.test"
        ]
        
        for prerelease in invalid_prereleases:
            assert manager._validate_prerelease(prerelease) is False


class TestVersionTagRetrieval:
    """Test retrieving and filtering version tags"""
    
    def test_get_version_tags_for_line_valid(self, tag_manager_with_tags):
        """Should return version tags for specific maintenance line"""
        manager = tag_manager_with_tags
        
        tags_1_3 = manager.get_version_tags_for_line("1.3.x")
        
        assert len(tags_1_3) == 3  # v1.3.1, v1.3.3, v1.3.8 (excluding pre-release)
        assert all(tag.major == 1 and tag.minor == 3 for tag in tags_1_3)
        assert not any(tag.is_pre_release for tag in tags_1_3)
        
        # Should be sorted by patch number
        patch_numbers = [tag.patch for tag in tags_1_3]
        assert patch_numbers == sorted(patch_numbers)
    
    def test_get_version_tags_for_line_empty(self, tag_manager_with_tags):
        """Should return empty list for maintenance line with no tags"""
        manager = tag_manager_with_tags
        
        tags_3_0 = manager.get_version_tags_for_line("3.0.x")
        
        assert tags_3_0 == []
    
    def test_get_version_tags_for_line_invalid_format(self, tag_manager_with_tags):
        """Should raise error for invalid maintenance line format"""
        manager = tag_manager_with_tags
        
        invalid_lines = [
            "1.3", "1.3.1", "invalid", "", "1.x", "x.3.x"
        ]
        
        for invalid_line in invalid_lines:
            with pytest.raises(GitTagManagerError):
                manager.get_version_tags_for_line(invalid_line)
    
    def test_get_existing_patch_numbers(self, tag_manager_with_tags):
        """Should return set of existing patch numbers"""
        manager = tag_manager_with_tags
        
        patches_1_3 = manager.get_existing_patch_numbers("1.3.x")
        assert patches_1_3 == {1, 3, 8}
        
        patches_1_4 = manager.get_existing_patch_numbers("1.4.x")
        assert patches_1_4 == {1, 2, 3}
        
        patches_empty = manager.get_existing_patch_numbers("3.0.x")
        assert patches_empty == set()


class TestNextAvailablePatchNumbers:
    """Test intelligent patch number assignment"""
    
    def test_get_next_available_patch_numbers_no_existing(self, tag_manager_with_tags):
        """Should start from 1 when no patches exist"""
        manager = tag_manager_with_tags
        
        next_numbers = manager.get_next_available_patch_numbers("3.0.x", count=3)
        assert next_numbers == [1, 2, 3]
    
    def test_get_next_available_patch_numbers_with_gaps(self, tag_manager_with_tags):
        """Should fill gaps first, then continue sequence"""
        manager = tag_manager_with_tags
        
        # 1.3.x has tags: 1, 3, 8 (missing: 2, 4, 5, 6, 7)
        next_numbers = manager.get_next_available_patch_numbers("1.3.x", count=5)
        assert next_numbers == [2, 4, 5, 6, 7]
    
    def test_get_next_available_patch_numbers_no_gaps(self, tag_manager_with_tags):
        """Should continue sequence after highest when no gaps"""
        manager = tag_manager_with_tags
        
        # 1.4.x has tags: 1, 2, 3 (no gaps)
        next_numbers = manager.get_next_available_patch_numbers("1.4.x", count=2)
        assert next_numbers == [4, 5]
    
    def test_get_next_available_patch_numbers_single(self, tag_manager_with_tags):
        """Should return single next number by default"""
        manager = tag_manager_with_tags
        
        next_number = manager.get_next_available_patch_numbers("1.3.x")
        assert next_number == [2]  # First gap in 1.3.x sequence
    
    def test_get_next_available_patch_numbers_invalid_count(self, tag_manager_with_tags):
        """Should raise error for invalid count values"""
        manager = tag_manager_with_tags
        
        with pytest.raises(GitTagManagerError):
            manager.get_next_available_patch_numbers("1.3.x", count=0)
        
        with pytest.raises(GitTagManagerError):
            manager.get_next_available_patch_numbers("1.3.x", count=-1)
    
    def test_get_highest_patch_number_existing(self, tag_manager_with_tags):
        """Should return highest patch number for line with tags"""
        manager = tag_manager_with_tags
        
        highest_1_3 = manager.get_highest_patch_number("1.3.x")
        assert highest_1_3 == 8
        
        highest_1_4 = manager.get_highest_patch_number("1.4.x")
        assert highest_1_4 == 3
    
    def test_get_highest_patch_number_none(self, tag_manager_with_tags):
        """Should return None for line with no tags"""
        manager = tag_manager_with_tags
        
        highest_empty = manager.get_highest_patch_number("3.0.x")
        assert highest_empty is None


class TestVersionExistenceChecking:
    """Test checking if versions already exist"""
    
    def test_check_version_exists_true(self, tag_manager_with_tags):
        """Should return True for existing versions"""
        manager = tag_manager_with_tags
        
        # Test with and without 'v' prefix
        assert manager.check_version_exists("1.3.1") is True
        assert manager.check_version_exists("v1.3.1") is True
        assert manager.check_version_exists("1.3.3") is True
        assert manager.check_version_exists("v1.3.8") is True
    
    def test_check_version_exists_false(self, tag_manager_with_tags):
        """Should return False for non-existing versions"""
        manager = tag_manager_with_tags
        
        assert manager.check_version_exists("1.3.2") is False
        assert manager.check_version_exists("v1.3.4") is False
        assert manager.check_version_exists("2.0.0") is False
        assert manager.check_version_exists("3.0.1") is False
    
    def test_check_version_exists_prerelease(self, tag_manager_with_tags):
        """Should handle pre-release versions correctly"""
        manager = tag_manager_with_tags
        
        assert manager.check_version_exists("1.3.4-alpha1") is True
        assert manager.check_version_exists("v1.3.4-alpha1") is True
        assert manager.check_version_exists("1.3.4-alpha2") is False


class TestTagCreation:
    """Test creating new version tags"""
    
    def test_create_version_tag_basic(self, temp_git_repo):
        """Should create new version tag successfully"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(temp_dir)
        
        tag_name = manager.create_version_tag("1.3.4", "Release 1.3.4")
        
        assert tag_name == "v1.3.4"
        assert "v1.3.4" in [tag.name for tag in repo.tags]
    
    def test_create_version_tag_without_message(self, temp_git_repo):
        """Should create tag without message"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(temp_dir)
        
        tag_name = manager.create_version_tag("1.3.4")
        assert tag_name == "v1.3.4"
    
    def test_create_version_tag_with_prerelease(self, temp_git_repo):
        """Should create pre-release version tag"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(temp_dir)
        
        tag_name = manager.create_version_tag("1.3.4-alpha1", "Alpha release")
        assert tag_name == "v1.3.4-alpha1"
    
    def test_create_version_tag_already_exists(self, tag_manager_with_tags):
        """Should raise VersionExistsError for existing version"""
        manager = tag_manager_with_tags
        
        with pytest.raises(VersionExistsError):
            manager.create_version_tag("1.3.1", "Duplicate release")
    
    def test_create_version_tag_force_overwrite(self, tag_manager_with_tags):
        """Should overwrite existing tag when force=True"""
        manager = tag_manager_with_tags
        
        tag_name = manager.create_version_tag("1.3.1", "Forced update", force=True)
        assert tag_name == "v1.3.1"
    
    def test_create_version_tag_invalid_format(self, temp_git_repo):
        """Should raise TagParsingError for invalid version format"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(temp_dir)
        
        with pytest.raises(TagParsingError):
            manager.create_version_tag("invalid")
        
        with pytest.raises(TagParsingError):
            manager.create_version_tag("1.3")


class TestTagDeletion:
    """Test deleting version tags"""
    
    def test_delete_version_tag_existing(self, tag_manager_with_tags):
        """Should delete existing tag and return True"""
        manager = tag_manager_with_tags
        
        result = manager.delete_version_tag("1.3.1")
        
        assert result is True
        assert not manager.check_version_exists("1.3.1")
    
    def test_delete_version_tag_nonexistent(self, tag_manager_with_tags):
        """Should return False for non-existent tag"""
        manager = tag_manager_with_tags
        
        result = manager.delete_version_tag("1.3.2")
        assert result is False
    
    def test_delete_version_tag_with_v_prefix(self, tag_manager_with_tags):
        """Should handle deletion with 'v' prefix"""
        manager = tag_manager_with_tags
        
        result = manager.delete_version_tag("v1.3.3")
        
        assert result is True
        assert not manager.check_version_exists("1.3.3")
    
    def test_delete_version_tag_with_remote(self, tag_manager_with_tags):
        """Should delete from remote when requested"""
        manager = tag_manager_with_tags
        
        # Mock remote deletion since we don't have actual remote
        with patch.object(manager.repo.git, 'push') as mock_push:
            result = manager.delete_version_tag("1.3.8", remote=True)
            
            assert result is True
            mock_push.assert_called_once()


class TestMaintenanceLineOperations:
    """Test operations on maintenance lines"""
    
    def test_get_all_maintenance_lines(self, tag_manager_with_tags):
        """Should return all maintenance lines with versions"""
        manager = tag_manager_with_tags
        
        lines = manager.get_all_maintenance_lines()
        
        expected_lines = {"1.3.x", "1.4.x", "2.0.x"}
        assert lines == expected_lines
    
    def test_get_all_maintenance_lines_empty(self, temp_git_repo):
        """Should return empty set when no version tags exist"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(temp_dir)
        
        lines = manager.get_all_maintenance_lines()
        assert lines == set()
    
    def test_get_version_gaps_with_gaps(self, tag_manager_with_tags):
        """Should return list of gaps in patch numbering"""
        manager = tag_manager_with_tags
        
        # 1.3.x has patches: 1, 3, 8
        gaps = manager.get_version_gaps("1.3.x")
        
        assert gaps == [2, 4, 5, 6, 7]
    
    def test_get_version_gaps_no_gaps(self, tag_manager_with_tags):
        """Should return empty list when no gaps exist"""
        manager = tag_manager_with_tags
        
        # 1.4.x has patches: 1, 2, 3 (no gaps)
        gaps = manager.get_version_gaps("1.4.x")
        
        assert gaps == []
    
    def test_get_version_gaps_empty_line(self, tag_manager_with_tags):
        """Should return empty list for maintenance line with no versions"""
        manager = tag_manager_with_tags
        
        gaps = manager.get_version_gaps("3.0.x")
        assert gaps == []


class TestVersionFormatValidation:
    """Test version format validation"""
    
    def test_validate_version_format_valid(self, temp_git_repo):
        """Should return True for valid version formats"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(temp_dir)
        
        valid_versions = [
            "1.3.4",
            "v1.3.4",
            "0.0.1",
            "10.25.100",
            "1.3.4-alpha1",
            "v2.0.0-beta",
            "1.5.0-rc2",
            "1.0.0-dev"
        ]
        
        for version in valid_versions:
            assert manager.validate_version_format(version) is True
    
    def test_validate_version_format_invalid(self, temp_git_repo):
        """Should return False for invalid version formats"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(temp_dir)
        
        invalid_versions = [
            "invalid",
            "1.3",
            "1.3.4.5",
            "v1.3.4-",
            "1.3.4-invalid_prerelease",
            "",
            "release-1.3.4"
        ]
        
        for version in invalid_versions:
            assert manager.validate_version_format(version) is False


class TestCacheManagement:
    """Test internal caching functionality"""
    
    def test_invalidate_cache(self, temp_git_repo):
        """Should invalidate internal cache"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(temp_dir)
        
        # Access cache to populate it
        manager._get_all_tags()
        
        # Invalidate cache
        manager._invalidate_cache()
        
        # Should not crash and should work normally
        tags = manager._get_all_tags()
        assert isinstance(tags, dict)
    
    def test_refresh_cache(self, temp_git_repo):
        """Should force refresh of cache"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(temp_dir)
        
        # Get initial tags
        initial_tags = manager._get_all_tags()
        
        # Add new tag externally
        repo.create_tag("v1.0.0", message="External tag")
        
        # Refresh cache
        manager.refresh_cache()
        
        # Should include new tag
        refreshed_tags = manager._get_all_tags()
        assert len(refreshed_tags) > len(initial_tags)
        assert "v1.0.0" in refreshed_tags


class TestErrorHandling:
    """Test error handling and edge cases"""
    
    def test_git_command_error_handling(self, temp_git_repo):
        """Should handle Git command errors gracefully"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(temp_dir)
        
        # Mock Git operation failure
        with patch.object(manager.repo, 'tags', side_effect=GitCommandError("git", 128, "error")):
            with pytest.raises(GitTagManagerError):
                manager._get_all_tags()
    
    def test_tag_creation_git_error(self, temp_git_repo):
        """Should raise TagCreationError when Git tag creation fails"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(temp_dir)
        
        # Mock Git tag creation failure
        with patch.object(manager.repo, 'create_tag', side_effect=GitCommandError("git", 128, "error")):
            with pytest.raises(TagCreationError):
                manager.create_version_tag("1.0.0")
    
    def test_large_repository_performance(self, temp_git_repo):
        """Should handle repositories with many tags efficiently"""
        temp_dir, repo = temp_git_repo
        
        # Create many tags
        for i in range(100):
            major = i // 50 + 1
            minor = (i // 10) % 5
            patch = i % 10 + 1
            repo.create_tag(f"v{major}.{minor}.{patch}")
        
        manager = GitTagManager(temp_dir)
        
        # Should handle large number of tags without issues
        all_lines = manager.get_all_maintenance_lines()
        assert len(all_lines) > 0
        
        # Operations should still be fast (no specific timing test, just no crash)
        next_patches = manager.get_next_available_patch_numbers("1.0.x", count=5)
        assert len(next_patches) == 5


class TestIntegrationScenarios:
    """Test realistic integration scenarios"""
    
    def test_schema_patches_workflow_simulation(self, temp_git_repo):
        """Should support typical SchemaPatches workflow"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(temp_dir)
        
        # Scenario: Start development on 1.3.x line
        # Get next available patch numbers for temp keys
        next_patches = manager.get_next_available_patch_numbers("1.3.x", count=3)
        assert next_patches == [1, 2, 3]  # Starting fresh
        
        # Finalize temp1 to patch 1
        tag1 = manager.create_version_tag("1.3.1", "Finalize temp1")
        assert tag1 == "v1.3.1"
        
        # Finalize temp2 to patch 2  
        tag2 = manager.create_version_tag("1.3.2", "Finalize temp2")
        assert tag2 == "v1.3.2"
        
        # External release creates gap (manual v1.3.5)
        manager.create_version_tag("1.3.5", "External release")
        
        # Get next available - should fill gaps and continue
        next_patches = manager.get_next_available_patch_numbers("1.3.x", count=3)
        assert next_patches == [3, 4, 6]  # Fill gap at 3,4 then continue after 5
    
    def test_multiple_maintenance_lines_workflow(self, temp_git_repo):
        """Should handle multiple maintenance lines independently"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(temp_dir)
        
        # Create versions in different lines
        manager.create_version_tag("1.3.1", "Line 1.3.x patch 1")
        manager.create_version_tag("1.4.1", "Line 1.4.x patch 1")
        manager.create_version_tag("2.0.1", "Line 2.0.x patch 1")
        
        # Each line should be independent
        next_1_3 = manager.get_next_available_patch_numbers("1.3.x", count=2)
        next_1_4 = manager.get_next_available_patch_numbers("1.4.x", count=2)
        next_2_0 = manager.get_next_available_patch_numbers("2.0.x", count=2)
        
        assert next_1_3 == [2, 3]
        assert next_1_4 == [2, 3]
        assert next_2_0 == [2, 3]
        
        # All maintenance lines should be tracked
        all_lines = manager.get_all_maintenance_lines()
        assert all_lines == {"1.3.x", "1.4.x", "2.0.x"}


class TestEdgeCases:
    """Test edge cases and boundary conditions"""
    
    def test_zero_version_handling(self, temp_git_repo):
        """Should handle version 0.0.x correctly"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(temp_dir)
        
        manager.create_version_tag("0.0.1", "Initial version")
        
        tags = manager.get_version_tags_for_line("0.0.x")
        assert len(tags) == 1
        assert tags[0].major == 0
        assert tags[0].minor == 0
        assert tags[0].patch == 1
    
    def test_very_large_version_numbers(self, temp_git_repo):
        """Should handle very large version numbers"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(temp_dir)
        
        manager.create_version_tag("999.999.999", "Large version")
        
        assert manager.check_version_exists("999.999.999") is True
        highest = manager.get_highest_patch_number("999.999.x")
        assert highest == 999
    
    def test_mixed_tag_formats_in_repo(self, temp_git_repo):
        """Should handle mixed tag formats gracefully"""
        temp_dir, repo = temp_git_repo
        
        # Create mix of semantic and non-semantic tags
        repo.create_tag("v1.3.1", message="Semantic version")
        repo.create_tag("release-2023", message="Non-semantic tag")
        repo.create_tag("v1.3.2", message="Another semantic version")
        repo.create_tag("random-tag", message="Random tag")
        
        manager = GitTagManager(temp_dir)
        
        # Should only process semantic version tags
        tags_1_3 = manager.get_version_tags_for_line("1.3.x")
        assert len(tags_1_3) == 2
        assert all(tag.major == 1 and tag.minor == 3 for tag in tags_1_3)
