#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PatchDirectory module for halfORM Git-centric SchemaPatches workflow

Handles the application of SchemaPatches directories with SQL and Python files
in lexicographic order. Integrates with GitTagManager for complete workflow.

Key Features:
- Application of SchemaPatches/XXX-name/ directories
- Lexicographic execution order (00_, 01_, 02_...)
- SQL execution with halfORM integration
- Python script execution with proper environment
- Validation of directory structure and file formats
- Rollback capabilities on errors
- Integration with GitTagManager workflow

Usage:
    >>> patch_dir = PatchDirectory("456-performance", hgit_instance)
    >>> patch_dir.validate_structure()
    >>> patch_dir.apply_all_files()
"""

import re
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass

# halfORM imports (will be available in the real environment)
try:
    from half_orm.model import Model
    from half_orm import utils
except ImportError:
    # Mock for development/testing
    class Model:
        pass
    class utils:
        @staticmethod
        def error(msg, exit_code=1):
            raise RuntimeError(msg)

from .exceptions import (
    PatchValidationError,
    SchemaPatchesError
)


@dataclass
class PatchFile:
    """
    Represents a single patch file within a SchemaPatches directory.
    
    Attributes:
        name (str): File name (e.g., "01_create_table.sql")
        path (Path): Full path to the file
        extension (str): File extension ("sql" or "py")
        sequence (int): Execution sequence number from filename prefix
        content (str): File content (loaded on demand)
    """
    name: str
    path: Path
    extension: str
    sequence: int
    content: Optional[str] = None
    
    def load_content(self) -> str:
        """
        Load file content from disk.
        
        Returns:
            str: File content as string
            
        Raises:
            PatchValidationError: If file cannot be read
        """
        pass
    
    def validate_syntax(self) -> bool:
        """
        Validate syntax of the patch file.
        
        For SQL files: Basic SQL syntax validation
        For Python files: AST compilation check
        
        Returns:
            bool: True if syntax is valid
            
        Raises:
            PatchValidationError: If syntax validation fails
        """
        pass
    
    def __lt__(self, other: 'PatchFile') -> bool:
        """Enable sorting by sequence number."""
        pass


class PatchDirectory:
    """
    Manages application of a single SchemaPatches directory.
    
    Handles validation, execution order, SQL/Python execution, and rollback
    for a single patch directory (e.g., SchemaPatches/456-performance/).
    
    Args:
        patch_id (str): Patch identifier (e.g., "456-performance")
        hgit_instance: HGit instance from halfORM repo
        base_dir (Optional[Path]): Base directory containing SchemaPatches
        
    Example:
        >>> patch_dir = PatchDirectory("456-performance", repo.hgit)
        >>> patch_dir.validate_structure()
        >>> if patch_dir.is_applicable():
        >>>     patch_dir.apply_all_files()
    """
    
    def __init__(self, patch_id: str, hgit_instance, base_dir: Optional[Path] = None):
        """
        Initialize PatchDirectory for a specific patch.
        
        Args:
            patch_id (str): Patch directory identifier (e.g., "456-performance")
            hgit_instance: HGit instance with Git repo and halfORM model
            base_dir (Optional[Path]): Custom base directory (defaults to repo base)
            
        Raises:
            PatchValidationError: If patch_id format is invalid
            SchemaPatchesError: If hgit_instance is invalid
        """
        # Validate patch_id
        if not patch_id or not isinstance(patch_id, str):
            raise PatchValidationError("Patch ID must be a non-empty string")
        
        # Remove whitespace and validate format
        patch_id = patch_id.strip()
        if not patch_id:
            raise PatchValidationError("Patch ID cannot be empty or whitespace only")
        
        # Check for path traversal attempts
        if '..' in patch_id or patch_id.startswith('/') or patch_id.startswith('\\'):
            raise PatchValidationError(f"Invalid patch ID format (path traversal attempt): '{patch_id}'")
        
        # Check for invalid characters (spaces, special chars that could cause issues)
        if ' ' in patch_id:
            raise PatchValidationError(f"Patch ID cannot contain spaces: '{patch_id}'")
        
        # Basic format validation - should be like "456-performance", "123-security", etc.
        if not re.match(r'^[a-zA-Z0-9_-]+$', patch_id):
            raise PatchValidationError(f"Patch ID contains invalid characters: '{patch_id}'")
        
        # Validate hgit_instance
        if hgit_instance is None:
            raise SchemaPatchesError("HGit instance cannot be None")
        
        # Check that hgit_instance has required attributes
        if not hasattr(hgit_instance, '_HGit__repo'):
            raise SchemaPatchesError("Invalid HGit instance: missing _HGit__repo attribute")
        
        if not hasattr(hgit_instance._HGit__repo, 'base_dir'):
            raise SchemaPatchesError("Invalid HGit instance: missing base_dir attribute")
        
        if not hasattr(hgit_instance._HGit__repo, 'model'):
            raise SchemaPatchesError("Invalid HGit instance: missing model attribute")
        
        # Store core attributes
        self._patch_id = patch_id
        self._hgit_instance = hgit_instance
        
        # Set base directory - use custom or default from repo
        if base_dir is not None:
            self._base_dir = Path(base_dir).resolve()
        else:
            self._base_dir = Path(hgit_instance._HGit__repo.base_dir).resolve()
        
        # Set up patch directory path
        self._patch_directory = self._base_dir / "SchemaPatches" / patch_id
        
        # Initialize execution state
        self._files_cache = None  # Cache for scanned files
        self._last_execution_result = None  # Last execution results
        self._rollback_points = []  # Stack of rollback points
        self._execution_summary = {
            'files_executed': 0,
            'total_time': 0,
            'success_rate': 0.0,
            'last_execution': None
        }
    
    def validate_structure(self) -> bool:
        """
        Validate the patch directory structure and files.
        
        Checks:
        - Directory exists and is readable
        - Contains at least one .sql or .py file
        - All files follow naming convention (NN_description.ext)
        - No duplicate sequence numbers
        - All files have valid syntax
        
        Returns:
            bool: True if structure is valid
            
        Raises:
            PatchValidationError: If validation fails with detailed error info
            
        Example:
            >>> patch_dir.validate_structure()  # True
            >>> # Validates SchemaPatches/456-performance/ structure
        """
        pass
    
    def scan_files(self) -> List[PatchFile]:
        """
        Scan and parse all patch files in the directory.
        
        Discovers all .sql and .py files, extracts sequence numbers from
        filenames, and returns them in execution order.
        
        Returns:
            List[PatchFile]: Ordered list of patch files by sequence
            
        Raises:
            PatchValidationError: If file naming convention is violated
            
        Example:
            >>> files = patch_dir.scan_files()
            >>> files[0].name  # "00_prerequisites.sql"
            >>> files[1].name  # "01_create_tables.sql"
            >>> files[2].name  # "02_populate_data.py"
        """
        pass
    
    def get_execution_order(self) -> List[PatchFile]:
        """
        Get files in lexicographic execution order.
        
        Returns files sorted by sequence number extracted from filename prefix.
        Files with same sequence number are sorted alphabetically by name.
        
        Returns:
            List[PatchFile]: Files ordered for execution
            
        Example:
            >>> order = patch_dir.get_execution_order()
            >>> [f.name for f in order]
            ['00_prerequisites.sql', '01_create_tables.sql', '02_populate_data.py']
        """
        pass
    
    def is_applicable(self) -> bool:
        """
        Check if patch directory can be applied to current database state.
        
        Validates:
        - Database connection is available
        - Required database objects exist (if specified)
        - No conflicting database state
        - All dependencies are satisfied
        
        Returns:
            bool: True if patch can be safely applied
            
        Example:
            >>> if patch_dir.is_applicable():
            >>>     patch_dir.apply_all_files()
            >>> else:
            >>>     print("Patch cannot be applied to current database state")
        """
        pass
    
    def apply_all_files(self) -> Dict[str, Any]:
        """
        Apply all patch files in the correct execution order.
        
        Executes SQL files using halfORM model connection and Python files
        using subprocess in the repository environment. Maintains transaction
        consistency and provides rollback on any failure.
        
        Returns:
            Dict[str, Any]: Execution results with success/failure details
            
        Raises:
            SchemaPatchesError: If any file execution fails
            
        Example:
            >>> result = patch_dir.apply_all_files()
            >>> result['success']  # True
            >>> result['files_applied']  # ['00_prerequisites.sql', '01_create_tables.sql']
            >>> result['execution_time']  # 2.34 seconds
        """
        pass
    
    def apply_single_file(self, patch_file: PatchFile) -> Dict[str, Any]:
        """
        Apply a single patch file (SQL or Python).
        
        Executes the file with appropriate interpreter and environment.
        For SQL files, uses halfORM model connection.
        For Python files, uses subprocess with repository context.
        
        Args:
            patch_file (PatchFile): File to execute
            
        Returns:
            Dict[str, Any]: Execution results and metrics
            
        Raises:
            SchemaPatchesError: If file execution fails
            
        Example:
            >>> file = PatchFile("01_create_table.sql", path, "sql", 1)
            >>> result = patch_dir.apply_single_file(file)
            >>> result['success']  # True
            >>> result['affected_rows']  # 0 (for DDL)
        """
        pass
    
    def execute_sql_file(self, patch_file: PatchFile) -> Dict[str, Any]:
        """
        Execute a SQL patch file using halfORM model connection.
        
        Loads SQL content, validates syntax, and executes using the
        halfORM model's database connection with proper transaction handling.
        
        Args:
            patch_file (PatchFile): SQL file to execute
            
        Returns:
            Dict[str, Any]: SQL execution results
            
        Raises:
            SchemaPatchesError: If SQL execution fails
            
        Example:
            >>> sql_file = PatchFile("01_create_table.sql", path, "sql", 1)
            >>> result = patch_dir.execute_sql_file(sql_file)
            >>> result['affected_rows']  # Number of rows affected
            >>> result['execution_time']  # Time taken in seconds
        """
        pass
    
    def execute_python_file(self, patch_file: PatchFile) -> Dict[str, Any]:
        """
        Execute a Python patch file using subprocess.
        
        Runs Python script with proper environment (PYTHONPATH, etc.)
        and captures output, return code, and execution metrics.
        
        Args:
            patch_file (PatchFile): Python file to execute
            
        Returns:
            Dict[str, Any]: Python execution results
            
        Raises:
            SchemaPatchesError: If Python execution fails
            
        Example:
            >>> py_file = PatchFile("02_data_migration.py", path, "py", 2)
            >>> result = patch_dir.execute_python_file(py_file)
            >>> result['return_code']  # 0 for success
            >>> result['stdout']  # Script output
        """
        pass
    
    def validate_sql_syntax(self, sql_content: str) -> bool:
        """
        Validate SQL syntax without executing.
        
        Performs basic SQL syntax validation to catch obvious errors
        before execution. Uses SQL parsing or halfORM validation.
        
        Args:
            sql_content (str): SQL content to validate
            
        Returns:
            bool: True if syntax appears valid
            
        Raises:
            PatchValidationError: If syntax validation fails
            
        Example:
            >>> sql = "CREATE TABLE users (id SERIAL PRIMARY KEY);"
            >>> patch_dir.validate_sql_syntax(sql)  # True
        """
        pass
    
    def validate_python_syntax(self, python_content: str) -> bool:
        """
        Validate Python syntax without executing.
        
        Uses AST compilation to validate Python syntax and catch
        syntax errors before execution.
        
        Args:
            python_content (str): Python content to validate
            
        Returns:
            bool: True if syntax is valid
            
        Raises:
            PatchValidationError: If syntax validation fails
            
        Example:
            >>> python = "print('Hello from patch')"
            >>> patch_dir.validate_python_syntax(python)  # True
        """
        pass
    
    def get_dependencies(self) -> List[str]:
        """
        Extract and return patch dependencies.
        
        Analyzes patch files to determine dependencies on other patches,
        database objects, or external requirements.
        
        Returns:
            List[str]: List of dependency identifiers
            
        Example:
            >>> deps = patch_dir.get_dependencies()
            >>> deps  # ['123-security', 'users_table']
        """
        pass
    
    def create_rollback_point(self) -> str:
        """
        Create a rollback point before applying patches.
        
        Establishes a database savepoint or backup mechanism to enable
        rollback if patch application fails.
        
        Returns:
            str: Rollback point identifier
            
        Example:
            >>> rollback_id = patch_dir.create_rollback_point()
            >>> try:
            >>>     patch_dir.apply_all_files()
            >>> except Exception:
            >>>     patch_dir.rollback_to_point(rollback_id)
        """
        pass
    
    def rollback_to_point(self, rollback_point: str) -> bool:
        """
        Rollback database to a specific rollback point.
        
        Restores database state to the specified rollback point,
        undoing any changes made since that point.
        
        Args:
            rollback_point (str): Rollback point identifier
            
        Returns:
            bool: True if rollback successful
            
        Raises:
            SchemaPatchesError: If rollback fails
            
        Example:
            >>> rollback_id = patch_dir.create_rollback_point()
            >>> # ... apply patches ...
            >>> patch_dir.rollback_to_point(rollback_id)  # Undo changes
        """
        pass
    
    def rollback_all(self) -> bool:
        """
        Rollback all changes made by this patch application.
        
        Complete rollback of all database changes made by the current
        patch directory application.
        
        Returns:
            bool: True if rollback successful
            
        Raises:
            SchemaPatchesError: If rollback fails
            
        Example:
            >>> try:
            >>>     patch_dir.apply_all_files()
            >>> except Exception:
            >>>     patch_dir.rollback_all()  # Complete rollback
        """
        pass
    
    def get_patch_info(self) -> Dict[str, Any]:
        """
        Get comprehensive information about the patch directory.
        
        Returns:
            Dict[str, Any]: Patch metadata and statistics
            
        Example:
            >>> info = patch_dir.get_patch_info()
            >>> info['patch_id']  # "456-performance"
            >>> info['file_count']  # 3
            >>> info['sql_files']  # 2
            >>> info['python_files']  # 1
            >>> info['total_size']  # 1024 bytes
        """
        pass
    
    def get_execution_summary(self) -> Dict[str, Any]:
        """
        Get summary of the last execution attempt.
        
        Returns:
            Dict[str, Any]: Execution summary with metrics and results
            
        Example:
            >>> summary = patch_dir.get_execution_summary()
            >>> summary['files_executed']  # 3
            >>> summary['total_time']  # 5.67 seconds
            >>> summary['success_rate']  # 100.0
        """
        pass
    
    def cleanup_resources(self) -> None:
        """
        Clean up any resources used during patch application.
        
        Releases database connections, temporary files, rollback points,
        and other resources to prevent memory leaks.
        
        Example:
            >>> try:
            >>>     patch_dir.apply_all_files()
            >>> finally:
            >>>     patch_dir.cleanup_resources()
        """
        try:
            # Clear file cache
            if self._files_cache is not None:
                # Clear content from cached files to free memory
                for patch_file in self._files_cache:
                    if hasattr(patch_file, 'content') and patch_file.content is not None:
                        patch_file.content = None
                
                self._files_cache.clear()
                self._files_cache = None
            
            # Clear rollback points
            if self._rollback_points:
                # Note: In a real implementation, we would properly release
                # database savepoints here
                self._rollback_points.clear()
            
            # Clear execution results
            self._last_execution_result = None
            
            # Reset execution summary (but keep basic stats)
            if self._execution_summary:
                # Keep the historical data but clear temporary state
                self._execution_summary['last_execution'] = None
            
            # Note: We don't close the hgit_instance or database connections
            # as they are managed by the parent system and may be used elsewhere
            
        except Exception as e:
            # Cleanup should never fail catastrophically
            # Log the error but don't raise (in real implementation, use logging)
            pass  # In real implementation: logging.warning(f"Cleanup warning: {e}")
        
        # Always ensure some cleanup happened
        if not hasattr(self, '_cleanup_performed'):
            self._cleanup_performed = True
    
    def __str__(self) -> str:
        """
        String representation of the patch directory.
        
        Returns:
            str: Human-readable description
            
        Example:
            >>> str(patch_dir)
            "PatchDirectory(456-performance, 3 files, SchemaPatches/456-performance)"
        """
        try:
            # Try to get file count if possible
            if self._files_cache is not None:
                file_count = len(self._files_cache)
            else:
                # Try to scan files quickly without caching
                try:
                    files = self.scan_files()
                    file_count = len(files)
                except:
                    file_count = "unknown"
            
            return f"PatchDirectory({self._patch_id}, {file_count} files, {self._patch_directory.name})"
        except:
            # Fallback if anything fails
            return f"PatchDirectory({self._patch_id})"


    def __repr__(self) -> str:
        """
        Detailed representation for debugging.
        
        Returns:
            str: Detailed representation with all key attributes
        """
        try:
            # Get file count
            if self._files_cache is not None:
                file_count = len(self._files_cache)
            else:
                try:
                    files = self.scan_files()
                    file_count = len(files)
                except:
                    file_count = "unknown"
            
            # Get execution summary
            summary = self._execution_summary
            
            return (
                f"PatchDirectory("
                f"patch_id='{self._patch_id}', "
                f"files={file_count}, "
                f"directory='{self._patch_directory}', "
                f"executed={summary['files_executed']}, "
                f"success_rate={summary['success_rate']}%"
                f")"
            )
        except:
            # Fallback if anything fails
            return f"PatchDirectory(patch_id='{self._patch_id}', directory='{self._patch_directory}')"
    
    # Private helper methods
    
    def _extract_sequence_number(self, filename: str) -> int:
        """
        Extract sequence number from filename prefix.
        
        Args:
            filename (str): File name to parse
            
        Returns:
            int: Sequence number
            
        Raises:
            PatchValidationError: If filename format is invalid
        """
        if not filename or not isinstance(filename, str):
            raise PatchValidationError("Filename must be a non-empty string")
        
        # Remove extension to get name_without_ext
        name_parts = filename.rsplit('.', 1)
        if len(name_parts) != 2:
            raise PatchValidationError(f"Filename must have an extension: '{filename}'")
        
        name_without_ext, extension = name_parts
        
        # Validate extension
        if extension not in ['sql', 'py']:
            raise PatchValidationError(f"Invalid file extension '{extension}' in '{filename}'. Only .sql and .py are supported")
        
        # Extract sequence number using split('_', 1)
        if '_' not in name_without_ext:
            raise PatchValidationError(f"Filename must follow format 'seq_description.ext': '{filename}'")
        
        parts = name_without_ext.split('_', 1)
        if len(parts) != 2:
            raise PatchValidationError(f"Filename must follow format 'seq_description.ext': '{filename}'")
        
        seq_part, description_part = parts
        
        # Validate sequence part is numeric
        if not seq_part.isdigit():
            raise PatchValidationError(f"Sequence prefix must be numeric: '{seq_part}' in '{filename}'")
        
        # Validate description part is not empty
        if not description_part.strip():
            raise PatchValidationError(f"Description part cannot be empty: '{filename}'")
        
        # Convert to int
        sequence_number = int(seq_part)
        
        # Additional validation for reasonable range (0-999999)
        if sequence_number < 0 or sequence_number > 999999:
            raise PatchValidationError(f"Sequence number must be between 0 and 999999: '{sequence_number}' in '{filename}'")
        
        return sequence_number
    
    def _validate_filename_format(self, filename: str) -> bool:
        """
        Validate that filename follows naming convention.
        
        Args:
            filename (str): File name to validate
            
        Returns:
            bool: True if format is valid
        """
        if not filename or not isinstance(filename, str):
            return False
        
        try:
            # Try to extract sequence number - if it succeeds, format is valid
            self._extract_sequence_number(filename)
            
            # Additional format validations
            name_parts = filename.rsplit('.', 1)
            if len(name_parts) != 2:
                return False
            
            name_without_ext, extension = name_parts
            
            # Check for invalid characters in the filename
            # Allow alphanumeric, underscore, hyphen
            import re
            if not re.match(r'^[a-zA-Z0-9_-]+\.[a-zA-Z0-9]+$', filename):
                return False
            
            # Check that filename doesn't start with underscore
            if filename.startswith('_'):
                return False
            
            # Check for spaces (not allowed)
            if ' ' in filename:
                return False
            
            # Check for invalid special characters
            invalid_chars = ['@', '$', '%', '&', '*', '(', ')', '+', '=', '{', '}', '[', ']', '|', '\\', ':', ';', '"', "'", '<', '>', ',', '?', '/', '!']
            if any(char in filename for char in invalid_chars):
                return False
            
            # Check for double extensions (e.g., .py.sql)
            if filename.count('.') > 1:
                return False
            
            # Check for empty description (just underscore)
            parts = name_without_ext.split('_', 1)
            if len(parts) == 2 and not parts[1].strip():
                return False
            
            return True
            
        except PatchValidationError:
            return False
    
    def _setup_python_environment(self) -> Dict[str, str]:
        """
        Setup environment variables for Python execution.
        
        Returns:
            Dict[str, str]: Environment variables
        """
        pass
    
    def _parse_sql_statements(self, sql_content: str) -> List[str]:
        """
        Parse SQL content into individual statements.
        
        Args:
            sql_content (str): SQL content to parse
            
        Returns:
            List[str]: Individual SQL statements
        """
        pass
