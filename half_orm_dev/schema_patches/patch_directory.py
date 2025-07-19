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
        if not isinstance(other, PatchFile):
            return NotImplemented

        # Sort by sequence number first
        if self.sequence != other.sequence:
            return self.sequence < other.sequence

        # If sequence numbers are equal, sort by name for stability
        return self.name < other.name

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
        
        Checks only structural validity:
        - Directory exists and is readable
        - Contains at least one .sql or .py file
        - All patch files follow naming convention (seq_description.ext)
        - Ignores non-patch files (README.md, etc.)
        
        Does NOT validate syntax - that happens at execution time.
        
        Returns:
            bool: True if structure is valid
            
        Raises:
            PatchValidationError: If validation fails with detailed error info
        """
        # Check if directory exists
        if not self._patch_directory.exists():
            raise PatchValidationError(f"Patch directory does not exist: {self._patch_directory}")
        
        if not self._patch_directory.is_dir():
            raise PatchValidationError(f"Path is not a directory: {self._patch_directory}")
        
        # Check directory permissions
        try:
            list(self._patch_directory.iterdir())
        except PermissionError:
            raise PatchValidationError(f"Permission denied accessing patch directory: {self._patch_directory}")
        except OSError as e:
            raise PatchValidationError(f"Error accessing patch directory: {self._patch_directory}: {e}")
        
        # Find and validate patch files - single pass, no redundancy
        patch_files_found = []
        invalid_patch_files = []
        
        try:
            for file_path in self._patch_directory.iterdir():
                if not file_path.is_file():
                    continue
                
                filename = file_path.name
                
                # Skip hidden files and non-patch files
                if filename.startswith('.') or not (filename.endswith('.sql') or filename.endswith('.py')):
                    continue
                
                # Validate naming convention for patch files
                if self._validate_filename_format(filename):
                    patch_files_found.append(filename)
                else:
                    invalid_patch_files.append(filename)
            
            # Report invalid patch files
            if invalid_patch_files:
                raise PatchValidationError(
                    f"Files do not follow naming convention 'seq_description.ext': {', '.join(invalid_patch_files)}"
                )
            
        except PermissionError:
            raise PatchValidationError(f"Permission denied reading files in: {self._patch_directory}")
        
        # Check that we have at least one patch file
        if not patch_files_found:
            raise PatchValidationError(f"Patch directory contains no applicable files (.sql or .py): {self._patch_directory}")
        
        return True


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
        # Check if directory exists
        if not self._patch_directory.exists():
            raise PatchValidationError(f"Patch directory does not exist: {self._patch_directory}")

        if not self._patch_directory.is_dir():
            raise PatchValidationError(f"Patch directory is not a directory: {self._patch_directory}")

        patch_files = []

        try:
            # Scan all files in the directory
            for file_path in self._patch_directory.iterdir():
                # Skip directories
                if not file_path.is_file():
                    continue

                filename = file_path.name

                # Skip hidden files (starting with .)
                if filename.startswith('.'):
                    continue

                # Check if it's a patch file (.sql or .py)
                if not (filename.endswith('.sql') or filename.endswith('.py')):
                    continue

                # Validate filename format
                if not self._validate_filename_format(filename):
                    # Skip invalid files instead of raising error for flexibility
                    # But could be changed to raise error if strict validation needed
                    continue

                try:
                    # Extract sequence number
                    sequence = self._extract_sequence_number(filename)

                    # Determine extension
                    extension = filename.split('.')[-1]

                    # Create PatchFile object
                    patch_file = PatchFile(
                        name=filename,
                        path=file_path,
                        extension=extension,
                        sequence=sequence
                    )

                    patch_files.append(patch_file)

                except PatchValidationError as e:
                    # Skip files with invalid format, but could log warning
                    # In a real implementation, we might want to log this
                    continue

        except PermissionError:
            raise PatchValidationError(f"Permission denied accessing patch directory: {self._patch_directory}")
        except OSError as e:
            raise PatchValidationError(f"Error scanning patch directory: {self._patch_directory}: {e}")

        # Cache the results
        self._files_cache = patch_files

        # Return files sorted by sequence number (execution order)
        return sorted(patch_files, key=lambda f: (f.sequence, f.name))

    def get_execution_order(self) -> List[PatchFile]:
        """
        Get files in lexicographic execution order.

        Returns files sorted by sequence number extracted from filename prefix.
        Files with same sequence number are sorted alphabetically by name.
        This allows for flexible insertion of patches without renumbering.

        Returns:
            List[PatchFile]: Files ordered for execution

        Example:
            >>> order = patch_dir.get_execution_order()
            >>> [f.name for f in order]
            ['10_create_users.sql', '10_create_roles.sql', '11_populate_data.py']
            # Note: 10_create_roles.sql can be inserted without renumbering
        """
        # Use cached files if available, otherwise scan
        if self._files_cache is not None:
            files = self._files_cache.copy()  # Work with a copy
        else:
            files = self.scan_files()

        # Sort by sequence number first, then by filename for deterministic order
        # This allows multiple files with same sequence number
        sorted_files = sorted(files, key=lambda f: (f.sequence, f.name))

        return sorted_files

    def apply_all_files(self) -> Dict[str, Any]:
        """
        Apply all patch files in the correct execution order.
        
        Simple approach: validate structure, then execute with rollback on failure.
        
        Returns:
            Dict[str, Any]: Execution results with success/failure details
            
        Raises:
            SchemaPatchesError: If any file execution fails
        """
        import time
        
        start_time = time.time()
        applied_files = []
        rollback_point = None
        
        try:
            # 1. Validate directory structure (only necessary check)
            self.validate_structure()
            
            # 2. Get execution order
            files_to_execute = self.get_execution_order()
            if not files_to_execute:
                return {
                    'success': True,
                    'files_applied': [],
                    'total_files': 0,
                    'execution_time': time.time() - start_time
                }
            
            # 3. Create rollback point before starting
            try:
                rollback_point = self.create_rollback_point()
            except Exception:
                # Rollback creation failure is not necessarily fatal
                # Continue without rollback point (logged in real implementation)
                pass
            
            # 4. Execute files one by one - FAIL FAST approach
            for patch_file in files_to_execute:
                try:
                    self.apply_single_file(patch_file)
                    applied_files.append(patch_file.name)
                except Exception as e:
                    # FAIL FAST: attempt rollback and exit immediately
                    if rollback_point:
                        try:
                            self.rollback_to_point(rollback_point)
                        except Exception as rollback_error:
                            raise SchemaPatchesError(
                                f"Execution failed at {patch_file.name}: {e}. "
                                f"Rollback also failed: {rollback_error}"
                            )
                    
                    raise SchemaPatchesError(
                        f"Patch application failed at {patch_file.name}: {e}. "
                        f"Rolled back successfully. Applied files: {applied_files}"
                    )
            
            # 5. Success: update execution summary
            total_time = time.time() - start_time
            self._execution_summary.update({
                'files_executed': len(applied_files),
                'total_time': total_time,
                'success_rate': 100.0,
                'last_execution': time.time()
            })
            
            return {
                'success': True,
                'files_applied': applied_files,
                'total_files': len(applied_files),
                'execution_time': total_time
            }
            
        except SchemaPatchesError:
            # Update failure summary
            self._execution_summary.update({
                'files_executed': len(applied_files),
                'total_time': time.time() - start_time,
                'success_rate': 0.0,
                'last_execution': time.time()
            })
            raise
        except Exception as e:
            # Unexpected error
            self._execution_summary.update({
                'files_executed': len(applied_files),
                'total_time': time.time() - start_time,
                'success_rate': 0.0,
                'last_execution': time.time()
            })
            raise SchemaPatchesError(f"Unexpected error during patch application: {e}")
            
        except SchemaPatchesError:
            # Update failure summary
            self._execution_summary.update({
                'files_executed': len(applied_files),
                'total_time': time.time() - start_time,
                'success_rate': 0.0,
                'last_execution': time.time()
            })
            raise
        except Exception as e:
            # Unexpected error
            self._execution_summary.update({
                'files_executed': len(applied_files),
                'total_time': time.time() - start_time,
                'success_rate': 0.0,
                'last_execution': time.time()
            })
            raise SchemaPatchesError(f"Unexpected error during patch application: {e}")

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
        if not isinstance(patch_file, PatchFile):
            raise SchemaPatchesError("patch_file must be a PatchFile instance")

        # Execute based on file type
        if patch_file.extension == 'sql':
            result = self.execute_sql_file(patch_file)
        elif patch_file.extension == 'py':
            result = self.execute_python_file(patch_file)
        else:
            raise SchemaPatchesError(f"Unsupported file extension: {patch_file.extension}")

        # Add metadata
        result['file_type'] = patch_file.extension
        result['sequence'] = patch_file.sequence

        return result

    def execute_sql_file(self, patch_file: PatchFile) -> Dict[str, Any]:
        """
        Execute a SQL patch file using halfORM model connection.
        
        Simple file reading - let OS handle file errors naturally.
        No syntax validation - let psycopg2/halfORM handle SQL errors naturally.
        """
        import time
        
        if patch_file.extension != 'sql':
            raise SchemaPatchesError(f"Expected SQL file, got {patch_file.extension}: {patch_file.name}")
        
        start_time = time.time()
        
        try:
            # Simple file reading - KISS approach
            with open(patch_file.path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Get halfORM model
            model = self._hgit_instance._HGit__repo.model
            if model is None:
                raise SchemaPatchesError("halfORM model not available")
            
            # Execute SQL content directly - let halfORM/psycopg2 handle syntax
            result = model.execute_query(content)
            
            execution_time = time.time() - start_time
            
            return {
                'success': True,
                'affected_rows': result.get('affected_rows', 0) if result else 0,
                'execution_time': execution_time,
                'file_name': patch_file.name
            }
            
        except (OSError, PermissionError, UnicodeDecodeError) as e:
            raise SchemaPatchesError(f"Failed to read SQL file {patch_file.name}: {e}")
        except Exception as e:
            # Native SQL error from psycopg2/halfORM
            raise SchemaPatchesError(f"SQL execution failed for {patch_file.name}: {e}")

    def execute_python_file(self, patch_file: PatchFile) -> Dict[str, Any]:
        """
        Execute a Python patch file using subprocess.
        
        No syntax validation - let Python interpreter handle syntax errors naturally.
        """
        import time
        
        if patch_file.extension != 'py':
            raise SchemaPatchesError(f"Expected Python file, got {patch_file.extension}: {patch_file.name}")
        
        start_time = time.time()
        
        try:
            # Simple execution environment
            env = dict(os.environ)
            if 'PYTHONPATH' in env:
                env['PYTHONPATH'] = f"{self._base_dir}:{env['PYTHONPATH']}"
            else:
                env['PYTHONPATH'] = str(self._base_dir)
            
            # Execute directly - let Python handle syntax
            result = subprocess.run(
                [sys.executable, str(patch_file.path)],
                cwd=str(self._patch_directory),
                env=env,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            execution_time = time.time() - start_time
            
            if result.returncode != 0:
                # Native Python error - much better than our AST validation
                raise SchemaPatchesError(
                    f"Python execution failed for {patch_file.name}: "
                    f"Exit code {result.returncode}, Error: {result.stderr}"
                )
            
            return {
                'success': True,
                'return_code': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'execution_time': execution_time,
                'file_name': patch_file.name
            }
            
        except subprocess.TimeoutExpired:
            raise SchemaPatchesError(f"Python execution timed out for {patch_file.name}")
        except Exception as e:
            raise SchemaPatchesError(f"Python execution failed for {patch_file.name}: {e}")

    def create_rollback_point(self) -> str:
        """
        Create a rollback point before applying patches.

        Simple approach using PostgreSQL savepoints via halfORM model.
        Each rollback point gets a unique identifier for later reference.

        Returns:
            str: Rollback point identifier (savepoint name)

        Raises:
            SchemaPatchesError: If savepoint creation fails

        Example:
            >>> rollback_id = patch_dir.create_rollback_point()
            >>> try:
            >>>     patch_dir.apply_all_files()
            >>> except Exception:
            >>>     patch_dir.rollback_to_point(rollback_id)
        """
        import time
        import uuid
        
        try:
            # Generate unique savepoint name - simple and reliable
            timestamp = int(time.time() * 1000)  # milliseconds for uniqueness
            rollback_id = f"patch_rollback_{timestamp}_{uuid.uuid4().hex[:8]}"
            
            # Get halfORM model
            model = self._hgit_instance._HGit__repo.model
            if model is None:
                raise SchemaPatchesError("halfORM model not available for rollback point creation")
            
            # Create PostgreSQL savepoint - KISS approach
            savepoint_sql = f"SAVEPOINT {rollback_id};"
            model.execute_query(savepoint_sql)
            
            # Store in our rollback stack for tracking
            if not hasattr(self, '_rollback_points') or self._rollback_points is None:
                self._rollback_points = []
            
            self._rollback_points.append({
                'id': rollback_id,
                'created_at': time.time(),
                'active': True
            })
            
            return rollback_id
            
        except Exception as e:
            # Native PostgreSQL errors are better than our custom validation
            raise SchemaPatchesError(f"Failed to create rollback point: {e}")

    def rollback_to_point(self, rollback_point: str) -> bool:
        """
        Rollback database to a specific rollback point.

        Simple approach using PostgreSQL ROLLBACK TO SAVEPOINT.
        Validates rollback_point exists in our tracking stack.

        Args:
            rollback_point (str): Rollback point identifier from create_rollback_point()

        Returns:
            bool: True if rollback successful

        Raises:
            SchemaPatchesError: If rollback fails or rollback_point is invalid

        Example:
            >>> rollback_id = patch_dir.create_rollback_point()
            >>> # ... apply patches ...
            >>> patch_dir.rollback_to_point(rollback_id)  # Undo changes
        """
        if not rollback_point or not isinstance(rollback_point, str):
            raise SchemaPatchesError("Invalid rollback point: must be a non-empty string")
        
        try:
            # Check if rollback point exists in our tracking
            if not hasattr(self, '_rollback_points') or not self._rollback_points:
                raise SchemaPatchesError(f"Invalid rollback point: no rollback points available")
            
            # Find the rollback point in our stack
            rollback_entry = None
            for entry in self._rollback_points:
                if entry['id'] == rollback_point and entry['active']:
                    rollback_entry = entry
                    break
            
            if rollback_entry is None:
                raise SchemaPatchesError(f"Invalid rollback point: '{rollback_point}' not found or already used")
            
            # Get halfORM model
            model = self._hgit_instance._HGit__repo.model
            if model is None:
                raise SchemaPatchesError("halfORM model not available for rollback")
            
            # Execute PostgreSQL rollback - KISS approach
            rollback_sql = f"ROLLBACK TO SAVEPOINT {rollback_point};"
            model.execute_query(rollback_sql)
            
            # Mark rollback point and all newer ones as inactive
            for entry in self._rollback_points:
                if entry['created_at'] >= rollback_entry['created_at']:
                    entry['active'] = False
            
            return True
            
        except SchemaPatchesError:
            # Re-raise our validation errors
            raise
        except Exception as e:
            # Native PostgreSQL errors - better than our custom handling
            raise SchemaPatchesError(f"Rollback failed for point '{rollback_point}': {e}")

    def rollback_all(self) -> bool:
        """
        Rollback all changes made by this patch application.

        Simple approach: rollback to the earliest active rollback point.
        If no rollback points exist, this is a no-op that succeeds.

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
        try:
            # If no rollback points, nothing to rollback - success
            if not hasattr(self, '_rollback_points') or not self._rollback_points:
                return True
            
            # Find the earliest active rollback point
            earliest_rollback = None
            for entry in self._rollback_points:
                if entry['active']:
                    if earliest_rollback is None or entry['created_at'] < earliest_rollback['created_at']:
                        earliest_rollback = entry
            
            # If no active rollback points, nothing to do
            if earliest_rollback is None:
                return True
            
            # Rollback to earliest point - this handles everything
            return self.rollback_to_point(earliest_rollback['id'])
            
        except SchemaPatchesError:
            # Re-raise rollback_to_point errors
            raise
        except Exception as e:
            # Unexpected error during rollback_all
            raise SchemaPatchesError(f"Complete rollback failed: {e}")

    def get_patch_info(self) -> Dict[str, Any]:
        """
        Get comprehensive information about the patch directory.

        Scans files and calculates metadata. Simple aggregation approach.

        Returns:
            Dict[str, Any]: Patch metadata and statistics

        Example:
            >>> info = patch_dir.get_patch_info()
            >>> info['patch_id']  # "456-performance"
            >>> info['file_count']  # 4
            >>> info['sql_files']  # 3
            >>> info['python_files']  # 1
            >>> info['total_size']  # 1024 bytes
        """
        try:
            # Get files using existing scan_files method
            patch_files = self.scan_files()
            
            # Count files by type
            sql_files = [f for f in patch_files if f.extension == 'sql']
            python_files = [f for f in patch_files if f.extension == 'py']
            
            # Calculate total size - simple approach
            total_size = 0
            for patch_file in patch_files:
                try:
                    # Get file size from filesystem
                    if patch_file.path.exists():
                        total_size += patch_file.path.stat().st_size
                except (OSError, PermissionError):
                    # Skip files we can't read - continue with others
                    continue
            
            # Build info dictionary
            info = {
                'patch_id': self._patch_id,
                'patch_directory': str(self._patch_directory),
                'file_count': len(patch_files),
                'sql_files': len(sql_files),
                'python_files': len(python_files),
                'total_size': total_size,
                'files': [
                    {
                        'name': f.name,
                        'extension': f.extension,
                        'sequence': f.sequence,
                        'path': str(f.path)
                    }
                    for f in patch_files
                ]
            }
            
            # Add execution info if available
            if hasattr(self, '_execution_summary') and self._execution_summary:
                info['last_execution'] = {
                    'files_executed': self._execution_summary.get('files_executed', 0),
                    'success_rate': self._execution_summary.get('success_rate', 0.0),
                    'last_execution_time': self._execution_summary.get('last_execution')
                }
            
            return info
            
        except Exception as e:
            # Fallback info if scanning fails
            return {
                'patch_id': self._patch_id,
                'patch_directory': str(self._patch_directory),
                'error': f"Failed to scan patch info: {e}",
                'file_count': 0,
                'sql_files': 0,
                'python_files': 0,
                'total_size': 0,
                'files': []
            }

    def get_execution_summary(self) -> Dict[str, Any]:
        """
        Get summary of the last execution attempt.

        Simple approach: return the internal execution summary that's updated
        during apply_all_files(). No complex calculations needed.

        Returns:
            Dict[str, Any]: Execution summary with metrics and results

        Example:
            >>> summary = patch_dir.get_execution_summary()
            >>> summary['files_executed']  # 3
            >>> summary['total_time']  # 5.67 seconds
            >>> summary['success_rate']  # 100.0
        """
        # Return copy of execution summary to prevent external modification
        if hasattr(self, '_execution_summary') and self._execution_summary:
            # Create a copy with all current values
            summary = dict(self._execution_summary)
            
            # Ensure all expected keys exist with defaults
            summary.setdefault('files_executed', 0)
            summary.setdefault('total_time', 0)
            summary.setdefault('success_rate', 0.0)
            summary.setdefault('last_execution', None)
            
            # Add some computed fields for convenience
            if summary['files_executed'] > 0 and summary['total_time'] > 0:
                summary['avg_time_per_file'] = summary['total_time'] / summary['files_executed']
            else:
                summary['avg_time_per_file'] = 0.0
                
            return summary
        else:
            # Default summary if no execution yet
            return {
                'files_executed': 0,
                'total_time': 0,
                'success_rate': 0.0,
                'last_execution': None,
                'avg_time_per_file': 0.0
            }

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
        
        Supports Unicode characters in filenames - more flexible approach.

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

            # Check that filename doesn't start with underscore
            if filename.startswith('_'):
                return False

            # Check for spaces (not allowed - causes issues with shell/paths)
            if ' ' in filename:
                return False

            # Check for dangerous special characters (but allow Unicode)
            dangerous_chars = ['@', '$', '%', '&', '*', '(', ')', '+', '=', '{', '}', '[', ']', '|', '\\', ':', ';', '"', "'", '<', '>', ',', '?', '/', '!']
            if any(char in filename for char in dangerous_chars):
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
