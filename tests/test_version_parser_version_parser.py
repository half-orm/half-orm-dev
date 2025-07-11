#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unit tests for VersionParser class methods

Tests all methods of the VersionParser class for parsing version specifications
and generating Git-centric branch/tag names in the halfORM workflow.
"""

import pytest
from typing import List

from half_orm_dev.version_parser import (
    VersionParser, VersionInfo, ReleaseType, BranchType,
    VersionParsingError, VersionProgressionError
)


class TestVersionParser:
    """Test suite for VersionParser class methods"""
    
    def test_version_parser_init_valid_version(self):
        """Test VersionParser initialization with valid current version"""
        parser = VersionParser("1.2.3")
        assert parser is not None
        
        # Test with pre-release versions
        parser_alpha = VersionParser("1.2.3-alpha1")
        assert parser_alpha is not None
        
        parser_beta = VersionParser("1.2.3-beta")
        assert parser_beta is not None
        
        parser_rc = VersionParser("1.2.3-rc2")
        assert parser_rc is not None
        
        parser_dev = VersionParser("1.2.3-dev")
        assert parser_dev is not None
    
    def test_version_parser_init_invalid_version(self):
        """Test VersionParser initialization with invalid current version"""
        with pytest.raises(VersionParsingError):
            VersionParser("1.2")  # Missing patch
        
        with pytest.raises(VersionParsingError):
            VersionParser("1.2.3.4")  # Too many components
            
        with pytest.raises(VersionParsingError):
            VersionParser("invalid")  # Non-numeric
            
        with pytest.raises(VersionParsingError):
            VersionParser("")  # Empty string
            
        # Invalid pre-release formats
        with pytest.raises(VersionParsingError):
            VersionParser("1.2.3-invalid")  # Invalid pre-release
            
        with pytest.raises(VersionParsingError):
            VersionParser("1.2.3-alpha0")  # Zero not allowed
            
        with pytest.raises(VersionParsingError):
            VersionParser("1.2.3-")  # Empty pre-release
    
    def test_parse_major_version_spec(self):
        """Test parsing major version specification (e.g., "2")"""
        parser = VersionParser("1.2.3")
        version_info = parser.parse("2")
        
        assert version_info.major == 2
        assert version_info.minor == 0
        assert version_info.patch == 0
        assert version_info.version_string == "2.0.0"
        assert version_info.release_type == ReleaseType.MAJOR
        assert version_info.dev_branch == "ho-dev/2.0.x"
        assert version_info.production_branch == "ho/2.0.x"
        assert version_info.release_tag == "v2.0.0"
    
    def test_parse_minor_version_spec(self):
        """Test parsing minor version specification (e.g., "1.3")"""
        parser = VersionParser("1.2.3")
        version_info = parser.parse("1.3")
        
        assert version_info.major == 1
        assert version_info.minor == 3
        assert version_info.patch == 0
        assert version_info.version_string == "1.3.0"
        assert version_info.release_type == ReleaseType.MINOR
        assert version_info.dev_branch == "ho-dev/1.3.x"
        assert version_info.production_branch == "ho/1.3.x"
        assert version_info.release_tag == "v1.3.0"
    
    def test_parse_version_with_prerelease_valid(self):
        """Test parsing versions with valid pre-release identifiers"""
        parser = VersionParser("1.2.3")
        
        # No pre-release
        base, pre = parser.parse_version_with_prerelease("1.3.0")
        assert base == "1.3.0"
        assert pre is None
        
        # Alpha pre-releases
        base, pre = parser.parse_version_with_prerelease("1.3.0-alpha")
        assert base == "1.3.0"
        assert pre == "alpha"
        
        base, pre = parser.parse_version_with_prerelease("1.3.0-alpha1")
        assert base == "1.3.0"
        assert pre == "alpha1"
        
        # Beta pre-releases
        base, pre = parser.parse_version_with_prerelease("1.3.0-beta3")
        assert base == "1.3.0"
        assert pre == "beta3"
        
        # RC pre-releases
        base, pre = parser.parse_version_with_prerelease("2.0.0-rc2")
        assert base == "2.0.0"
        assert pre == "rc2"
        
        # Dev pre-releases
        base, pre = parser.parse_version_with_prerelease("1.4.1-dev")
        assert base == "1.4.1"
        assert pre == "dev"
    
    def test_parse_version_with_prerelease_invalid(self):
        """Test parsing versions with invalid pre-release identifiers"""
        parser = VersionParser("1.2.3")
        
        with pytest.raises(VersionParsingError):
            parser.parse_version_with_prerelease("1.3.0-invalid")
            
        with pytest.raises(VersionParsingError):
            parser.parse_version_with_prerelease("1.3.0-alpha0")  # Zero not allowed
            
        with pytest.raises(VersionParsingError):
            parser.parse_version_with_prerelease("1.3.0-betaX")  # Non-numeric suffix
            
        with pytest.raises(VersionParsingError):
            parser.parse_version_with_prerelease("1.3.0-")  # Empty pre-release
    
    def test_is_valid_prerelease_identifier_valid(self):
        """Test validation of valid pre-release identifiers"""
        parser = VersionParser("1.2.3")
        
        # Basic identifiers
        assert parser.is_valid_prerelease_identifier("alpha") is True
        assert parser.is_valid_prerelease_identifier("beta") is True
        assert parser.is_valid_prerelease_identifier("rc") is True
        assert parser.is_valid_prerelease_identifier("dev") is True
        
        # Numbered identifiers
        assert parser.is_valid_prerelease_identifier("alpha1") is True
        assert parser.is_valid_prerelease_identifier("beta3") is True
        assert parser.is_valid_prerelease_identifier("rc2") is True
        assert parser.is_valid_prerelease_identifier("dev5") is True
        
        # Higher numbers
        assert parser.is_valid_prerelease_identifier("alpha10") is True
        assert parser.is_valid_prerelease_identifier("beta100") is True
    
    def test_is_valid_prerelease_identifier_invalid(self):
        """Test validation of invalid pre-release identifiers"""
        parser = VersionParser("1.2.3")
        
        # Invalid prefixes
        assert parser.is_valid_prerelease_identifier("invalid") is False
        assert parser.is_valid_prerelease_identifier("gamma") is False
        assert parser.is_valid_prerelease_identifier("stable") is False
        
        # Invalid suffixes
        assert parser.is_valid_prerelease_identifier("alpha0") is False  # Zero not allowed
        assert parser.is_valid_prerelease_identifier("betaX") is False   # Non-numeric
        assert parser.is_valid_prerelease_identifier("rc-1") is False    # Negative
        
        # Empty or malformed
        assert parser.is_valid_prerelease_identifier("") is False
        assert parser.is_valid_prerelease_identifier("alpha-beta") is False
    def test_parse_patch_version_spec(self):
        """Test parsing patch version specification (e.g., "1.2.4")"""
        parser = VersionParser("1.2.3")
        version_info = parser.parse("1.2.4")
        
        assert version_info.major == 1
        assert version_info.minor == 2
        assert version_info.patch == 4
        assert version_info.version_string == "1.2.4"
        assert version_info.base_version == "1.2.4"
        assert version_info.pre_release is None
        assert version_info.is_pre_release is False
        assert version_info.release_type == ReleaseType.PATCH
        assert version_info.dev_branch == "ho-dev/1.2.x"
        assert version_info.production_branch == "ho/1.2.x"
        assert version_info.release_tag == "v1.2.4"
    
    def test_parse_prerelease_version_spec(self):
        """Test parsing pre-release version specifications"""
        parser = VersionParser("1.2.3")
        
        # Alpha pre-release
        version_info = parser.parse("1.3.0-alpha1")
        assert version_info.version_string == "1.3.0-alpha1"
        assert version_info.base_version == "1.3.0"
        assert version_info.pre_release == "alpha1"
        assert version_info.is_pre_release is True
        assert version_info.release_tag == "v1.3.0-alpha1"
        assert version_info.dev_branch == "ho-dev/1.3.x"  # No pre-release in branch
        
        # Beta pre-release
        version_info = parser.parse("2.0.0-beta")
        assert version_info.version_string == "2.0.0-beta"
        assert version_info.base_version == "2.0.0"
        assert version_info.pre_release == "beta"
        assert version_info.is_pre_release is True
        assert version_info.release_tag == "v2.0.0-beta"
    
    def test_parse_invalid_version_spec(self):
        """Test parsing invalid version specifications"""
        parser = VersionParser("1.2.3")
        
        with pytest.raises(VersionParsingError):
            parser.parse("1.2.3.4")  # Too many components
            
        with pytest.raises(VersionParsingError):
            parser.parse("invalid")  # Non-numeric
            
        with pytest.raises(VersionParsingError):
            parser.parse("")  # Empty
            
        with pytest.raises(VersionParsingError):
            parser.parse("1.2.03")  # Leading zero
            
        # Invalid pre-release formats
        with pytest.raises(VersionParsingError):
            parser.parse("1.3.0-invalid")  # Invalid pre-release
            
        with pytest.raises(VersionParsingError):
            parser.parse("1.3.0-alpha0")  # Zero not allowed in pre-release
    
    def test_parse_backward_version_progression(self):
        """Test parsing version that goes backward"""
        parser = VersionParser("1.2.3")
        
        with pytest.raises(VersionProgressionError):
            parser.parse("1.1.0")  # Backward minor
            
        with pytest.raises(VersionProgressionError):
            parser.parse("1.2.2")  # Backward patch
            
        with pytest.raises(VersionProgressionError):
            parser.parse("0.9.0")  # Backward major
    
    def test_determine_release_type_major(self):
        """Test determining major release type"""
        parser = VersionParser("1.2.3")
        
        assert parser.determine_release_type("2.0.0") == ReleaseType.MAJOR
        assert parser.determine_release_type("0.0.0") == ReleaseType.MAJOR  # Edge case
    
    def test_determine_release_type_minor(self):
        """Test determining minor release type"""
        parser = VersionParser("1.2.3")
        
        assert parser.determine_release_type("1.3.0") == ReleaseType.MINOR
        assert parser.determine_release_type("1.5.0") == ReleaseType.MINOR
    
    def test_determine_release_type_patch(self):
        """Test determining patch release type"""
        parser = VersionParser("1.2.3")
        
        assert parser.determine_release_type("1.2.4") == ReleaseType.PATCH
        assert parser.determine_release_type("1.2.10") == ReleaseType.PATCH
    
    def test_determine_release_type_invalid(self):
        """Test determining release type with invalid progression"""
        parser = VersionParser("1.2.3")
        
        with pytest.raises(VersionProgressionError):
            parser.determine_release_type("1.2.2")  # Backward
            
        with pytest.raises(VersionParsingError):
            parser.determine_release_type("invalid")  # Invalid format
    
    def test_validate_version_progression_valid(self):
        """Test valid version progression validation"""
        parser = VersionParser("1.2.3")
        
        assert parser.validate_version_progression("1.2.3", "1.2.4") is True
        assert parser.validate_version_progression("1.2.3", "1.3.0") is True
        assert parser.validate_version_progression("1.2.3", "2.0.0") is True
    
    def test_validate_version_progression_invalid(self):
        """Test invalid version progression validation"""
        parser = VersionParser("1.2.3")
        
        assert parser.validate_version_progression("1.2.3", "1.2.2") is False
        assert parser.validate_version_progression("1.2.3", "1.1.0") is False
        assert parser.validate_version_progression("1.2.3", "0.9.0") is False
        assert parser.validate_version_progression("1.2.3", "1.2.3") is False  # Same version
    
    def test_expand_version_spec_major(self):
        """Test expanding major version spec"""
        parser = VersionParser("1.2.3")
        
        assert parser.expand_version_spec("2") == "2.0.0"
        assert parser.expand_version_spec("0") == "0.0.0"
        assert parser.expand_version_spec("10") == "10.0.0"
    
    def test_expand_version_spec_minor(self):
        """Test expanding minor version spec"""
        parser = VersionParser("1.2.3")
        
        assert parser.expand_version_spec("1.3") == "1.3.0"
        assert parser.expand_version_spec("2.5") == "2.5.0"
        assert parser.expand_version_spec("0.1") == "0.1.0"
    
    def test_expand_version_spec_complete(self):
        """Test expanding complete version spec"""
        parser = VersionParser("1.2.3")
        
        assert parser.expand_version_spec("1.2.4") == "1.2.4"
        assert parser.expand_version_spec("2.0.0") == "2.0.0"
        assert parser.expand_version_spec("10.25.100") == "10.25.100"
    
    def test_expand_version_spec_invalid(self):
        """Test expanding invalid version specs"""
        parser = VersionParser("1.2.3")
        
        with pytest.raises(VersionParsingError):
            parser.expand_version_spec("1.2.3.4")  # Too many parts
            
        with pytest.raises(VersionParsingError):
            parser.expand_version_spec("invalid")  # Non-numeric
            
        with pytest.raises(VersionParsingError):
            parser.expand_version_spec("")  # Empty
    
    def test_get_next_version_major(self):
        """Test getting next major version"""
        parser = VersionParser("1.2.3")
        
        assert parser.get_next_version(ReleaseType.MAJOR) == "2.0.0"
        
        parser = VersionParser("0.5.10")
        assert parser.get_next_version(ReleaseType.MAJOR) == "1.0.0"
    
    def test_get_next_version_minor(self):
        """Test getting next minor version"""
        parser = VersionParser("1.2.3")
        
        assert parser.get_next_version(ReleaseType.MINOR) == "1.3.0"
        
        parser = VersionParser("2.0.5")
        assert parser.get_next_version(ReleaseType.MINOR) == "2.1.0"
    
    def test_get_next_version_patch(self):
        """Test getting next patch version"""
        parser = VersionParser("1.2.3")
        
        assert parser.get_next_version(ReleaseType.PATCH) == "1.2.4"
        
        parser = VersionParser("0.0.0")
        assert parser.get_next_version(ReleaseType.PATCH) == "0.0.1"
    
    def test_generate_git_branch_name_development(self):
        """Test generating development branch names"""
        parser = VersionParser("1.2.3")
        
        assert parser.generate_git_branch_name("1.3.0", BranchType.DEVELOPMENT) == "ho-dev/1.3.x"
        assert parser.generate_git_branch_name("2.0.0", BranchType.DEVELOPMENT) == "ho-dev/2.0.x"
        assert parser.generate_git_branch_name("10.25.100", BranchType.DEVELOPMENT) == "ho-dev/10.25.x"
    
    def test_generate_git_branch_name_production(self):
        """Test generating production branch names"""
        parser = VersionParser("1.2.3")
        
        assert parser.generate_git_branch_name("1.3.0", BranchType.PRODUCTION) == "ho/1.3.x"
        assert parser.generate_git_branch_name("2.0.0", BranchType.PRODUCTION) == "ho/2.0.x"
        assert parser.generate_git_branch_name("0.1.0", BranchType.PRODUCTION) == "ho/0.1.x"
    
    def test_generate_git_branch_name_main(self):
        """Test generating main branch name"""
        parser = VersionParser("1.2.3")
        
        assert parser.generate_git_branch_name("1.3.0", BranchType.MAIN) == "main"
        # Version should be ignored for main branch
        assert parser.generate_git_branch_name("99.99.99", BranchType.MAIN) == "main"
    
    def test_generate_git_branch_name_default(self):
        """Test generating branch name with default type (development)"""
        parser = VersionParser("1.2.3")
        
        assert parser.generate_git_branch_name("1.3.0") == "ho-dev/1.3.x"
    
    def test_generate_git_branch_name_invalid_version(self):
        """Test generating branch name with invalid version"""
        parser = VersionParser("1.2.3")
        
        with pytest.raises(VersionParsingError):
            parser.generate_git_branch_name("invalid")
            
        with pytest.raises(VersionParsingError):
            parser.generate_git_branch_name("1.2")
    
    def test_generate_release_tag(self):
        """Test generating release tags"""
        parser = VersionParser("1.2.3")
        
        assert parser.generate_release_tag("1.3.0") == "v1.3.0"
        assert parser.generate_release_tag("2.0.0") == "v2.0.0"
        assert parser.generate_release_tag("0.0.1") == "v0.0.1"
        assert parser.generate_release_tag("10.25.100") == "v10.25.100"
    
    def test_generate_release_tag_invalid_version(self):
        """Test generating release tag with invalid version"""
        parser = VersionParser("1.2.3")
        
        with pytest.raises(VersionParsingError):
            parser.generate_release_tag("invalid")
            
        with pytest.raises(VersionParsingError):
            parser.generate_release_tag("1.2")
    
    def test_generate_maintenance_branch_name_development(self):
        """Test generating development maintenance branch names"""
        parser = VersionParser("1.2.3")
        
        assert parser.generate_maintenance_branch_name("1.3.0") == "ho-dev/1.3.x"
        assert parser.generate_maintenance_branch_name("2.0.0", False) == "ho-dev/2.0.x"
    
    def test_generate_maintenance_branch_name_production(self):
        """Test generating production maintenance branch names"""
        parser = VersionParser("1.2.3")
        
        assert parser.generate_maintenance_branch_name("1.3.0", True) == "ho/1.3.x"
        assert parser.generate_maintenance_branch_name("2.0.0", for_production=True) == "ho/2.0.x"
    
    def test_is_valid_version_format_valid(self):
        """Test validating correct version formats"""
        parser = VersionParser("1.2.3")
        
        assert parser.is_valid_version_format("1.2.3") is True
        assert parser.is_valid_version_format("0.0.0") is True
        assert parser.is_valid_version_format("10.25.100") is True
        assert parser.is_valid_version_format("1.0.0") is True
    
    def test_is_valid_version_format_invalid(self):
        """Test validating incorrect version formats"""
        parser = VersionParser("1.2.3")
        
        assert parser.is_valid_version_format("1.2") is False  # Missing patch
        assert parser.is_valid_version_format("1.2.3.4") is False  # Too many parts
        assert parser.is_valid_version_format("1.2.03") is False  # Leading zero
        assert parser.is_valid_version_format("invalid") is False  # Non-numeric
        assert parser.is_valid_version_format("") is False  # Empty
        assert parser.is_valid_version_format("1.-2.3") is False  # Negative
        assert parser.is_valid_version_format("1.2.") is False  # Trailing dot
    
    def test_compare_versions_equal(self):
        """Test comparing equal versions"""
        parser = VersionParser("1.2.3")
        
        assert parser.compare_versions("1.2.3", "1.2.3") == 0
        assert parser.compare_versions("0.0.0", "0.0.0") == 0
        assert parser.compare_versions("10.25.100", "10.25.100") == 0
    
    def test_compare_versions_less_than(self):
        """Test comparing versions where first is less than second"""
        parser = VersionParser("1.2.3")
        
        assert parser.compare_versions("1.2.3", "1.2.4") < 0  # Patch difference
        assert parser.compare_versions("1.2.3", "1.3.0") < 0  # Minor difference
        assert parser.compare_versions("1.2.3", "2.0.0") < 0  # Major difference
        assert parser.compare_versions("0.9.9", "1.0.0") < 0  # Cross major
    
    def test_compare_versions_greater_than(self):
        """Test comparing versions where first is greater than second"""
        parser = VersionParser("1.2.3")
        
        assert parser.compare_versions("1.2.4", "1.2.3") > 0  # Patch difference
        assert parser.compare_versions("1.3.0", "1.2.3") > 0  # Minor difference
        assert parser.compare_versions("2.0.0", "1.2.3") > 0  # Major difference
        assert parser.compare_versions("1.0.0", "0.9.9") > 0  # Cross major
    
    def test_compare_versions_invalid(self):
        """Test comparing invalid versions"""
        parser = VersionParser("1.2.3")
        
        with pytest.raises(VersionParsingError):
            parser.compare_versions("invalid", "1.2.3")
            
        with pytest.raises(VersionParsingError):
            parser.compare_versions("1.2.3", "invalid")
    
    def test_get_version_components_valid(self):
        """Test extracting version components from valid versions"""
        parser = VersionParser("1.2.3")
        
        assert parser.get_version_components("1.2.3") == (1, 2, 3)
        assert parser.get_version_components("0.0.0") == (0, 0, 0)
        assert parser.get_version_components("10.25.100") == (10, 25, 100)
    
    def test_get_version_components_invalid(self):
        """Test extracting version components from invalid versions"""
        parser = VersionParser("1.2.3")
        
        with pytest.raises(VersionParsingError):
            parser.get_version_components("invalid")
            
        with pytest.raises(VersionParsingError):
            parser.get_version_components("1.2")
            
        with pytest.raises(VersionParsingError):
            parser.get_version_components("1.2.3.4")
    
    def test_list_possible_next_versions(self):
        """Test listing all possible next versions"""
        parser = VersionParser("1.2.3")
        
        next_versions = parser.list_possible_next_versions()
        
        assert len(next_versions) == 3
        
        # Find each type
        major_version = next((v for v in next_versions if v.release_type == ReleaseType.MAJOR), None)
        minor_version = next((v for v in next_versions if v.release_type == ReleaseType.MINOR), None)
        patch_version = next((v for v in next_versions if v.release_type == ReleaseType.PATCH), None)
        
        assert major_version is not None
        assert major_version.version_string == "2.0.0"
        
        assert minor_version is not None
        assert minor_version.version_string == "1.3.0"
        
        assert patch_version is not None
        assert patch_version.version_string == "1.2.4"


# Test fixtures for VersionParser
@pytest.fixture
def sample_parser():
    """Fixture providing a VersionParser with version 1.2.3"""
    return VersionParser("1.2.3")


@pytest.fixture
def zero_version_parser():
    """Fixture providing a VersionParser with version 0.0.0"""
    return VersionParser("0.0.0")


class TestVersionParserWithFixtures:
    """Test suite using fixtures for VersionParser testing"""
    
    def test_parser_fixture(self, sample_parser):
        """Test using sample_parser fixture"""
        assert sample_parser is not None
        # Current version should be accessible through internal state if needed
    
    def test_zero_version_fixture(self, zero_version_parser):
        """Test parser with zero version"""
        next_major = zero_version_parser.get_next_version(ReleaseType.MAJOR)
        assert next_major == "1.0.0"
        
        next_minor = zero_version_parser.get_next_version(ReleaseType.MINOR)
        assert next_minor == "0.1.0"
        
        next_patch = zero_version_parser.get_next_version(ReleaseType.PATCH)
        assert next_patch == "0.0.1"


class TestVersionParserEdgeCases:
    """Test suite for VersionParser edge cases and error conditions"""
    
    def test_large_version_numbers(self):
        """Test handling of large version numbers"""
        parser = VersionParser("999.999.999")
        
        # Should handle large numbers correctly
        next_major = parser.get_next_version(ReleaseType.MAJOR)
        assert next_major == "1000.0.0"
        
        next_minor = parser.get_next_version(ReleaseType.MINOR)
        assert next_minor == "999.1000.0"
        
        next_patch = parser.get_next_version(ReleaseType.PATCH)
        assert next_patch == "999.999.1000"
    
    def test_whitespace_handling(self):
        """Test handling of whitespace in version strings"""
        with pytest.raises(VersionParsingError):
            VersionParser(" 1.2.3 ")  # Leading/trailing whitespace
            
        with pytest.raises(VersionParsingError):
            VersionParser("1.2.3\n")  # Newline
            
        with pytest.raises(VersionParsingError):
            VersionParser("1 . 2 . 3")  # Spaces in version
    
    def test_special_characters(self):
        """Test handling of special characters in version strings"""
        parser = VersionParser("1.2.3")
        
        with pytest.raises(VersionParsingError):
            parser.parse("1.2.3-alpha")  # Pre-release suffix
            
        with pytest.raises(VersionParsingError):
            parser.parse("v1.2.3")  # Version prefix
            
        with pytest.raises(VersionParsingError):
            parser.parse("1.2.3+build")  # Build metadata
