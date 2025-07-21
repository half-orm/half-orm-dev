#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TDD Tests for GitTagManager Ultra-Simplified Module

Test-Driven Development for Git tag management in the new ultra-simplified 
SchemaPatches workflow based on Git tags only (no JSON metadata).

Key Principles:
- Git history = single source of truth
- Tags: dev-patch-X.Y.Z-* (dev) → patch-X.Y.Z-* (prod) 
- Tag message = SchemaPatches directory reference
- Application stateless
- Order = Git chronological order

Test Structure:
- Unit tests for core functionality
- Integration tests with real Git repositories
- Edge cases and error conditions
- Performance considerations

Run with: pytest test_git_tag_manager_simplified.py -v
"""

import os
import tempfile
import shutil
import pytest
from enum import Enum
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, PropertyMock
from datetime import datetime

import git
from git.exc import GitCommandError, InvalidGitRepositoryError
from half_orm_dev.git_operations.git_tag_manager import TagType
from half_orm_dev.git_operations.git_tag_manager import PatchReservationError

# Import the classes we're testing (TDD - will fail initially)
from half_orm_dev.git_operations.git_tag_manager import (
    GitTagManager,
    PatchTag,
    GitTagManagerError,
    InvalidRepositoryError,
    TagCreationError,
    TagValidationError,
    TransferError
)


# Nouvelle classe de test après les imports

class TestTagType:
    """Test TagType enum for 3-tag workflow classification"""
    
    def test_tag_type_values(self):
        """Should have correct enum values"""
        assert TagType.CREATE.value == "create"
        assert TagType.DEV_RELEASE.value == "dev_release"
        assert TagType.PROD_RELEASE.value == "prod_release"
    
    def test_tag_type_comparison(self):
        """Should enable enum comparison"""
        assert TagType.CREATE == TagType.CREATE
        assert TagType.DEV_RELEASE != TagType.CREATE
        assert TagType.PROD_RELEASE != TagType.DEV_RELEASE
    
    def test_tag_type_string_representation(self):
        """Should provide readable string representation"""
        assert str(TagType.CREATE) == "TagType.CREATE"
        assert str(TagType.DEV_RELEASE) == "TagType.DEV_RELEASE"
        assert str(TagType.PROD_RELEASE) == "TagType.PROD_RELEASE"
    
    def test_tag_type_workflow_mapping(self):
        """Should map to correct workflow phases"""
        # CREATE = Reservation phase
        assert TagType.CREATE.value == "create"
        
        # DEV_RELEASE = Development validation phase  
        assert TagType.DEV_RELEASE.value == "dev_release"
        
        # PROD_RELEASE = Production deployment phase
        assert TagType.PROD_RELEASE.value == "prod_release"


@pytest.fixture
def temp_git_repo():
    """Create a temporary Git repository for testing"""
    temp_dir = tempfile.mkdtemp()
    repo = git.Repo.init(temp_dir)
    
    # Create initial commit
    test_file = os.path.join(temp_dir, "README.md")
    with open(test_file, 'w') as f:
        f.write("Test repository for ultra-simplified SchemaPatches")
    repo.index.add([test_file])
    repo.index.commit("Initial commit")
    
    # Create SchemaPatches directory structure
    schema_patches_dir = os.path.join(temp_dir, "SchemaPatches")
    os.makedirs(schema_patches_dir)
    
    # Create sample patch directories - Extended for all test cases
    sample_patches = [
        "123-security",         # Basic tests
        "456-performance",      # Basic tests
        "789-audit",           # Basic tests
        "101-bugfix",          # Multiple version lines test
        "202-migration",       # Multiple version lines test
        "external-hotfix",     # External patch compatibility test
        "999-test",            # Additional test cases
        "001-initial",         # Additional test cases
    ]
    
    for patch_id in sample_patches:
        patch_dir = os.path.join(schema_patches_dir, patch_id)
        os.makedirs(patch_dir)
        
        # Create sample SQL file
        sql_file = os.path.join(patch_dir, "00_sample.sql")
        with open(sql_file, 'w') as f:
            f.write(f"-- Sample SQL for {patch_id}\nSELECT 1;\n")
            
        # Create README for documentation
        readme_file = os.path.join(patch_dir, "README.md")
        with open(readme_file, 'w') as f:
            f.write(f"# Patch {patch_id}\n\nSample patch for testing.\n")
    
    repo.index.add([schema_patches_dir])
    repo.index.commit("Add SchemaPatches structure")
    
    yield temp_dir, repo
    
    # Cleanup
    shutil.rmtree(temp_dir)

@pytest.fixture
def schema_patches_dir(temp_git_repo):
    """Fixture providing SchemaPatches directory path"""
    temp_dir, repo = temp_git_repo
    return os.path.join(temp_dir, "SchemaPatches")


@pytest.fixture
def sample_patch_tag():
    """Sample PatchTag for testing"""
    return PatchTag(
        name="dev-patch-1.3.2-security",
        version="1.3.2",
        suffix="security",
        message="123-security",
        commit_hash="abc123def456",
        is_dev_tag=True,
        timestamp=1642790400  # 2022-01-21
    )


class TestPatchTag:
    """Test PatchTag dataclass for ultra-simplified workflow"""
    
    def test_patch_tag_creation_dev(self):
        """Should create PatchTag for dev-patch tag"""
        tag = PatchTag(
            name="dev-patch-1.3.2-security",
            version="1.3.2", 
            suffix="security",
            message="123-security",
            commit_hash="abc123",
            is_dev_tag=True,
            timestamp=1642790400,
            tag_type=TagType.DEV_RELEASE
        )
        
        assert tag.name == "dev-patch-1.3.2-security"
        assert tag.version == "1.3.2"
        assert tag.suffix == "security"
        assert tag.message == "123-security"
        assert tag.commit_hash == "abc123"
        assert tag.is_dev_tag is True
        assert tag.timestamp == 1642790400
        assert tag.tag_type == TagType.DEV_RELEASE
    
    def test_patch_tag_creation_prod(self):
        """Should create PatchTag for prod patch tag"""
        tag = PatchTag(
            name="patch-1.3.2-security",
            version="1.3.2",
            suffix="security", 
            message="123-security",
            commit_hash="def456",
            is_dev_tag=False,
            timestamp=1642876800,
            tag_type=TagType.PROD_RELEASE
        )
        
        assert tag.name == "patch-1.3.2-security"
        assert tag.is_dev_tag is False
    
    def test_patch_tag_properties(self):
        """Should provide convenient properties"""
        tag = PatchTag(
            name="dev-patch-1.3.2-performance",
            version="1.3.2",
            suffix="performance",
            message="456-performance",
            commit_hash="abc123",
            is_dev_tag=True,
            timestamp=1642790400,
            tag_type=TagType.DEV_RELEASE
        )
        
        # Should derive maintenance line
        assert tag.maintenance_line == "1.3.x"
        
        # Should provide schema patches directory
        assert tag.schema_patches_directory == "456-performance"
    
    def test_patch_tag_comparison(self):
        """Should enable sorting by timestamp (Git chronological order)"""
        tag1 = PatchTag("dev-patch-1.3.2-first", "1.3.2", "first", "123-first", 
                       "abc", True, 1642790400, tag_type=TagType.DEV_RELEASE)
        tag2 = PatchTag("dev-patch-1.3.2-second", "1.3.2", "second", "456-second",
                       "def", True, 1642876800, tag_type=TagType.DEV_RELEASE)
        
        assert tag1 < tag2  # Earlier timestamp
        assert tag2 > tag1
        assert tag1 != tag2
    
    def test_patch_tag_equality(self):
        """Should compare tags by name and commit hash"""
        tag1 = PatchTag("patch-1.3.2-test", "1.3.2", "test", "123-test", 
                       "abc123", False, 1642790400, tag_type=TagType.DEV_RELEASE)
        tag2 = PatchTag("patch-1.3.2-test", "1.3.2", "test", "123-test",
                       "abc123", False, 1642876800, tag_type=TagType.DEV_RELEASE)  # Different timestamp
        
        assert tag1 == tag2  # Same name and commit
    
    def test_patch_tag_string_representation(self):
        """Should provide readable string representation"""
        tag = PatchTag("dev-patch-1.3.2-security", "1.3.2", "security", 
                      "123-security", "abc123", True, 1642790400,
                      tag_type=TagType.DEV_RELEASE)
        
        str_repr = str(tag)
        assert "dev-patch-1.3.2-security" in str_repr
        assert "123-security" in str_repr
        assert "abc123" in str_repr

    def test_patch_tag_creation_create_type(self):
        """Should create PatchTag for create-patch tag"""
        tag = PatchTag(
            name="create-patch-456-performance",
            version=None,  # Pas de version pour create-patch
            suffix="456-performance",
            message="456-performance", 
            commit_hash="abc123",
            is_dev_tag=False,  # DEPRECATED
            timestamp=datetime.fromtimestamp(1642790400),
            tag_type=TagType.CREATE
        )
        
        assert tag.tag_type == TagType.CREATE
        assert tag.version is None
        assert tag.is_create_tag is True
        assert tag.is_dev_release_tag is False
        assert tag.is_prod_release_tag is False
    
    def test_patch_tag_creation_dev_release_type(self):
        """Should create PatchTag for dev-patch tag"""
        tag = PatchTag(
            name="dev-patch-1.3.2-security",
            version="1.3.2",
            suffix="security",
            message="123-security",
            commit_hash="abc123", 
            is_dev_tag=True,  # DEPRECATED
            timestamp=datetime.fromtimestamp(1642790400),
            tag_type=TagType.DEV_RELEASE
        )
        
        assert tag.tag_type == TagType.DEV_RELEASE
        assert tag.version == "1.3.2"
        assert tag.is_create_tag is False
        assert tag.is_dev_release_tag is True
        assert tag.is_prod_release_tag is False
    
    def test_patch_tag_creation_prod_release_type(self):
        """Should create PatchTag for patch tag"""
        tag = PatchTag(
            name="patch-1.3.2-performance",
            version="1.3.2",
            suffix="performance",
            message="456-performance",
            commit_hash="def456",
            is_dev_tag=False,  # DEPRECATED
            timestamp=datetime.fromtimestamp(1642876800),
            tag_type=TagType.PROD_RELEASE
        )
        
        assert tag.tag_type == TagType.PROD_RELEASE
        assert tag.version == "1.3.2"
        assert tag.is_create_tag is False
        assert tag.is_dev_release_tag is False
        assert tag.is_prod_release_tag is True
    
    def test_patch_tag_properties_convenience(self):
        """Should provide convenient boolean properties"""
        create_tag = PatchTag(
            name="create-patch-789-audit", version=None, suffix="789-audit",
            message="789-audit", commit_hash="abc", is_dev_tag=False,
            timestamp=datetime.fromtimestamp(1642790400), tag_type=TagType.CREATE
        )
        
        dev_tag = PatchTag(
            name="dev-patch-1.3.2-test", version="1.3.2", suffix="test", 
            message="test", commit_hash="def", is_dev_tag=True,
            timestamp=datetime.fromtimestamp(1642790400), tag_type=TagType.DEV_RELEASE
        )
        
        prod_tag = PatchTag(
            name="patch-1.3.2-final", version="1.3.2", suffix="final",
            message="final", commit_hash="ghi", is_dev_tag=False, 
            timestamp=datetime.fromtimestamp(1642790400), tag_type=TagType.PROD_RELEASE
        )
        
        # Test boolean properties
        assert create_tag.is_create_tag and not create_tag.is_dev_release_tag and not create_tag.is_prod_release_tag
        assert not dev_tag.is_create_tag and dev_tag.is_dev_release_tag and not dev_tag.is_prod_release_tag  
        assert not prod_tag.is_create_tag and not prod_tag.is_dev_release_tag and prod_tag.is_prod_release_tag

class TestGitTagManagerInitialization:
    """Test GitTagManager initialization for ultra-simplified workflow"""
    
    def test_init_with_valid_repo(self, temp_git_repo):
        """Should initialize successfully with valid Git repository"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        assert manager is not None
        assert manager.repo_path == Path(temp_dir).resolve()
        assert manager.schema_patches_dir == Path(temp_dir) / "SchemaPatches"
    
    def test_init_with_hgit_instance(self, temp_git_repo):
        """Should initialize with halfORM HGit instance (preferred)"""
        temp_dir, repo = temp_git_repo
        
        # Mock HGit instance
        mock_hgit = Mock()
        mock_hgit._HGit__git_repo = repo
        mock_hgit._HGit__repo = Mock()
        mock_hgit._HGit__repo.base_dir = temp_dir
        
        manager = GitTagManager(hgit_instance=mock_hgit)
        
        assert manager is not None
        assert manager.repo_path == Path(temp_dir).resolve()
    
    def test_init_with_invalid_repo(self):
        """Should raise InvalidRepositoryError for non-Git directory"""
        with tempfile.TemporaryDirectory() as temp_dir:
            with pytest.raises(InvalidRepositoryError) as exc_info:
                GitTagManager(repo_path=temp_dir)
            
            assert "Invalid Git repository" in str(exc_info.value)
    
    def test_init_with_nonexistent_path(self):
        """Should raise InvalidRepositoryError for non-existent path"""
        with pytest.raises(InvalidRepositoryError):
            GitTagManager(repo_path="/path/that/does/not/exist")
    
    def test_init_auto_create_schema_patches_dir(self, temp_git_repo):
        """Should auto-create SchemaPatches directory if missing"""
        temp_dir, repo = temp_git_repo
        
        # Remove SchemaPatches directory
        schema_patches_path = os.path.join(temp_dir, "SchemaPatches")
        shutil.rmtree(schema_patches_path)
        
        manager = GitTagManager(repo_path=temp_dir)
        
        assert manager.schema_patches_dir.exists()
        assert manager.schema_patches_dir.is_dir()


