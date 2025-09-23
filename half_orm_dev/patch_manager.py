"""
PatchManager module for half-orm-dev

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


class PatchManagerError(Exception):
    """Base exception for PatchManager operations."""
    pass


class PatchStructureError(PatchManagerError):
    """Raised when patch directory structure is invalid."""
    pass


class PatchFileError(PatchManagerError):
    """Raised when patch file operations fail."""
    pass


@dataclass
class PatchFile:
    """Information about a file within a patch directory."""
    name: str
    path: Path
    extension: str
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


class PatchManager:
    """
    Manages patch directory structure and file operations.

    Handles creation, validation, and management of SchemaPatches/patch-name/ 
    directories following the patch-centric workflow specifications.

    Examples:
        # Create new patch directory
        patch_mgr = PatchManager(repo)
        patch_mgr.create_patch_directory("456-user-authentication")

        # Validate existing patch
        structure = patch_mgr.get_patch_structure("456-user-authentication")
        if not structure.is_valid:
            print(f"Validation errors: {structure.validation_errors}")

        # Apply patch files in order
        patch_mgr.apply_patch_files("456-user-authentication")
    """

    def __init__(self, repo):
        """
        Initialize PatchManager manager.

        Args:
            repo: Repository instance providing base_dir and configuration

        Raises:
            PatchManagerError: If repository is invalid or not in development mode
        """
        # Validate repository is not None
        if repo is None:
            raise PatchManagerError("Repository cannot be None")

        # Validate repository has required attributes
        required_attrs = ['base_dir', 'devel', 'name']
        for attr in required_attrs:
            if not hasattr(repo, attr):
                raise PatchManagerError(f"Repository is invalid: missing '{attr}' attribute")

        # Validate repository is in development mode
        if not repo.devel:
            raise PatchManagerError("Repository is not in development mode")

        # Validate base directory exists and is a directory
        if repo.base_dir is None:
            raise PatchManagerError("Repository is invalid: base_dir cannot be None")

        base_path = Path(repo.base_dir)
        if not base_path.exists():
            raise PatchManagerError(f"Base directory does not exist: {repo.base_dir}")

        if not base_path.is_dir():
            raise PatchManagerError(f"Base directory is not a directory: {repo.base_dir}")

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
            raise PatchManagerError(f"Permission denied: cannot access SchemaPatches directory")

        if not schema_exists:
            try:
                self._schema_patches_dir.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                raise PatchManagerError(f"Permission denied: cannot create SchemaPatches directory")
            except OSError as e:
                raise PatchManagerError(f"Failed to create SchemaPatches directory: {e}")

        # Validate SchemaPatches is a directory
        try:
            if not self._schema_patches_dir.is_dir():
                raise PatchManagerError(f"SchemaPatches exists but is not a directory: {self._schema_patches_dir}")
        except PermissionError:
            raise PatchManagerError(f"Permission denied: cannot access SchemaPatches directory")

        # Initialize PatchValidator
        self._validator = PatchValidator()

    def create_patch_directory(self, patch_id: str) -> Path:
        """
        Create complete patch directory structure.

        Creates SchemaPatches/patch-name/ directory with minimal README.md template
        following the patch-centric workflow specifications.

        Args:
            patch_id: Patch identifier (validated and normalized)

        Returns:
            Path to created patch directory

        Raises:
            PatchManagerError: If directory creation fails
            PatchStructureError: If patch directory already exists

        Examples:
            # Create with numeric ID
            path = patch_mgr.create_patch_directory("456")
            # Creates: SchemaPatches/456/ with README.md

            # Create with full ID
            path = patch_mgr.create_patch_directory("456-user-auth")
            # Creates: SchemaPatches/456-user-auth/ with README.md
        """
        # Validate patch ID format
        try:
            patch_info = self._validator.validate_patch_id(patch_id)
        except Exception as e:
            raise PatchManagerError(f"Invalid patch ID: {e}")

        # Get patch directory path
        patch_path = self.get_patch_directory_path(patch_info.normalized_id)

        # Check if directory already exists (handle permission errors)
        try:
            path_exists = patch_path.exists()
        except PermissionError:
            raise PatchManagerError(f"Permission denied: cannot access patch directory {patch_info.normalized_id}")

        if path_exists:
            raise PatchStructureError(f"Patch directory already exists: {patch_info.normalized_id}")

        # Create the patch directory
        try:
            patch_path.mkdir(parents=True, exist_ok=False)
        except PermissionError:
            raise PatchManagerError(f"Permission denied: cannot create patch directory {patch_info.normalized_id}")
        except OSError as e:
            raise PatchManagerError(f"Failed to create patch directory {patch_info.normalized_id}: {e}")

        # Create minimal README.md template
        try:
            readme_content = f"# Patch {patch_info.normalized_id}\n"
            readme_path = patch_path / "README.md"
            readme_path.write_text(readme_content, encoding='utf-8')
        except Exception as e:
            # If README creation fails, clean up the directory
            try:
                shutil.rmtree(patch_path)
            except:
                pass  # Best effort cleanup
            raise PatchManagerError(f"Failed to create README.md for patch {patch_info.normalized_id}: {e}")

        return patch_path

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
            structure = patch_mgr.get_patch_structure("456-user-auth")

            if structure.is_valid:
                print(f"Patch has {len(structure.files)} files")
                for file in structure.files:
                    print(f"  {file.order:02d}_{file.name}")
            else:
                print(f"Errors: {structure.validation_errors}")
        """
        # Get patch directory path
        patch_path = self.get_patch_directory_path(patch_id)
        readme_path = patch_path / "README.md"

        # Use validate_patch_structure for basic validation
        is_valid, validation_errors = self.validate_patch_structure(patch_id)

        # If basic validation fails, return structure with errors
        if not is_valid:
            return PatchStructure(
                patch_id=patch_id,
                directory_path=patch_path,
                readme_path=readme_path,
                files=[],
                is_valid=False,
                validation_errors=validation_errors
            )

        # Analyze files in the patch directory
        patch_files = []

        try:
            # Get all files in lexicographic order (excluding README.md)
            all_items = sorted(patch_path.iterdir(), key=lambda x: x.name.lower())
            executable_files = [item for item in all_items if item.is_file() and item.name != "README.md"]

            for item in executable_files:
                # Create PatchFile object
                extension = item.suffix.lower().lstrip('.')
                is_sql = extension == 'sql'
                is_python = extension in ['py', 'python']

                patch_file = PatchFile(
                    name=item.name,
                    path=item,
                    extension=extension,
                    is_sql=is_sql,
                    is_python=is_python,
                    exists=True
                )

                patch_files.append(patch_file)

        except PermissionError:
            # If we can't read directory contents, mark as invalid
            validation_errors.append(f"Permission denied: cannot read patch directory contents")
            is_valid = False

        # Create and return PatchStructure
        return PatchStructure(
            patch_id=patch_id,
            directory_path=patch_path,
            readme_path=readme_path,
            files=patch_files,
            is_valid=is_valid,
            validation_errors=validation_errors
        )

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
            files = patch_mgr.list_patch_files("456-user-auth")

            # SQL files only
            sql_files = patch_mgr.list_patch_files("456-user-auth", "sql")

            # Files are returned in lexicographic order:
            # 01_create_users.sql, 02_add_indexes.sql, 03_permissions.py
        """
        pass

    def validate_patch_structure(self, patch_id: str) -> Tuple[bool, List[str]]:
        """
        Validate patch directory structure and contents.

        Performs minimal validation following KISS principle:
        - Directory exists and accessible

        Developers have full flexibility for patch content and structure.

        Args:
            patch_id: Patch identifier to validate

        Returns:
            Tuple of (is_valid, list_of_errors)

        Examples:
            is_valid, errors = patch_mgr.validate_patch_structure("456-user-auth")

            if not is_valid:
                for error in errors:
                    print(f"Validation error: {error}")
        """
        errors = []

        # Get patch directory path
        patch_path = self.get_patch_directory_path(patch_id)

        # Minimal validation: directory exists and is accessible
        try:
            if not patch_path.exists():
                errors.append(f"Patch directory does not exist: {patch_id}")
            elif not patch_path.is_dir():
                errors.append(f"Path is not a directory: {patch_path}")
        except PermissionError:
            errors.append(f"Permission denied: cannot access patch directory {patch_id}")

        # Return validation results
        is_valid = len(errors) == 0
        return is_valid, errors

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
            content = patch_mgr.generate_readme_content(
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
            readme_path = patch_mgr.create_readme_file("456-user-auth")
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
            sql_path = patch_mgr.add_patch_file(
                "456-user-auth",
                "01_create_users.sql",
                "CREATE TABLE users (id SERIAL PRIMARY KEY);"
            )

            # Add Python file
            py_path = patch_mgr.add_patch_file(
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
            removed = patch_mgr.remove_patch_file("456-user-auth", "old_script.sql")

            # Cannot remove README.md
            try:
                patch_mgr.remove_patch_file("456-user-auth", "README.md")
            except PatchFileError as e:
                print(f"Cannot remove protected file: {e}")
        """
        pass

    def apply_patch_files(self, patch_id: str, database_model) -> List[str]:
        """
        Apply all patch files in correct order.

        Executes SQL files and Python scripts from patch directory in
        lexicographic order. Integrates with halfORM modules.py for
        code generation after schema changes.

        Args:
            patch_id: Patch identifier to apply
            database_model: halfORM Model instance for SQL execution

        Returns:
            List of applied filenames in execution order

        Raises:
            PatchManagerError: If patch application fails

        Examples:
            applied_files = patch_mgr.apply_patch_files("456-user-auth", repo.model)

            # Returns: ["01_create_users.sql", "02_add_indexes.sql", "03_permissions.py"]
            # After execution:
            # - Schema changes applied to database
            # - halfORM code regenerated via modules.py integration
            # - Business logic stubs created if needed
        """
        applied_files = []

        # Get patch structure
        structure = self.get_patch_structure(patch_id)

        # Validate patch is valid
        if not structure.is_valid:
            error_msg = "; ".join(structure.validation_errors)
            raise PatchManagerError(f"Cannot apply invalid patch {patch_id}: {error_msg}")

        # Apply files in lexicographic order
        for patch_file in structure.files:
            if patch_file.is_sql:
                self._execute_sql_file(patch_file.path, database_model)
                applied_files.append(patch_file.name)
            elif patch_file.is_python:
                self._execute_python_file(patch_file.path)
                applied_files.append(patch_file.name)
            # Other file types are ignored (not executed)

        return applied_files

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
            path = patch_mgr.get_patch_directory_path("456-user-auth")
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
            patches = patch_mgr.list_all_patches()
            # Returns: ["456-user-auth", "789-security-fix", "234-performance"]

            for patch_id in patches:
                structure = patch_mgr.get_patch_structure(patch_id)
                print(f"{patch_id}: {'valid' if structure.is_valid else 'invalid'}")
        """
        valid_patches = []

        try:
            # Scan SchemaPatches directory
            if not self._schema_patches_dir.exists():
                return []

            for item in self._schema_patches_dir.iterdir():
                # Skip files, only process directories
                if not item.is_dir():
                    continue

                # Basic patch ID validation - must start with number
                # This excludes hidden directories, __pycache__, etc.
                if not item.name or not item.name[0].isdigit():
                    continue

                # Check for required README.md file
                readme_path = item / "README.md"
                try:
                    if readme_path.exists() and readme_path.is_file():
                        valid_patches.append(item.name)
                except PermissionError:
                    # Skip directories we can't read
                    continue

        except PermissionError:
            # If we can't read SchemaPatches directory, return empty list
            return []
        except OSError:
            # Handle other filesystem errors
            return []

        # Sort patches by numeric value of ticket number
        def sort_key(patch_id):
            try:
                # Extract number part for sorting
                if '-' in patch_id:
                    number_part = patch_id.split('-', 1)[0]
                else:
                    number_part = patch_id
                return int(number_part)
            except ValueError:
                # Fallback to string sort if not numeric
                return float('inf')

        valid_patches.sort(key=sort_key)
        return valid_patches

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
            PatchManagerError: If deletion fails

        Examples:
            # Safe call - returns False without deleting
            deleted = patch_mgr.delete_patch_directory("456-user-auth")

            # Actually delete
            deleted = patch_mgr.delete_patch_directory("456-user-auth", confirm=True)
            if deleted:
                print("Patch directory deleted successfully")
        """
        # Safety check - require explicit confirmation
        if not confirm:
            return False

        # Validate patch ID format - require full patch name for safety
        if not patch_id or not patch_id.strip():
            raise PatchManagerError("Invalid patch ID: cannot be empty")

        patch_id = patch_id.strip()

        # Validate patch ID using PatchValidator for complete validation
        try:
            patch_info = self._validator.validate_patch_id(patch_id)
        except Exception as e:
            raise PatchManagerError(f"Invalid patch ID format: {e}")

        # For deletion safety, require full patch name (not just numeric ID)
        if patch_info.is_numeric_only:
            raise PatchManagerError(
                f"For safety, deletion requires full patch name, not just ID '{patch_id}'. "
                f"Use complete format like '{patch_id}-description'"
            )

        # Get patch directory path
        patch_path = self.get_patch_directory_path(patch_id)

        # Check if directory exists (handle permission errors)
        try:
            path_exists = patch_path.exists()
        except PermissionError:
            raise PatchManagerError(f"Permission denied: cannot access patch directory {patch_id}")

        if not path_exists:
            raise PatchManagerError(f"Patch directory does not exist: {patch_id}")

        # Verify it's actually a directory, not a file (handle permission errors)
        try:
            is_directory = patch_path.is_dir()
        except PermissionError:
            raise PatchManagerError(f"Permission denied: cannot access patch directory {patch_id}")

        if not is_directory:
            raise PatchManagerError(f"Path exists but is not a directory: {patch_path}")

        # Delete the directory and all contents
        try:
            shutil.rmtree(patch_path)
            return True

        except PermissionError as e:
            raise PatchManagerError(f"Permission denied: cannot delete {patch_path}") from e
        except OSError as e:
            raise PatchManagerError(f"Failed to delete patch directory {patch_path}: {e}") from e

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

    def _execute_sql_file(self, file_path: Path, database_model) -> None:
        """
        Execute SQL file against database.

        Internal method to safely execute SQL files with error handling
        using halfORM Model.execute_query().

        Args:
            file_path: Path to SQL file
            database_model: halfORM Model instance

        Raises:
            PatchManagerError: If SQL execution fails
        """
        try:
            # Read SQL content
            sql_content = file_path.read_text(encoding='utf-8')

            # Skip empty files
            if not sql_content.strip():
                return

            # Execute SQL using halfORM model (same as patch.py line 144)
            database_model.execute_query(sql_content)

        except Exception as e:
            raise PatchManagerError(f"SQL execution failed in {file_path.name}: {e}") from e

    def _execute_python_file(self, file_path: Path) -> None:
        """
        Execute Python script file.

        Internal method to safely execute Python scripts with proper
        environment setup and error handling.

        Args:
            file_path: Path to Python file

        Raises:
            PatchManagerError: If Python execution fails
        """
        try:
            # Setup Python execution environment
            import subprocess
            import sys

            # Execute Python script as subprocess
            result = subprocess.run(
                [sys.executable, str(file_path)],
                cwd=file_path.parent,
                capture_output=True,
                text=True,
                check=True
            )

            # Log output if any (could be enhanced with proper logging)
            if result.stdout.strip():
                print(f"Python output from {file_path.name}: {result.stdout.strip()}")

        except subprocess.CalledProcessError as e:
            error_msg = f"Python execution failed in {file_path.name}"
            if e.stderr:
                error_msg += f": {e.stderr.strip()}"
            raise PatchManagerError(error_msg) from e
        except Exception as e:
            raise PatchManagerError(f"Failed to execute Python file {file_path.name}: {e}") from e