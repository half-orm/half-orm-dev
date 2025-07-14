#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Git Tag Manager for SchemaPatches Module

Provides Git-aware tag management for the ultra-simplified SchemaPatches workflow.
Handles both dev-patch-* and patch-* tags with minimal metadata (tag message = directory reference).

Key Features:
- Auto-discovery of patch tags by pattern
- Chronological ordering based on Git history
- Tag creation and validation
- Integration with halfORM HGit instances
- Transfer dev-patch-* → patch-* workflow

Usage:
    # Preferred: Integration with halfORM
    tag_manager = GitTagManager(repo.hgit)
    
    # Standalone: For testing
    tag_manager = GitTagManager(repo_path=".")
    
    # Get all patch tags between versions
    tags = tag_manager.get_patch_tags_between("v1.3.1", "v1.3.2")
    
    # Create development validation tag
    tag_manager.create_tag("dev-patch-1.3.2-security", "123-security")
    
    # Transfer to production
    tag_manager.transfer_dev_tags_to_prod("1.3.2")
"""

import os
import re
from datetime import datetime
from typing import List, Optional, Set, Dict
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


class TagValidationError(GitTagManagerError):
    """Raised when tag validation fails"""
    pass


class TransferError(GitTagManagerError):
    """Raised when dev-patch → patch transfer fails"""
    pass


@dataclass(frozen=True)
class PatchTag:
    """
    Represents a schema patch tag with parsed information.
    
    Attributes:
        name (str): Full tag name (e.g., "dev-patch-1.3.2-security")
        version (str): Version part (e.g., "1.3.2")
        suffix (str): Tag suffix (e.g., "security")
        message (str): Tag message = SchemaPatches directory reference
        commit_hash (str): Git commit hash
        is_dev_tag (bool): True if dev-patch-*, False if patch-*
        timestamp (int): Creation timestamp for ordering
    """
    name: str
    version: str
    suffix: str
    message: str
    commit_hash: str
    is_dev_tag: bool
    timestamp: datetime
    
    @property
    def maintenance_line(self) -> str:
        """Get maintenance line (X.Y.x) from version"""
        parts = self.version.split('.')
        if len(parts) >= 2:
            return f"{parts[0]}.{parts[1]}.x"
        return self.version
    
    @property
    def schema_patches_directory(self) -> str:
        """Get SchemaPatches directory from tag message"""
        return self.message
    
    def __lt__(self, other: 'PatchTag') -> bool:
        """Enable sorting by timestamp (Git chronological order)"""
        return self.timestamp < other.timestamp
    
    def __str__(self) -> str:
        """String representation with key information"""
        status = "DEV" if self.is_dev_tag else "PROD"
        return f"PatchTag({self.name}, {self.message}, {self.commit_hash[:8]}, {status})"

class GitTagManager:
    """
    Manages Git tags for ultra-simplified SchemaPatches workflow.
    
    Handles creation, validation, and transfer of dev-patch-* and patch-* tags
    with minimal metadata. Integrates with halfORM HGit instances when available.
    """

    DEV_PATCH_PATTERN = re.compile(r'^dev-patch-(\d+\.\d+\.\d+)-([a-zA-Z0-9_-]+)$')
    PATCH_PATTERN = re.compile(r'^patch-(\d+\.\d+\.\d+)-([a-zA-Z0-9_-]+)$')

    def __init__(self, hgit_instance=None, repo_path: str = "."):
        """
        Initialize GitTagManager with HGit instance or repository path.
        
        Args:
            hgit_instance: HGit instance from halfORM repo (preferred)
            repo_path (str): Path to Git repository (fallback)
            
        Raises:
            InvalidRepositoryError: If repository is invalid
        """
        if hgit_instance is not None:
            # Use halfORM HGit instance (preferred mode)
            self.repo = hgit_instance._HGit__git_repo
            self.repo_path = Path(hgit_instance._HGit__repo.base_dir).resolve()
        else:
            # Standalone mode (fallback)
            self.repo_path = Path(repo_path).resolve()
            
            # Check if path exists first
            if not self.repo_path.exists():
                raise InvalidRepositoryError(f"Path does not exist: {self.repo_path}")
            
            try:
                self.repo = git.Repo(self.repo_path)
            except (GitCommandError, InvalidGitRepositoryError, Exception) as e:
                raise InvalidRepositoryError(f"Invalid Git repository at {self.repo_path}: {e}")
        
        # SchemaPatches directory
        self.schema_patches_dir = self.repo_path / "SchemaPatches"
        
        # Ensure SchemaPatches directory exists
        if not self.schema_patches_dir.exists():
            self.schema_patches_dir.mkdir(parents=True, exist_ok=True)
    
    def get_all_tags_between(self, from_version: str, to_version: str) -> List[PatchTag]:
        """
        Get all tags between two version tags, sorted by Git chronological order.
        
        Args:
            from_version (str): Starting version tag (e.g., "v1.3.1")
            to_version (str): Ending version tag (e.g., "v1.3.2")
            
        Returns:
            List[PatchTag]: All tags in chronological order
            
        Raises:
            GitTagManagerError: If version tags don't exist or Git operations fail
        """
        pass
    
    def get_patch_tags_between(self, from_version: str, to_version: str, 
                              dev_tags: bool = False) -> List[PatchTag]:
        """
        Get patch-* or dev-patch-* tags between versions in chronological order.
        
        Args:
            from_version (str): Starting version (e.g., "v1.3.1")
            to_version (str): Ending version (e.g., "v1.3.2")
            dev_tags (bool): If True, return dev-patch-*, else patch-*
            
        Returns:
            List[PatchTag]: Patch tags in Git chronological order
        """
        pass
    
    def create_tag(self, tag_name: str, message: str, commit_ref: str = "HEAD") -> PatchTag:
        """
        Create a new schema patch tag with validation.
        
        Args:
            tag_name (str): Tag name (e.g., "dev-patch-1.3.2-security")
            message (str): Tag message = SchemaPatches directory (e.g., "123-security")
            commit_ref (str): Git commit reference
            
        Returns:
            PatchTag: Created tag information
            
        Raises:
            TagCreationError: If tag creation fails
            TagValidationError: If tag format is invalid
        """
        pass
    
    def validate_tag_format(self, tag_name: str) -> bool:
        """
        Validate that tag name follows schema patch conventions.
        
        Args:
            tag_name (str): Tag name to validate
            
        Returns:
            bool: True if format is valid
        """
        if not tag_name or not isinstance(tag_name, str):
            return False
        
        # Check if matches dev-patch or patch pattern
        dev_match = self.DEV_PATCH_PATTERN.match(tag_name)
        patch_match = self.PATCH_PATTERN.match(tag_name)
        
        if dev_match or patch_match:
            # Additional validation: suffix cannot be empty
            match = dev_match or patch_match
            version, suffix = match.groups()
            
            # Suffix must not be empty and must be valid
            if not suffix or suffix.endswith('-') or suffix.startswith('-'):
                return False
            
            return True
        
        return False
    
    def validate_schema_patch_reference(self, message: str) -> bool:
        """
        Validate that tag message references an existing SchemaPatches directory.
        
        Args:
            message (str): Tag message (should be SchemaPatches/XXX-name)
            
        Returns:
            bool: True if directory exists
        """
        if not message or not isinstance(message, str):
            return False
        
        # Check for path traversal attempts
        if '..' in message or message.startswith('/'):
            return False
        
        # Check if directory exists
        patch_dir = self.schema_patches_dir / message
        return patch_dir.exists() and patch_dir.is_dir()
    
    def parse_patch_tag(self, tag_name: str, git_tag) -> Optional[PatchTag]:
        """
        Parse a Git tag into PatchTag if it matches schema patch patterns.
        
        Args:
            tag_name (str): Tag name
            git_tag: GitPython tag object
            
        Returns:
            Optional[PatchTag]: Parsed tag info or None if not a patch tag
        """
        pass
    
    def transfer_dev_tags_to_prod(self, version: str) -> List[PatchTag]:
        """
        Transfer all dev-patch-X.Y.Z-* tags to corresponding patch-X.Y.Z-* tags.
        
        Args:
            version (str): Version to transfer (e.g., "1.3.2")
            
        Returns:
            List[PatchTag]: Created production tags
            
        Raises:
            TransferError: If transfer validation fails
        """
        pass
    
    def get_dev_tags_for_version(self, version: str) -> List[PatchTag]:
        """
        Get all dev-patch-* tags for a specific version in chronological order.
        
        Args:
            version (str): Version (e.g., "1.3.2")
            
        Returns:
            List[PatchTag]: Development tags for version
        """
        pass
    
    def get_prod_tags_for_version(self, version: str) -> List[PatchTag]:
        """
        Get all patch-* tags for a specific version in chronological order.
        
        Args:
            version (str): Version (e.g., "1.3.2")
            
        Returns:
            List[PatchTag]: Production tags for version
        """
        pass
    
    def validate_dev_to_prod_consistency(self, version: str) -> bool:
        """
        Validate that dev-patch-* and patch-* tags are consistent for a version.
        
        Args:
            version (str): Version to validate
            
        Returns:
            bool: True if dev and prod tags match
        """
        pass
    
    def sort_tags_by_commit_order(self, tags: List[PatchTag]) -> List[PatchTag]:
        """
        Sort patch tags by Git commit chronological order (not tag name).
        
        Args:
            tags (List[PatchTag]): Tags to sort
            
        Returns:
            List[PatchTag]: Tags sorted by Git history order
        """
        pass
    
    def tag_exists(self, tag_name: str) -> bool:
        """
        Check if a tag exists in the repository.
        
        Args:
            tag_name (str): Tag name to check
            
        Returns:
            bool: True if tag exists
        """
        pass
    
    def delete_tag(self, tag_name: str, remote: bool = False) -> bool:
        """
        Delete a tag from repository.
        
        Args:
            tag_name (str): Tag to delete
            remote (bool): Also delete from remote
            
        Returns:
            bool: True if tag was deleted
            
        Raises:
            TagCreationError: If deletion fails
        """
        pass
    
    def get_latest_version_tag(self) -> Optional[str]:
        """
        Get the latest version tag (vX.Y.Z) in the repository.
        
        Returns:
            Optional[str]: Latest version tag name or None
        """
        pass
    
    def checkout(self, ref: str) -> None:
        """
        Checkout to a specific Git reference.
        
        Args:
            ref (str): Git reference (tag, branch, commit)
            
        Raises:
            GitTagManagerError: If checkout fails
        """
        pass