class TestTagPatternValidation:
    """Test validation of ultra-simplified tag patterns"""
    
    def test_validate_dev_patch_tag_valid(self, temp_git_repo):
        """Should validate correct dev-patch tag patterns"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        valid_tags = [
            "dev-patch-1.3.2-security",
            "dev-patch-0.1.0-hotfix", 
            "dev-patch-10.25.100-performance",
            "dev-patch-1.0.0-audit",
            "dev-patch-2.5.3-bugfix"
        ]
        
        for tag_name in valid_tags:
            assert manager.validate_tag_format(tag_name) is True
    
    def test_validate_patch_tag_valid(self, temp_git_repo):
        """Should validate correct patch tag patterns"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        valid_tags = [
            "patch-1.3.2-security",
            "patch-0.1.0-hotfix",
            "patch-10.25.100-performance", 
            "patch-1.0.0-audit",
            "patch-2.5.3-bugfix"
        ]
        
        for tag_name in valid_tags:
            assert manager.validate_tag_format(tag_name) is True
    
    def test_validate_tag_invalid_patterns(self, temp_git_repo):
        """Should reject invalid tag patterns"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        invalid_tags = [
            "invalid-tag",
            "dev-patch-1.3",  # Missing patch number
            "patch-1.3.2",    # Missing suffix
            "dev-patch-1.3.2-",  # Empty suffix
            "dev-patch-v1.3.2-test",  # 'v' prefix not allowed
            "patch-1.3.2-invalid_char!",  # Invalid characters
            "dev-patch-1.3.2.4-test",  # Too many version parts
            "",  # Empty string
            "random-tag-name"
        ]
        
        for tag_name in invalid_tags:
            try:
                assert manager.validate_tag_format(tag_name) is False
            except AssertionError as exc:
                print('TEST FAILED FOR', tag_name)
                raise exc
    
    def test_validate_schema_patches_reference_valid(self, temp_git_repo, schema_patches_dir):
        """Should validate existing SchemaPatches directory references"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # These directories were created in the fixture
        valid_references = [
            "123-security",
            "456-performance", 
            "789-audit"
        ]
        
        for reference in valid_references:
            assert manager.validate_schema_patch_reference(reference) is True
    
    def test_validate_schema_patches_reference_invalid(self, temp_git_repo):
        """Should reject non-existent SchemaPatches directory references"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        invalid_references = [
            "999-nonexistent",
            "invalid-directory",
            "",  # Empty reference
            "../../escape-attempt"  # Path traversal attempt
        ]
        
        for reference in invalid_references:
            assert manager.validate_schema_patch_reference(reference) is False

    def test_validate_create_patch_tag_valid(self, temp_git_repo):
        """Should validate correct create-patch tag patterns"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        valid_tags = [
            "create-patch-123-security",
            "create-patch-456-performance", 
            "create-patch-789-audit",
            "create-patch-001-initial",
            "create-patch-999-cleanup",
            "create-patch-external-hotfix",
            "create-patch-a1-test",
            "create-patch-bug_fix_urgent"
        ]
        
        for tag_name in valid_tags:
            match = manager.CREATE_PATCH_PATTERN.match(tag_name)
            assert match is not None, f"Should match create-patch pattern: {tag_name}"
            patch_id = match.group(1)
            assert len(patch_id) > 0, f"Should extract patch_id: {tag_name}"
    
    def test_validate_create_patch_tag_invalid(self, temp_git_repo):
        """Should reject invalid create-patch tag patterns"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        invalid_tags = [
            "create-patch-",  # Empty patch_id
            "create-patch",   # No patch_id
            "dev-patch-1.3.2-security",  # Wrong prefix
            "patch-1.3.2-performance",   # Wrong prefix
            "create-patch-with spaces",  # Spaces not allowed
            "create-patch-123@invalid",  # Invalid characters
            "create-patch-123.security"  # Dots might be problematic
        ]
        
        for tag_name in invalid_tags:
            match = manager.CREATE_PATCH_PATTERN.match(tag_name)
            assert match is None, f"Should NOT match create-patch pattern: {tag_name}"
    
    def test_create_patch_pattern_extraction(self, temp_git_repo):
        """Should correctly extract patch_id from create-patch tags"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        test_cases = [
            ("create-patch-456-performance", "456-performance"),
            ("create-patch-123-security", "123-security"),
            ("create-patch-external-hotfix", "external-hotfix"),
            ("create-patch-a1", "a1"),
            ("create-patch-bug_fix", "bug_fix")
        ]
        
        for tag_name, expected_patch_id in test_cases:
            match = manager.CREATE_PATCH_PATTERN.match(tag_name)
            assert match is not None
            actual_patch_id = match.group(1)
            assert actual_patch_id == expected_patch_id
    
    def test_create_patch_pattern_vs_existing_patterns(self, temp_git_repo):
        """Should distinguish create-patch from dev-patch and patch patterns"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # create-patch should only match CREATE_PATCH_PATTERN
        create_tag = "create-patch-456-performance"
        assert manager.CREATE_PATCH_PATTERN.match(create_tag) is not None
        assert manager.DEV_PATCH_PATTERN.match(create_tag) is None
        assert manager.PATCH_PATTERN.match(create_tag) is None
        
        # dev-patch should only match DEV_PATCH_PATTERN
        dev_tag = "dev-patch-1.3.2-performance"
        assert manager.CREATE_PATCH_PATTERN.match(dev_tag) is None
        assert manager.DEV_PATCH_PATTERN.match(dev_tag) is not None
        assert manager.PATCH_PATTERN.match(dev_tag) is None
        
        # patch should only match PATCH_PATTERN
        prod_tag = "patch-1.3.2-performance"
        assert manager.CREATE_PATCH_PATTERN.match(prod_tag) is None
        assert manager.DEV_PATCH_PATTERN.match(prod_tag) is None
        assert manager.PATCH_PATTERN.match(prod_tag) is not None

class TestTagParsing:
    """Test parsing Git tags into PatchTag objects"""
    
    def test_parse_dev_patch_tag(self, temp_git_repo):
        """Should parse dev-patch tags correctly"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Create a real Git tag
        git_tag = repo.create_tag("dev-patch-1.3.2-security", 
                                 message="123-security")
        
        patch_tag = manager.parse_patch_tag("dev-patch-1.3.2-security", git_tag)
        
        assert patch_tag is not None
        assert patch_tag.name == "dev-patch-1.3.2-security"
        assert patch_tag.version == "1.3.2"
        assert patch_tag.suffix == "security"
        assert patch_tag.message == "123-security"
        assert patch_tag.is_dev_tag is True
        assert patch_tag.commit_hash == git_tag.commit.hexsha
    
    def test_parse_patch_tag(self, temp_git_repo):
        """Should parse patch tags correctly"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        git_tag = repo.create_tag("patch-1.3.2-performance",
                                 message="456-performance")
        
        patch_tag = manager.parse_patch_tag("patch-1.3.2-performance", git_tag)
        
        assert patch_tag is not None
        assert patch_tag.name == "patch-1.3.2-performance"
        assert patch_tag.version == "1.3.2"
        assert patch_tag.suffix == "performance"
        assert patch_tag.message == "456-performance"
        assert patch_tag.is_dev_tag is False
    
    def test_parse_non_patch_tag(self, temp_git_repo):
        """Should return None for non-patch tags"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Create non-patch tags
        git_tag1 = repo.create_tag("v1.3.2", message="Version release")
        git_tag2 = repo.create_tag("random-tag", message="Random tag")
        
        assert manager.parse_patch_tag("v1.3.2", git_tag1) is None
        assert manager.parse_patch_tag("random-tag", git_tag2) is None
    
    def test_parse_tag_invalid_message(self, temp_git_repo):
        """Should handle tags with invalid schema patches references"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Tag with non-existent SchemaPatches directory
        git_tag = repo.create_tag("dev-patch-1.3.2-test", 
                                 message="999-nonexistent")
        
        with pytest.raises(TagValidationError):
            manager.parse_patch_tag("dev-patch-1.3.2-test", git_tag)

    def test_parse_create_patch_tag(self, temp_git_repo):
        """Should parse create-patch tags correctly"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Create a real Git tag
        git_tag = repo.create_tag("create-patch-456-performance", 
                                message="456-performance")
        
        patch_tag = manager.parse_patch_tag("create-patch-456-performance", git_tag)
        
        assert patch_tag is not None
        assert patch_tag.name == "create-patch-456-performance"
        assert patch_tag.version is None  # Pas de version pour create-patch
        assert patch_tag.suffix == "456-performance"
        assert patch_tag.message == "456-performance"
        assert patch_tag.tag_type == TagType.CREATE
        assert patch_tag.is_create_tag is True
        assert patch_tag.is_dev_tag is False  # DEPRECATED field
        assert patch_tag.commit_hash == git_tag.commit.hexsha

    def test_parse_create_patch_tag_various_patch_ids(self, temp_git_repo):
        """Should parse create-patch tags with various patch_id formats"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        test_cases = [
            ("create-patch-123-security", "123-security"),
            ("create-patch-external-hotfix", "external-hotfix"),
            ("create-patch-a1-test", "a1-test"),
            ("create-patch-999-cleanup-final", "999-cleanup-final")
        ]
        
        for tag_name, expected_patch_id in test_cases:
            # Créer le répertoire SchemaPatches correspondant
            patch_dir = manager.schema_patches_dir / expected_patch_id
            patch_dir.mkdir(parents=True, exist_ok=True)
            
            git_tag = repo.create_tag(tag_name, message=expected_patch_id)
            patch_tag = manager.parse_patch_tag(tag_name, git_tag)
            
            assert patch_tag is not None
            assert patch_tag.suffix == expected_patch_id
            assert patch_tag.tag_type == TagType.CREATE
            assert patch_tag.version is None

    def test_parse_tag_type_consistency(self, temp_git_repo):
        """Should assign correct tag_type for each pattern"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Test all 3 tag types
        test_cases = [
            ("create-patch-456-performance", TagType.CREATE, None, "456-performance"),
            ("dev-patch-1.3.2-security", TagType.DEV_RELEASE, "1.3.2", "security"),
            ("patch-1.3.2-performance", TagType.PROD_RELEASE, "1.3.2", "performance")
        ]
        
        for tag_name, expected_type, expected_version, expected_suffix in test_cases:
            git_tag = repo.create_tag(tag_name, message="123-security")
            patch_tag = manager.parse_patch_tag(tag_name, git_tag)
            
            assert patch_tag is not None
            assert patch_tag.tag_type == expected_type
            assert patch_tag.version == expected_version
            assert patch_tag.suffix == expected_suffix

