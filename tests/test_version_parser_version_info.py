#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unit tests for VersionInfo dataclass

Tests the VersionInfo dataclass which represents structured version information
with Git branch and tag naming for the halfORM Git-centric workflow.
"""

import pytest
from dataclasses import FrozenInstanceError

from half_orm_dev.version_parser import VersionInfo, ReleaseType, BranchType


class TestVersionInfo:
    """Test suite for VersionInfo dataclass"""
    
    def test_version_info_creation_basic(self):
        """Test basic VersionInfo creation with all required fields"""
        version_info = VersionInfo(
            major=1,
            minor=3,
            patch=1,
            version_string="1.3.1",
            dev_branch="ho-dev/1.3.x",
            production_branch="ho/1.3.x",
            release_tag="v1.3.1",
            release_type=ReleaseType.PATCH,
            branch_type=BranchType.DEVELOPMENT
        )
        
        assert version_info.major == 1
        assert version_info.minor == 3
        assert version_info.patch == 1
        assert version_info.version_string == "1.3.1"
        assert version_info.dev_branch == "ho-dev/1.3.x"
        assert version_info.production_branch == "ho/1.3.x"
        assert version_info.release_tag == "v1.3.1"
        assert version_info.release_type == ReleaseType.PATCH
        assert version_info.branch_type == BranchType.DEVELOPMENT
    
    def test_version_info_equality(self):
        """Test VersionInfo equality comparison"""
        version1 = VersionInfo(
            major=1, minor=3, patch=1, version_string="1.3.1",
            dev_branch="ho-dev/1.3.x", production_branch="ho/1.3.x",
            release_tag="v1.3.1", release_type=ReleaseType.PATCH,
            branch_type=BranchType.DEVELOPMENT
        )
        
        version2 = VersionInfo(
            major=1, minor=3, patch=1, version_string="1.3.1",
            dev_branch="ho-dev/1.3.x", production_branch="ho/1.3.x",
            release_tag="v1.3.1", release_type=ReleaseType.PATCH,
            branch_type=BranchType.DEVELOPMENT
        )
        
        assert version1 == version2
    
    def test_version_info_inequality(self):
        """Test VersionInfo inequality when fields differ"""
        version1 = VersionInfo(
            major=1, minor=3, patch=1, version_string="1.3.1",
            dev_branch="ho-dev/1.3.x", production_branch="ho/1.3.x",
            release_tag="v1.3.1", release_type=ReleaseType.PATCH,
            branch_type=BranchType.DEVELOPMENT
        )
        
        version2 = VersionInfo(
            major=1, minor=3, patch=2, version_string="1.3.2",  # Different patch
            dev_branch="ho-dev/1.3.x", production_branch="ho/1.3.x",
            release_tag="v1.3.2", release_type=ReleaseType.PATCH,
            branch_type=BranchType.DEVELOPMENT
        )
        
        assert version1 != version2
    
    def test_version_info_major_release(self):
        """Test VersionInfo for major release (2.0.0)"""
        version_info = VersionInfo(
            major=2,
            minor=0,
            patch=0,
            version_string="2.0.0",
            dev_branch="ho-dev/2.0.x",
            production_branch="ho/2.0.x",
            release_tag="v2.0.0",
            release_type=ReleaseType.MAJOR,
            branch_type=BranchType.DEVELOPMENT
        )
        
        assert version_info.major == 2
        assert version_info.minor == 0
        assert version_info.patch == 0
        assert version_info.release_type == ReleaseType.MAJOR
        assert "2.0.x" in version_info.dev_branch
        assert "2.0.x" in version_info.production_branch
        assert version_info.release_tag == "v2.0.0"
    
    def test_version_info_minor_release(self):
        """Test VersionInfo for minor release (1.4.0)"""
        version_info = VersionInfo(
            major=1,
            minor=4,
            patch=0,
            version_string="1.4.0",
            dev_branch="ho-dev/1.4.x",
            production_branch="ho/1.4.x",
            release_tag="v1.4.0",
            release_type=ReleaseType.MINOR,
            branch_type=BranchType.DEVELOPMENT
        )
        
        assert version_info.major == 1
        assert version_info.minor == 4
        assert version_info.patch == 0
        assert version_info.release_type == ReleaseType.MINOR
        assert "1.4.x" in version_info.dev_branch
        assert "1.4.x" in version_info.production_branch
        assert version_info.release_tag == "v1.4.0"
    
    def test_version_info_patch_release(self):
        """Test VersionInfo for patch release (1.3.5)"""
        version_info = VersionInfo(
            major=1,
            minor=3,
            patch=5,
            version_string="1.3.5",
            dev_branch="ho-dev/1.3.x",
            production_branch="ho/1.3.x",
            release_tag="v1.3.5",
            release_type=ReleaseType.PATCH,
            branch_type=BranchType.DEVELOPMENT
        )
        
        assert version_info.major == 1
        assert version_info.minor == 3
        assert version_info.patch == 5
        assert version_info.release_type == ReleaseType.PATCH
        assert "1.3.x" in version_info.dev_branch
        assert "1.3.x" in version_info.production_branch
        assert version_info.release_tag == "v1.3.5"
    
    def test_version_info_production_branch_type(self):
        """Test VersionInfo with production branch type"""
        version_info = VersionInfo(
            major=1,
            minor=3,
            patch=1,
            version_string="1.3.1",
            dev_branch="ho-dev/1.3.x",
            production_branch="ho/1.3.x",
            release_tag="v1.3.1",
            release_type=ReleaseType.PATCH,
            branch_type=BranchType.PRODUCTION
        )
        
        assert version_info.branch_type == BranchType.PRODUCTION
    
    def test_version_info_zero_version(self):
        """Test VersionInfo with initial version 0.0.0"""
        version_info = VersionInfo(
            major=0,
            minor=0,
            patch=0,
            version_string="0.0.0",
            dev_branch="ho-dev/0.0.x",
            production_branch="ho/0.0.x",
            release_tag="v0.0.0",
            release_type=ReleaseType.MAJOR,
            branch_type=BranchType.DEVELOPMENT
        )
        
        assert version_info.major == 0
        assert version_info.minor == 0
        assert version_info.patch == 0
        assert version_info.version_string == "0.0.0"
    
    def test_version_info_large_numbers(self):
        """Test VersionInfo with large version numbers"""
        version_info = VersionInfo(
            major=10,
            minor=25,
            patch=100,
            version_string="10.25.100",
            dev_branch="ho-dev/10.25.x",
            production_branch="ho/10.25.x",
            release_tag="v10.25.100",
            release_type=ReleaseType.PATCH,
            branch_type=BranchType.DEVELOPMENT
        )
        
        assert version_info.major == 10
        assert version_info.minor == 25
        assert version_info.patch == 100
        assert "10.25.x" in version_info.dev_branch
        assert "10.25.x" in version_info.production_branch
        assert version_info.release_tag == "v10.25.100"
    
    def test_version_info_string_representation(self):
        """Test string representation of VersionInfo"""
        version_info = VersionInfo(
            major=1,
            minor=3,
            patch=1,
            version_string="1.3.1",
            dev_branch="ho-dev/1.3.x",
            production_branch="ho/1.3.x",
            release_tag="v1.3.1",
            release_type=ReleaseType.PATCH,
            branch_type=BranchType.DEVELOPMENT
        )
        
        str_repr = str(version_info)
        assert "1.3.1" in str_repr
        assert "ho-dev/1.3.x" in str_repr
        assert "ho/1.3.x" in str_repr
        assert "v1.3.1" in str_repr
    
    def test_version_info_repr(self):
        """Test repr representation of VersionInfo"""
        version_info = VersionInfo(
            major=1,
            minor=3,
            patch=1,
            version_string="1.3.1",
            dev_branch="ho-dev/1.3.x",
            production_branch="ho/1.3.x",
            release_tag="v1.3.1",
            release_type=ReleaseType.PATCH,
            branch_type=BranchType.DEVELOPMENT
        )
        
        repr_str = repr(version_info)
        assert "VersionInfo" in repr_str
        assert "major=1" in repr_str
        assert "minor=3" in repr_str
        assert "patch=1" in repr_str
    
    def test_version_info_branch_consistency(self):
        """Test that branch names are consistent with version components"""
        version_info = VersionInfo(
            major=2,
            minor=1,
            patch=3,
            version_string="2.1.3",
            dev_branch="ho-dev/2.1.x",
            production_branch="ho/2.1.x",
            release_tag="v2.1.3",
            release_type=ReleaseType.PATCH,
            branch_type=BranchType.DEVELOPMENT
        )
        
        # Both branches should reference the same major.minor line
        assert "2.1.x" in version_info.dev_branch
        assert "2.1.x" in version_info.production_branch
        
        # Tag should match exact version
        assert version_info.release_tag == "v2.1.3"
        
        # Version string should match components
        assert version_info.version_string == "2.1.3"
    
    def test_version_info_tag_format(self):
        """Test that release tags follow correct format (vX.Y.Z)"""
        test_cases = [
            (1, 0, 0, "v1.0.0"),
            (1, 3, 1, "v1.3.1"),
            (10, 25, 100, "v10.25.100"),
            (0, 0, 1, "v0.0.1"),
        ]
        
        for major, minor, patch, expected_tag in test_cases:
            version_info = VersionInfo(
                major=major,
                minor=minor,
                patch=patch,
                version_string=f"{major}.{minor}.{patch}",
                dev_branch=f"ho-dev/{major}.{minor}.x",
                production_branch=f"ho/{major}.{minor}.x",
                release_tag=expected_tag,
                release_type=ReleaseType.PATCH,
                branch_type=BranchType.DEVELOPMENT
            )
            
            assert version_info.release_tag == expected_tag
            assert version_info.release_tag.startswith("v")
    
    def test_version_info_branch_format(self):
        """Test that branch names follow correct format"""
        version_info = VersionInfo(
            major=1,
            minor=3,
            patch=1,
            version_string="1.3.1",
            dev_branch="ho-dev/1.3.x",
            production_branch="ho/1.3.x",
            release_tag="v1.3.1",
            release_type=ReleaseType.PATCH,
            branch_type=BranchType.DEVELOPMENT
        )
        
        # Development branch format
        assert version_info.dev_branch.startswith("ho-dev/")
        assert version_info.dev_branch.endswith(".x")
        
        # Production branch format  
        assert version_info.production_branch.startswith("ho/")
        assert version_info.production_branch.endswith(".x")
        
        # Both should use maintenance format (X.Y.x)
        assert "1.3.x" in version_info.dev_branch
        assert "1.3.x" in version_info.production_branch


class TestReleaseType:
    """Test suite for ReleaseType enum"""
    
    def test_release_type_values(self):
        """Test ReleaseType enum values"""
        assert ReleaseType.MAJOR.value == "major"
        assert ReleaseType.MINOR.value == "minor"
        assert ReleaseType.PATCH.value == "patch"
    
    def test_release_type_comparison(self):
        """Test ReleaseType enum comparison"""
        assert ReleaseType.MAJOR == ReleaseType.MAJOR
        assert ReleaseType.MINOR != ReleaseType.MAJOR
        assert ReleaseType.PATCH != ReleaseType.MINOR
    
    def test_release_type_string_representation(self):
        """Test ReleaseType string representation"""
        assert str(ReleaseType.MAJOR) == "ReleaseType.MAJOR"
        assert str(ReleaseType.MINOR) == "ReleaseType.MINOR"
        assert str(ReleaseType.PATCH) == "ReleaseType.PATCH"


class TestBranchType:
    """Test suite for BranchType enum"""
    
    def test_branch_type_values(self):
        """Test BranchType enum values"""
        assert BranchType.DEVELOPMENT.value == "development"
        assert BranchType.PRODUCTION.value == "production"
        assert BranchType.MAIN.value == "main"
    
    def test_branch_type_comparison(self):
        """Test BranchType enum comparison"""
        assert BranchType.DEVELOPMENT == BranchType.DEVELOPMENT
        assert BranchType.PRODUCTION != BranchType.DEVELOPMENT
        assert BranchType.MAIN != BranchType.PRODUCTION
    
    def test_branch_type_string_representation(self):
        """Test BranchType string representation"""
        assert str(BranchType.DEVELOPMENT) == "BranchType.DEVELOPMENT"
        assert str(BranchType.PRODUCTION) == "BranchType.PRODUCTION"
        assert str(BranchType.MAIN) == "BranchType.MAIN"


# Test fixtures and utilities
@pytest.fixture
def sample_version_info():
    """Fixture providing a sample VersionInfo for testing"""
    return VersionInfo(
        major=1,
        minor=3,
        patch=1,
        version_string="1.3.1",
        dev_branch="ho-dev/1.3.x",
        production_branch="ho/1.3.x",
        release_tag="v1.3.1",
        release_type=ReleaseType.PATCH,
        branch_type=BranchType.DEVELOPMENT
    )


@pytest.fixture
def major_release_version_info():
    """Fixture providing a major release VersionInfo for testing"""
    return VersionInfo(
        major=2,
        minor=0,
        patch=0,
        version_string="2.0.0",
        dev_branch="ho-dev/2.0.x",
        production_branch="ho/2.0.x",
        release_tag="v2.0.0",
        release_type=ReleaseType.MAJOR,
        branch_type=BranchType.DEVELOPMENT
    )


class TestVersionInfoWithFixtures:
    """Test suite using fixtures for VersionInfo testing"""
    
    def test_sample_version_info_fixture(self, sample_version_info):
        """Test using sample_version_info fixture"""
        assert sample_version_info.version_string == "1.3.1"
        assert sample_version_info.release_type == ReleaseType.PATCH
        assert sample_version_info.major == 1
        assert sample_version_info.minor == 3
        assert sample_version_info.patch == 1
    
    def test_major_release_fixture(self, major_release_version_info):
        """Test using major_release_version_info fixture"""
        assert major_release_version_info.version_string == "2.0.0"
        assert major_release_version_info.release_type == ReleaseType.MAJOR
        assert major_release_version_info.major == 2
        assert major_release_version_info.minor == 0
        assert major_release_version_info.patch == 0
    
    def test_version_info_mutation_attempt(self, sample_version_info):
        """Test that VersionInfo fields cannot be mutated (if frozen)"""
        # Note: This test assumes VersionInfo might be made frozen in the future
        # If not frozen, this test documents the expected behavior
        original_major = sample_version_info.major
        
        # This should work with current dataclass implementation
        sample_version_info.major = 999
        assert sample_version_info.major == 999
        
        # Reset for other tests
        sample_version_info.major = original_major
