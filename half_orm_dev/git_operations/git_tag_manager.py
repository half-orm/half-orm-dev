#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Git Tag Manager for SchemaPatches Module

Provides Git-aware version assignment by automatically finding next available 
patch numbers from existing Git tags. Essential for the Git-centric workflow
where Git tags are the source of truth for production releases.

Key Features:
- Automatic detection of existing version tags
- Smart gap filling for external/manual releases  
- Semantic versioning validation
- Thread-safe Git operations
- Comprehensive error handling

Usage:
    tag_manager = GitTagManager(repo_path=".")
    next_numbers = tag_manager.get_next_available_patch_numbers("1.3.x", count=3)
    # Returns: [4, 5, 6] if v1.3.1, v1.3.2, v1.3.3 exist
    
    tag_manager.create_version_tag("1.3.4", "Release 1.3.4")
"""

import os
import re
import subprocess
from typing import List, Optional, Set, Dict, Tuple
from dataclasses import dataclass
from pathlib import Path

import git
from git.exc import GitCommandError, InvalidGitRepositoryError


class GitTagManagerError(Exception):
    """Base exception for GitTagManager operations"""
    pass


class InvalidRepositoryError(GitTagManagerError):
    """Raised when repository path is invalid or not a Git repository"""
    pass


class TagCreationError(GitTagManagerError):
    """Raised when tag creation fails"""
    pass


class TagParsingError(GitTagManagerError):
    """Raised when tag parsing fails"""
    pass


class VersionExistsError(GitTagManagerError):
    """Raised when attempting to create a tag that already exists"""
    pass


@dataclass(frozen=True)
class VersionTag:
    """
    Represents a semantic version tag with parsed components.
    
    Attributes:
        raw_tag (str): Original tag name (e.g., "v1.3.1", "1.3.1-alpha")
        major (int): Major version number
        minor (int): Minor version number  
        patch (int): Patch version number
        pre_release (Optional[str]): Pre-release identifier (e.g., "alpha1", "rc2")
        is_pre_release (bool): Whether this is a pre-release version
    """
    raw_tag: str
    major: int
    minor: int
    patch: int
    pre_release: Optional[str] = None
    is_pre_release: bool = False
    
    @property
    def maintenance_line(self) -> str:
        """Get maintenance branch identifier (X.Y.x format)"""
        pass
    
    @property
    def version_string(self) -> str:
        """Get version string without 'v' prefix"""
        pass
    
    def __str__(self) -> str:
        """String representation returns raw tag"""
        pass


class GitTagManager:
    """
    Manages Git tags for SchemaPatches version assignment.
    
    Provides intelligent version number assignment by analyzing existing Git tags
    and finding gaps for optimal patch numbering. Supports both regular releases
    and pre-release versions while maintaining semantic versioning compliance.
    """
    
    # Tag patterns for semantic versioning
    SEMANTIC_VERSION_PATTERN = re.compile(
        r'^v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)'
        r'(?:-(?P<prerelease>[a-zA-Z0-9]+(?:\.[a-zA-Z0-9]+)*))?$'
    )
    
    PRERELEASE_PATTERNS = {
        'alpha': re.compile(r'^alpha(\d+)?$'),
        'beta': re.compile(r'^beta(\d+)?$'), 
        'rc': re.compile(r'^rc(\d+)?$'),
        'dev': re.compile(r'^dev(\d+)?$')
    }
    
    def __init__(self, repo_path: str = "."):
        """
        Initialize GitTagManager with repository path.
        
        Args:
            repo_path (str): Path to Git repository (default: current directory)
            
        Raises:
            InvalidRepositoryError: If path is not a valid Git repository
        """
        pass
    
    def _invalidate_cache(self) -> None:
        """
        Invalidate tag cache to force refresh on next access.
        
        Used internally when repository state might have changed
        (e.g., after creating new tags).
        """
        pass
    
    def _get_all_tags(self) -> Dict[str, VersionTag]:
        """
        Get all semantic version tags from repository with caching.
        
        Scans repository for tags matching semantic versioning pattern and
        returns parsed VersionTag objects. Results are cached for performance.
        
        Returns:
            Dict[str, VersionTag]: Mapping of tag names to VersionTag objects
            
        Raises:
            GitTagManagerError: If Git operations fail
        """
        pass
    
    def _parse_version_tag(self, tag_name: str) -> VersionTag:
        """
        Parse a version tag into components.
        
        Extracts semantic version components from tag name and validates
        pre-release identifiers if present.
        
        Args:
            tag_name (str): Tag name to parse (e.g., "v1.3.1", "1.3.1-alpha1")
            
        Returns:
            VersionTag: Parsed version information
            
        Raises:
            TagParsingError: If tag doesn't follow semantic versioning
            
        Examples:
            >>> self._parse_version_tag("v1.3.1")
            VersionTag(raw_tag="v1.3.1", major=1, minor=3, patch=1)
            
            >>> self._parse_version_tag("1.3.1-alpha1")
            VersionTag(raw_tag="1.3.1-alpha1", major=1, minor=3, patch=1, 
                      pre_release="alpha1", is_pre_release=True)
        """
        pass
    
    def _validate_prerelease(self, pre_release: str) -> bool:
        """
        Validate pre-release identifier format.
        
        Checks if pre-release identifier follows acceptable patterns:
        alpha, alpha1, beta, beta1, rc, rc1, dev, dev1, etc.
        
        Args:
            pre_release (str): Pre-release identifier to validate
            
        Returns:
            bool: True if valid pre-release format
            
        Examples:
            >>> self._validate_prerelease("alpha1")
            True
            >>> self._validate_prerelease("invalid")
            False
        """
        pass
    
    def get_version_tags_for_line(self, maintenance_line: str) -> List[VersionTag]:
        """
        Get all version tags for a specific maintenance line.
        
        Filters tags by major.minor version and excludes pre-release versions
        for production patch numbering.
        
        Args:
            maintenance_line (str): Maintenance line (e.g., "1.3.x")
            
        Returns:
            List[VersionTag]: Sorted list of version tags for the line
            
        Raises:
            GitTagManagerError: If maintenance line format is invalid
            
        Examples:
            >>> manager.get_version_tags_for_line("1.3.x")
            [VersionTag(v1.3.1), VersionTag(v1.3.2), VersionTag(v1.3.8)]
        """
        pass
    
    def get_existing_patch_numbers(self, maintenance_line: str) -> Set[int]:
        """
        Get set of existing patch numbers for a maintenance line.
        
        Extracts patch numbers from all release tags in the maintenance line.
        Used for gap detection and next number calculation.
        
        Args:
            maintenance_line (str): Maintenance line (e.g., "1.3.x")
            
        Returns:
            Set[int]: Set of existing patch numbers
            
        Examples:
            >>> manager.get_existing_patch_numbers("1.3.x")
            {1, 2, 8}  # if tags v1.3.1, v1.3.2, v1.3.8 exist
        """
        pass
    
    def get_next_available_patch_numbers(self, maintenance_line: str, count: int = 1) -> List[int]:
        """
        Get next available patch numbers for a maintenance line.
        
        Intelligently finds gaps in existing patch numbers and returns the next
        available numbers in sequence. Handles external/manual releases gracefully
        by filling gaps first, then continuing sequence.
        
        Args:
            maintenance_line (str): Maintenance line (e.g., "1.3.x")
            count (int): Number of patch numbers to return
            
        Returns:
            List[int]: Next available patch numbers in ascending order
            
        Raises:
            GitTagManagerError: If count is invalid or maintenance line format is wrong
            
        Examples:
            # Existing tags: v1.3.1, v1.3.3, v1.3.8
            >>> manager.get_next_available_patch_numbers("1.3.x", 3)
            [2, 4, 5]  # Fills gaps first, then continues sequence
            
            # No existing tags
            >>> manager.get_next_available_patch_numbers("1.4.x", 2)
            [1, 2]  # Start from 1
            
            # No gaps
            >>> manager.get_next_available_patch_numbers("1.5.x", 2) 
            [4, 5]  # Continue after highest (if highest is 3)
        """
        pass
    
    def get_highest_patch_number(self, maintenance_line: str) -> Optional[int]:
        """
        Get the highest existing patch number for a maintenance line.
        
        Useful for determining the latest release in a maintenance line.
        
        Args:
            maintenance_line (str): Maintenance line (e.g., "1.3.x")
            
        Returns:
            Optional[int]: Highest patch number, or None if no patches exist
            
        Examples:
            >>> manager.get_highest_patch_number("1.3.x")
            8  # if v1.3.8 is highest
            
            >>> manager.get_highest_patch_number("1.4.x")
            None  # if no v1.4.x tags exist
        """
        pass
    
    def check_version_exists(self, version: str) -> bool:
        """
        Check if a specific version tag already exists.
        
        Supports both with and without 'v' prefix for flexibility.
        
        Args:
            version (str): Version to check (e.g., "1.3.4" or "v1.3.4")
            
        Returns:
            bool: True if version tag exists
            
        Examples:
            >>> manager.check_version_exists("1.3.4")
            True  # if v1.3.4 or 1.3.4 tag exists
            
            >>> manager.check_version_exists("v1.3.5")
            False  # if no such tag exists
        """
        pass
    
    def create_version_tag(self, version: str, message: Optional[str] = None, 
                          force: bool = False) -> str:
        """
        Create a new version tag in the repository.
        
        Creates an annotated tag with optional message. Validates version format
        and checks for conflicts unless force is specified.
        
        Args:
            version (str): Version to tag (e.g., "1.3.4")
            message (Optional[str]): Tag annotation message
            force (bool): Whether to overwrite existing tag
            
        Returns:
            str: Created tag name (with 'v' prefix)
            
        Raises:
            VersionExistsError: If version already exists and force=False
            TagCreationError: If Git tag creation fails
            TagParsingError: If version format is invalid
            
        Examples:
            >>> manager.create_version_tag("1.3.4", "Release 1.3.4")
            "v1.3.4"
            
            >>> manager.create_version_tag("1.3.4-alpha1", "Alpha release")
            "v1.3.4-alpha1"
        """
        pass
    
    def delete_version_tag(self, version: str, remote: bool = False) -> bool:
        """
        Delete a version tag from repository.
        
        Removes tag locally and optionally from remote repository.
        Used for cleanup or correcting mistakes.
        
        Args:
            version (str): Version tag to delete (e.g., "1.3.4" or "v1.3.4")
            remote (bool): Whether to also delete from remote
            
        Returns:
            bool: True if tag was deleted, False if tag didn't exist
            
        Raises:
            TagCreationError: If Git delete operation fails
            
        Examples:
            >>> manager.delete_version_tag("1.3.4")
            True  # Tag deleted locally
            
            >>> manager.delete_version_tag("1.3.4", remote=True)
            True  # Tag deleted locally and from remote
        """
        pass
    
    def get_all_maintenance_lines(self) -> Set[str]:
        """
        Get all maintenance lines that have released versions.
        
        Analyzes all version tags to determine which maintenance lines
        (major.minor combinations) have been used.
        
        Returns:
            Set[str]: Set of maintenance line identifiers (e.g., {"1.3.x", "2.0.x"})
            
        Examples:
            >>> manager.get_all_maintenance_lines()
            {"1.3.x", "1.4.x", "2.0.x"}  # if versions exist in these lines
        """
        pass
    
    def get_version_gaps(self, maintenance_line: str) -> List[int]:
        """
        Get list of gaps in patch numbering for a maintenance line.
        
        Identifies missing patch numbers in the sequence, useful for
        detecting external/manual releases or planning gap fills.
        
        Args:
            maintenance_line (str): Maintenance line (e.g., "1.3.x")
            
        Returns:
            List[int]: Sorted list of missing patch numbers
            
        Examples:
            # Existing: v1.3.1, v1.3.3, v1.3.8
            >>> manager.get_version_gaps("1.3.x")
            [2, 4, 5, 6, 7]  # Missing numbers in sequence
            
            # No gaps
            >>> manager.get_version_gaps("1.4.x")
            []  # if v1.4.1, v1.4.2, v1.4.3 exist
        """
        pass
    
    def validate_version_format(self, version: str) -> bool:
        """
        Validate that version string follows semantic versioning.
        
        Checks format compliance without requiring the version to be unique.
        Supports both with and without 'v' prefix.
        
        Args:
            version (str): Version string to validate
            
        Returns:
            bool: True if format is valid
            
        Examples:
            >>> manager.validate_version_format("1.3.4")
            True
            
            >>> manager.validate_version_format("v1.3.4-alpha1")
            True
            
            >>> manager.validate_version_format("invalid")
            False
        """
        pass
    
    def refresh_cache(self) -> None:
        """
        Force refresh of internal tag cache.
        
        Useful when external Git operations might have modified tags
        and cache needs to be updated.
        
        Examples:
            >>> manager.refresh_cache()  # After external git tag operations
        """
        pass