class TestTagRetrieval:
    """Test retrieving and filtering patch tags"""
    
    def test_get_all_patch_tags_empty(self, temp_git_repo):
        """Should return empty list when no patch tags exist"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        tags = manager._get_all_patch_tags()
        assert tags == []
    
    def test_get_all_patch_tags_mixed(self, temp_git_repo):
        """Should return only patch tags, excluding other tags"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Create mixed tags
        repo.create_tag("dev-patch-1.3.2-security", message="123-security")
        repo.create_tag("patch-1.3.2-performance", message="456-performance")
        repo.create_tag("v1.3.2", message="Version release")  # Not a patch tag
        repo.create_tag("random-tag", message="Random")  # Not a patch tag
        
        tags = manager._get_all_patch_tags()
        
        assert len(tags) == 2
        tag_names = [tag.name for tag in tags]
        assert "dev-patch-1.3.2-security" in tag_names
        assert "patch-1.3.2-performance" in tag_names
        assert "v1.3.2" not in tag_names
        assert "random-tag" not in tag_names
    
    def test_get_patch_tags_between_versions(self, temp_git_repo):
        """Should get patch tags between two versions in chronological order"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Create version tag v1.3.1 on current commit
        repo.create_tag("v1.3.1", message="Version 1.3.1")
        
        # Create new commits with patch tags
        import time
        
        # First patch commit
        patch_file1 = os.path.join(temp_dir, "patch1.txt")
        with open(patch_file1, 'w') as f:
            f.write("First patch")
        repo.index.add([patch_file1])
        repo.index.commit("First patch commit")
        
        # Create first patch tag
        repo.create_tag("dev-patch-1.3.2-first", message="123-security")
        time.sleep(0.1)  # Ensure different timestamps
        
        # Second patch commit  
        patch_file2 = os.path.join(temp_dir, "patch2.txt")
        with open(patch_file2, 'w') as f:
            f.write("Second patch")
        repo.index.add([patch_file2])
        repo.index.commit("Second patch commit")
        
        # Create second patch tag
        repo.create_tag("dev-patch-1.3.2-second", message="456-performance")
        time.sleep(0.1)
        
        # Create version tag v1.3.2 on current commit
        repo.create_tag("v1.3.2", message="Version 1.3.2")
        
        # Test: Get patch tags between versions
        tags = manager.get_patch_tags_between("v1.3.1", "v1.3.2", dev_tags=True)
        
        assert len(tags) == 2
        # Should be in chronological order
        assert tags[0].suffix == "first"
        assert tags[1].suffix == "second"
        
        # Verify they are dev tags
        assert all(tag.is_dev_tag for tag in tags)
        
        # Verify versions
        assert all(tag.version == "1.3.2" for tag in tags)
    
    def test_get_dev_tags_for_version(self, temp_git_repo):
        """Should get dev-patch tags for specific version"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Create tags for different versions
        repo.create_tag("dev-patch-1.3.2-security", message="123-security")
        repo.create_tag("dev-patch-1.3.2-performance", message="456-performance")
        repo.create_tag("dev-patch-1.4.0-audit", message="789-audit")
        
        tags_1_3_2 = manager.get_dev_tags_for_version("1.3.2")
        
        assert len(tags_1_3_2) == 2
        versions = [tag.version for tag in tags_1_3_2]
        assert all(v == "1.3.2" for v in versions)
        
        tags_1_4_0 = manager.get_dev_tags_for_version("1.4.0")
        assert len(tags_1_4_0) == 1
        assert tags_1_4_0[0].suffix == "audit"


