"""
PatchManager module for half-orm-dev

Manages Patches/patch-name/ directory structure, SQL/Python files,
and README.md generation for the patch-centric workflow.
"""

from __future__ import annotations

import os
import re
import sys
import shutil
import subprocess
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
import click
from git.exc import GitCommandError

from half_orm import utils
from half_orm_dev import modules
from half_orm_dev.release_file import ReleaseFile, ReleaseFileError
from .patch_validator import PatchValidator, PatchInfo
from .decorators import with_dynamic_branch_lock


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

    Handles creation, validation, and management of Patches/patch-name/
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
            PatchManagerError: If repository is invalid
        """
        # Validate repository is not None
        if repo is None:
            raise PatchManagerError("Repository cannot be None")

        # Validate repository has required attributes
        required_attrs = ['base_dir', 'devel', 'name']
        for attr in required_attrs:
            if not hasattr(repo, attr):
                raise PatchManagerError(f"Repository is invalid: missing '{attr}' attribute")

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
        self._schema_patches_dir = base_path / "Patches"
        self._releases_dir = Path(repo.releases_dir)

        # Store repository name
        self._repo_name = repo.name

        # Ensure Patches directory exists
        try:
            schema_exists = self._schema_patches_dir.exists()
        except PermissionError:
            raise PatchManagerError(f"Permission denied: cannot access Patches directory")

        if not schema_exists:
            try:
                self._schema_patches_dir.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                raise PatchManagerError(f"Permission denied: cannot create Patches directory")
            except OSError as e:
                raise PatchManagerError(f"Failed to create Patches directory: {e}")

        # Validate Patches is a directory
        try:
            if not self._schema_patches_dir.is_dir():
                raise PatchManagerError(f"Patches exists but is not a directory: {self._schema_patches_dir}")
        except PermissionError:
            raise PatchManagerError(f"Permission denied: cannot access Patches directory")

        # Initialize PatchValidator
        self._validator = PatchValidator()

    def create_patch_directory(self, patch_id: str) -> Path:
        """
        Create complete patch directory structure.

        Creates Patches/patch-name/ directory with minimal README.md template
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
            # Creates: Patches/456/ with README.md

            # Create with full ID
            path = patch_mgr.create_patch_directory("456-user-auth")
            # Creates: Patches/456-user-auth/ with README.md
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

        Examines Patches/patch-name/ directory and returns complete
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
            # Creates: Patches/456-user-auth/README.md
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

    def apply_patch_complete_workflow(self, patch_id: str) -> dict:
        """
        Apply patch with full release context.

        Workflow:
        1. Restore DB from production baseline (model/schema.sql)
        2. Apply all release patches in order (RC1, RC2, ..., stage)
        3. If current patch is in release, apply it in correct order
        4. If current patch is NOT in release, apply it at the end
        5. Generate Python code

        Examples:
            # Release context: [123, 456, 789, 234]
            # Current patch: 789 (already in release)

            apply_patch_complete_workflow("789")
            # Execution:
            # 1. Restore DB (1.3.5)
            # 2. Apply 123
            # 3. Apply 456
            # 4. Apply 789 ← In correct order
            # 5. Apply 234
            # 6. Generate code

            # Current patch: 999 (NOT in release)
            apply_patch_complete_workflow("999")
            # Execution:
            # 1. Restore DB (1.3.5)
            # 2. Apply 123
            # 3. Apply 456
            # 4. Apply 789
            # 5. Apply 234
            # 6. Apply 999 ← At the end
            # 7. Generate code
        """

        try:
            # Étape 1: Restauration DB
            self._repo.restore_database_from_schema()

            # Étape 2: Récupérer contexte release complet
            release_patches = self._repo.release_manager.get_all_release_context_patches()

            applied_release_files = []
            applied_current_files = []
            patch_was_in_release = False

            # Étape 3: Appliquer patches
            for patch in release_patches:
                if patch == patch_id:
                    patch_was_in_release = True
                files = self.apply_patch_files(patch, self._repo.model)
                applied_release_files.extend(files)

            # Étape 4: Si patch courant pas dans release, l'appliquer maintenant
            if not patch_was_in_release:
                files = self.apply_patch_files(patch_id, self._repo.model)
                applied_current_files = files

            # Étape 5: Génération code Python
            # Track generated files
            package_dir = Path(self._base_dir) / self._repo_name
            files_before = set()
            if package_dir.exists():
                files_before = set(package_dir.rglob('*.py'))

            modules.generate(self._repo)

            files_after = set()
            if package_dir.exists():
                files_after = set(package_dir.rglob('*.py'))

            generated_files = [str(f.relative_to(self._base_dir)) for f in files_after]

            # Étape 6: Retour succès
            return {
                'patch_id': patch_id,
                'release_patches': [p for p in release_patches if p != patch_id],
                'applied_release_files': applied_release_files,
                'applied_current_files': applied_current_files,
                'patch_was_in_release': patch_was_in_release,
                'generated_files': generated_files,
                'status': 'success',
                'error': None
            }

        except PatchManagerError:
            self._repo.restore_database_from_schema()
            raise

        except Exception as e:
            self._repo.restore_database_from_schema()
            raise PatchManagerError(
                f"Apply patch workflow failed for {patch_id}: {e}"
            ) from e

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

        Returns Path object for Patches/patch-name/ directory.
        Does not validate existence - use get_patch_structure() for validation.

        Args:
            patch_id: Patch identifier

        Returns:
            Path object for patch directory

        Examples:
            path = patch_mgr.get_patch_directory_path("456-user-auth")
            # Returns: Path("Patches/456-user-auth")

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

        Scans Patches/ directory and returns all valid patch identifiers.
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
            # Scan Patches directory
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
            # If we can't read Patches directory, return empty list
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

        Removes Patches/patch-name/ directory and all contents.
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

    def _is_data_file(self, file_path: Path) -> bool:
        """
        Check if SQL file is annotated with @HOP:data marker.

        Data files contain reference data (DML) that should be preserved
        for from-scratch installations. They must be marked with `-- @HOP:data`
        as the first line of the file.

        Args:
            file_path: Path to SQL file to check

        Returns:
            True if file has @HOP:data annotation, False otherwise

        Examples:
            if self._is_data_file(Path("Patches/456/01_roles.sql")):
                # This is a data file
                pass
        """
        try:
            with file_path.open('r', encoding='utf-8') as f:
                first_line = f.readline().strip().lower()
                return re.match(r"--\s*@hop:data", first_line) is not None
        except Exception:
            return False

    def _get_data_files_from_patch(self, patch_id: str) -> List[Path]:
        """
        Get all data files (annotated with @HOP:data) from a patch.

        Returns SQL files from the patch directory that are annotated with
        `-- @HOP:data` marker, in lexicographic order for proper sequencing.

        Args:
            patch_id: Patch identifier (e.g., "456-user-auth")

        Returns:
            List of Path objects for data files in application order

        Examples:
            data_files = self._get_data_files_from_patch("456-user-auth")
            # Returns [Path("Patches/456-user-auth/01_roles.sql"), ...]
        """
        data_files = []
        structure = self.get_patch_structure(patch_id)

        if not structure.is_valid:
            return []

        for patch_file in structure.files:
            if patch_file.is_sql and self._is_data_file(patch_file.path):
                data_files.append(patch_file.path)

        return data_files

    def _validate_data_file_idempotent(self, file_path: Path) -> Tuple[bool, List[str]]:
        """
        Validate that data file uses idempotent SQL patterns.

        Data files must be replayable without errors. This checks for common
        idempotent patterns like:
        - INSERT ... ON CONFLICT DO NOTHING
        - INSERT ... ON CONFLICT DO UPDATE
        - DELETE before INSERT
        - Conditional statements

        Args:
            file_path: Path to SQL file to validate

        Returns:
            Tuple of (is_valid, list_of_warnings)
            - is_valid: True if file appears idempotent
            - warnings: List of warning messages if patterns not detected

        Examples:
            is_valid, warnings = self._validate_data_file_idempotent(
                Path("Patches/456/01_roles.sql")
            )
            if not is_valid:
                for warning in warnings:
                    print(f"Warning: {warning}")
        """
        warnings = []

        try:
            content = file_path.read_text(encoding='utf-8')
            content_lower = content.lower()

            # Check if file has INSERT statements
            has_insert = 'insert' in content_lower and 'into' in content_lower

            if has_insert:
                # Check for idempotent patterns
                has_on_conflict = 'on conflict' in content_lower
                has_delete_before = 'delete' in content_lower and content_lower.find('delete') < content_lower.find('insert')
                has_where_not_exists = 'where not exists' in content_lower

                if not (has_on_conflict or has_delete_before or has_where_not_exists):
                    warnings.append(
                        f"{file_path.name}: Contains INSERT without idempotent pattern.\n"
                        f"  Consider using:\n"
                        f"  - INSERT ... ON CONFLICT DO NOTHING\n"
                        f"  - INSERT ... ON CONFLICT DO UPDATE\n"
                        f"  - DELETE before INSERT\n"
                        f"  - INSERT ... WHERE NOT EXISTS"
                    )

            # Note: Empty or comment-only files are considered valid
            return len(warnings) == 0, warnings

        except Exception as e:
            warnings.append(f"Failed to validate {file_path.name}: {e}")
            return False, warnings

    def _collect_data_files_from_patches(self, patch_list: List[str]) -> List[Path]:
        """
        Collect all data files from a list of patches.

        Processes a list of patch IDs and returns all data files (marked with
        @HOP:data) in the order they should be applied. Validates idempotency
        and shows warnings for non-idempotent patterns.

        Args:
            patch_list: List of patch identifiers in application order

        Returns:
            List of Path objects for all data files across patches

        Raises:
            PatchManagerError: If validation fails critically

        Examples:
            patches = ["456-user-auth", "457-roles", "458-permissions"]
            data_files = self._collect_data_files_from_patches(patches)
            # Returns all @HOP:data files from these patches in order
        """
        all_data_files = []
        all_warnings = []

        for patch_id in patch_list:
            data_files = self._get_data_files_from_patch(patch_id)

            for data_file in data_files:
                # Validate idempotency
                is_valid, warnings = self._validate_data_file_idempotent(data_file)

                if warnings:
                    all_warnings.extend(warnings)

                all_data_files.append(data_file)

        # Show warnings if any
        if all_warnings:
            click.echo(f"\n{utils.Color.bold('⚠ Data file idempotency warnings:')}")
            for warning in all_warnings:
                click.echo(f"  {warning}")
            click.echo("")

        return all_data_files

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
            sql_content = str(file_path.read_text(encoding='utf-8'))

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

    def _fetch_from_remote(self) -> None:
        """
        Fetch all references from remote before patch creation.

        Updates local knowledge of remote state including:
        - Remote branches (ho-prod, ho-patch/*)
        - Remote tags (ho-patch/{number} reservation tags)
        - All other remote references

        This ensures patch creation is based on the latest remote state and
        prevents conflicts with recently created patches by other developers.

        Called early in create_patch() workflow to synchronize with remote
        before checking patch number availability.

        Raises:
            PatchManagerError: If fetch fails (network, auth, etc.)

        Examples:
            self._fetch_from_remote()
            # Local git now has up-to-date view of remote
            # Can accurately check tag/branch availability
        """
        try:
            self._repo.hgit.fetch_from_origin()
        except Exception as e:
            raise PatchManagerError(
                f"Failed to fetch from remote: {e}\n"
                f"Cannot synchronize with remote repository.\n"
                f"Check network connection and remote access."
            )

    def _commit_patch_directory(self, patch_id: str, description: Optional[str] = None) -> None:
        """
        Commit patch directory to git repository.

        Creates a commit containing the Patches/patch-id/ directory and README.md.
        This commit becomes the target for the reservation tag, ensuring the tag
        points to a repository state that includes the patch directory structure.

        Args:
            patch_id: Patch identifier (e.g., "456-user-auth")
            description: Optional description included in commit message

        Raises:
            PatchManagerError: If git operations fail

        Examples:
            self._commit_patch_directory("456-user-auth")
            # Creates commit: "[HOP] Add Patches/456-user-auth directory"

            self._commit_patch_directory("456-user-auth", "Add user authentication")
            # Creates commit: "[HOP] Add Patches/456-user-auth directory - Add user authentication"
        """
        try:
            # Add the patch directory to git
            patch_path = self.get_patch_directory_path(patch_id)
            self._repo.hgit.add(str(patch_path))

            # Create commit message
            if description:
                commit_message = f"[HOP] Add Patches/{patch_id} directory - {description}"
            else:
                commit_message = f"[HOP] Add Patches/{patch_id} directory"

            # Commit the changes
            self._repo.hgit.commit('-m', commit_message)

        except Exception as e:
            raise PatchManagerError(
                f"Failed to commit patch directory {patch_id}: {e}"
            )

    def _create_local_tag(self, patch_id: str, description: Optional[str] = None) -> None:
        """
        Create local git tag without pushing to remote.

        Creates tag ho-patch/{number} pointing to current HEAD (which should be
        the commit containing the Patches/ directory). Tag is created locally only;
        push happens separately as the atomic reservation operation.

        Args:
            patch_id: Patch identifier (e.g., "456-user-auth")
            description: Optional description for tag message

        Raises:
            PatchManagerError: If tag creation fails

        Examples:
            self._create_local_tag("456-user-auth")
            # Creates local tag: ho-patch/456 with message "Patch 456 reserved"

            self._create_local_tag("456-user-auth", "Add user authentication")
            # Creates local tag: ho-patch/456 with message "Patch 456: Add user authentication"
        """
        # Extract patch number
        patch_number = patch_id.split('-')[0]
        tag_name = f"ho-patch/{patch_number}"

        # Create tag message
        if description:
            tag_message = f"Patch {patch_number}: {description}"
        else:
            tag_message = f"Patch {patch_number} reserved"

        try:
            # Create tag locally (no push)
            self._repo.hgit.create_tag(tag_name, tag_message)
        except Exception as e:
            raise PatchManagerError(
                f"Failed to create local tag {tag_name}: {e}"
            )

    def _push_tag_to_reserve_number(self, patch_id: str) -> None:
        """
        Push tag to remote for atomic global reservation.

        This is the point of no return in the patch creation workflow. Once the
        tag is successfully pushed, the patch number is reserved globally and
        cannot be rolled back. This must happen BEFORE pushing the branch to
        prevent race conditions between developers.

        Tag-first strategy prevents race conditions:
        - Developer A pushes tag ho-patch/456 → reservation complete
        - Developer B fetches tags, sees 456 reserved → cannot create
        - Developer A pushes branch → content available

        vs. branch-first (problematic):
        - Developer A pushes branch → visible but not reserved
        - Developer B checks (no tag yet) → appears available
        - Developer B creates patch → conflict when pushing tag

        Args:
            patch_id: Patch identifier (e.g., "456-user-auth")

        Raises:
            PatchManagerError: If tag push fails

        Examples:
            self._push_tag_to_reserve_number("456-user-auth")
            # Pushes tag ho-patch/456 to remote
            # After this succeeds, patch number is globally reserved
        """
        # Extract patch number
        patch_number = patch_id.split('-')[0]
        tag_name = f"ho-patch/{patch_number}"

        try:
            # Push tag to reserve globally (ATOMIC OPERATION)
            self._repo.hgit.push_tag(tag_name)
        except Exception as e:
            raise PatchManagerError(
                f"Failed to push reservation tag {tag_name}: {e}\n"
                f"Patch number reservation failed."
            )

    def _push_branch_to_remote(self, branch_name: str, retry_count: int = 3) -> None:
        """
        Push branch to remote with automatic retry on failure.

        Attempts to push branch to remote with exponential backoff retry strategy.
        If tag was already pushed successfully, branch push failure is not critical
        as the patch number is already reserved. Retries help handle transient
        network issues.

        Retry strategy:
        - Attempt 1: immediate
        - Attempt 2: 1 second delay
        - Attempt 3: 2 seconds delay
        - Attempt 4: 4 seconds delay (if retry_count allows)

        Args:
            branch_name: Full branch name (e.g., "ho-patch/456-user-auth")
            retry_count: Number of retry attempts (default: 3)

        Raises:
            PatchManagerError: If all retry attempts fail

        Examples:
            self._push_branch_to_remote("ho-patch/456-user-auth")
            # Tries to push branch, retries up to 3 times with backoff

            self._push_branch_to_remote("ho-patch/456-user-auth", retry_count=5)
            # Custom retry count for unreliable networks
        """
        last_error = None

        for attempt in range(retry_count):
            try:
                # Attempt to push branch
                self._repo.hgit.push_branch(branch_name, set_upstream=True)
                return  # Success!

            except Exception as e:
                last_error = e

                # If not last attempt, wait before retry
                if attempt < retry_count - 1:
                    delay = 2 ** attempt  # Exponential backoff: 1, 2, 4 seconds
                    time.sleep(delay)

        # All retries failed
        raise PatchManagerError(
            f"Failed to push branch {branch_name} after {retry_count} attempts: {last_error}\n"
            "Check network connection and remote access permissions."
        )

    def _update_readme_with_description(
        self,
        patch_dir: Path,
        patch_id: str,
        description: str
    ) -> None:
        """
        Update README.md in patch directory with description.

        Helper method to update the README.md file with user-provided description.
        Separated from main workflow for clarity and testability.

        Args:
            patch_dir: Path to patch directory
            patch_id: Patch identifier for README header
            description: Description text to add

        Raises:
            PatchManagerError: If README update fails

        Examples:
            patch_dir = Path("Patches/456-user-auth")
            self._update_readme_with_description(
                patch_dir,
                "456-user-auth",
                "Add user authentication system"
            )
            # Updates README.md with description
        """
        try:
            readme_path = patch_dir / "README.md"
            readme_content = f"# Patch {patch_id}\n\n{description}\n"
            readme_path.write_text(readme_content, encoding='utf-8')

        except Exception as e:
            raise PatchManagerError(
                f"Failed to update README for patch {patch_id}: {e}"
            )


    def _rollback_patch_creation(
        self,
        initial_branch: str,
        branch_name: str,
        patch_id: str,
        patch_dir: Optional[Path] = None,
        commit_created: bool = False  # DEFAULT: False pour rétrocompatibilité
    ) -> None:
        """
        Rollback patch creation to initial state on failure.

        Performs complete cleanup of all local changes made during patch creation
        when an error occurs BEFORE the tag is pushed to remote. This ensures a
        clean repository state for retry.

        UPDATED FOR NEW WORKFLOW (v0.17.2+): Patches/ directories are now created
        on patch branches only, not on ho-release. The rollback must handle:
        - Commit on ho-release (only patches file metadata)
        - Potential commit on patch branch (Patches/ directory)
        - Potential branch not yet created

        Rollback operations (best-effort, continues on individual failures):
        1. Try to checkout patch branch if exists and remove Patches/ directory
        2. Return to initial branch (ho-release)
        3. Reset commit if it was created (git reset --hard HEAD~1)
        4. Delete patch branch if it was created
        5. Delete patch tag (local)

        Note: This method is only called when tag push has NOT succeeded yet.
        Once tag is pushed, rollback is not performed as the patch number is
        already globally reserved.

        Args:
            initial_branch: Branch to return to (usually "ho-release/X.Y.Z")
            branch_name: Patch branch name (e.g., "ho-patch/456-user-auth")
            patch_id: Patch identifier for tag/directory cleanup
            patch_dir: Path to patch directory if it was created (may be on branch)
            commit_created: Whether commit was created on ho-release (metadata)

        Examples:
            # NEW WORKFLOW (v0.17.2+): Rollback with metadata commit on ho-release
            self._rollback_patch_creation(
                "ho-release/0.17.0",
                "ho-patch/456-user-auth",
                "456-user-auth",
                Path("Patches/456-user-auth"),  # Created on branch
                commit_created=True  # Metadata commit on ho-release
            )
            # Cleans patch branch, reverts metadata commit on ho-release
        """
        # Best-effort cleanup - continue even if individual operations fail

        # Track which branch we're currently on for cleanup
        current_branch = None
        try:
            current_branch = self._repo.hgit.branch
        except Exception:
            pass

        # 1. If patch directory exists, delete it (wherever it is)
        # In new workflow, it may be on patch branch or not created yet
        if patch_dir and patch_dir.exists():
            try:
                shutil.rmtree(patch_dir)
            except Exception:
                # Directory deletion may fail (permissions, etc.) - continue
                pass

        # 2. Ensure we're on initial branch (ho-release)
        try:
            self._repo.hgit.checkout(initial_branch)
        except Exception:
            # Continue cleanup even if checkout fails
            pass

        # 3. Reset commit if it was created on ho-release (metadata commit)
        if commit_created:
            try:
                # Hard reset to remove the commit
                # Using git reset --hard HEAD~1
                self._repo.hgit._HGit__git_repo.git.reset('--hard', 'HEAD~1')
            except Exception:
                # Continue cleanup even if reset fails
                pass

        # 4. Delete patch branch (may not exist if failure before branch creation)
        try:
            self._repo.hgit.delete_local_branch(branch_name)
        except Exception:
            # Branch may not exist yet or deletion may fail - continue
            pass

        # 5. Delete local tag
        patch_number = patch_id.split('-')[0]
        tag_name = f"ho-patch/{patch_number}"
        try:
            self._repo.hgit.delete_local_tag(tag_name)
        except Exception:
            # Tag may not exist yet or deletion may fail - continue
            pass

    @with_dynamic_branch_lock(lambda self, patch_id, description=None, before=None: "ho-prod")
    def create_patch(self, patch_id: str, description: Optional[str] = None, before: Optional[str] = None) -> dict:
        """
        Create new patch with atomic tag-first reservation strategy.

        UPDATED WORKFLOW (v0.17.2+): Patches/ directories are now isolated to patch branches!

        Orchestrates the full patch creation workflow with transactional guarantees:
        1. Validates we're on ho-release/X.Y.Z branch
        2. Validates repository is clean
        3. Validates git remote is configured
        4. Validates and normalizes patch ID format
        5. **ACQUIRES DISTRIBUTED LOCK on ho-release/X.Y.Z** (30min timeout)
        6. Fetches all references from remote (branches + tags) - with lock
        7. Validates ho-release is synced with origin
        8. Checks patch number available via tag lookup (with up-to-date state)
        9. **Adds PATCH_ID to X.Y.Z-patches.toml** (metadata only)
        10. Commits metadata on ho-release/X.Y.Z "[HOP] Add patch #{patch_id} to %X.Y.Z candidates"
        11. Creates local tag ho-patch/{number} (points to metadata commit on ho-release)
        12. **Pushes tag to reserve number globally** ← POINT OF NO RETURN
        13. Pushes ho-release branch
        14. Syncs release files to ho-prod (non-critical)
        15. Creates ho-patch/PATCH_ID branch from current commit
        16. **Creates Patches/PATCH_ID/ directory ON PATCH BRANCH** (isolation!)
        17. Commits Patches/ directory on ho-patch/PATCH_ID "[HOP] Create patch directory for {patch_id}"
        18. Pushes branch to remote (with retry)
        19. **RELEASES LOCK** (always, even on error)

        Key improvement: Patches/ directories are now isolated to their patch branches,
        preventing pollution of ho-release with all patch directories.

        Transactional guarantees:
        - Failure before step 12 (tag push): Complete rollback to initial state
        - Success at step 12 (tag push): Patch reserved, no rollback even if branch push fails
        - Tag-first strategy prevents race conditions between developers
        - Remote fetch + sync validation ensures up-to-date base

        Race condition prevention:
        Tag pushed BEFORE branch ensures atomic reservation:
        - Dev A: Push tag → reservation complete
        - Dev B: Fetch tags → sees reservation → cannot create
        vs. branch-first approach allows conflicts

        Args:
            patch_id: Patch identifier (e.g., "456-user-auth")
            description: Optional description for README and commit message
            before: Optional patch ID to insert before in application order

        Returns:
            dict: Creation result with keys:
                - patch_id: Normalized patch identifier
                - branch_name: Created branch name
                - patch_dir: Path to patch directory (on patch branch)
                - on_branch: Current branch after checkout
                - version: Release version (e.g., "0.17.0")

        Raises:
            PatchManagerError: If validation fails or creation errors occur

        Examples:
            # On branch ho-release/0.17.0:
            result = patch_mgr.create_patch("456-user-auth")
            # Creates metadata on ho-release, Patches/ on ho-patch/456-user-auth

            result = patch_mgr.create_patch("456", "Add authentication")
            # With description for README and commits
        """
        # Step 1-3: Validate context
        release_branch = self._validate_on_ho_release()
        release_version = release_branch.replace("ho-release/", "")
        self._validate_repo_clean()
        self._validate_has_remote()

        # Step 4: Validate and normalize patch ID
        try:
            patch_info = self._validator.validate_patch_id(patch_id)
            normalized_id = patch_info.normalized_id
        except Exception as e:
            raise PatchManagerError(f"Invalid patch ID: {e}")
        lock_tag = None
        # Save initial state for rollback
        initial_branch = self._repo.hgit.branch  # Should be ho-release/X.Y.Z
        patch_dir = None
        commit_created = False
        tag_pushed = False
        modifications_started = False  # Track if we started making changes
        branch_name = f"ho-patch/{normalized_id}"
        try:
            # Step 6: Fetch all references from remote (branches + tags) - with lock held
            self._fetch_from_remote()

            # Step 6.5: Validate ho-release/X.Y.Z is synced with origin
            self._validate_branch_synced_with_origin(release_branch)

            # Step 7: Check patch number available (via tag, with up-to-date state)
            self._check_patch_id_available(normalized_id)

            # === LOCAL OPERATIONS ON HO-RELEASE (rollback on failure) ===
            modifications_started = True  # From here, rollback is needed on failure

            # Step 8: Add patch to candidates.txt (only metadata on ho-release)
            self._add_patch_to_candidates(normalized_id, release_version, before=before)

            # Step 9: Commit patches file ON HO-RELEASE (without Patches/ directory)
            # Build commit message
            msg = f"[HOP] Add patch #{normalized_id} to %{release_version} candidates"
            if description:
                msg += f"\n\n{description}"

            # Commit using unified commit and sync (TOML file is in .hop/releases/)
            self._repo.commit_and_sync_to_active_branches(message=msg)
            commit_created = True  # Track that commit was made

            # Step 10: Create local tag (points to commit on ho-release without Patches/)
            self._create_local_tag(normalized_id, description)

            # === REMOTE OPERATIONS (point of no return) ===

            # Step 11: Push tag FIRST → ATOMIC RESERVATION
            self._push_tag_to_reserve_number(normalized_id)
            tag_pushed = True  # Tag pushed = point of no return
            # ✅ If we reach here: patch number globally reserved!

            # === BRANCH CREATION (after reservation) ===

            # Step 12: Create branch FROM current commit (after tag push)
            self._create_git_branch(branch_name)

            # Step 13: Push empty branch to remote FIRST (required by git hooks)
            # This allows the pre-commit hook to verify the branch exists on origin
            try:
                self._push_branch_to_remote(branch_name)
            except PatchManagerError as e:
                # Tag already pushed = success, just warn about branch
                click.echo(f"⚠️  Warning: Branch push failed after 3 attempts")
                click.echo(f"⚠️  Patch {normalized_id} is reserved (tag pushed successfully)")
                click.echo(f"⚠️  Push branch manually: git push -u origin {branch_name}")
                # Don't raise - tag pushed means success

            # Step 14: Create patch directory ON PATCH BRANCH ONLY (isolation!)
            patch_dir = self.create_patch_directory(normalized_id)
            self._repo.hgit.add(patch_dir)

            # Step 14b: Update README if description provided
            if description:
                self._update_readme_with_description(patch_dir, normalized_id, description)
                # Add the updated README to staging
                readme_path = patch_dir / "README.md"
                self._repo.hgit.add(readme_path)

            # Step 14c: Commit patch directory ON PATCH BRANCH
            # Now the pre-commit hook will find the branch on origin
            self._commit_patch_directory_to_branch(normalized_id, description)

            # Step 15: Push the commit
            try:
                self._repo.hgit.push()
            except Exception as e:
                # Commit was created, just warn about push failure
                click.echo(f"⚠️  Warning: Failed to push commit: {e}")
                click.echo(f"⚠️  Push manually: git push")

            # Note: Already on branch after _create_git_branch()

        except Exception as e:
            # Only rollback if tag NOT pushed yet AND modifications started
            # modifications_started=False means failure during validation (steps 1-7)
            # modifications_started=True means failure during creation (steps 8+)
            if not tag_pushed and modifications_started:
                self._rollback_patch_creation(
                    initial_branch,
                    branch_name,
                    normalized_id,
                    patch_dir,
                    commit_created=commit_created  # Pass commit status
                )
            raise PatchManagerError(f"Patch creation failed: {e}")

        # Return result
        return {
            'patch_id': normalized_id,
            'branch_name': branch_name,
            'patch_dir': patch_dir,
            'on_branch': branch_name,
            'version': release_version,  # NEW: include release version
        }

    def _sync_release_files_to_ho_prod(self, version: str, release_branch: str, critical: bool = False) -> None:
        """
        Sync release files for a specific version to ho-prod.

        This ensures that ho-prod always has the latest state of release metadata
        files, making it the single source of truth for release information.

        Args:
            version: Release version (e.g., "0.17.0")
            release_branch: Source release branch (e.g., "ho-release/0.17.0")
            critical: If True, raise exception on failure. If False, just warn.

        Raises:
            PatchManagerError: If critical=True and sync fails

        Examples:
            # After modifying patches.toml on ho-release/0.17.0
            self._sync_release_files_to_ho_prod("0.17.0", "ho-release/0.17.0")
        """
        try:
            # Save current branch
            current_branch = release_branch

            # Check which files exist in the release branch
            # We need to check before attempting git checkout to avoid errors

            # Build list of files to sync
            paths_to_sync = []

            # Check for TOML patches file (dev tracking)
            toml_path = f".hop/releases/{version}-patches.toml"
            toml_file = Path(self._repo.base_dir) / toml_path
            if toml_file.exists():
                paths_to_sync.append(toml_path)

            # Check for TXT snapshot files (RC, prod, hotfix)
            # List all matching files using glob
            releases_dir = Path(self._repo.releases_dir)
            txt_files = list(releases_dir.glob(f"{version}*.txt"))
            for txt_file in txt_files:
                # Convert to relative path from repo root
                rel_path = f".hop/releases/{txt_file.name}"
                paths_to_sync.append(rel_path)

            # If no files to sync, nothing to do
            if not paths_to_sync:
                return

            # Checkout ho-prod
            self._repo.hgit.checkout("ho-prod")

            # Copy files from release branch
            self._repo.hgit.checkout_paths_from_branch(release_branch, paths_to_sync)

            # Commit on ho-prod
            self._repo.hgit.commit("-m", f"[HOP] sync release {version} files from {release_branch}")
            self._repo.hgit.push_branch("ho-prod")

            # Return to release branch
            self._repo.hgit.checkout(current_branch)
        except Exception as e:
            # Try to return to release branch even on error
            try:
                self._repo.hgit.checkout(release_branch)
            except:
                pass

            if critical:
                raise PatchManagerError(f"Failed to sync release files to ho-prod: {e}")
            else:
                # Non-critical - just warn
                click.echo(f"⚠️  Warning: Failed to sync release files to ho-prod: {e}")
                click.echo(f"⚠️  You may need to manually sync .hop/releases/ to ho-prod")

    def _get_release_branch_for_patch(self, patch_id: str, *args, **kwargs) -> str:
        """
        Helper to determine release branch for close_patch lock.

        Args:
            patch_id: Patch identifier

        Returns:
            Release branch name (e.g., "ho-release/0.17.0")

        Raises:
            PatchManagerError: If patch not found in candidates
        """
        version = self._find_version_for_candidate(patch_id)
        if not version:
            raise PatchManagerError(
                f"Patch {patch_id} not found in any candidates file.\n"
                f"Available candidates:\n{self._list_all_candidates()}"
            )
        return f"ho-release/{version}"

    def get_patch_close_info(self) -> dict:
        """
        Get all information needed to display before closing a patch.

        Extracts patch_id from current branch, gathers patch information,
        checks synchronization status, and prepares action summary.

        Returns:
            dict with keys:
                - patch_id: Extracted patch identifier
                - current_branch: Current branch name
                - version: Target release version
                - release_branch: Target release branch name
                - readme: README.md content or None
                - files: List of patch files with metadata
                - sync_status: Branch synchronization status
                - actions: List of actions that will be performed

        Raises:
            PatchManagerError: If not on patch branch or patch not in candidates

        Examples:
            info = patch_mgr.get_patch_close_info()
            # Returns all info needed for CLI display
        """
        # 1. Validate we're on a patch branch
        current_branch = self._repo.hgit.branch
        if not current_branch.startswith('ho-patch/'):
            raise PatchManagerError(
                f"Must be on a patch branch to close.\n"
                f"Current branch: {current_branch}\n"
                f"Expected: ho-patch/PATCH_ID"
            )

        # 2. Extract patch_id
        patch_id = current_branch.replace('ho-patch/', '')

        # 3. Find version from candidates
        version = self._find_version_for_candidate(patch_id)
        if not version:
            raise PatchManagerError(
                f"Patch {patch_id} is not in candidates.\n\n"
                f"Possible reasons:\n"
                f"  • Patch was already closed (check stage files)\n"
                f"  • Patch was removed from release\n\n"
                f"To check patch status:\n"
                f"  grep -r '{patch_id}' releases/*.txt"
            )

        release_branch = f"ho-release/{version}"

        # 4. Get README content
        readme = None
        patch_dir = Path(self._repo.base_dir) / "Patches" / patch_id
        readme_file = patch_dir / "README.md"
        if readme_file.exists():
            try:
                readme = readme_file.read_text(encoding='utf-8').strip()
            except Exception:
                pass

        # 5. Get patch files
        files = []
        try:
            structure = self.get_patch_structure(patch_id)
            for patch_file in structure.files:
                file_info = {
                    'name': patch_file.path.name,
                    'is_sql': patch_file.is_sql,
                    'is_python': patch_file.is_python
                }
                files.append(file_info)
        except Exception:
            pass

        # 6. Check synchronization status
        sync_status = self._check_branch_synchronization(current_branch)

        # 7. Prepare actions list
        actions = [
            f"Merge {current_branch} into {release_branch}",
            f"Move patch from candidates to stage",
            f"Delete the patch branch"
        ]

        return {
            'patch_id': patch_id,
            'current_branch': current_branch,
            'version': version,
            'release_branch': release_branch,
            'readme': readme,
            'files': files,
            'sync_status': sync_status,
            'actions': actions
        }

    def _check_branch_synchronization(self, branch_name: str) -> dict:
        """
        Check branch synchronization with origin.

        Args:
            branch_name: Branch to check

        Returns:
            dict with keys:
                - has_remote: bool
                - is_synced: bool or None
                - status: 'synced', 'behind', 'ahead', 'diverged', or 'no_remote'
                - message: Human-readable status message
        """
        try:
            if not self._repo.hgit.has_remote():
                return {
                    'has_remote': False,
                    'is_synced': None,
                    'status': 'no_remote',
                    'message': 'No remote configured (local-only repository)'
                }

            # Fetch to get latest state
            try:
                self._repo.hgit.fetch_from_origin()
            except Exception as e:
                return {
                    'has_remote': True,
                    'is_synced': None,
                    'status': 'fetch_failed',
                    'message': f'Could not fetch from origin: {e}'
                }

            # Check sync status
            is_synced, status = self._repo.hgit.is_branch_synced(branch_name)

            messages = {
                'synced': 'Branch is synchronized with origin',
                'behind': f'Branch is behind origin - updates available',
                'ahead': 'Branch is ahead of origin - unpushed commits',
                'diverged': 'Branch has diverged from origin - manual resolution needed'
            }

            return {
                'has_remote': True,
                'is_synced': is_synced,
                'status': status if status in messages else 'unknown',
                'message': messages.get(status, f'Branch sync status: {status}')
            }

        except Exception as e:
            return {
                'has_remote': True,
                'is_synced': None,
                'status': 'check_failed',
                'message': f'Could not check synchronization: {e}'
            }

    @with_dynamic_branch_lock(lambda self: "ho-prod")
    def close_patch(self) -> dict:
        """
        Close a patch by merging it into the release branch.

        Extracts patch_id from current branch (must be on ho-patch/PATCH_ID).
        This replaces the old add_patch_to_release workflow. Instead of merging
        into ho-prod, we merge into ho-release/X.Y.Z where other patches can
        see the changes.

        Workflow:
        1. Extract patch_id from current branch
        2. Find which release the patch belongs to (from candidates.txt)
        3. Validate patch branch exists
        4. Checkout to ho-release/X.Y.Z
        5. Merge ho-patch/PATCH_ID into ho-release/X.Y.Z
        6. Move patch from candidates.txt to stage.txt
        7. Delete ho-patch/PATCH_ID branch
        8. Commit and push
        9. Notify other candidate patches to sync

        Returns:
            dict with keys:
                - version: Release version
                - patch_id: Patch identifier
                - stage_file: Path to stage file
                - merged_into: Release branch name
                - notified_branches: List of notified patch branches

        Raises:
            PatchManagerError: If not on patch branch, patch not found, or merge fails

        Examples:
            # Must be on ho-patch/456-user-auth
            result = patch_mgr.close_patch()
            # Merges into ho-release/0.17.0, moves to stage
        """
        # 1. Extract patch_id from current branch
        current_branch = self._repo.hgit.branch
        if not current_branch.startswith('ho-patch/'):
            raise PatchManagerError(
                f"Must be on a patch branch to close.\n"
                f"Current branch: {current_branch}\n"
                f"Expected: ho-patch/PATCH_ID"
            )

        patch_id = current_branch.replace('ho-patch/', '')

        # 2. Find version from candidates.txt
        version = self._find_version_for_candidate(patch_id)
        if not version:
            raise PatchManagerError(
                f"Patch {patch_id} not found in any candidates file.\n"
                f"Available candidates:\n{self._list_all_candidates()}"
            )

        release_branch = f"ho-release/{version}"
        patch_branch = f"ho-patch/{patch_id}"

        # 2. Validate patch branch exists
        if not self._repo.hgit.branch_exists(patch_branch):
            raise PatchManagerError(
                f"Patch branch {patch_branch} does not exist.\n"
                f"The patch may have already been closed or deleted."
            )

        # 3. Validate patch before merge (apply + tests)
        self._validate_patch_before_merge(patch_id, version, release_branch, patch_branch)

        # 4. Checkout to release branch
        try:
            self._repo.hgit.checkout(release_branch)
        except Exception as e:
            raise PatchManagerError(f"Failed to checkout {release_branch}: {e}")

        # 5. Merge patch branch into release branch
        try:
            self._repo.hgit.merge(patch_branch, message=f'''[HOP] Merge #{patch_id} into %"{version}"''')
        except Exception as e:
            raise PatchManagerError(
                f"Failed to merge {patch_branch} into {release_branch}: {e}\n"
                f"You may need to resolve conflicts manually."
            )

        # 6. Move from candidates to stage
        self._move_patch_to_stage(patch_id, version)

        # 7. Commit changes on release branch (TOML file is in .hop/releases/)
        # This also syncs .hop/ to all active branches automatically via decorator
        try:
            self._repo.commit_and_sync_to_active_branches(
                message=f"[HOP] move patch #{patch_id} from candidate to stage %{version}"
            )
        except Exception as e:
            raise PatchManagerError(f"Failed to commit/push changes: {e}")

        # 8. Delete patch branch (local and remote)
        try:
            self._repo.hgit.delete_local_branch(patch_branch)
            self._repo.hgit.delete_remote_branch(patch_branch)
        except Exception as e:
            # Non-critical - branch deletion can fail
            click.echo(f"⚠️  Warning: Failed to delete branch {patch_branch}: {e}")

        return {
            'version': version,
            'patch_id': patch_id,
            'patches_file': f"releases/{version}-patches.toml",
            'merged_into': release_branch
        }

    def _validate_patch_before_merge(
        self,
        patch_id: str,
        version: str,
        release_branch: str,
        patch_branch: str
    ) -> None:
        """
        Validate patch before merging by testing in temporary branch.

        Creates a temporary validation branch, merges the patch, runs apply
        to verify no modifications, and optionally runs tests. Ensures patch
        is safe to merge before committing to the release branch.

        Workflow:
        1. Save current branch
        2. Create temporary validation branch from release branch
        3. Merge patch into temp branch
        4. Run patch apply and verify no modifications
        5. Run tests (best-effort if available)
        6. Cleanup temp branch
        7. Return to original branch

        Args:
            patch_id: Patch identifier (e.g., "456-user-auth")
            version: Release version (e.g., "0.17.0")
            release_branch: Release branch name (e.g., "ho-release/0.17.0")
            patch_branch: Patch branch name (e.g., "ho-patch/456-user-auth")

        Raises:
            PatchManagerError: If validation fails (apply modifies files, tests fail, etc.)

        Examples:
            self._validate_patch_before_merge("456", "0.17.0", "ho-release/0.17.0", "ho-patch/456")
            # Creates temp branch, validates, cleans up
        """

        # Save current branch
        original_branch = self._repo.hgit.branch
        temp_branch = f"ho-validate/{patch_id}"

        try:
            click.echo(f"\n🔍 Validating patch {utils.Color.bold(patch_id)} before merge...")

            # 1. Create temporary validation branch from release branch
            click.echo(f"  • Creating temporary validation branch: {temp_branch}")
            self._repo.hgit.checkout(release_branch)
            self._repo.hgit.checkout('-b', temp_branch)

            # 2. Merge patch into temp branch
            click.echo(f"  • Merging {patch_branch} into temp branch...")
            try:
                self._repo.hgit.merge(patch_branch, message=f"[VALIDATE] Test merge #{patch_id}")
            except Exception as e:
                raise PatchManagerError(
                    f"Failed to merge {patch_branch} during validation: {e}\n"
                    f"Please resolve conflicts before closing the patch."
                )

            # 3. Run patch apply and verify no modifications
            click.echo(f"  • Running patch apply to verify idempotency...")
            try:
                # Get list of staged patches for this version from TOML file
                release_file = ReleaseFile(version, Path(self._repo.releases_dir))
                staged_patches = []
                if release_file.exists():
                    staged_patches = release_file.get_patches(status="staged")

                # Apply all staged patches + current patch
                all_patches = staged_patches + [patch_id]

                # Restore database and apply patches
                self._repo.restore_database_from_schema()

                for pid in all_patches:
                    patch_dir = Path(self._repo.base_dir) / "Patches" / pid
                    if patch_dir.exists():
                        self.apply_patch_files(pid, self._repo.model)

                # Generate modules                
                modules.generate(self._repo)

                # Check if any files were modified
                if not self._repo.hgit.repos_is_clean():
                    modified_files = self._repo.hgit.get_modified_files()
                    raise PatchManagerError(
                        f"Patch validation failed: patch apply modified files!\n"
                        f"This indicates the patch is not idempotent or schema is out of sync.\n\n"
                        f"Modified files:\n" + "\n".join(f"  • {f}" for f in modified_files) + "\n\n"
                        f"Actions required:\n"
                        f"  1. Verify patch SQL is idempotent (uses CREATE IF NOT EXISTS, etc.)\n"
                        f"  2. Ensure schema.sql is up to date with all previous patches\n"
                        f"  3. Run 'half_orm dev patch apply' on your patch branch to test"
                    )

                click.echo(f"  • {utils.Color.green('✓')} Patch apply succeeded with no modifications")

            except PatchManagerError:
                raise
            except Exception as e:
                raise PatchManagerError(
                    f"Failed to run patch apply during validation: {e}"
                )

            # 4. Run tests (best-effort)
            self._run_tests_if_available()

            click.echo(f"  • {utils.Color.green('✓')} Validation passed!\n")

        finally:
            # 5. Cleanup: Delete temp branch and return to original branch
            try:
                # Return to original branch
                if self._repo.hgit.branch != original_branch:
                    self._repo.hgit.checkout(original_branch)

                # Delete temp branch if it exists
                if self._repo.hgit.branch_exists(temp_branch):
                    self._repo.hgit.delete_branch(temp_branch, force=True)
            except Exception as e:
                # Cleanup errors are non-critical, just warn
                click.echo(f"⚠️  Warning: Failed to cleanup temp branch {temp_branch}: {e}")

    def _run_tests_if_available(self) -> None:
        """
        Run tests if test configuration is available.

        Detects if the project has test configuration (pytest.ini, pyproject.toml
        with pytest config, etc.) and runs pytest if available.
        - If no test config found: skip silently
        - If tests fail: raise PatchManagerError (BLOCKS workflow)
        - If tests pass: success message
        - If pytest not installed: warning but continue

        This ensures code quality by blocking patches with failing tests.

        Raises:
            PatchManagerError: If tests fail

        Examples:
            self._run_tests_if_available()
            # With tests configured and passing → ✓ Tests passed
            # With tests configured but failing → raises PatchManagerError
            # Without test config → skips silently
        """
        base_dir = Path(self._repo.base_dir)

        # Check if test configuration exists
        test_config_files = [
            base_dir / "pytest.ini",
            base_dir / "pyproject.toml",
            base_dir / "setup.cfg",
            base_dir / "tox.ini"
        ]

        has_test_config = any(f.exists() for f in test_config_files)

        # Also check if tests directory exists
        tests_dir = base_dir / "tests"
        has_tests_dir = tests_dir.exists() and tests_dir.is_dir()

        if not has_test_config and not has_tests_dir:
            # No test config - skip silently (project may not have tests yet)
            return

        # Try to run pytest
        try:
            click.echo(f"  • Running tests...")
            result = subprocess.run(
                ["pytest", "-v", "--tb=short"],
                cwd=str(base_dir),
                capture_output=True,
                text=True
                # No timeout - user can Ctrl+C if needed
                # Cleanup (temp branch + lock) is protected by finally blocks
            )

            if result.returncode == 0:
                click.echo(f"  • {utils.Color.green('✓')} Tests passed")
            else:
                # Tests failed - BLOCK the workflow
                error_msg = f"Tests failed! Cannot close patch with failing tests.\n\n"

                if result.stdout:
                    # Show test output
                    error_msg += "Test output:\n"
                    output_lines = result.stdout.strip().split('\n')
                    # Show last 20 lines to give enough context
                    last_lines = output_lines[-20:] if len(output_lines) > 20 else output_lines
                    for line in last_lines:
                        error_msg += f"  {line}\n"

                if result.stderr:
                    error_msg += f"\nErrors:\n{result.stderr}\n"

                error_msg += "\nFix the failing tests before closing the patch."
                raise PatchManagerError(error_msg)

        except FileNotFoundError:
            # pytest not installed - warn but don't block
            click.echo(f"  • {utils.Color.bold('⚠')} pytest not found (install pytest to run tests)")
        except PatchManagerError:
            # Re-raise our own exceptions (test failures)
            raise
        except Exception as e:
            # Any other error - warn but don't block (might be environment issue)
            click.echo(f"  • {utils.Color.bold('⚠')} Failed to run tests: {e} (continuing anyway)")

        # Note: KeyboardInterrupt (Ctrl+C) is not caught here - it inherits from
        # BaseException, not Exception, so it will propagate up to the decorator
        # where the lock will be properly released in the finally block

    def _validate_on_ho_release(self) -> str:
        """
        Validate that current branch is ho-release/X.Y.Z.

        The create_patch operation must start from a release integration branch
        to allow patches to see each other's changes and support dependencies.

        Returns:
            branch name (e.g., "ho-release/0.17.0")

        Raises:
            PatchManagerError: If not on ho-release/* branch

        Examples:
            branch_name = self._validate_on_ho_release()
            # On ho-release/X.Y.Z → returns "ho-release/X.Y.Z"
            # On main → raises PatchManagerError
        """
        current_branch = self._repo.hgit.branch
        if not current_branch.startswith("ho-release/"):
            raise PatchManagerError(
                "Must be on ho-release/X.Y.Z branch to create patch. "
                f"Current branch: {current_branch}\n"
                "Hint: Run 'half_orm dev release new <level>' first to create a release "
                "or switch to a release branch."
            )

        return current_branch

    def _validate_on_ho_prod(self) -> None:
        """
        Validate that current branch is ho-prod.

        DEPRECATED: Legacy validation for old workflow.
        New workflow uses _validate_on_ho_release() instead.

        Raises:
            PatchManagerError: If not on ho-prod branch

        Examples:
            self._validate_on_ho_prod()
            # Passes if on ho-prod, raises otherwise
        """
        current_branch = self._repo.hgit.branch
        if current_branch != "ho-prod":
            raise PatchManagerError(
                f"Must be on ho-prod branch to create patch. "
                f"Current branch: {current_branch}"
            )

    def _validate_repo_clean(self) -> None:
        """
        Validate that git repository has no uncommitted changes.

        Ensures clean state before creating new patch branch to avoid
        accidentally including unrelated changes in the patch.

        Raises:
            PatchManagerError: If repository has uncommitted changes

        Examples:
            self._validate_repo_clean()
            # Passes if clean, raises if uncommitted changes exist
        """
        if not self._repo.hgit.repos_is_clean():
            raise PatchManagerError(
                "Repository has uncommitted changes. "
                "Commit or stash changes before creating patch."
            )

    def _create_git_branch(self, branch_name: str) -> None:
        """
        Create new git branch from current HEAD.

        Creates the patch branch in git repository. Branch name follows
        the convention: ho-patch/PATCH_ID

        Args:
            branch_name: Full branch name to create (e.g., "ho-patch/456-user-auth")

        Raises:
            PatchManagerError: If branch creation fails or branch already exists

        Examples:
            self._create_git_branch("ho-patch/456-user-auth")
            # Creates branch from current HEAD but doesn't checkout to it
        """
        try:
            # Use HGit checkout proxy to create branch
            self._repo.hgit.checkout('-b', branch_name)
        except GitCommandError as e:
            if "already exists" in str(e):
                raise PatchManagerError(
                    f"Branch already exists: {branch_name}"
                )
            raise PatchManagerError(
                f"Failed to create branch {branch_name}: {e}"
            )

    def _checkout_branch(self, branch_name: str) -> None:
        """
        Checkout to specified branch.

        Switches the working directory to the specified branch.

        Args:
            branch_name: Branch name to checkout (e.g., "ho-patch/456-user-auth")

        Raises:
            PatchManagerError: If checkout fails

        Examples:
            self._checkout_branch("ho-patch/456-user-auth")
            # Working directory now on ho-patch/456-user-auth
        """
        try:
            self._repo.hgit.checkout(branch_name)
        except GitCommandError as e:
            raise PatchManagerError(
                f"Failed to checkout branch {branch_name}: {e}"
            )

    def _validate_has_remote(self) -> None:
        """
        Validate that git remote is configured for patch ID reservation.

        Patch IDs must be globally unique across all developers working
        on the project. Remote configuration is required to push patch
        branches and reserve IDs.

        Raises:
            PatchManagerError: If no git remote configured

        Examples:
            self._validate_has_remote()
            # Raises if no origin remote configured
        """
        if not self._repo.hgit.has_remote():
            raise PatchManagerError(
                "No git remote configured. Cannot reserve patch ID globally.\n"
                "Patch IDs must be globally unique across all developers.\n\n"
                "Configure remote with: git remote add origin <url>"
            )

    def _push_branch_to_reserve_id(self, branch_name: str) -> None:
        """
        Push branch to remote to reserve patch ID globally.

        Pushes the newly created patch branch to remote, ensuring
        the patch ID is reserved and preventing conflicts between
        developers working on different patches.

        Args:
            branch_name: Branch name to push (e.g., "ho-patch/456-user-auth")

        Raises:
            PatchManagerError: If push fails

        Examples:
            self._push_branch_to_reserve_id("ho-patch/456-user-auth")
            # Branch pushed to origin with upstream tracking
        """
        try:
            self._repo.hgit.push_branch(branch_name, set_upstream=True)
        except Exception as e:
            raise PatchManagerError(
                f"Failed to push branch {branch_name} to remote: {e}\n"
                "Patch ID reservation requires successful push to origin.\n"
                "Check network connection and remote access permissions."
            )

    def _check_patch_id_available(self, patch_id: str) -> None:
        """
        Check if patch number is available via tag lookup.

        Fetches tags and checks if reservation tag exists.
        Much more efficient than scanning all branches.

        Args:
            patch_id: Full patch ID (e.g., "456-user-auth")

        Raises:
            PatchManagerError: If patch number already reserved

        Examples:
            self._check_patch_id_available("456-user-auth")
            # Checks if tag ho-patch/456 exists
        """
        try:
            # Fetch latest tags from remote
            self._repo.hgit.fetch_tags()
        except Exception as e:
            raise PatchManagerError(
                f"Failed to fetch tags from remote: {e}\n"
                f"Cannot verify patch number availability.\n"
                f"Check network connection and remote access."
            )

        # Extract patch number
        patch_number = patch_id.split('-')[0]
        tag_name = f"ho-patch/{patch_number}"

        # Check if reservation tag exists
        if self._repo.hgit.tag_exists(tag_name):
            raise PatchManagerError(
                f"Patch number {patch_number} already reserved.\n"
                f"Tag {tag_name} exists on remote.\n"
                f"Another developer is using this patch number.\n"
                f"Choose a different patch number."
            )


    def _create_reservation_tag(self, patch_id: str, description: Optional[str] = None) -> None:
        """
        Create and push tag to reserve patch number.

        Creates tag ho-patch/{number} to globally reserve the patch number.
        This prevents other developers from using the same number.

        Args:
            patch_id: Full patch ID (e.g., "456-user-auth")
            description: Optional description for tag message

        Raises:
            PatchManagerError: If tag creation/push fails

        Examples:
            self._create_reservation_tag("456-user-auth", "Add user authentication")
            # Creates and pushes tag ho-patch/456
        """
        # Extract patch number
        patch_number = patch_id.split('-')[0]
        tag_name = f"ho-patch/{patch_number}"

        # Create tag message
        if description:
            tag_message = f"Patch {patch_number}: {description}"
        else:
            tag_message = f"Patch {patch_number} reserved"

        try:
            # Create tag locally
            self._repo.hgit.create_tag(tag_name, tag_message)

            # Push tag to reserve globally
            self._repo.hgit.push_tag(tag_name)
        except Exception as e:
            raise PatchManagerError(
                f"Failed to create reservation tag {tag_name}: {e}\n"
                f"Patch number reservation failed."
            )


    def _validate_branch_synced_with_origin(self, branch: str) -> None:
        """
        Validate that local release branch is synchronized with origin.

        Prevents creating branch on an outdated integration branch.

        Args:
            branch: branch name (e.g., "ho-release/0.17.0", "ho-prod", ...)

        Raises:
            PatchManagerError: If branch is not synced with origin

        Examples:
            self._validate_branch_synced_with_origin("ho-release/0.17.0")
            # Passes if synced, raises otherwise
        """
        try:
            # Check sync status with origin
            is_synced, status = self._repo.hgit.is_branch_synced(branch, remote="origin")

            if is_synced:
                return

            # Not synced - provide specific guidance
            if status == "ahead":
                raise PatchManagerError(
                    f"{branch} is ahead of origin/{branch}.\n"
                    f"Push your local commits before creating patch:\n"
                    f"  git push origin {branch}"
                )
            elif status == "behind":
                raise PatchManagerError(
                    f"{branch} is behind origin/{branch}.\n"
                    f"Pull remote commits before creating patch:\n"
                    f"  git pull origin {branch}"
                )
            elif status == "diverged":
                raise PatchManagerError(
                    f"{branch} has diverged from origin/{branch}.\n"
                    f"Resolve conflicts before creating patch:\n"
                    f"  git pull --rebase origin {branch}"
                )
            else:
                raise PatchManagerError(
                    f"{branch} sync check failed with status: {status}\n"
                    f"Ensure {branch} is synchronized with origin."
                )

        except GitCommandError as e:
            raise PatchManagerError(
                f"Failed to check {branch} sync status: {e}\n"
                "Ensure origin remote is configured and accessible."
            )
        except PatchManagerError:
            raise
        except Exception as e:
            raise PatchManagerError(
                f"Unexpected error checking {branch} sync: {e}"
            )


    def _add_patch_to_candidates(self, patch_id: str, version: str, before: str = None) -> None:
        """
        Add patch ID to X.Y.Z-patches.toml file as candidate.

        Automatically tracks patches in development by adding to the patches file.

        Args:
            patch_id: Normalized patch identifier (e.g., "456-user-auth")
            version: Release version (e.g., "0.17.0")
            before: Optional patch ID to insert before

        Raises:
            PatchManagerError: If patches file doesn't exist or write fails

        Examples:
            self._add_patch_to_candidates("456-user-auth", "0.17.0")
            # Adds "456-user-auth" = "candidate" to releases/0.17.0-patches.toml

            self._add_patch_to_candidates("456-user-auth", "0.17.0", before="457-feature")
            # Inserts before "457-feature"
        """
        release_file = ReleaseFile(version, self._releases_dir)

        try:
            release_file.add_patch(patch_id, before=before)
        except ReleaseFileError as e:
            raise PatchManagerError(str(e))

    def _commit_patch_metadata_to_candidates(
        self,
        patch_id: str,
        version: str,
        description: Optional[str] = None
    ) -> None:
        """
        Commit only patches file metadata to release branch (without Patches/ directory).

        This is the first commit on ho-release/X.Y.Z that reserves the patch ID
        in the patches file, but doesn't include the Patches/PATCH_ID directory yet.
        The directory will be created later on the patch branch.

        Args:
            patch_id: Normalized patch identifier
            version: Release version
            description: Optional description for commit message

        Raises:
            PatchManagerError: If commit fails

        Examples:
            self._commit_patch_metadata_to_candidates("456-user-auth", "0.17.0", "Add auth")
            # Commits with message: "[HOP] Add patch #456-user-auth to %0.17.0 candidates"
        """
        try:
            release_file = ReleaseFile(version, self._releases_dir)
            self._repo.hgit.add(str(release_file.file_path))

            # Construct commit message
            msg = f"[HOP] Add patch #{patch_id} to %{version} candidates"
            if description:
                msg += f"\n\n{description}"

            # Commit only the patches file (no Patches/ directory)
            self._repo.hgit.commit("-m", msg)

        except Exception as e:
            raise PatchManagerError(
                f"Failed to commit patch metadata to candidates: {e}"
            )

    def _commit_patch_directory_to_branch(
        self,
        patch_id: str,
        description: Optional[str] = None
    ) -> None:
        """
        Commit Patches/PATCH_ID directory on patch branch.

        This is the second commit that happens on the ho-patch/PATCH_ID branch,
        creating the actual Patches/PATCH_ID directory structure isolated to this branch.

        Args:
            patch_id: Normalized patch identifier
            description: Optional description for commit message

        Raises:
            PatchManagerError: If commit fails

        Examples:
            self._commit_patch_directory_to_branch("456-user-auth", "Add auth")
            # Commits with message: "[HOP] Create patch directory for 456-user-auth"
        """
        try:
            # Construct commit message
            msg = f"[HOP] Create patch directory for {patch_id}"
            if description:
                msg += f"\n\n{description}"

            # Commit the Patches/ directory on patch branch
            self._repo.hgit.commit("-m", msg)

        except Exception as e:
            raise PatchManagerError(
                f"Failed to commit patch directory to branch: {e}"
            )

    def _find_version_for_candidate(self, patch_id: str) -> Optional[str]:
        """
        Find which release version a patch belongs to from patches files.

        Searches all X.Y.Z-patches.toml files in releases/ directory to find
        which release the patch is assigned to.

        Args:
            patch_id: Patch identifier to search for

        Returns:
            Version string (e.g., "0.17.0") or None if not found

        Examples:
            version = self._find_version_for_candidate("456-user-auth")
            # Returns "0.17.0" if found in 0.17.0-patches.toml
        """
        patches_files = self._releases_dir.glob("*-patches.toml")

        for patches_file in patches_files:
            # Extract version from filename (X.Y.Z-patches.toml → X.Y.Z)
            version = patches_file.stem.replace('-patches', '')
            release_file = ReleaseFile(version, self._releases_dir)

            status = release_file.get_patch_status(patch_id)
            if status is not None:
                return version

        return None

    def _list_all_candidates(self) -> str:
        """
        List all candidate patches across all releases for error messages.

        Returns:
            Formatted string showing all releases and their candidates

        Examples:
            candidates = self._list_all_candidates()
            # Returns:
            # "Release 0.17.0:\n  - 456-user-auth\n  - 457-feature-x"
        """
        patches_files = sorted(self._releases_dir.glob("*-patches.toml"))

        if not patches_files:
            return "No releases with candidates found."

        lines = []
        for patches_file in patches_files:
            version = patches_file.stem.replace('-patches', '')
            release_file = ReleaseFile(version, self._releases_dir)

            candidates = release_file.get_patches(status="candidate")

            if candidates:
                lines.append(f"Release {version}:")
                for patch in candidates:
                    lines.append(f"  - {patch}")
            else:
                lines.append(f"Release {version}: (no candidates)")

        return '\n'.join(lines)

    def _move_patch_to_stage(self, patch_id: str, version: str) -> None:
        """
        Move patch from candidate to staged status.

        Changes the patch status from "candidate" to "staged" in the TOML file,
        preserving its position (order) in the file.

        Args:
            patch_id: Patch identifier to move
            version: Release version

        Raises:
            PatchManagerError: If operation fails

        Examples:
            self._move_patch_to_stage("456-user-auth", "0.17.0")
            # Changes "456-user-auth" = "candidate" to "456-user-auth" = "staged"
            # Order is preserved!
        """
        release_file = ReleaseFile(version, self._releases_dir)

        try:
            release_file.move_to_staged(patch_id)

            # Stage file for commit
            self._repo.hgit.add(str(release_file.file_path))

        except ReleaseFileError as e:
            raise PatchManagerError(str(e))
        except Exception as e:
            raise PatchManagerError(
                f"Failed to move patch to staged: {e}"
            )

    def _get_other_candidates(self, version: str, exclude_patch: str) -> List[str]:
        """
        Get list of other candidate patches for a release (excluding one).

        Used to notify other developers that they should sync their patches
        after one patch is closed.

        Args:
            version: Release version
            exclude_patch: Patch ID to exclude from the list

        Returns:
            List of patch IDs that are still candidates

        Examples:
            others = self._get_other_candidates("0.17.0", "456-user-auth")
            # Returns ["457-feature-x", "458-bugfix"] if they exist
        """
        release_file = ReleaseFile(version, self._releases_dir)

        if not release_file.exists():
            return []

        candidates = release_file.get_patches(status="candidate")
        return [p for p in candidates if p != exclude_patch]
