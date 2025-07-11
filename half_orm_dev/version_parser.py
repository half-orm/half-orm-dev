#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Version Parser for halfORM-dev Git-centric Architecture

This module provides intelligent version specification parsing and semantic versioning
logic for the Git-centric workflow. It handles user-friendly version specifications
and converts them into actionable version information for the halfORM development workflow.

Key Features:
- Flexible version_spec parsing (1, 1.3, 1.3.1)
- Automatic release type detection (major, minor, patch)
- Semantic versioning validation
- Production/Development branch separation with Git tags
- Git-centric branch naming conventions
- Version progression logic

Branch & Tag Convention:
- Development: ho-dev/X.Y.x (e.g., ho-dev/1.3.x) + commits
- Production: ho/X.Y.x (e.g., ho/1.3.x) + tags
- Release tags: vX.Y.Z (e.g., v1.3.1) or vX.Y.Z-prerelease (e.g., v1.3.1-alpha1)
- Pre-release support: -alpha1, -beta3, -rc2, -dev formats
- Main development: main

Workflow:
1. Develop on ho-dev/1.3.x
2. Promote to ho/1.3.x when stable  
3. Tag releases as v1.3.1, v1.3.2, etc. on ho/1.3.x

Examples:
    >>> parser = VersionParser("1.2.3")  # current version
    >>> parser.parse("1.3")              # → 1.3.0 (minor release)
    >>> parser.parse("2")                # → 2.0.0 (major release)
    >>> parser.parse("1.2.4")            # → 1.2.4 (patch release)