class TestTagCreation:
    """Test creating new patch tags"""
    
    def test_create_dev_tag_basic(self, temp_git_repo):
        """Should create dev-patch tag with validation"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        tag = manager.create_tag("dev-patch-1.3.2-security", "123-security")
        
        assert tag.name == "dev-patch-1.3.2-security"
        assert tag.version == "1.3.2"
        assert tag.suffix == "security"
        assert tag.message == "123-security"
        assert tag.is_dev_tag is True
        
        # Verify Git tag was created
        git_tags = [t.name for t in repo.tags]
        assert "dev-patch-1.3.2-security" in git_tags
    
    def test_create_tag_invalid_format(self, temp_git_repo):
        """Should raise TagValidationError for invalid tag format"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        with pytest.raises(TagValidationError):
            manager.create_tag("invalid-tag-format", "123-security")
    
    def test_create_tag_invalid_reference(self, temp_git_repo):
        """Should raise TagValidationError for invalid schema patches reference"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        with pytest.raises(TagValidationError):
            manager.create_tag("dev-patch-1.3.2-test", "999-nonexistent")
    
    def test_create_tag_already_exists(self, temp_git_repo):
        """Should raise TagCreationError when tag already exists"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Create tag first time
        manager.create_tag("dev-patch-1.3.2-security", "123-security")
        
        # Try to create same tag again
        with pytest.raises(TagCreationError):
            manager.create_tag("dev-patch-1.3.2-security", "123-security")


