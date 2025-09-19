"""
PatchDirectory module for half-orm-dev

Manages SchemaPatches/patch-name/ directory structure, SQL/Python files,
and README.md generation for the patch-centric workflow.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from half_orm import utils
from .patch_validator import PatchValidator, PatchInfo


class PatchDirectoryError(Exception):
    """Base exception for PatchDirectory operations."""
    pass


class PatchStructureError(PatchDirectoryError):
    """Raised when patch directory structure is invalid."""
    pass


class PatchFileError(PatchDirectoryError):
    """Raised when patch file operations fail."""
    pass


@dataclass
class PatchFile:
    """Information about a file within a patch directory."""
    name: str
    path: Path
    extension: str
    order: int
    is_sql: bool
    is_python: bool
    exists: bool


@dataclass
class PatchStructure:
    """Complete structure information for a patch directory."""
    patch_id: str
    directory_path: Path
    readme_path: Path
    files: List[PatchFile]
    is_valid: bool
    validation_errors: List[str]


class PatchDirectory:
    """
    Manages patch directory structure and file operations.

    Handles creation, validation, and management of SchemaPatches/patch-name/ 
    directories following the patch-centric workflow specifications.

    Examples:
        # Create new patch directory
        patch_dir = PatchDirectory(repo)
        patch_dir.create_patch_directory("456-user-authentication")

        # Validate existing patch
        structure = patch_dir.get_patch_structure("456-user-authentication")
        if not structure.is_valid:
            print(f"Validation errors: {structure.validation_errors}")

        # Apply patch files in order
        patch_dir.apply_patch_files("456-user-authentication")
    """

    def __init__(self, repo):
        """
        Initialize PatchDirectory manager.

        Args:
            repo: Repository instance providing base_dir and configuration

        Raises:
            PatchDirectoryError: If repository is invalid or not in development mode
        """
        # Validate repository is not None
        if repo is None:
            raise PatchDirectoryError("Repository cannot be None")

        # Validate repository has required attributes
        required_attrs = ['base_dir', 'devel', 'name']
        for attr in required_attrs:
            if not hasattr(repo, attr):
                raise PatchDirectoryError(f"Repository is invalid: missing '{attr}' attribute")

        # Validate repository is in development mode
        if not repo.devel:
            raise PatchDirectoryError("Repository is not in development mode")

        # Validate base directory exists and is a directory
        if repo.base_dir is None:
            raise PatchDirectoryError("Repository is invalid: base_dir cannot be None")

        base_path = Path(repo.base_dir)
        if not base_path.exists():
            raise PatchDirectoryError(f"Base directory does not exist: {repo.base_dir}")

        if not base_path.is_dir():
            raise PatchDirectoryError(f"Base directory is not a directory: {repo.base_dir}")

        # Store repository reference and paths
        self._repo = repo
        self._base_dir = str(repo.base_dir)
        self._schema_patches_dir = base_path / "SchemaPatches"

        # Store repository name
        self._repo_name = repo.name

        # Ensure SchemaPatches directory exists
        try:
            schema_exists = self._schema_patches_dir.exists()
        except PermissionError:
            raise PatchDirectoryError(f"Permission denied: cannot access SchemaPatches directory")

        if not schema_exists:
            try:
                self._schema_patches_dir.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                raise PatchDirectoryError(f"Permission denied: cannot create SchemaPatches directory")
            except OSError as e:
                raise PatchDirectoryError(f"Failed to create SchemaPatches directory: {e}")

        # Validate SchemaPatches is a directory
        try:
            if not self._schema_patches_dir.is_dir():
                raise PatchDirectoryError(f"SchemaPatches exists but is not a directory: {self._schema_patches_dir}")
        except PermissionError:
            raise PatchDirectoryError(f"Permission denied: cannot access SchemaPatches directory")

        # Initialize PatchValidator
        self._validator = PatchValidator()

    def create_patch_directory(self, patch_id: str, description_hint: Optional[str] = None) -> Path:
        """
        Create complete patch directory structure.

        Creates SchemaPatches/patch-name/ directory with auto-generated README.md
        following the patch-centric workflow specifications.

        Args:
            patch_id: Patch identifier (validated and normalized)
            description_hint: Optional description for README generation

        Returns:
            Path to created patch directory

        Raises:
            PatchDirectoryError: If directory creation fails
            PatchStructureError: If patch directory already exists

        Examples:
            # Create with numeric ID
            path = patch_dir.create_patch_directory("456")
            # Creates: SchemaPatches/456/

            # Create with full ID and hint
            path = patch_dir.create_patch_directory(
                "456-user-auth", 
                "User authentication system"
            )
            # Creates: SchemaPatches/456-user-auth/
        """
        pass

    def get_patch_structure(self, patch_id: str) -> PatchStructure:
        """
        Analyze and validate patch directory structure.

        Examines SchemaPatches/patch-name/ directory and returns complete
        structure information including file validation and ordering.

        Args:
            patch_id: Patch identifier to analyze

        Returns:
            PatchStructure with complete analysis results

        Examples:
            structure = patch_dir.get_patch_structure("456-user-auth")

            if structure.is_valid:
                print(f"Patch has {len(structure.files)} files")
                for file in structure.files:
                    print(f"  {file.order:02d}_{file.name}")
            else:
                print(f"Errors: {structure.validation_errors}")
        """
        pass

    def list_patch_files(self, patch_id: str, file_type: Optional[str] = None) -> List[PatchFile]:
        """
        List all files in patch directory with ordering information.

        Returns files in lexicographic order suitable for sequential application.
        Supports filtering by file type (sql, python, or None for all).

        Args:
            patch_id: Patch identifier
            file_type: Filter by 'sql', 'python', or None for all files

        Returns:
            List of PatchFile objects in application order

        Examples:
            # All files in order
            files = patch_dir.list_patch_files("456-user-auth")

            # SQL files only
            sql_files = patch_dir.list_patch_files("456-user-auth", "sql")

            # Files are returned in lexicographic order:
            # 01_create_users.sql, 02_add_indexes.sql, 03_permissions.py
        """
        pass

    def validate_patch_structure(self, patch_id: str) -> Tuple[bool, List[str]]:
        """
        Validate patch directory structure and contents.

        Performs comprehensive validation of patch directory:
        - Directory exists and accessible
        - README.md present and valid
        - SQL/Python files follow naming conventions
        - No conflicting or invalid files

        Args:
            patch_id: Patch identifier to validate

        Returns:
            Tuple of (is_valid, list_of_errors)

        Examples:
            is_valid, errors = patch_dir.validate_patch_structure("456-user-auth")

            if not is_valid:
                for error in errors:
                    print(f"Validation error: {error}")
        """
        pass

    def generate_readme_content(self, patch_info: PatchInfo, description_hint: Optional[str] = None) -> str:
        """
        Generate README.md content for patch directory.

        Creates comprehensive README.md with:
        - Patch identification and purpose
        - File execution order documentation
        - Integration instructions
        - Template placeholders for manual completion

        Args:
            patch_info: Validated patch information
            description_hint: Optional description for content generation

        Returns:
            Complete README.md content as string

        Examples:
            patch_info = validator.validate_patch_id("456-user-auth")
            content = patch_dir.generate_readme_content(
                patch_info, 
                "User authentication and session management"
            )

            # Content includes:
            # # Patch 456: User Authentication
            # ## Purpose
            # User authentication and session management
            # ## Files
            # - 01_create_users.sql: Create users table
            # - 02_add_indexes.sql: Add performance indexes
        """
        pass

    def create_readme_file(self, patch_id: str, description_hint: Optional[str] = None) -> Path:
        """
        Create README.md file in patch directory.

        Generates and writes comprehensive README.md file for the patch
        using templates and patch information.

        Args:
            patch_id: Patch identifier (validated)
            description_hint: Optional description for README content

        Returns:
            Path to created README.md file

        Raises:
            PatchFileError: If README creation fails

        Examples:
            readme_path = patch_dir.create_readme_file("456-user-auth")
            # Creates: SchemaPatches/456-user-auth/README.md
        """
        pass

    def add_patch_file(self, patch_id: str, filename: str, content: str = "") -> Path:
        """
        Add new file to patch directory.

        Creates new SQL or Python file in patch directory with optional
        initial content. Validates filename follows conventions.

        Args:
            patch_id: Patch identifier
            filename: Name of file to create (must include .sql or .py extension)
            content: Optional initial content for file

        Returns:
            Path to created file

        Raises:
            PatchFileError: If file creation fails or filename invalid

        Examples:
            # Add SQL file
            sql_path = patch_dir.add_patch_file(
                "456-user-auth",
                "01_create_users.sql",
                "CREATE TABLE users (id SERIAL PRIMARY KEY);"
            )

            # Add Python file
            py_path = patch_dir.add_patch_file(
                "456-user-auth",
                "02_update_permissions.py",
                "# Update user permissions"
            )
        """
        pass

    def remove_patch_file(self, patch_id: str, filename: str) -> bool:
        """
        Remove file from patch directory.

        Safely removes specified file from patch directory with validation.
        Does not remove README.md (protected file).

        Args:
            patch_id: Patch identifier
            filename: Name of file to remove

        Returns:
            True if file was removed, False if file didn't exist

        Raises:
            PatchFileError: If removal fails or file is protected

        Examples:
            # Remove SQL file
            removed = patch_dir.remove_patch_file("456-user-auth", "old_script.sql")

            # Cannot remove README.md
            try:
                patch_dir.remove_patch_file("456-user-auth", "README.md")
            except PatchFileError as e:
                print(f"Cannot remove protected file: {e}")
        """
        pass

    def apply_patch_files(self, patch_id: str, database_connection) -> List[str]:
        """
        Apply all patch files in correct order.

        Executes SQL files and Python scripts from patch directory in
        lexicographic order. Integrates with halfORM modules.py for
        code generation after schema changes.

        Args:
            patch_id: Patch identifier to apply
            database_connection: Database connection for SQL execution

        Returns:
            List of applied filenames in execution order

        Raises:
            PatchDirectoryError: If patch application fails

        Examples:
            applied_files = patch_dir.apply_patch_files("456-user-auth", db_conn)

            # Returns: ["01_create_users.sql", "02_add_indexes.sql", "03_permissions.py"]
            # After execution:
            # - Schema changes applied to database
            # - halfORM code regenerated via modules.py integration
            # - Business logic stubs created if needed
        """
        pass

    def get_patch_directory_path(self, patch_id: str) -> Path:
        """
        Get path to patch directory.

        Returns Path object for SchemaPatches/patch-name/ directory.
        Does not validate existence - use get_patch_structure() for validation.

        Args:
            patch_id: Patch identifier

        Returns:
            Path object for patch directory

        Examples:
            path = patch_dir.get_patch_directory_path("456-user-auth")
            # Returns: Path("SchemaPatches/456-user-auth")

            # Check if exists
            if path.exists():
                print(f"Patch directory exists at {path}")
        """
        # Normalize patch_id by stripping whitespace
        normalized_patch_id = patch_id.strip() if patch_id else ""

        # Return path without validation (as documented)
        return self._schema_patches_dir / normalized_patch_id

    def list_all_patches(self) -> List[str]:
        """
        List all existing patch directories.

        Scans SchemaPatches/ directory and returns all valid patch identifiers.
        Only returns directories that pass basic validation.

        Returns:
            List of patch identifiers

        Examples:
            patches = patch_dir.list_all_patches()
            # Returns: ["456-user-auth", "789-security-fix", "234-performance"]

            for patch_id in patches:
                structure = patch_dir.get_patch_structure(patch_id)
                print(f"{patch_id}: {'valid' if structure.is_valid else 'invalid'}")
        """
        pass

    def delete_patch_directory(self, patch_id: str, confirm: bool = False) -> bool:
        """
        Delete entire patch directory.

        Removes SchemaPatches/patch-name/ directory and all contents.
        Requires explicit confirmation to prevent accidental deletion.

        Args:
            patch_id: Patch identifier to delete
            confirm: Must be True to actually delete (safety measure)

        Returns:
            True if directory was deleted, False if confirm=False

        Raises:
            PatchDirectoryError: If deletion fails

        Examples:
            # Safe call - returns False without deleting
            deleted = patch_dir.delete_patch_directory("456-user-auth")

            # Actually delete
            deleted = patch_dir.delete_patch_directory("456-user-auth", confirm=True)
            if deleted:
                print("Patch directory deleted successfully")
        """
        pass

    def _validate_filename(self, filename: str) -> Tuple[bool, str]:
        """
        Validate patch filename follows conventions.

        Internal method to validate SQL/Python filenames follow naming
        conventions for proper lexicographic ordering.

        Args:
            filename: Filename to validate

        Returns:
            Tuple of (is_valid, error_message_if_invalid)
        """
        pass

    def _get_file_order(self, filename: str) -> int:
        """
        Extract ordering number from filename.

        Internal method to determine file execution order from filename.
        Supports patterns like "01_create.sql", "02_update.py", etc.

        Args:
            filename: Filename to analyze

        Returns:
            Order number (0 if no order found)
        """
        pass

    def _execute_sql_file(self, file_path: Path, database_connection) -> None:
        """
        Execute SQL file against database.

        Internal method to safely execute SQL files with error handling
        and transaction management.

        Args:
            file_path: Path to SQL file
            database_connection: Database connection

        Raises:
            PatchDirectoryError: If SQL execution fails
        """
        pass

    def _execute_python_file(self, file_path: Path) -> None:
        """
        Execute Python script file.

        Internal method to safely execute Python scripts with proper
        environment setup and error handling.

        Args:
            file_path: Path to Python file

        Raises:
            PatchDirectoryError: If Python execution fails
        """
        pass