"""

from enum import Enum
from typing import Optional, Tuple, List
from dataclasses import dataclass


class BranchType(Enum):
    """
    Enumeration of Git branch types in the halfORM workflow.
    
    Separates development and production concerns with Git tags for releases:
    - DEVELOPMENT: Active development branches (ho-dev/X.Y.x)
    - PRODUCTION: Production-ready branches (ho/X.Y.x) with release tags
    - MAIN: Main development branch
    """
    DEVELOPMENT = "development"      # ho-dev/1.3.x
    PRODUCTION = "production"        # ho/1.3.x + tags v1.3.1, v1.3.2...
    MAIN = "main"                   # main


class ReleaseType(Enum):
    """
    Enumeration of semantic versioning release types.
    
    Used to categorize version changes according to semantic versioning principles:
    - MAJOR: Incompatible API changes (X.y.z)
    - MINOR: Backward-compatible functionality additions (x.Y.z)
    - PATCH: Backward-compatible bug fixes (x.y.Z)
    """
    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"


@dataclass
class VersionInfo:
    """
    Structured representation of a semantic version with Git branch and tag information.
    
    Provides a comprehensive view of version information including
    semantic components, Git branch naming for both development and production,
    release tags, pre-release information, and categorization.
    
    Attributes:
        major (int): Major version number (breaking changes)
        minor (int): Minor version number (new features)
        patch (int): Patch version number (bug fixes)
        version_string (str): Full semantic version (e.g., "1.2.3" or "1.2.3-alpha1")
        base_version (str): Base version without pre-release (e.g., "1.2.3")
        pre_release (Optional[str]): Pre-release identifier (e.g., "alpha1", "beta3", "rc2")
        is_pre_release (bool): Whether this is a pre-release version
        dev_branch (str): Development branch name (e.g., "ho-dev/1.2.x")
        production_branch (str): Production branch name (e.g., "ho/1.2.x")
        release_tag (str): Git tag for release (e.g., "v1.2.3" or "v1.2.3-alpha1")
        release_type (ReleaseType): Type of release (major/minor/patch)
        branch_type (BranchType): Primary branch type for this version
    """
    major: int
    minor: int
    patch: int
    version_string: str
    base_version: str
    pre_release: Optional[str]
    is_pre_release: bool
    dev_branch: str
    production_branch: str
    release_tag: str
    release_type: ReleaseType
    branch_type: BranchType


class VersionParsingError(Exception):
    """
    Exception raised when version specification cannot be parsed.
    
    This exception is raised when:
    - Invalid version format is provided
    - Version components are not numeric
    - Version progression violates semantic versioning rules
    - Negative version numbers are specified
    """
    pass


class VersionProgressionError(Exception):
    """
    Exception raised when version progression violates semantic versioning.
    
    This exception is raised when:
    - New version is not greater than current version
    - Version jumps multiple levels (e.g., 1.0.0 → 3.0.0)
    - Backward version progression is attempted
    - Invalid version sequence is detected
    """
    pass


class VersionParser:
    """
    Intelligent version specification parser for Git-centric halfORM workflow.
    
    This class handles the parsing and validation of user-provided version specifications,
    converting them into structured VersionInfo objects with all necessary metadata
    for the Git-centric development workflow.
    
    The parser supports flexible input formats:
    - "1" → next major version (1.0.0)
    - "1.3" → specific minor version (1.3.0)
    - "1.3.1" → specific patch version (1.3.1)
    
    It automatically determines release types and validates version progression
    according to semantic versioning principles.
    
    Args:
        current_version (str): Current version in the project (e.g., "1.2.3")
        
    Example:
        >>> parser = VersionParser("1.2.3")
        >>> version_info = parser.parse("1.3")
        >>> print(version_info.version_string)  # "1.3.0"
        >>> print(version_info.release_type)    # ReleaseType.MINOR
    """
    
    def __init__(self, current_version: str):
        """
        Initialize the version parser with the current project version.
        
        Args:
            current_version (str): Current semantic version (e.g., "1.2.3" or "1.2.3-alpha1")
            
        Raises:
            VersionParsingError: If current_version format is invalid
        """
        if not isinstance(current_version, str):
            raise VersionParsingError(f"Version must be a string, got {type(current_version).__name__}")
        
        if not current_version or not current_version.strip():
            raise VersionParsingError("Version cannot be empty")
        
        # Remove any whitespace
        current_version = current_version.strip()
        
        # Parse base version and pre-release
        self._current_version = current_version
        self._base_version, self._pre_release = self._parse_version_with_prerelease(current_version)
        self._is_pre_release = self._pre_release is not None
        
        # Validate base version format
        if not self._is_valid_semantic_version(self._base_version):
            raise VersionParsingError(f"Invalid version format: '{current_version}'. Expected X.Y.Z[-prerelease] format")
        
        # Parse and store components for quick access
        self._current_major, self._current_minor, self._current_patch = self._parse_version_components(self._base_version)
    
    def _parse_version_with_prerelease(self, version: str) -> Tuple[str, Optional[str]]:
        """
        Internal method to parse version with optional pre-release.
        
        Args:
            version (str): Version string potentially with pre-release
            
        Returns:
            Tuple[str, Optional[str]]: (base_version, pre_release)
            
        Raises:
            VersionParsingError: If pre-release format is invalid
        """
        if '-' not in version:
            # No pre-release
            return version, None
        
        # Split on first hyphen only
        parts = version.split('-', 1)
        if len(parts) != 2:
            raise VersionParsingError(f"Invalid version format: '{version}'")
        
        base_version, pre_release = parts
        
        # Validate pre-release identifier
        if not self._is_valid_prerelease_identifier(pre_release):
            raise VersionParsingError(f"Invalid pre-release identifier: '{pre_release}'")
        
        return base_version, pre_release
    
    def _is_valid_prerelease_identifier(self, prerelease: str) -> bool:
        """
        Internal method to validate pre-release identifier.
        
        Valid formats: alpha, alpha1, beta, beta1, rc, rc1, dev, dev1, etc.
        
        Args:
            prerelease (str): Pre-release identifier
            
        Returns:
            bool: True if valid
        """
        if not prerelease:
            return False
        
        # Valid prefixes
        valid_prefixes = ['alpha', 'beta', 'rc', 'dev']
        
        # Check if it starts with a valid prefix
        for prefix in valid_prefixes:
            if prerelease.startswith(prefix):
                # Check what follows the prefix
                suffix = prerelease[len(prefix):]
                
                # Either nothing (just "alpha") or a number ("alpha1")
                if suffix == "":
                    return True
                
                # Must be a positive integer
                if suffix.isdigit() and int(suffix) > 0:
                    return True
                
                # Invalid suffix
                return False
        
        # Doesn't start with valid prefix
        return False
    
    def _is_valid_semantic_version(self, version: str) -> bool:
        """
        Internal method to validate semantic version format.
        
        Args:
            version (str): Version string to validate
            
        Returns:
            bool: True if format is valid
        """
        if not version:
            return False
        
        # Split by dots
        parts = version.split('.')
        
        # Must have exactly 3 parts
        if len(parts) != 3:
            return False
        
        # Each part must be a non-negative integer without leading zeros
        for part in parts:
            if not part:  # Empty part
                return False
            
            # Check if it's numeric
            if not part.isdigit():
                return False
            
            # Check for leading zeros (except for "0")
            if len(part) > 1 and part[0] == '0':
                return False
            
            # Ensure it's non-negative (isdigit already ensures this)
            if int(part) < 0:
                return False
        
        return True
    
    def _parse_version_components(self, version: str) -> Tuple[int, int, int]:
        """
        Internal method to parse version components.
        
        Args:
            version (str): Valid semantic version string
            
        Returns:
            Tuple[int, int, int]: (major, minor, patch) components
        """
        parts = version.split('.')
        return int(parts[0]), int(parts[1]), int(parts[2])
    
    def parse(self, version_spec: str) -> VersionInfo:
        """
        Parse a version specification into structured version information.
        
        Converts user-friendly version specifications into complete VersionInfo
        objects with all metadata needed for Git-centric operations.
        
        Supported formats:
        - "1" → Major version (1.0.0)
        - "1.3" → Minor version (1.3.0)  
        - "1.3.1" → Patch version (1.3.1)
        - "1.3.1-alpha1" → Pre-release version
        
        Args:
            version_spec (str): Version specification from user input
            
        Returns:
            VersionInfo: Complete version information with Git branch names
            
        Raises:
            VersionParsingError: If version_spec format is invalid
            VersionProgressionError: If version progression is invalid
            
        Example:
            >>> parser = VersionParser("1.2.3")
            >>> info = parser.parse("1.3")
            >>> info.version_string      # "1.3.0"
            >>> info.dev_branch          # "ho-dev/1.3.x"
            >>> info.production_branch   # "ho/1.3.x"
            >>> info.release_tag         # "v1.3.0"
            >>> info.release_type        # ReleaseType.MINOR
        """
        pass
    
    def parse_version_with_prerelease(self, version: str) -> Tuple[str, Optional[str]]:
        """
        Parse a version string that may include pre-release information.
        
        Supports semantic versioning pre-release format: X.Y.Z-prerelease
        Common pre-release identifiers: alpha, beta, rc, dev
        
        Args:
            version (str): Version string (e.g., "1.2.3-alpha1", "1.2.3")
            
        Returns:
            Tuple[str, Optional[str]]: (base_version, pre_release)
            
        Raises:
            VersionParsingError: If format is invalid
            
        Example:
            >>> parser = VersionParser("1.2.3")
            >>> parser.parse_version_with_prerelease("1.3.0-alpha1")  # ("1.3.0", "alpha1")
            >>> parser.parse_version_with_prerelease("1.3.0")         # ("1.3.0", None)
        """
        pass
    
    def is_valid_prerelease_identifier(self, prerelease: str) -> bool:
        """
        Validate pre-release identifier format.
        
        Valid formats:
        - alpha, alpha1, alpha2, ...
        - beta, beta1, beta2, ...
        - rc, rc1, rc2, ...
        - dev, dev1, dev2, ...
        
        Args:
            prerelease (str): Pre-release identifier to validate
            
        Returns:
            bool: True if valid pre-release identifier
            
        Example:
            >>> parser = VersionParser("1.2.3")
            >>> parser.is_valid_prerelease_identifier("alpha1")  # True
            >>> parser.is_valid_prerelease_identifier("invalid") # False
        """
        pass
    
    def list_possible_next_versions(self) -> List[VersionInfo]:
        """
        Generate list of all possible next versions from current version.
        
        Returns all valid next versions according to semantic versioning:
        - Next major version (X+1.0.0)
        - Next minor version (X.Y+1.0)
        - Next patch version (X.Y.Z+1)
        
        Returns:
            List[VersionInfo]: All possible next versions with metadata
            
        Example:
            >>> parser = VersionParser("1.2.3")
            >>> versions = parser.list_possible_next_versions()
            >>> # Returns: [2.0.0 (major), 1.3.0 (minor), 1.2.4 (patch)]
        """
        pass

    def determine_release_type(self, target_version: str) -> ReleaseType:
        """
        Determine the semantic versioning release type for a target version.
        
        Analyzes the difference between current version and target version
        to determine whether this represents a major, minor, or patch release.
        
        Logic:
        - Major: X changes (1.2.3 → 2.0.0)
        - Minor: Y changes, X same (1.2.3 → 1.3.0)
        - Patch: Z changes, X.Y same (1.2.3 → 1.2.4)
        
        Args:
            target_version (str): Target version to analyze
            
        Returns:
            ReleaseType: The type of release (MAJOR, MINOR, or PATCH)
            
        Raises:
            VersionParsingError: If target_version format is invalid
            VersionProgressionError: If progression is invalid
            
        Example:
            >>> parser = VersionParser("1.2.3")
            >>> parser.determine_release_type("1.3.0")  # ReleaseType.MINOR
            >>> parser.determine_release_type("2.0.0")  # ReleaseType.MAJOR
        """
        pass
    
    def validate_version_progression(self, from_version: str, to_version: str) -> bool:
        """
        Validate that version progression follows semantic versioning rules.
        
        Ensures that the version progression is valid according to semantic
        versioning principles:
        - Target version must be greater than source version
        - Version components must progress logically
        - No backward progression allowed
        - No skipping multiple major versions (>1 major jump)
        - Pre-release information is ignored for progression validation
        
        Args:
            from_version (str): Source version
            to_version (str): Target version
            
        Returns:
            bool: True if progression is valid, False otherwise
            
        Raises:
            VersionParsingError: If either version format is invalid
            
        Example:
            >>> parser = VersionParser("1.2.3")
            >>> parser.validate_version_progression("1.2.3", "1.3.0")  # True
            >>> parser.validate_version_progression("1.2.3", "1.2.2")  # False
            >>> parser.validate_version_progression("1.2.3", "3.0.0")  # False (too big jump)
            >>> parser.validate_version_progression("1.2.3-alpha", "1.2.3")  # True (pre-release ignored)
        """
        try:
            # Extract components from both versions (handles pre-release automatically)
            from_major, from_minor, from_patch = self.get_version_components(from_version)
            to_major, to_minor, to_patch = self.get_version_components(to_version)
            
        except VersionParsingError as e:
            # Re-raise with context about validation failure
            raise VersionParsingError(f"Version progression validation failed: {str(e)}")
        
        # Check if versions are identical (not a valid progression)
        if (from_major, from_minor, from_patch) == (to_major, to_minor, to_patch):
            return False
        
        # Use compare_versions for main logic (reuse existing implementation)
        comparison = self.compare_versions(from_version, to_version)
        
        # Target version must be greater than source version
        if comparison >= 0:  # from >= to
            return False
        
        # Check for reasonable progression (no massive jumps)
        major_diff = to_major - from_major
        
        # Major version jumps should be reasonable (max 1 major version jump)
        if major_diff > 1:
            return False
        
        # If major version increases, minor and patch should reset to 0
        if major_diff == 1:
            if to_minor != 0 or to_patch != 0:
                return False
        
        # If major version is same, check minor progression
        if major_diff == 0:
            minor_diff = to_minor - from_minor
            
            # Minor version can increase by any amount, but not decrease
            if minor_diff < 0:
                return False
            
            # If minor version increases, patch should reset to 0
            if minor_diff > 0 and to_patch != 0:
                return False
            
            # If minor version is same, check patch progression
            if minor_diff == 0:
                patch_diff = to_patch - from_patch
                
                # Patch version must increase by at least 1
                if patch_diff <= 0:
                    return False
        
        # All validation passed
        return True
    
    def expand_version_spec(self, version_spec: str) -> str:
        """
        Expand a partial version specification to a complete semantic version.
        
        Converts user-friendly short forms into complete X.Y.Z versions:
        - "1" → "1.0.0" (major version)
        - "1.3" → "1.3.0" (minor version)
        - "1.3.1" → "1.3.1" (complete version)
        - "1.3.1-alpha1" → "1.3.1-alpha1" (pre-release, unchanged)
        
        Args:
            version_spec (str): Partial or complete version specification
            
        Returns:
            str: Complete semantic version (X.Y.Z format, possibly with pre-release)
            
        Raises:
            VersionParsingError: If version_spec format is invalid
            
        Example:
            >>> parser = VersionParser("1.2.3")
            >>> parser.expand_version_spec("1")           # "1.0.0"
            >>> parser.expand_version_spec("1.4")         # "1.4.0"
            >>> parser.expand_version_spec("1.4.2")       # "1.4.2"
            >>> parser.expand_version_spec("1.4.2-alpha") # "1.4.2-alpha"
        """
        if not isinstance(version_spec, str):
            raise VersionParsingError(f"Version spec must be a string, got {type(version_spec).__name__}")
        
        if not version_spec or not version_spec.strip():
            raise VersionParsingError("Version spec cannot be empty")
        
        # Remove whitespace
        version_spec = version_spec.strip()
        
        # Check if it contains pre-release (has hyphen)
        has_prerelease = '-' in version_spec
        
        if has_prerelease:
            # Split base version and pre-release
            try:
                base_version, pre_release = self._parse_version_with_prerelease(version_spec)
            except VersionParsingError as e:
                raise VersionParsingError(f"Invalid version spec with pre-release: '{version_spec}'. {str(e)}")
            
            # Expand base version and add pre-release back
            expanded_base = self._expand_base_version(base_version)
            return f"{expanded_base}-{pre_release}"
        
        else:
            # No pre-release, expand base version only
            return self._expand_base_version(version_spec)
    
    def _expand_base_version(self, base_version: str) -> str:
        """
        Internal helper to expand base version (without pre-release).
        
        Args:
            base_version (str): Base version to expand (e.g., "1", "1.3", "1.3.1")
            
        Returns:
            str: Expanded base version (e.g., "1.0.0", "1.3.0", "1.3.1")
            
        Raises:
            VersionParsingError: If base version format is invalid
        """
        # Split by dots
        parts = base_version.split('.')
        
        # Validate number of parts (1, 2, or 3)
        if len(parts) == 0 or len(parts) > 3:
            raise VersionParsingError(f"Invalid version spec: '{base_version}'. Expected 1-3 components")
        
        # Validate each part is a valid integer
        validated_parts = []
        for i, part in enumerate(parts):
            if not part:
                raise VersionParsingError(f"Empty version component in: '{base_version}'")
            
            if not part.isdigit():
                raise VersionParsingError(f"Non-numeric version component '{part}' in: '{base_version}'")
            
            # Check for leading zeros (except for "0")
            if len(part) > 1 and part[0] == '0':
                raise VersionParsingError(f"Leading zero in version component '{part}' in: '{base_version}'")
            
            # Convert to int to validate range
            num = int(part)
            if num < 0:
                raise VersionParsingError(f"Negative version component '{part}' in: '{base_version}'")
            
            validated_parts.append(str(num))
        
        # Expand to full X.Y.Z format
        if len(validated_parts) == 1:
            # "1" → "1.0.0"
            return f"{validated_parts[0]}.0.0"
        elif len(validated_parts) == 2:
            # "1.3" → "1.3.0"
            return f"{validated_parts[0]}.{validated_parts[1]}.0"
        else:
            # "1.3.1" → "1.3.1" (already complete)
            return f"{validated_parts[0]}.{validated_parts[1]}.{validated_parts[2]}"
    
    def get_next_version(self, release_type: ReleaseType) -> str:
        """
        Calculate the next version based on current version and release type.
        
        Automatically increments the appropriate version component based on
        semantic versioning rules:
        - MAJOR: Increment major, reset minor and patch to 0
        - MINOR: Increment minor, reset patch to 0, keep major
        - PATCH: Increment patch, keep major and minor
        
        Args:
            release_type (ReleaseType): Type of release to generate
            
        Returns:
            str: Next semantic version string
            
        Example:
            >>> parser = VersionParser("1.2.3")
            >>> parser.get_next_version(ReleaseType.MAJOR)  # "2.0.0"
            >>> parser.get_next_version(ReleaseType.MINOR)  # "1.3.0"
            >>> parser.get_next_version(ReleaseType.PATCH)  # "1.2.4"
        """
        pass
    
    def generate_git_branch_name(self, version: str, branch_type: BranchType = BranchType.DEVELOPMENT) -> str:
        """
        Generate the Git branch name for a given version and branch type.
        
        Creates consistent Git branch names following the halfORM convention:
        - Development: "ho-dev/X.Y.x" (e.g., "ho-dev/1.3.x")
        - Production: "ho/X.Y.x" (e.g., "ho/1.3.x")  
        - Main: "main"
        
        Note: Individual releases are represented as tags (v1.3.1, v1.3.2) 
        on the appropriate production branch, not as separate branches.
        
        Args:
            version (str): Semantic version (X.Y.Z format)
            branch_type (BranchType): Type of branch to generate
            
        Returns:
            str: Git branch name following halfORM convention
            
        Raises:
            VersionParsingError: If version format is invalid
            
        Example:
            >>> parser = VersionParser("1.2.3")
            >>> parser.generate_git_branch_name("1.3.1", BranchType.DEVELOPMENT)  # "ho-dev/1.3.x"
            >>> parser.generate_git_branch_name("1.3.0", BranchType.PRODUCTION)   # "ho/1.3.x"
        """
        pass
    
    def generate_release_tag(self, version: str) -> str:
        """
        Generate the Git tag name for a release version.
        
        Creates release tags following semantic versioning convention:
        - Release tags: "vX.Y.Z" (e.g., "v1.3.1") or "vX.Y.Z-prerelease" (e.g., "v1.3.1-alpha1")
        - Applied to production branches (ho/X.Y.x)
        - Used to mark specific release points
        
        Args:
            version (str): Semantic version (X.Y.Z format)
            
        Returns:
            str: Git tag name for the release
            
        Raises:
            VersionParsingError: If version format is invalid
            
        Example:
            >>> parser = VersionParser("1.2.3")
            >>> parser.generate_release_tag("1.3.1")  # "v1.3.1"
        """
        pass
    
    def generate_maintenance_branch_name(self, version: str, for_production: bool = False) -> str:
        """
        Generate the maintenance branch name for a given version.
        
        Creates maintenance branch names for ongoing support:
        - Development maintenance: "ho-dev/X.Y.x" (e.g., "ho-dev/1.3.x")
        - Production maintenance: "ho/X.Y.x" (e.g., "ho/1.3.x")
        - Used for patch releases within a minor version line
        - Individual patches are tagged (v1.3.1, v1.3.2) not branched
        
        Args:
            version (str): Semantic version (X.Y.Z format)
            for_production (bool): Whether to generate production branch name
            
        Returns:
            str: Maintenance branch name
            
        Raises:
            VersionParsingError: If version format is invalid
            
        Example:
            >>> parser = VersionParser("1.2.3")
            >>> parser.generate_maintenance_branch_name("1.3.0")              # "ho-dev/1.3.x"
            >>> parser.generate_maintenance_branch_name("1.3.0", True)        # "ho/1.3.x"
        """
        pass
    
    def is_valid_version_format(self, version: str) -> bool:
        """
        Validate that a version string follows semantic versioning format.
        
        Checks that the version string:
        - Contains exactly 3 numeric components separated by dots
        - All components are non-negative integers
        - No leading zeros (except for "0")
        - No extra characters or whitespace
        
        Args:
            version (str): Version string to validate
            
        Returns:
            bool: True if format is valid, False otherwise
            
        Example:
            >>> parser = VersionParser("1.2.3")
            >>> parser.is_valid_version_format("1.2.3")   # True
            >>> parser.is_valid_version_format("1.2")     # False
            >>> parser.is_valid_version_format("1.2.03")  # False (leading zero)
        """
        pass
    
    def compare_versions(self, version1: str, version2: str) -> int:
        """
        Compare two semantic versions and return ordering result.
        
        Performs semantic version comparison following standard rules:
        - Compare major, then minor, then patch
        - Pre-release versions are ignored (base version is compared)
        - Returns negative if version1 < version2
        - Returns zero if version1 == version2  
        - Returns positive if version1 > version2
        
        Args:
            version1 (str): First version to compare
            version2 (str): Second version to compare
            
        Returns:
            int: Comparison result (-1, 0, or 1)
            
        Raises:
            VersionParsingError: If either version format is invalid
            
        Example:
            >>> parser = VersionParser("1.2.3")
            >>> parser.compare_versions("1.2.3", "1.3.0")        # -1 (1.2.3 < 1.3.0)
            >>> parser.compare_versions("1.3.0", "1.2.3")        # 1  (1.3.0 > 1.2.3)
            >>> parser.compare_versions("1.2.3", "1.2.3")        # 0  (equal)
            >>> parser.compare_versions("1.2.3-alpha", "1.2.3")  # 0  (base versions equal)
        """
        try:
            # Extract components from both versions
            major1, minor1, patch1 = self.get_version_components(version1)
            major2, minor2, patch2 = self.get_version_components(version2)
            
        except VersionParsingError as e:
            # Re-raise with more context about which version failed
            raise VersionParsingError(f"Version comparison failed: {str(e)}")
        
        # Compare major version first
        if major1 < major2:
            return -1
        elif major1 > major2:
            return 1
        
        # Major versions are equal, compare minor
        if minor1 < minor2:
            return -1
        elif minor1 > minor2:
            return 1
        
        # Major and minor are equal, compare patch
        if patch1 < patch2:
            return -1
        elif patch1 > patch2:
            return 1
        
        # All components are equal
        return 0
    
    def get_version_components(self, version: str) -> Tuple[int, int, int]:
        """
        Extract major, minor, and patch components from a version string.
        
        Parses a semantic version string and returns the individual numeric
        components as a tuple of integers. Handles both regular versions
        and pre-release versions by extracting the base version.
        
        Args:
            version (str): Semantic version string (X.Y.Z format or X.Y.Z-prerelease)
            
        Returns:
            Tuple[int, int, int]: (major, minor, patch) components
            
        Raises:
            VersionParsingError: If version format is invalid
            
        Example:
            >>> parser = VersionParser("1.2.3")
            >>> parser.get_version_components("1.4.2")          # (1, 4, 2)
            >>> parser.get_version_components("2.0.1-alpha1")   # (2, 0, 1)
        """
        if not isinstance(version, str):
            raise VersionParsingError(f"Version must be a string, got {type(version).__name__}")
        
        if not version or not version.strip():
            raise VersionParsingError("Version cannot be empty")
        
        # Remove whitespace
        version = version.strip()
        
        # Parse version to handle potential pre-release
        try:
            base_version, _ = self._parse_version_with_prerelease(version)
        except VersionParsingError as e:
            raise VersionParsingError(f"Invalid version format: '{version}'. {str(e)}")
        
        # Validate base version format
        if not self._is_valid_semantic_version(base_version):
            raise VersionParsingError(f"Invalid semantic version format: '{version}'")
        
        # Parse components using internal helper
        return self._parse_version_components(base_version)