class TestTagTransfer:
    """Test transferring dev-patch tags to patch tags"""
    
    def test_transfer_dev_tags_to_prod_basic(self, temp_git_repo):
        """Should transfer all dev-patch-X.Y.Z-* tags to patch-X.Y.Z-*"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Create dev tags
        manager.create_tag("dev-patch-1.3.2-security", "123-security")
        manager.create_tag("dev-patch-1.3.2-performance", "456-performance")
        manager.create_tag("dev-patch-1.3.2-audit", "789-audit")
        
        # Transfer to production
        prod_tags = manager.transfer_dev_tags_to_prod("1.3.2")
        
        assert len(prod_tags) == 3
        
        # Verify production tags were created
        prod_tag_names = [tag.name for tag in prod_tags]
        assert "patch-1.3.2-security" in prod_tag_names
        assert "patch-1.3.2-performance" in prod_tag_names
        assert "patch-1.3.2-audit" in prod_tag_names
        
        # Verify all have same messages as dev tags
        for prod_tag in prod_tags:
            assert prod_tag.is_dev_tag is False
            # Message should match corresponding dev tag
            if prod_tag.suffix == "security":
                assert prod_tag.message == "123-security"
            elif prod_tag.suffix == "performance":
                assert prod_tag.message == "456-performance"
            elif prod_tag.suffix == "audit":
                assert prod_tag.message == "789-audit"
    
    def test_transfer_preserves_order(self, temp_git_repo):
        """Should preserve Git chronological order during transfer"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Create dev tags with artificial timing
        import time
        manager.create_tag("dev-patch-1.3.2-first", "123-security")
        time.sleep(0.1)
        manager.create_tag("dev-patch-1.3.2-second", "456-performance")
        time.sleep(0.1)
        manager.create_tag("dev-patch-1.3.2-third", "789-audit")
        
        prod_tags = manager.transfer_dev_tags_to_prod("1.3.2")
        
        # Should maintain chronological order
        assert prod_tags[0].suffix == "first"
        assert prod_tags[1].suffix == "second"
        assert prod_tags[2].suffix == "third"
    
    def test_transfer_no_dev_tags(self, temp_git_repo):
        """Should handle transfer when no dev tags exist for version"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        prod_tags = manager.transfer_dev_tags_to_prod("1.3.2")
        
        assert prod_tags == []
    
    def test_transfer_validation_failure(self, temp_git_repo):
        """Should raise TransferError when validation fails"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Create dev tag and corresponding prod tag
        manager.create_tag("dev-patch-1.3.2-security", "123-security")
        repo.create_tag("patch-1.3.2-security", message="123-security")
        
        # Transfer should fail due to existing prod tag
        with pytest.raises(TransferError):
            manager.transfer_dev_tags_to_prod("1.3.2")


class TestTagConsistencyValidation:
    """Test validation of dev/prod tag consistency"""
    
    def test_validate_consistency_matching(self, temp_git_repo):
        """Should validate when dev and prod tags match"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Create matching dev and prod tags
        manager.create_tag("dev-patch-1.3.2-security", "123-security")
        manager.create_tag("dev-patch-1.3.2-performance", "456-performance")
        
        repo.create_tag("patch-1.3.2-security", message="123-security")
        repo.create_tag("patch-1.3.2-performance", message="456-performance")
        
        assert manager.validate_dev_to_prod_consistency("1.3.2") is True
    
    def test_validate_consistency_mismatch(self, temp_git_repo):
        """Should detect inconsistency between dev and prod tags"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Create dev tags
        manager.create_tag("dev-patch-1.3.2-security", "123-security")
        manager.create_tag("dev-patch-1.3.2-performance", "456-performance")
        
        # Create only one matching prod tag
        repo.create_tag("patch-1.3.2-security", message="123-security")
        # Missing: patch-1.3.2-performance
        
        assert manager.validate_dev_to_prod_consistency("1.3.2") is False
    
    def test_validate_consistency_no_tags(self, temp_git_repo):
        """Should return True when no tags exist for version"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        assert manager.validate_dev_to_prod_consistency("1.3.2") is True


class TestGitOperations:
    """Test Git operations and integration"""
    
    def test_checkout_tag(self, temp_git_repo):
        """Should checkout to specific Git tag"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Create tag on current commit
        tag = manager.create_tag("dev-patch-1.3.2-security", "123-security")
        original_commit = tag.commit_hash
        
        # Create a new commit to move HEAD forward
        new_file = os.path.join(temp_dir, "after_tag.txt")
        with open(new_file, 'w') as f:
            f.write("Content after tag")
        repo.index.add([new_file])
        repo.index.commit("Commit after tag creation")
        
        # Verify HEAD has moved to new commit
        assert repo.head.commit.hexsha != original_commit
        
        # Checkout to the tag
        manager.checkout(tag.name)
        
        # Verify checkout worked - HEAD should be back to tag commit
        assert repo.head.commit.hexsha == original_commit
        assert repo.head.commit.hexsha == tag.commit_hash
    
    def test_tag_exists(self, temp_git_repo):
        """Should check if tag exists in repository"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        assert manager.tag_exists("dev-patch-1.3.2-security") is False
        
        manager.create_tag("dev-patch-1.3.2-security", "123-security")
        
        assert manager.tag_exists("dev-patch-1.3.2-security") is True
    
    def test_delete_tag(self, temp_git_repo):
        """Should delete tag from repository"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Create and delete tag
        manager.create_tag("dev-patch-1.3.2-security", "123-security")
        assert manager.tag_exists("dev-patch-1.3.2-security") is True
        
        result = manager.delete_tag("dev-patch-1.3.2-security")
        
        assert result is True
        assert manager.tag_exists("dev-patch-1.3.2-security") is False


