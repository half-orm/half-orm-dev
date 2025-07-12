#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SchemaPatches module for halfORM Git-centric workflow

This module provides intelligent SQL patch management with temporary keys (temp1, temp2, etc.)
during development phase and business-priority-driven finalization to sequential patch numbers.

Key Features:
- Temporary key management (temp1, temp2, temp3...) for parallel development
- Content-preserving finalization (tempX → patch N with identical SQL content)
- Git-aware version assignment with automatic tag creation
- Multiple patches per version support
- External patch compatibility (handles gaps from manual releases)
- JSON-based sequence tracking (ho_dev_schema vs ho_schema files)

Main Classes:
- SchemaPatches: Main orchestrator for patch management
- TemporaryKey: Temporary key management (temp1, temp2, ...)
- PatchEntry: JSON sequence file entries
- PatchDirectory: Physical patch directory management
- SequenceFile: JSON file operations
- GitTagManager: Git tag integration

Exception Hierarchy:
- SchemaPatchesError: Base exception
- TemporaryKeyError: Temporary key issues
- FinalizationError: Patch finalization failures
- PatchValidationError: Patch content validation
- GitIntegrationError: Git operations failures
- SequenceFileError: JSON file operations

Usage:
    >>> from half_orm_dev.schema_patches import SchemaPatches
    >>> schema_patches = SchemaPatches("1.3.x")
    >>> schema_patches.add_patch("temp1", "456-performance")
    >>> patch_number = schema_patches.finalize_patch("temp1")  # temp1 → 6 + v1.3.6
"""

# Core classes
from .schema_patches import SchemaPatches
from .temporary_key import TemporaryKey
from .patch_entry import PatchEntry
from .patch_directory import PatchDirectory
from .sequence_file import SequenceFile
from .git_tag_manager import GitTagManager

# Exceptions
from .exceptions import (
    SchemaPatchesError,
    TemporaryKeyError,
    FinalizationError,
    PatchValidationError,
    GitIntegrationError,
    SequenceFileError,
    validate_temporary_key_format,
    validate_patch_id_format,
    validate_version_line_format,
)

# Version info
__version__ = "0.1.0-dev"
__author__ = "halfORM Development Team"
__email__ = "dev@halfORM.org"

# Public API
__all__ = [
    # Main classes
    "SchemaPatches",
    "TemporaryKey", 
    "PatchEntry",
    "PatchDirectory",
    "SequenceFile",
    "GitTagManager",
    
    # Exceptions
    "SchemaPatchesError",
    "TemporaryKeyError",
    "FinalizationError", 
    "PatchValidationError",
    "GitIntegrationError",
    "SequenceFileError",
    
    # Utilities
    "validate_temporary_key_format",
    "validate_patch_id_format", 
    "validate_version_line_format",
]

# Module-level configuration
DEFAULT_SCHEMA_PATCHES_DIR = "SchemaPatches"
DEFAULT_DEV_SEQUENCE_FILE_PATTERN = "ho_dev_schema_patches_sequence_{version}.json"
DEFAULT_PROD_SEQUENCE_FILE_PATTERN = "ho_schema_patches_sequence_{version}.json"

# Convenience functions for common operations
def create_schema_patches(version_line: str, base_dir=None, repo_path=None) -> SchemaPatches:
    """
    Convenience function to create SchemaPatches instance.
    
    Args:
        version_line (str): Version line (e.g., "1.3.x")
        base_dir (Path, optional): Base directory for patches
        repo_path (Path, optional): Git repository path
        
    Returns:
        SchemaPatches: Configured SchemaPatches instance
        
    Example:
        >>> schema_patches = create_schema_patches("1.3.x")
        >>> schema_patches.add_patch("temp1", "456-performance")
    """
    return SchemaPatches(version_line, base_dir, repo_path)


def validate_temp_key(key: str) -> bool:
    """
    Validate temporary key format.
    
    Args:
        key (str): Temporary key to validate
        
    Returns:
        bool: True if valid, False otherwise
        
    Example:
        >>> validate_temp_key("temp1")  # True
        >>> validate_temp_key("invalid")  # False
    """
    try:
        validate_temporary_key_format(key)
        return True
    except TemporaryKeyError:
        return False


def parse_temp_key(key_input) -> TemporaryKey:
    """
    Parse temporary key from various input formats.
    
    Args:
        key_input: String key or integer number
        
    Returns:
        TemporaryKey: Parsed temporary key
        
    Example:
        >>> parse_temp_key("temp1")  # TemporaryKey("temp1")
        >>> parse_temp_key(1)        # TemporaryKey("temp1")
    """
    return TemporaryKey.parse(key_input)
