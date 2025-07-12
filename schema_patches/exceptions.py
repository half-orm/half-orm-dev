#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SchemaPatches Exception Hierarchy

Custom exceptions for the SchemaPatches module providing specific error handling
for different failure modes in the Git-centric patch management workflow.

Exception Hierarchy:
    SchemaPatchesError (base)
    ├── TemporaryKeyError (temporary key format/operations)
    ├── FinalizationError (patch finalization failures)
    ├── PatchValidationError (patch content validation)
    ├── GitIntegrationError (Git operations failures)
    └── SequenceFileError (JSON file operations)

Usage:
    >>> try:
    ...     schema_patches.add_patch("invalid-key", "456-performance")
    ... except TemporaryKeyError as e:
    ...     print(f"Invalid temporary key: {e}")
"""


class SchemaPatchesError(Exception):
    """
    Base exception for all SchemaPatches operations.
    
    Provides common functionality for all schema patches related errors
    including error codes and context information.
    
    Attributes:
        message (str): Human-readable error message
        context (dict): Additional context information
        error_code (str): Specific error code for programmatic handling
    """
    
    def __init__(self, message: str, context: dict = None, error_code: str = None):
        """
        Initialize SchemaPatches base exception.
        
        Args:
            message (str): Error message
            context (dict): Additional context information
            error_code (str): Specific error code
        """
        super().__init__(message)
        self.message = message
        self.context = context or {}
        self.error_code = error_code or "SCHEMA_PATCHES_ERROR"
    
    def __str__(self) -> str:
        """String representation with context if available."""
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            return f"{self.message} (context: {context_str})"
        return self.message


class TemporaryKeyError(SchemaPatchesError):
    """
    Exception raised when temporary key format or operations are invalid.
    
    Covers scenarios like:
    - Invalid tempX format (temp0, tempX, invalid-key)
    - Duplicate temporary keys
    - Non-existent temporary keys in operations
    - Temporary key range issues
    
    Examples:
        >>> raise TemporaryKeyError("Invalid temporary key format: 'temp0'")
        >>> raise TemporaryKeyError("Temporary key already exists", 
        ...                        context={"temp_key": "temp1"})
    """
    
    def __init__(self, message: str, temp_key: str = None, **kwargs):
        """
        Initialize TemporaryKeyError with optional temp_key context.
        
        Args:
            message (str): Error message
            temp_key (str): The problematic temporary key
            **kwargs: Additional context
        """
        context = kwargs.get('context', {})
        if temp_key:
            context['temp_key'] = temp_key
        
        super().__init__(
            message=message,
            context=context,
            error_code=kwargs.get('error_code', 'TEMPORARY_KEY_ERROR')
        )


class FinalizationError(SchemaPatchesError):
    """
    Exception raised when patch finalization fails.
    
    Covers scenarios like:
    - Patches already finalized
    - Git tag creation failures during finalization
    - Sequence file update failures
    - Missing patch directories during finalization
    - Business logic violations in finalization order
    
    Examples:
        >>> raise FinalizationError("Patch already finalized", 
        ...                        context={"temp_key": "temp1", "patch_number": 5})
        >>> raise FinalizationError("Cannot finalize: Git tag already exists")
    """
    
    def __init__(self, message: str, temp_key: str = None, patch_number: int = None, **kwargs):
        """
        Initialize FinalizationError with finalization context.
        
        Args:
            message (str): Error message
            temp_key (str): Temporary key being finalized
            patch_number (int): Target patch number
            **kwargs: Additional context
        """
        context = kwargs.get('context', {})
        if temp_key:
            context['temp_key'] = temp_key
        if patch_number:
            context['patch_number'] = patch_number
        
        super().__init__(
            message=message,
            context=context,
            error_code=kwargs.get('error_code', 'FINALIZATION_ERROR')
        )


class PatchValidationError(SchemaPatchesError):
    """
    Exception raised when patch content validation fails.
    
    Covers scenarios like:
    - Invalid SQL syntax in patch files
    - Missing patch directories
    - Invalid patch directory structure
    - Dangerous SQL operations detection
    - Patch dependency violations
    - Invalid patch_id format
    
    Examples:
        >>> raise PatchValidationError("SQL syntax error in patch file",
        ...                           context={"patch_id": "456-performance", 
        ...                                   "file": "01_create_indexes.sql"})
        >>> raise PatchValidationError("Patch directory not found")
    """
    
    def __init__(self, message: str, patch_id: str = None, file_path: str = None, **kwargs):
        """
        Initialize PatchValidationError with validation context.
        
        Args:
            message (str): Error message
            patch_id (str): Patch identifier being validated
            file_path (str): Specific file that failed validation
            **kwargs: Additional context
        """
        context = kwargs.get('context', {})
        if patch_id:
            context['patch_id'] = patch_id
        if file_path:
            context['file_path'] = file_path
        
        super().__init__(
            message=message,
            context=context,
            error_code=kwargs.get('error_code', 'PATCH_VALIDATION_ERROR')
        )


class GitIntegrationError(SchemaPatchesError):
    """
    Exception raised when Git operations fail.
    
    Covers scenarios like:
    - Git repository not found or inaccessible
    - Git tag creation failures
    - Git tag query failures
    - Branch operation failures
    - Git command execution errors
    - Invalid Git repository state
    
    Examples:
        >>> raise GitIntegrationError("Failed to create Git tag",
        ...                          context={"tag_name": "v1.3.6", "git_error": "tag already exists"})
        >>> raise GitIntegrationError("Git repository not found")
    """
    
    def __init__(self, message: str, git_operation: str = None, git_error: str = None, **kwargs):
        """
        Initialize GitIntegrationError with Git operation context.
        
        Args:
            message (str): Error message
            git_operation (str): Git operation that failed (tag, branch, etc.)
            git_error (str): Underlying Git error message
            **kwargs: Additional context
        """
        context = kwargs.get('context', {})
        if git_operation:
            context['git_operation'] = git_operation
        if git_error:
            context['git_error'] = git_error
        
        super().__init__(
            message=message,
            context=context,
            error_code=kwargs.get('error_code', 'GIT_INTEGRATION_ERROR')
        )


class SequenceFileError(SchemaPatchesError):
    """
    Exception raised when JSON sequence file operations fail.
    
    Covers scenarios like:
    - Invalid JSON format in sequence files
    - File read/write permission errors
    - Corrupted sequence file structure
    - Missing required fields in JSON
    - Sequence file version mismatches
    - Backup/restore operation failures
    
    Examples:
        >>> raise SequenceFileError("Invalid JSON format in sequence file",
        ...                        context={"file_path": "ho_dev_schema_patches_sequence_1.3.json"})
        >>> raise SequenceFileError("Cannot write to sequence file: permission denied")
    """
    
    def __init__(self, message: str, file_path: str = None, json_error: str = None, **kwargs):
        """
        Initialize SequenceFileError with file operation context.
        
        Args:
            message (str): Error message
            file_path (str): Path to problematic sequence file
            json_error (str): Underlying JSON parsing error
            **kwargs: Additional context
        """
        context = kwargs.get('context', {})
        if file_path:
            context['file_path'] = file_path
        if json_error:
            context['json_error'] = json_error
        
        super().__init__(
            message=message,
            context=context,
            error_code=kwargs.get('error_code', 'SEQUENCE_FILE_ERROR')
        )


# Exception utilities for common patterns
def validate_temporary_key_format(key: str) -> None:
    """
    Validate temporary key format and raise TemporaryKeyError if invalid.
    
    Args:
        key (str): Temporary key to validate
        
    Raises:
        TemporaryKeyError: If key format is invalid
        
    Example:
        >>> validate_temporary_key_format("temp1")  # OK
        >>> validate_temporary_key_format("invalid")  # Raises TemporaryKeyError
    """
    if not key or not isinstance(key, str):
        raise TemporaryKeyError(
            "Temporary key must be a non-empty string",
            temp_key=str(key) if key else None
        )
    
    if not key.startswith('temp'):
        raise TemporaryKeyError(
            f"Temporary key must start with 'temp': '{key}'",
            temp_key=key
        )
    
    number_part = key[4:]  # Remove 'temp' prefix
    if not number_part.isdigit():
        raise TemporaryKeyError(
            f"Temporary key must be tempX where X is a positive integer: '{key}'",
            temp_key=key
        )
    
    if int(number_part) <= 0:
        raise TemporaryKeyError(
            f"Temporary key number must be positive: '{key}'",
            temp_key=key
        )


def validate_patch_id_format(patch_id: str) -> None:
    """
    Validate patch ID format and raise PatchValidationError if invalid.
    
    Args:
        patch_id (str): Patch ID to validate
        
    Raises:
        PatchValidationError: If patch_id format is invalid
        
    Example:
        >>> validate_patch_id_format("456-performance")  # OK
        >>> validate_patch_id_format("invalid format")  # Raises PatchValidationError
    """
    if not patch_id or not isinstance(patch_id, str):
        raise PatchValidationError(
            "Patch ID must be a non-empty string",
            patch_id=str(patch_id) if patch_id else None
        )
    
    # Basic format validation: should contain alphanumeric, hyphens, underscores
    if not re.match(r'^[a-zA-Z0-9_-]+$', patch_id):
        raise PatchValidationError(
            f"Patch ID contains invalid characters: '{patch_id}'",
            patch_id=patch_id
        )
    
    # Should not start or end with hyphen/underscore
    if patch_id.startswith(('-', '_')) or patch_id.endswith(('-', '_')):
        raise PatchValidationError(
            f"Patch ID cannot start or end with hyphen/underscore: '{patch_id}'",
            patch_id=patch_id
        )


def validate_version_line_format(version_line: str) -> None:
    """
    Validate version line format and raise SchemaPatchesError if invalid.
    
    Args:
        version_line (str): Version line to validate (e.g., "1.3.x")
        
    Raises:
        SchemaPatchesError: If version_line format is invalid
        
    Example:
        >>> validate_version_line_format("1.3.x")  # OK
        >>> validate_version_line_format("invalid")  # Raises SchemaPatchesError
    """
    if not version_line or not isinstance(version_line, str):
        raise SchemaPatchesError(
            "Version line must be a non-empty string",
            context={"version_line": str(version_line) if version_line else None}
        )
    
    # Format: X.Y.x where X and Y are positive integers
    pattern = r'^\d+\.\d+\.x$'
    if not re.match(pattern, version_line):
        raise SchemaPatchesError(
            f"Version line must follow X.Y.x format: '{version_line}'",
            context={"version_line": version_line}
        )


# Import guard to prevent circular imports
import re