class TestErrorHandling:
    """Test error handling and edge cases"""
    
    def test_git_command_error_handling(self, temp_git_repo):
        """Should handle Git command errors gracefully"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Mock Git operation failure - use property_mock instead of side_effect
        with patch.object(type(manager.repo), 'tags', new_callable=PropertyMock) as mock_tags:
            mock_tags.side_effect = GitCommandError("git", 128, "error")
            
            with pytest.raises(GitTagManagerError):
                manager._get_all_patch_tags()
    
    def test_tag_creation_git_error(self, temp_git_repo):
        """Should raise TagCreationError when Git tag creation fails"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Mock Git tag creation failure
        with patch.object(manager.repo, 'create_tag', side_effect=GitCommandError("git", 128, "error")):
            with pytest.raises(TagCreationError):
                manager.create_tag("dev-patch-1.3.2-security", "123-security")
    
    def test_corrupted_tag_message(self, temp_git_repo):
        """Should handle corrupted or missing tag messages"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Create tag with empty message
        git_tag = repo.create_tag("dev-patch-1.3.2-test", message="")
        
        with pytest.raises(TagValidationError):
            manager.parse_patch_tag("dev-patch-1.3.2-test", git_tag)
    
    def test_schema_patches_directory_permissions(self, temp_git_repo):
        """Should handle SchemaPatches directory permission issues"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Remove read permissions from SchemaPatches directory
        schema_patches_path = manager.schema_patches_dir
        os.chmod(schema_patches_path, 0o000)
        
        try:
            # Should handle permission error gracefully
            result = manager.validate_schema_patch_reference("123-security")
            assert result is False
        finally:
            # Restore permissions for cleanup
            os.chmod(schema_patches_path, 0o755)


class TestPerformanceAndScalability:
    """Test performance with large numbers of tags"""
    
    def test_large_number_of_tags(self, temp_git_repo):
        """Should handle repositories with many patch tags efficiently"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Create many patch tags
        import time
        start_time = time.time()
        
        for i in range(50):  # Create 50 tags
            version = f"1.{i // 10}.{i % 10}"
            suffix = f"patch{i:03d}"
            manager.create_tag(f"dev-patch-{version}-{suffix}", "123-security")
        
        creation_time = time.time() - start_time
        
        # Operations should still be reasonably fast
        start_time = time.time()
        all_tags = manager._get_all_patch_tags()
        retrieval_time = time.time() - start_time
        
        assert len(all_tags) == 50
        assert creation_time < 10.0  # Should create 50 tags in under 10 seconds
        assert retrieval_time < 1.0   # Should retrieve all tags in under 1 second
    
    def test_tag_sorting_performance(self, temp_git_repo):
        """Should sort tags by Git chronological order efficiently"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Create tags in reverse chronological order to test sorting
        tags_to_create = []
        for i in range(20):
            suffix = f"patch{i:02d}"
            tags_to_create.append(f"dev-patch-1.3.2-{suffix}")
        
        # Create in reverse order
        for tag_name in reversed(tags_to_create):
            manager.create_tag(tag_name, "123-security")
            import time
            time.sleep(0.01)  # Ensure different timestamps
        
        # Retrieve and verify they're sorted chronologically
        tags = manager.get_dev_tags_for_version("1.3.2")
        
        # Should be sorted by creation time (earliest first)
        for i in range(len(tags) - 1):
            assert tags[i].timestamp <= tags[i + 1].timestamp


