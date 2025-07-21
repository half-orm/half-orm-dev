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
from enum import Enum
from typing import List, Optional, Set, Dict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import git
from git.exc import GitCommandError, InvalidGitRepositoryError

class TagType(Enum):
    """
    Enumeration of Git tag types in the ultra-simplified SchemaPatches workflow.
    
    Separates the 3 phases of patch lifecycle:
    - CREATE: Reservation tags (create-patch-*) for anti-conflict
    - DEV_RELEASE: Development validation tags (dev-patch-*) 
    - PROD_RELEASE: Production deployment tags (patch-*)
    """
    CREATE = "create"           # create-patch-456-performance
    DEV_RELEASE = "dev_release" # dev-patch-1.3.2-performance
    PROD_RELEASE = "prod_release" # patch-1.3.2-performance


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

class PatchReservationError(GitTagManagerError):
    """Raised when patch reservation operations fail"""
    pass


@dataclass(frozen=True)
class PatchTag:
    """
    Represents a schema patch tag with parsed information.
    
    Attributes:
        name (str): Full tag name (e.g., "dev-patch-1.3.2-security")
        version (Optional[str]): Version part (e.g., "1.3.2", None for create-patch)
        suffix (str): Tag suffix (e.g., "security")
        message (str): Tag message = SchemaPatches directory reference
        commit_hash (str): Git commit hash
        is_dev_tag (bool): DEPRECATED - use tag_type instead
        timestamp (datetime): Creation timestamp for ordering
        tag_type (TagType): Type of tag (CREATE, DEV_RELEASE, PROD_RELEASE)
    """
    name: str
    version: Optional[str]  # None for create-patch-*
    suffix: str
    message: str
    commit_hash: str
    is_dev_tag: bool  # DEPRECATED
    timestamp: datetime
    tag_type: TagType  # NEW
    
    @property
    def is_create_tag(self) -> bool:
        """True if this is a reservation tag (create-patch-*)"""
        return self.tag_type == TagType.CREATE
    
    @property 
    def is_dev_release_tag(self) -> bool:
        """True if this is a development release tag (dev-patch-*)"""
        return self.tag_type == TagType.DEV_RELEASE
        
    @property
    def is_prod_release_tag(self) -> bool:
        """True if this is a production release tag (patch-*)"""
        return self.tag_type == TagType.PROD_RELEASE
    
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
    
    def __eq__(self, other) -> bool:
        """Compare tags by name and commit hash (ignore timestamp)"""
        if not isinstance(other, PatchTag):
            return False
        return self.name == other.name and self.commit_hash == other.commit_hash
    
    def __hash__(self) -> int:
        """Hash by name and commit hash for consistency with __eq__"""
        return hash((self.name, self.commit_hash))
    
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

    CREATE_PATCH_PATTERN = re.compile(r'^create-patch-([a-zA-Z0-9_-]+)$')
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
                              tag_type: TagType) -> List[PatchTag]:
        """
        Get patch tags between versions in chronological order, filtered by type.
        
        Args:
            from_version (str): Starting version (e.g., "v1.3.1")
            to_version (str): Ending version (e.g., "v1.3.2")
            tag_type (TagType): Filter by specific tag type (CREATE, DEV_RELEASE, PROD_RELEASE)
            
        Returns:
            List[PatchTag]: Patch tags in Git chronological order
            
        Examples:
            >>> # Get all dev-patch tags (new way)
            >>> tags = manager.get_patch_tags_between("v1.3.1", "v1.3.2", TagType.DEV_RELEASE)
            >>> 
            >>> # Get all create-patch tags (new functionality)
            >>> tags = manager.get_patch_tags_between("v1.3.1", "v1.3.2", TagType.CREATE)
        """
        try:
            # Get commits between version tags
            commit_range = f"{from_version}..{to_version}"
            commits_in_range = set(commit.hexsha for commit in self.repo.iter_commits(commit_range))
            
            # Get all patch tags and filter by type and commit range
            all_patch_tags = self._get_all_patch_tags()
            filtered_tags = []
            
            for tag in all_patch_tags:
                # Handle filtering logic with backward compatibility
                # New filtering by TagType (preferred)
                if tag.tag_type != tag_type:
                    continue
                
                # Check if tag's commit is in the range
                if tag.commit_hash in commits_in_range:
                    filtered_tags.append(tag)
            
            return sorted(filtered_tags)
            
        except GitCommandError as e:
            raise GitTagManagerError(f"Failed to get tags between versions {from_version}..{to_version}: {e}")
    
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
        # Validate tag format
        if not self.validate_tag_format(tag_name):
            raise TagValidationError(f"Invalid tag format: {tag_name}")
        
        # Validate schema patch reference
        if not self.validate_schema_patch_reference(message):
            raise TagValidationError(f"Invalid schema patch reference: {message}")
        
        # Check if tag already exists
        if self.tag_exists(tag_name):
            raise TagCreationError(f"Tag already exists: {tag_name}")
        
        try:
            # Create the Git tag
            git_tag = self.repo.create_tag(tag_name, ref=commit_ref, message=message)
            
            # Parse the created tag and return PatchTag
            patch_tag = self.parse_patch_tag(tag_name, git_tag)
            if patch_tag is None:
                raise TagCreationError(f"Failed to parse created tag: {tag_name}")
            
            return patch_tag
            
        except GitCommandError as e:
            raise TagCreationError(f"Failed to create Git tag {tag_name}: {e}")
        except Exception as e:
            raise TagCreationError(f"Unexpected error creating tag {tag_name}: {e}")
    
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
        
        # Check if matches create-patch, dev-patch or patch pattern
        create_patch_match = self.CREATE_PATCH_PATTERN.match(tag_name)
        dev_match = self.DEV_PATCH_PATTERN.match(tag_name)
        patch_match = self.PATCH_PATTERN.match(tag_name)
        
        if create_patch_match:
            # For create-patch tags, just validate patch_id is not empty
            patch_id = create_patch_match.group(1)
            if not patch_id or patch_id.endswith('-') or patch_id.startswith('-'):
                return False
            return True
        
        elif dev_match or patch_match:
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
        
        try:
            # Check if directory exists
            patch_dir = self.schema_patches_dir / message
            return patch_dir.exists() and patch_dir.is_dir()
        except (PermissionError, OSError):
            # Handle permission errors gracefully
            return False
    
    def parse_patch_tag(self, tag_name: str, git_tag) -> Optional[PatchTag]:
        """
        Parse a Git tag into PatchTag if it matches schema patch patterns.
        
        Args:
            tag_name (str): Tag name
            git_tag: GitPython tag object
            
        Returns:
            Optional[PatchTag]: Parsed tag info or None if not a patch tag
            
        Raises:
            TagValidationError: If tag format is valid but content is invalid
        """
        # Try create-patch pattern FIRST
        create_match = self.CREATE_PATCH_PATTERN.match(tag_name)
        if create_match:
            patch_id = create_match.group(1)
            
            # Get tag message and validate
            message = git_tag.tag.message.strip() if git_tag.tag else ""
            if not message:
                raise TagValidationError(f"Tag {tag_name} has empty message")
            
            if not self.validate_schema_patch_reference(message):
                raise TagValidationError(f"Tag {tag_name} references non-existent SchemaPatches directory: {message}")
            
            # Get commit hash and timestamp
            commit_hash = git_tag.commit.hexsha
            
            # Handle timestamp - prefer tag object timestamp, fallback to commit timestamp
            if git_tag.tag and hasattr(git_tag.tag, 'tagged_date'):
                timestamp = datetime.fromtimestamp(git_tag.tag.tagged_date)
            else:
                timestamp = datetime.fromtimestamp(git_tag.commit.committed_date)
            
            return PatchTag(
                name=tag_name,
                version=None,  # Pas de version pour create-patch
                suffix=patch_id,
                message=message,
                commit_hash=commit_hash,
                is_dev_tag=False,  # DEPRECATED - create-patch n'est pas dev
                timestamp=timestamp,
                tag_type=TagType.CREATE
            )
        
        # Try dev-patch pattern
        dev_match = self.DEV_PATCH_PATTERN.match(tag_name)
        if dev_match:
            version, suffix = dev_match.groups()
            is_dev_tag = True
            tag_type = TagType.DEV_RELEASE
        else:
            # Try patch pattern  
            patch_match = self.PATCH_PATTERN.match(tag_name)
            if patch_match:
                version, suffix = patch_match.groups()
                is_dev_tag = False
                tag_type = TagType.PROD_RELEASE
            else:
                # Not a patch tag
                return None
        
        # Get tag message and validate (pour dev-patch et patch)
        message = git_tag.tag.message.strip() if git_tag.tag else ""
        if not message:
            raise TagValidationError(f"Tag {tag_name} has empty message")
        
        if not self.validate_schema_patch_reference(message):
            raise TagValidationError(f"Tag {tag_name} references non-existent SchemaPatches directory: {message}")
        
        # Get commit hash and timestamp
        commit_hash = git_tag.commit.hexsha
        
        # Handle timestamp - prefer tag object timestamp, fallback to commit timestamp
        if git_tag.tag and hasattr(git_tag.tag, 'tagged_date'):
            timestamp = datetime.fromtimestamp(git_tag.tag.tagged_date)
        else:
            timestamp = datetime.fromtimestamp(git_tag.commit.committed_date)
        
        return PatchTag(
            name=tag_name,
            version=version,
            suffix=suffix,
            message=message,
            commit_hash=commit_hash,
            is_dev_tag=is_dev_tag,  # DEPRECATED
            timestamp=timestamp,
            tag_type=tag_type
        )
    
    def validate_tag_branch_consistency(self, patch_tag: PatchTag) -> bool:
        """
        Validate that tag type matches current branch (utility for higher layers).
        
        Args:
            patch_tag (PatchTag): Tag to validate
            
        Returns:
            bool: True if tag type is consistent with current branch
        """
        try:
            current_branch = self.repo.active_branch.name
            if patch_tag.is_dev_tag:
                return current_branch.startswith('ho-dev/')
            else:
                return current_branch.startswith('ho/')
        except Exception:
            # If we can't determine branch, assume consistency
            return True

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
        try:
            # Get all dev tags for this version
            dev_tags = self.get_dev_tags_for_version(version)
            
            # If no dev tags, return empty list
            if not dev_tags:
                return []
            
            # Check for existing prod tags that would conflict
            for dev_tag in dev_tags:
                prod_tag_name = f"patch-{dev_tag.version}-{dev_tag.suffix}"
                if self.tag_exists(prod_tag_name):
                    raise TransferError(f"Production tag already exists: {prod_tag_name}")
            
            # Create corresponding prod tags
            prod_tags = []
            for dev_tag in dev_tags:
                prod_tag_name = f"patch-{dev_tag.version}-{dev_tag.suffix}"
                
                # Create prod tag with same message and commit
                prod_tag = self.create_tag(
                    tag_name=prod_tag_name,
                    message=dev_tag.message,
                    commit_ref=dev_tag.commit_hash
                )
                prod_tags.append(prod_tag)
            
            return prod_tags
            
        except (GitTagManagerError, TagCreationError, TagValidationError) as e:
            raise TransferError(f"Failed to transfer dev tags to prod for version {version}: {e}")
        except Exception as e:
            raise TransferError(f"Unexpected error during transfer for version {version}: {e}")
    
    def get_dev_tags_for_version(self, version: str) -> List[PatchTag]:
        """
        Get all dev-patch-* tags for a specific version in chronological order.
        
        Args:
            version (str): Version (e.g., "1.3.2")
            
        Returns:
            List[PatchTag]: Development tags for version
        """
        all_tags = self._get_all_patch_tags()
        dev_tags = [tag for tag in all_tags 
                if tag.is_dev_tag and tag.version == version]
        return sorted(dev_tags)

    
    def get_prod_tags_for_version(self, version: str) -> List[PatchTag]:
        """
        Get all patch-* tags for a specific version in chronological order.
        
        Args:
            version (str): Version (e.g., "1.3.2")
            
        Returns:
            List[PatchTag]: Production tags for version
        """
        all_tags = self._get_all_patch_tags()
        prod_tags = [tag for tag in all_tags 
                    if not tag.is_dev_tag and tag.version == version]
        return sorted(prod_tags)

    def _get_all_patch_tags(self) -> List[PatchTag]:
        """
        Internal method to get all patch tags (dev-patch-* and patch-*) sorted by Git chronological order.
        
        Returns:
            List[PatchTag]: All patch tags in chronological order
            
        Raises:
            GitTagManagerError: If Git operations fail
        """
        patch_tags = []
        
        try:
            for git_tag in self.repo.tags:
                patch_tag = self.parse_patch_tag(git_tag.name, git_tag)
                if patch_tag is not None:
                    patch_tags.append(patch_tag)
                    
            # Sort by Git commit order (more reliable than timestamp)
            return self.sort_tags_by_commit_order(patch_tags)
            
        except GitCommandError as e:
            raise GitTagManagerError(f"Failed to retrieve Git tags: {e}")

    def validate_dev_to_prod_consistency(self, version: str) -> bool:
        """
        Validate that dev-patch-* and patch-* tags are consistent for a version.
        
        Args:
            version (str): Version to validate
            
        Returns:
            bool: True if dev and prod tags match
        """
        try:
            # Get dev and prod tags for this version
            dev_tags = self.get_dev_tags_for_version(version)
            prod_tags = self.get_prod_tags_for_version(version)
            
            # If no tags exist for this version, consider it consistent
            if not dev_tags and not prod_tags:
                return True
            
            # Check if number of tags match
            if len(dev_tags) != len(prod_tags):
                return False
            
            # Create maps by suffix for comparison
            dev_tags_by_suffix = {tag.suffix: tag for tag in dev_tags}
            prod_tags_by_suffix = {tag.suffix: tag for tag in prod_tags}
            
            # Check if all suffixes match
            if set(dev_tags_by_suffix.keys()) != set(prod_tags_by_suffix.keys()):
                return False
            
            # Check if corresponding tags have same message and commit
            for suffix in dev_tags_by_suffix:
                dev_tag = dev_tags_by_suffix[suffix]
                prod_tag = prod_tags_by_suffix[suffix]
                
                # Check message consistency
                if dev_tag.message != prod_tag.message:
                    return False
                
                # Check commit consistency
                if dev_tag.commit_hash != prod_tag.commit_hash:
                    return False
            
            return True
            
        except Exception:
            # If any error occurs during validation, consider inconsistent
            return False
    
    def sort_tags_by_commit_order(self, tags: List[PatchTag]) -> List[PatchTag]:
        """
        Sort patch tags by Git commit chronological order (not tag name).
        
        Args:
            tags (List[PatchTag]): Tags to sort
            
        Returns:
            List[PatchTag]: Tags sorted by Git history order
        """
        if not tags:
            return tags
            
        try:
            # Get all commits in chronological order
            commits = list(self.repo.iter_commits())
            
            # Create a mapping from commit hash to its position in history
            # Earlier commits have higher index (reverse chronological)
            commit_order = {commit.hexsha: i for i, commit in enumerate(commits)}
            
            # Sort tags by their commit's position in Git history
            # Lower index = more recent = should come later in the list
            def sort_key(tag: PatchTag) -> int:
                return commit_order.get(tag.commit_hash, float('inf'))
            
            # Sort in reverse order (most recent commits last)
            return sorted(tags, key=sort_key, reverse=True)
            
        except Exception:
            # Fallback to timestamp sorting if Git operations fail
            return sorted(tags)

    def tag_exists(self, tag_name: str) -> bool:
        """
        Check if a tag exists in the repository.
        
        Args:
            tag_name (str): Tag name to check
            
        Returns:
            bool: True if tag exists
        """
        try:
            # Check if tag exists in the repository
            return tag_name in [tag.name for tag in self.repo.tags]
        except GitCommandError:
            return False

    
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
        try:
            # Check if tag exists first
            if not self.tag_exists(tag_name):
                return False
            
            # Delete the local tag
            self.repo.delete_tag(tag_name)
            
            # Delete from remote if requested
            if remote:
                try:
                    self.repo.git.push('origin', f':refs/tags/{tag_name}')
                except GitCommandError:
                    # Remote deletion failed, but local deletion succeeded
                    # This is not considered a failure for the method
                    pass
            
            return True
            
        except GitCommandError as e:
            raise TagCreationError(f"Failed to delete tag {tag_name}: {e}")
        except Exception as e:
            raise TagCreationError(f"Unexpected error deleting tag {tag_name}: {e}")

    
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
        try:
            # Checkout to the specified reference
            self.repo.git.checkout(ref)
        except GitCommandError as e:
            raise GitTagManagerError(f"Failed to checkout to {ref}: {e}")
        except Exception as e:
            raise GitTagManagerError(f"Unexpected error during checkout to {ref}: {e}")

    def check_patch_reservation_conflicts(self, patch_id: str) -> List[str]:
        """
        Check for patch reservation conflicts across all remote branches.
        
        Scans all remote branches for existing create-patch-{patch_id} tags
        to detect version conflicts before creating a new patch reservation.
        
        Args:
            patch_id (str): Patch identifier to check (e.g., "456-performance")
            
        Returns:
            List[str]: List of branch names where patch_id is already reserved
            
        Raises:
            GitTagManagerError: If Git operations fail
            
        Example:
            >>> conflicts = manager.check_patch_reservation_conflicts("456-performance")
            >>> if conflicts:
            >>>     print(f"Patch already reserved in: {conflicts}")
        """
        if not patch_id or not isinstance(patch_id, str):
            raise GitTagManagerError("patch_id must be a non-empty string")
        
        # Remove whitespace and validate
        patch_id = patch_id.strip()
        if not patch_id:
            raise GitTagManagerError("patch_id cannot be empty or whitespace only")
        
        try:
            # Fetch latest remote state
            for remote in self.repo.remotes:
                remote.fetch()
            
            conflicts = []
            reservation_tag_name = f"create-patch-{patch_id}"
            
            # Check all remote branches for the reservation tag
            for remote in self.repo.remotes:
                for ref in remote.refs:
                    branch_name = ref.name  # e.g., "origin/ho-dev/1.3.x"
                    
                    try:
                        # Check if reservation tag exists in this branch
                        commit = ref.commit
                        
                        # Look for our reservation tag in this branch's history
                        for tag in self.repo.tags:
                            if tag.name == reservation_tag_name:
                                # Check if this tag is reachable from this branch
                                try:
                                    # Use git merge-base to check if tag is in branch history
                                    merge_base = self.repo.git.merge_base(tag.commit.hexsha, commit.hexsha)
                                    if merge_base == tag.commit.hexsha:
                                        # Tag is in this branch's history
                                        conflicts.append(branch_name)
                                        break
                                except Exception:
                                    # If merge-base fails, skip this check
                                    continue
                                    
                    except Exception:
                        # Skip branches we can't access
                        continue
            
            return conflicts
            
        except Exception as e:
            raise GitTagManagerError(f"Failed to check patch reservation conflicts: {e}")

    def create_patch_reservation(self, patch_id: str) -> PatchTag:
        """
        Create a patch reservation tag to prevent conflicts.
        
        Creates a create-patch-{patch_id} tag after checking for conflicts
        across all remote branches. This reserves the patch_id globally.
        
        Args:
            patch_id (str): Patch identifier to reserve (e.g., "456-performance")
            
        Returns:
            PatchTag: Created reservation tag information
            
        Raises:
            GitTagManagerError: If patch_id is already reserved or creation fails
            PatchReservationError: If patch_id format is invalid
            
        Example:
            >>> tag = manager.create_patch_reservation("456-performance")
            >>> print(f"Reserved: {tag.name}")
        """
        if not patch_id or not isinstance(patch_id, str):
            raise PatchReservationError("patch_id must be a non-empty string")
        
        # Remove whitespace and validate format
        patch_id = patch_id.strip()
        if not patch_id:
            raise PatchReservationError("patch_id cannot be empty or whitespace only")
        
        # Basic format validation for patch_id
        if not re.match(r'^[a-zA-Z0-9_-]+$', patch_id):
            raise PatchReservationError(f"patch_id contains invalid characters: '{patch_id}'")
        
        try:
            # 1. Check for conflicts first
            conflicts = self.check_patch_reservation_conflicts(patch_id)
            if conflicts:
                raise GitTagManagerError(
                    f"Patch '{patch_id}' already reserved in branches: {', '.join(conflicts)}"
                )
            
            # 2. Validate that SchemaPatches directory exists
            if not self.validate_schema_patch_reference(patch_id):
                raise PatchReservationError(
                    f"SchemaPatches directory does not exist: {patch_id}. "
                    f"Create SchemaPatches/{patch_id}/ before reserving."
                )
            
            # 3. Create the reservation tag
            tag_name = f'create-patch-{patch_id}'
            
            # Check if tag already exists locally
            if self.tag_exists(tag_name):
                raise GitTagManagerError(f"Reservation tag already exists: {tag_name}")
            
            # Create the Git tag with patch_id as message
            reservation_tag = self.create_tag(tag_name, patch_id)
            
            return reservation_tag
            
        except (GitTagManagerError, PatchReservationError):
            # Re-raise our exceptions as-is
            raise
        except Exception as e:
            raise GitTagManagerError(f"Failed to create patch reservation '{patch_id}': {e}")

    def create_patch_with_full_workflow(self, patch_id: str) -> Dict[str, Any]:
        """
        Create patch with complete workflow: directory + reservation + push.
        
        Orchestrates the complete patch creation workflow:
        1. Create SchemaPatches/{patch_id}/ directory if not exists
        2. Create reservation tag (create-patch-{patch_id})
        3. Push reservation to remote for global conflict prevention
        
        Args:
            patch_id (str): Patch identifier (e.g., "456-performance")
            
        Returns:
            Dict[str, Any]: Workflow status and created resources
            
        Raises:
            GitTagManagerError: If any step fails
            PatchReservationError: If patch_id is invalid
            
        Example:
            >>> result = manager.create_patch_with_full_workflow("456-performance")
            >>> print(f"Created: {result['patch_directory']}")
            >>> print(f"Reserved: {result['reservation_tag']}")
        """
        if not patch_id or not isinstance(patch_id, str):
            raise PatchReservationError("patch_id must be a non-empty string")
        
        patch_id = patch_id.strip()
        if not patch_id:
            raise PatchReservationError("patch_id cannot be empty")
        
        workflow_result = {
            'patch_id': patch_id,
            'patch_directory': None,
            'reservation_tag': None,
            'pushed_to_remote': False,
            'created_directory': False
        }
        
        try:
            # 1. Create SchemaPatches directory if it doesn't exist
            patch_dir = self.schema_patches_dir / patch_id
            if not patch_dir.exists():
                patch_dir.mkdir(parents=True, exist_ok=True)
                
                # Create a README.md placeholder
                readme_file = patch_dir / "README.md"
                with open(readme_file, 'w') as f:
                    f.write(f"# Patch {patch_id}\n\n")
                    f.write("Add your SQL migration files to this directory.\n")
                    f.write("Files are applied in alphabetical order.\n\n")
                    f.write("## Example\n")
                    f.write("```sql\n")
                    f.write("-- 01_create_table.sql\n")
                    f.write("CREATE TABLE example (id SERIAL PRIMARY KEY);\n")
                    f.write("```\n")
                
                workflow_result['created_directory'] = True
            
            workflow_result['patch_directory'] = str(patch_dir)
            
            # 2. Create reservation tag
            reservation_tag = self.create_patch_reservation(patch_id)
            workflow_result['reservation_tag'] = reservation_tag.name
            
            # 3. Push to remote if configured
            try:
                if hasattr(self.repo, 'remotes') and self.repo.remotes:
                    # Push the tag to origin
                    self.repo.git.push('origin', reservation_tag.name)
                    workflow_result['pushed_to_remote'] = True
            except Exception as push_error:
                # Push failure is not fatal - tag is created locally
                workflow_result['push_error'] = str(push_error)
            
            return workflow_result
            
        except (GitTagManagerError, PatchReservationError):
            raise
        except Exception as e:
            raise GitTagManagerError(f"Workflow failed for patch '{patch_id}': {e}")

    def get_all_remote_branches(self) -> List[str]:
        """
        Get list of all remote branch names.
        
        Returns:
            List[str]: Remote branch names (e.g., ["origin/main", "origin/ho-dev/1.3.x"])
            
        Raises:
            GitTagManagerError: If Git operations fail
        """
        try:
            # Fetch latest remote state
            for remote in self.repo.remotes:
                remote.fetch()
            
            remote_branches = []
            for remote in self.repo.remotes:
                for ref in remote.refs:
                    remote_branches.append(ref.name)
            
            return remote_branches
            
        except Exception as e:
            raise GitTagManagerError(f"Failed to get remote branches: {e}")