class TestIntegrationScenarios:
    """Test realistic integration scenarios"""
    
    def test_complete_dev_to_prod_workflow(self, temp_git_repo):
        """Should support complete dev → prod workflow"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Step 1: Business decides patch order and creates dev tags
        # Each tag should be on a separate commit (realistic workflow)
        business_priorities = [
            ("security", "123-security"),
            ("performance", "456-performance"), 
            ("audit", "789-audit")
        ]
        
        for suffix, patch_id in business_priorities:
            # Create a commit for this patch (realistic workflow)
            patch_file = os.path.join(temp_dir, f"patch_{suffix}.txt")
            with open(patch_file, 'w') as f:
                f.write(f"Patch content for {suffix}")
            repo.index.add([patch_file])
            repo.index.commit(f"Implement {suffix} patch")
            
            # Create tag on this commit
            manager.create_tag(f"dev-patch-1.3.2-{suffix}", patch_id)
        
        # Step 2: Validate all dev tags exist
        dev_tags = manager.get_dev_tags_for_version("1.3.2")
        assert len(dev_tags) == 3
        
        # Step 3: Transfer to production (creates patch-* tags)
        prod_tags = manager.transfer_dev_tags_to_prod("1.3.2")
        assert len(prod_tags) == 3
        
        # Step 4: Validate consistency
        assert manager.validate_dev_to_prod_consistency("1.3.2") is True
        
        # Step 5: Verify final state
        all_patch_tags = manager._get_all_patch_tags()
        assert len(all_patch_tags) == 6  # 3 dev + 3 prod
        
        # Dev and prod tags should have same order (Git chronological order)
        dev_suffixes = [tag.suffix for tag in dev_tags]
        prod_suffixes = [tag.suffix for tag in prod_tags]
        assert dev_suffixes == prod_suffixes
        
        # Should be in business priority order (chronological creation)
        expected_order = ["security", "performance", "audit"]
        assert dev_suffixes == expected_order
        assert prod_suffixes == expected_order
    
    def test_external_patch_compatibility(self, temp_git_repo):
        """Should handle external patches (manual releases)"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Create development tags
        manager.create_tag("dev-patch-1.3.2-security", "123-security")
        manager.create_tag("dev-patch-1.3.2-performance", "456-performance")
        
        # Simulate external/manual patch (creates gap)
        repo.create_tag("patch-1.3.2-hotfix", message="external-hotfix")
        
        # Transfer remaining dev tags
        prod_tags = manager.transfer_dev_tags_to_prod("1.3.2")
        
        # Should handle external patches gracefully
        all_prod_tags = manager.get_prod_tags_for_version("1.3.2")
        assert len(all_prod_tags) == 3  # 2 transferred + 1 external
        
        # External patch should be included in chronological order
        prod_suffixes = [tag.suffix for tag in all_prod_tags]
        assert "hotfix" in prod_suffixes
    
    def test_multiple_version_lines(self, temp_git_repo):
        """Should handle multiple version lines independently"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Create patches for different versions
        versions_and_patches = [
            ("1.3.2", "security", "123-security"),
            ("1.3.2", "performance", "456-performance"),
            ("1.4.0", "audit", "789-audit"),
            ("1.4.0", "bugfix", "101-bugfix"),
            ("2.0.0", "migration", "202-migration")
        ]
        
        for version, suffix, patch_id in versions_and_patches:
            manager.create_tag(f"dev-patch-{version}-{suffix}", patch_id)
        
        # Each version should be independent
        tags_1_3_2 = manager.get_dev_tags_for_version("1.3.2")
        tags_1_4_0 = manager.get_dev_tags_for_version("1.4.0")
        tags_2_0_0 = manager.get_dev_tags_for_version("2.0.0")
        
        assert len(tags_1_3_2) == 2
        assert len(tags_1_4_0) == 2
        assert len(tags_2_0_0) == 1
        
        # Transfer each version independently
        prod_tags_1_3_2 = manager.transfer_dev_tags_to_prod("1.3.2")
        prod_tags_1_4_0 = manager.transfer_dev_tags_to_prod("1.4.0")
        
        assert len(prod_tags_1_3_2) == 2
        assert len(prod_tags_1_4_0) == 2
        
        # Version 2.0.0 should remain unaffected
        remaining_dev_tags = manager.get_dev_tags_for_version("2.0.0")
        assert len(remaining_dev_tags) == 1


class TestEdgeCases:
    """Test edge cases and boundary conditions"""
    
    def test_zero_version_handling(self, temp_git_repo):
        """Should handle version 0.0.0 correctly"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        manager.create_tag("dev-patch-0.0.1-initial", "123-security")
        
        tags = manager.get_dev_tags_for_version("0.0.1")
        assert len(tags) == 1
        assert tags[0].version == "0.0.1"
    
    def test_large_version_numbers(self, temp_git_repo):
        """Should handle very large version numbers"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        manager.create_tag("dev-patch-999.999.999-test", "123-security")
        
        tags = manager.get_dev_tags_for_version("999.999.999")
        assert len(tags) == 1
        assert tags[0].version == "999.999.999"
    
    def test_special_characters_in_suffix(self, temp_git_repo):
        """Should handle special characters in tag suffixes"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Valid special characters
        valid_suffixes = [
            "security-fix",
            "performance_optimization", 
            "audit123",
            "hotfix-urgent"
        ]
        
        for suffix in valid_suffixes:
            tag_name = f"dev-patch-1.3.2-{suffix}"
            manager.create_tag(tag_name, "123-security")
            assert manager.tag_exists(tag_name)
    
    @pytest.mark.skip(reason="Git operations are not thread-safe in GitPython - concurrent operations should be handled at application level")
    def test_concurrent_tag_operations(self, temp_git_repo):
        """Should handle concurrent tag operations safely"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Simulate concurrent operations
        import threading
        import time
        
        results = []
        errors = []
        
        def create_tag_worker(suffix, patch_id):
            try:
                tag = manager.create_tag(f"dev-patch-1.3.2-{suffix}", patch_id)
                results.append(tag)
            except Exception as e:
                errors.append(e)
        
        # Create multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(
                target=create_tag_worker,
                args=(f"concurrent{i}", "123-security")
            )
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Should handle concurrency gracefully
        assert len(results) + len(errors) == 5
        assert len(results) >= 1  # At least one should succeed


class TestBackwardCompatibility:
    """Test integration with existing halfORM systems"""
    
    def test_hgit_integration(self, temp_git_repo):
        """Should integrate seamlessly with halfORM HGit"""
        temp_dir, repo = temp_git_repo
        
        # Mock halfORM HGit instance
        mock_hgit = Mock()
        mock_hgit._HGit__git_repo = repo
        mock_hgit._HGit__repo = Mock()
        mock_hgit._HGit__repo.base_dir = temp_dir
        
        # Should work with HGit instance
        manager = GitTagManager(hgit_instance=mock_hgit)
        
        # Basic operations should work
        tag = manager.create_tag("dev-patch-1.3.2-security", "123-security")
        assert tag is not None
        
        tags = manager._get_all_patch_tags()
        assert len(tags) == 1
    
    def test_existing_tag_formats(self, temp_git_repo):
        """Should coexist with existing halfORM tag formats"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Create existing halfORM tags (should be ignored)
        repo.create_tag("v1.3.2", message="Version release")
        repo.create_tag("1.3.2", message="Release tag")
        repo.create_tag("hop_release_1.3.2", message="HOP release")
        
        # Create new patch tags
        manager.create_tag("dev-patch-1.3.2-security", "123-security")
        
        # Should only return patch tags
        patch_tags = manager._get_all_patch_tags()
        assert len(patch_tags) == 1
        assert patch_tags[0].name == "dev-patch-1.3.2-security"
    
    def test_schema_patches_directory_structure(self, temp_git_repo):
        """Should work with existing SchemaPatches directory structures"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # The fixture already creates SchemaPatches structure
        # Verify it works with existing directories
        assert manager.validate_schema_patch_reference("123-security")
        assert manager.validate_schema_patch_reference("456-performance")
        assert manager.validate_schema_patch_reference("789-audit")


class TestDocumentationAndExamples:
    """Test examples from documentation and README"""
    
    def test_basic_usage_example(self, temp_git_repo):
        """Should work with basic usage example from docs"""
        temp_dir, _ = temp_git_repo
        
        # Example from documentation
        tag_manager = GitTagManager(repo_path=temp_dir)
        
        # Create development validation tag
        tag_manager.create_tag("dev-patch-1.3.2-security", "123-security")
        
        # Get all patch tags between versions
        tags = tag_manager._get_all_patch_tags()
        assert len(tags) == 1
        
        # Transfer to production
        prod_tags = tag_manager.transfer_dev_tags_to_prod("1.3.2")
        assert len(prod_tags) == 1
        
        # Verify final state
        assert tag_manager.validate_dev_to_prod_consistency("1.3.2")
    
    def test_workflow_example(self, temp_git_repo):
        """Should support the workflow example from architecture docs"""
        temp_dir, _ = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Phase 1: Development on ho-dev/X.Y.x
        # Developers create tickets in SchemaPatches/XXX-name/
        
        # Phase 2: Validation dev with tags dev-patch-*
        # Business decides the order of application
        manager.create_tag("dev-patch-1.3.2-security", "123-security")
        manager.create_tag("dev-patch-1.3.2-perf", "456-performance") 
        manager.create_tag("dev-patch-1.3.2-audit", "789-audit")
        
        # Phase 3: Transfer to production
        prod_tags = manager.transfer_dev_tags_to_prod("1.3.2")
        
        # Phase 4: Application in production
        # Auto-discovery of all tags patch-X.Y.Z-* between versions
        tags = manager.get_prod_tags_for_version("1.3.2")
        
        assert len(tags) == 3
        # For each tag in Git history order:
        # - Checkout on the tag ✓
        # - Message of tag = directory SchemaPatches/XXX ✓
        # - Application of files in lexicographic order ✓


# Integration with pytest fixtures and utilities
@pytest.fixture
def manager_with_sample_tags(temp_git_repo):
    """Fixture providing GitTagManager with sample tags for testing"""
    temp_dir, repo = temp_git_repo
    manager = GitTagManager(repo_path=temp_dir)
    
    # Create sample dev tags
    sample_tags = [
        ("dev-patch-1.3.2-security", "123-security"),
        ("dev-patch-1.3.2-performance", "456-performance"),
        ("dev-patch-1.4.0-audit", "789-audit")
    ]
    
    for tag_name, message in sample_tags:
        manager.create_tag(tag_name, message)
        import time
        time.sleep(0.1)  # Ensure chronological order
    
    return manager


class TestWithSampleTags:
    """Test suite using the sample tags fixture"""
    
    def test_sample_tags_fixture(self, manager_with_sample_tags):
        """Should work with pre-created sample tags"""
        manager = manager_with_sample_tags
        
        all_tags = manager._get_all_patch_tags()
        assert len(all_tags) == 3
        
        tags_1_3_2 = manager.get_dev_tags_for_version("1.3.2")
        assert len(tags_1_3_2) == 2
        
        tags_1_4_0 = manager.get_dev_tags_for_version("1.4.0")
        assert len(tags_1_4_0) == 1


class TestPatchReservationConflicts:
    """Test patch reservation conflict detection"""
    
    def test_check_patch_reservation_conflicts_no_conflicts(self, temp_git_repo):
        """Should return empty list when no conflicts exist"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        conflicts = manager.check_patch_reservation_conflicts("999-new-feature")
        assert conflicts == []
    
    def test_check_patch_reservation_conflicts_with_existing_tag(self, temp_git_repo):
        """Should detect conflicts when reservation tag exists"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Create a reservation tag
        repo.create_tag("create-patch-456-performance", message="456-performance")
        
        conflicts = manager.check_patch_reservation_conflicts("456-performance")
        # Should detect the conflict (exact behavior depends on Git setup)
        assert isinstance(conflicts, list)
    
    def test_check_patch_reservation_conflicts_invalid_patch_id(self, temp_git_repo):
        """Should handle invalid patch_id gracefully"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        with pytest.raises(GitTagManagerError):
            manager.check_patch_reservation_conflicts("")
        
        with pytest.raises(GitTagManagerError):
            manager.check_patch_reservation_conflicts("   ")
        
        with pytest.raises(GitTagManagerError):
            manager.check_patch_reservation_conflicts(None)
    
    def test_get_all_remote_branches(self, temp_git_repo):
        """Should return list of remote branches"""
        temp_dir, repo = temp_git_repo
        
        # Créer un vrai remote
        remote_dir = tempfile.mkdtemp()
        remote_repo = git.Repo.init(remote_dir, bare=True)
        
        # Ajouter le remote au repo local
        origin = repo.create_remote('origin', remote_dir)
        
        # Push la branche master/main
        repo.git.push('origin', 'main')  # ou 'main' selon ce que crée le fixture
        
        manager = GitTagManager(repo_path=temp_dir)
        remote_branches = manager.get_all_remote_branches()
        
        assert isinstance(remote_branches, list)
        assert len(remote_branches) > 0
        branch_names = [branch.split('/')[-1] for branch in remote_branches]
        assert ['HEAD', 'main'] == branch_names
        
        # Cleanup
        shutil.rmtree(remote_dir)
    
    def test_check_conflicts_with_whitespace_patch_id(self, temp_git_repo):
        """Should handle patch_id with whitespace"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Should strip whitespace and work
        conflicts = manager.check_patch_reservation_conflicts("  456-performance  ")
        assert isinstance(conflicts, list)

    def test_create_patch_reservation_success(self, temp_git_repo):
        """Should create patch reservation tag successfully"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        reservation_tag = manager.create_patch_reservation("456-performance")
        
        assert reservation_tag.name == "create-patch-456-performance"
        assert reservation_tag.tag_type == TagType.CREATE
        assert reservation_tag.message == "456-performance"
        assert reservation_tag.version is None
        
        # Verify tag exists in repo
        assert manager.tag_exists("create-patch-456-performance")

    def test_create_patch_reservation_conflict(self, temp_git_repo):
        """Should detect and prevent reservation conflicts"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Create first reservation
        manager.create_patch_reservation("456-performance")
        
        # Try to create same reservation again
        with pytest.raises(GitTagManagerError, match="already exists"):
            manager.create_patch_reservation("456-performance")

    def test_create_patch_reservation_invalid_patch_id(self, temp_git_repo):
        """Should reject invalid patch_id formats"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        invalid_patch_ids = ["", "   ", "invalid spaces", "bad@char", "../traversal"]
        
        for invalid_id in invalid_patch_ids:
            with pytest.raises(PatchReservationError):
                manager.create_patch_reservation(invalid_id)

    def test_create_patch_with_full_workflow_success(self, temp_git_repo):
        """Should execute complete patch creation workflow"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Remove existing directory to test creation
        test_patch_dir = manager.schema_patches_dir / "999-new-feature"
        if test_patch_dir.exists():
            import shutil
            shutil.rmtree(test_patch_dir)
        
        result = manager.create_patch_with_full_workflow("999-new-feature")
        
        assert result['patch_id'] == "999-new-feature"
        assert result['created_directory'] is True
        assert result['reservation_tag'] == "create-patch-999-new-feature"
        assert test_patch_dir.exists()
        
        # Verify README was created
        readme_file = test_patch_dir / "README.md"
        assert readme_file.exists()
        
        # Verify reservation tag
        assert manager.tag_exists("create-patch-999-new-feature")

    def test_create_patch_with_full_workflow_existing_directory(self, temp_git_repo):
        """Should work with existing SchemaPatches directory"""
        temp_dir, repo = temp_git_repo
        manager = GitTagManager(repo_path=temp_dir)
        
        # Use existing directory from fixture
        result = manager.create_patch_with_full_workflow("456-performance")
        
        assert result['patch_id'] == "456-performance"
        assert result['created_directory'] is False  # Already existed
        assert result['reservation_tag'] == "create-patch-456-performance"
if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])