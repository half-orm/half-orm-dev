"""
PatchManager module for half-orm-dev

Manages Patches/patch-name/ directory structure, SQL/Python files,
and README.md generation for the patch-centric workflow.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from git.exc import GitCommandError

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
        self._releases_dir = base_path / "releases"

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
        from half_orm_dev import modules

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

        UPDATED FOR NEW WORKFLOW: Now handles commit on ho-prod (not on branch).

        Rollback operations (best-effort, continues on individual failures):
        1. Ensure we're on initial branch (ho-prod)
        2. Reset commit if it was created (git reset --hard HEAD~1)
        3. Delete patch branch if it was created (may not exist in new workflow)
        4. Delete patch tag (local)
        5. Delete patch directory (if created)

        Note: This method is only called when tag push has NOT succeeded yet.
        Once tag is pushed, rollback is not performed as the patch number is
        already globally reserved.

        Args:
            initial_branch: Branch to return to (usually "ho-prod")
            branch_name: Patch branch name (e.g., "ho-patch/456-user-auth")
            patch_id: Patch identifier for tag/directory cleanup
            patch_dir: Path to patch directory if it was created
            commit_created: Whether commit was created on ho-prod (NEW)

        Examples:
            # NEW WORKFLOW: Rollback with commit on ho-prod
            self._rollback_patch_creation(
                "ho-prod",
                "ho-patch/456-user-auth",
                "456-user-auth",
                Path("Patches/456-user-auth"),
                commit_created=True  # NEW: commit was made on ho-prod
            )
            # Reverts commit, deletes tag/directory, returns to clean state

            # OLD WORKFLOW (still supported): Rollback with commit on branch
            self._rollback_patch_creation(
                "ho-prod",
                "ho-patch/456-user-auth",
                "456-user-auth",
                Path("Patches/456-user-auth"),
                commit_created=False  # No commit on ho-prod
            )
        """
        # Best-effort cleanup - continue even if individual operations fail

        # 1. Ensure we're on initial branch (usually ho-prod)
        # ALWAYS checkout to ensure we're on the right branch for reset
        try:
            self._repo.hgit.checkout(initial_branch)
        except Exception:
            # Continue cleanup even if checkout fails
            pass

        # 2. Reset commit if it was created on ho-prod (NEW WORKFLOW)
        if commit_created:
            try:
                # Hard reset to remove the commit
                # Using git reset --hard HEAD~1
                self._repo.hgit._HGit__git_repo.git.reset('--hard', 'HEAD~1')
            except Exception:
                # Continue cleanup even if reset fails
                pass

        # 3. Delete patch branch (may not exist if failure before branch creation)
        try:
            self._repo.hgit.delete_local_branch(branch_name)
        except Exception:
            # Branch may not exist yet or deletion may fail - continue
            pass

        # 4. Delete local tag
        patch_number = patch_id.split('-')[0]
        tag_name = f"ho-patch/{patch_number}"
        try:
            self._repo.hgit.delete_local_tag(tag_name)
        except Exception:
            # Tag may not exist yet or deletion may fail - continue
            pass

        # 5. Delete patch directory (if created)
        if patch_dir and patch_dir.exists():
            try:
                import shutil
                shutil.rmtree(patch_dir)
            except Exception:
                # Directory deletion may fail (permissions, etc.) - continue
                pass

    def create_patch(self, patch_id: str, description: Optional[str] = None) -> dict:
        """
        Create new patch with atomic tag-first reservation strategy.

        Orchestrates the full patch creation workflow with transactional guarantees:
        1. Validates we're on ho-release/X.Y.Z branch
        2. Validates repository is clean
        3. Validates git remote is configured
        4. Validates and normalizes patch ID format
        5. **ACQUIRES DISTRIBUTED LOCK on ho-release/X.Y.Z** (30min timeout)
        6. Fetches all references from remote (branches + tags) - with lock
        6.5 Validates ho-release is synced with origin
        7. Checks patch number available via tag lookup (with up-to-date state)
        8. Creates Patches/PATCH_ID/ directory (on ho-release/X.Y.Z)
        8.5. **Adds PATCH_ID to X.Y.Z-candidates.txt** (NEW)
        9. Commits changes on ho-release/X.Y.Z "[HOP] Add patch {patch_id} to candidates"
        10. Creates local tag ho-patch/{number} (points to commit on ho-release)
        11. **Pushes tag to reserve number globally** ← POINT OF NO RETURN
        12. Creates ho-patch/PATCH_ID branch from current commit
        13. Pushes branch to remote (with retry)
        14. **RELEASES LOCK** (always, even on error)
        15. Checkouts to new patch branch

        Transactional guarantees:
        - Failure before step 10 (tag push): Complete rollback to initial state
        - Success at step 10 (tag push): Patch reserved, no rollback even if branch push fails
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

        Returns:
            dict: Creation result with keys:
                - patch_id: Normalized patch identifier
                - branch_name: Created branch name
                - patch_dir: Path to patch directory
                - on_branch: Current branch after checkout
                - version: Release version (e.g., "0.17.0")

        Raises:
            PatchManagerError: If validation fails or creation errors occur

        Examples:
            # On branch ho-release/0.17.0:
            result = patch_mgr.create_patch("456-user-auth")
            # Creates patch, adds to 0.17.0-candidates.txt

            result = patch_mgr.create_patch("456", "Add authentication")
            # With description for README and commits
        """
        # Step 1-3: Validate context
        release_version = self._validate_on_ho_release()  # NEW: returns version
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
        release_branch = f"ho-release/{release_version}"
        patch_dir = None
        commit_created = False
        tag_pushed = False
        modifications_started = False  # Track if we started making changes
        branch_name = f"ho-patch/{normalized_id}"
        try:
            # Step 5: ACQUIRE LOCK on ho-release/X.Y.Z (with 30 min timeout for stale locks)
            lock_tag = self._repo.hgit.acquire_branch_lock(release_branch, timeout_minutes=30)

            # Step 6: Fetch all references from remote (branches + tags) - with lock held
            self._fetch_from_remote()

            # Step 6.5: Validate ho-release/X.Y.Z is synced with origin
            self._validate_release_branch_synced_with_origin(release_branch)

            # Step 7: Check patch number available (via tag, with up-to-date state)
            self._check_patch_id_available(normalized_id)

            # === LOCAL OPERATIONS ON HO-RELEASE (rollback on failure) ===
            modifications_started = True  # From here, rollback is needed on failure

            # Step 7: Create patch directory (on ho-release/X.Y.Z, not on branch!)
            patch_dir = self.create_patch_directory(normalized_id)

            # Step 7b: Update README if description provided
            if description:
                self._update_readme_with_description(patch_dir, normalized_id, description)

            # Step 8: Add patch to candidates.txt (NEW)
            self._add_patch_to_candidates(normalized_id, release_version)

            # Step 9: Commit patch directory and candidates file ON HO-RELEASE
            self._commit_patch_to_candidates(normalized_id, release_version, description)
            commit_created = True  # Track that commit was made

            # Step 10: Create local tag (points to commit on ho-release with Patches/)
            self._create_local_tag(normalized_id, description)

            # === REMOTE OPERATIONS (point of no return) ===

            # Step 11: Push tag FIRST → ATOMIC RESERVATION
            self._push_tag_to_reserve_number(normalized_id)
            self._repo.hgit.push_branch(release_branch)
            tag_pushed = True  # Tag pushed = point of no return
            # ✅ If we reach here: patch number globally reserved!

            # === BRANCH CREATION (after reservation) ===

            # Step 11: Create branch FROM current commit (after tag push)
            self._create_git_branch(branch_name)

            # Step 12: Push branch (with retry)
            try:
                self._push_branch_to_remote(branch_name)
            except PatchManagerError as e:
                # Tag already pushed = success, just warn about branch
                import click
                click.echo(f"⚠️  Warning: Branch push failed after 3 attempts")
                click.echo(f"⚠️  Patch {normalized_id} is reserved (tag pushed successfully)")
                click.echo(f"⚠️  Push branch manually: git push -u origin {branch_name}")
                # Don't raise - tag pushed means success

            # Step 13: Checkout to new branch (non-critical, warn if fails)
            try:
                self._checkout_branch(branch_name)
            except Exception as e:
                import click
                click.echo(f"⚠️  Checkout failed but patch created successfully")
                click.echo(f"Run: git checkout {branch_name}")

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

        finally:
            # ALWAYS release lock (even on error)
            self._repo.hgit.release_branch_lock(lock_tag)

        # Return result
        return {
            'patch_id': normalized_id,
            'branch_name': branch_name,
            'patch_dir': patch_dir,
            'on_branch': branch_name,
            'version': release_version  # NEW: include release version
        }

    def close_patch(self, patch_id: str) -> dict:
        """
        Close a patch by merging it into the release branch.

        This replaces the old add_patch_to_release workflow. Instead of merging
        into ho-prod, we merge into ho-release/X.Y.Z where other patches can
        see the changes.

        Workflow:
        1. Find which release the patch belongs to (from candidates.txt)
        2. Validate patch branch exists
        3. Checkout to ho-release/X.Y.Z
        4. Merge ho-patch/PATCH_ID into ho-release/X.Y.Z
        5. Move patch from candidates.txt to stage.txt
        6. Delete ho-patch/PATCH_ID branch
        7. Commit and push
        8. Notify other candidate patches to sync

        Args:
            patch_id: Patch identifier (e.g., "456-user-auth")

        Returns:
            dict with keys:
                - version: Release version
                - patch_id: Patch identifier
                - stage_file: Path to stage file
                - merged_into: Release branch name
                - notified_branches: List of notified patch branches

        Raises:
            PatchManagerError: If patch not found or merge fails

        Examples:
            result = patch_mgr.close_patch("456-user-auth")
            # Merges into ho-release/0.17.0, moves to stage
        """
        # 1. Find version from candidates.txt
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

        # 3. Checkout to release branch
        try:
            self._repo.hgit.checkout(release_branch)
        except Exception as e:
            raise PatchManagerError(f"Failed to checkout {release_branch}: {e}")

        # 4. Merge patch branch into release branch
        try:
            self._repo.hgit.merge(patch_branch)
        except Exception as e:
            raise PatchManagerError(
                f"Failed to merge {patch_branch} into {release_branch}: {e}\n"
                f"You may need to resolve conflicts manually."
            )

        # 5. Move from candidates to stage
        self._move_patch_to_stage(patch_id, version)

        # 6. Commit changes
        try:
            self._repo.hgit.commit("-m", f"[HOP] Close patch {patch_id} for {version}")
            self._repo.hgit.push_branch(release_branch)
        except Exception as e:
            raise PatchManagerError(f"Failed to commit/push changes: {e}")

        # 7. Delete patch branch (local and remote)
        try:
            self._repo.hgit.delete_local_branch(patch_branch)
            self._repo.hgit.delete_remote_branch(patch_branch)
        except Exception as e:
            # Non-critical - branch deletion can fail
            import click
            click.echo(f"⚠️  Warning: Failed to delete branch {patch_branch}: {e}")

        # 8. Get other candidates for notification
        other_candidates = self._get_other_candidates(version, patch_id)

        return {
            'version': version,
            'patch_id': patch_id,
            'stage_file': f"releases/{version}-stage.txt",
            'merged_into': release_branch,
            'notified_branches': other_candidates
        }

    def _validate_on_ho_release(self) -> str:
        """
        Validate that current branch is ho-release/X.Y.Z.

        The create_patch operation must start from a release integration branch
        to allow patches to see each other's changes and support dependencies.

        Returns:
            Version string extracted from branch name (e.g., "0.17.0")

        Raises:
            PatchManagerError: If not on ho-release/* branch

        Examples:
            version = self._validate_on_ho_release()
            # On ho-release/0.17.0 → returns "0.17.0"
            # On main → raises PatchManagerError
        """
        current_branch = self._repo.hgit.branch
        if not current_branch.startswith("ho-release/"):
            raise PatchManagerError(
                f"Must be on ho-release/X.Y.Z branch to create patch. "
                f"Current branch: {current_branch}\n"
                f"Hint: Run 'half_orm dev release new <level>' first to create a release"
            )

        # Extract version from branch name (ho-release/X.Y.Z → X.Y.Z)
        version = current_branch.replace("ho-release/", "")
        return version

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


    def _validate_ho_prod_synced_with_origin(self) -> None:
        """
        Validate that local ho-prod is synchronized with origin/ho-prod.

        Prevents creating patches on an outdated or unsynchronized base which
        would cause merge conflicts, inconsistent patch history, and potential
        data loss. Must be called after fetch_from_origin() to ensure accurate
        comparison.

        Sync requirements:
        - Local ho-prod must be at the same commit as origin/ho-prod (synced)
        - If ahead: Must push local commits before creating patch
        - If behind: Must pull remote commits before creating patch
        - If diverged: Must resolve conflicts before creating patch

        Raises:
            PatchManagerError: If ho-prod is not synced with origin with specific
                guidance on how to resolve the sync issue

        Examples:
            # Successful validation (synced)
            self._fetch_from_remote()
            self._validate_ho_prod_synced_with_origin()
            # Continues to patch creation

            # Failed validation (behind)
            try:
                self._validate_ho_prod_synced_with_origin()
            except PatchManagerError as e:
                # Error: "ho-prod is behind origin/ho-prod. Run: git pull"

            # Failed validation (ahead)
            try:
                self._validate_ho_prod_synced_with_origin()
            except PatchManagerError as e:
                # Error: "ho-prod is ahead of origin/ho-prod. Run: git push"

            # Failed validation (diverged)
            try:
                self._validate_ho_prod_synced_with_origin()
            except PatchManagerError as e:
                # Error: "ho-prod has diverged from origin/ho-prod.
                #         Resolve conflicts first."
        """
        try:
            # Check sync status with origin
            is_synced, status = self._repo.hgit.is_branch_synced("ho-prod", remote="origin")

            if is_synced:
                # All good - ho-prod is synced with origin
                return

            # Not synced - provide specific guidance based on status
            if status == "ahead":
                raise PatchManagerError(
                    "ho-prod is ahead of origin/ho-prod.\n"
                    "Push your local commits before creating patch:\n"
                    "  git push origin ho-prod"
                )
            elif status == "behind":
                raise PatchManagerError(
                    "ho-prod is behind origin/ho-prod.\n"
                    "Pull remote commits before creating patch:\n"
                    "  git pull origin ho-prod"
                )
            elif status == "diverged":
                raise PatchManagerError(
                    "ho-prod has diverged from origin/ho-prod.\n"
                    "Resolve conflicts before creating patch:\n"
                    "  git pull --rebase origin ho-prod\n"
                    "  or\n"
                    "  git pull origin ho-prod (and resolve merge conflicts)"
                )
            else:
                # Unknown status - generic error
                raise PatchManagerError(
                    f"ho-prod sync check failed with status: {status}\n"
                    "Ensure ho-prod is synchronized with origin before creating patch."
                )

        except GitCommandError as e:
            raise PatchManagerError(
                f"Failed to check ho-prod sync status: {e}\n"
                "Ensure origin remote is configured and accessible."
            )
        except PatchManagerError:
            # Re-raise PatchManagerError as-is
            raise
        except Exception as e:
            raise PatchManagerError(
                f"Unexpected error checking ho-prod sync: {e}"
            )

    def _validate_release_branch_synced_with_origin(self, release_branch: str) -> None:
        """
        Validate that local release branch is synchronized with origin.

        Similar to _validate_ho_prod_synced_with_origin but for ho-release/X.Y.Z branches.
        Prevents creating patches on an outdated release integration branch.

        Args:
            release_branch: Release branch name (e.g., "ho-release/0.17.0")

        Raises:
            PatchManagerError: If branch is not synced with origin

        Examples:
            self._validate_release_branch_synced_with_origin("ho-release/0.17.0")
            # Passes if synced, raises otherwise
        """
        try:
            # Check sync status with origin
            is_synced, status = self._repo.hgit.is_branch_synced(release_branch, remote="origin")

            if is_synced:
                return

            # Not synced - provide specific guidance
            if status == "ahead":
                raise PatchManagerError(
                    f"{release_branch} is ahead of origin/{release_branch}.\n"
                    f"Push your local commits before creating patch:\n"
                    f"  git push origin {release_branch}"
                )
            elif status == "behind":
                raise PatchManagerError(
                    f"{release_branch} is behind origin/{release_branch}.\n"
                    f"Pull remote commits before creating patch:\n"
                    f"  git pull origin {release_branch}"
                )
            elif status == "diverged":
                raise PatchManagerError(
                    f"{release_branch} has diverged from origin/{release_branch}.\n"
                    f"Resolve conflicts before creating patch:\n"
                    f"  git pull --rebase origin {release_branch}"
                )
            else:
                raise PatchManagerError(
                    f"{release_branch} sync check failed with status: {status}\n"
                    f"Ensure {release_branch} is synchronized with origin."
                )

        except GitCommandError as e:
            raise PatchManagerError(
                f"Failed to check {release_branch} sync status: {e}\n"
                "Ensure origin remote is configured and accessible."
            )
        except PatchManagerError:
            raise
        except Exception as e:
            raise PatchManagerError(
                f"Unexpected error checking {release_branch} sync: {e}"
            )

    def _add_patch_to_candidates(self, patch_id: str, version: str) -> None:
        """
        Add patch ID to X.Y.Z-candidates.txt file.

        Automatically tracks patches in development by appending to the candidates file.
        Creates one line per patch: "PATCH_ID # Optional comment"

        Args:
            patch_id: Normalized patch identifier (e.g., "456-user-auth")
            version: Release version (e.g., "0.17.0")

        Raises:
            PatchManagerError: If candidates file doesn't exist or write fails

        Examples:
            self._add_patch_to_candidates("456-user-auth", "0.17.0")
            # Appends "456-user-auth\n" to releases/0.17.0-candidates.txt
        """
        candidates_file = self._releases_dir / f"{version}-candidates.txt"

        if not candidates_file.exists():
            raise PatchManagerError(
                f"Candidates file not found: {candidates_file}\n"
                f"Hint: Run 'half_orm dev release new <level>' first"
            )

        try:
            # Append patch ID to candidates file
            with candidates_file.open('a', encoding='utf-8') as f:
                f.write(f"{patch_id}\n")
        except Exception as e:
            raise PatchManagerError(
                f"Failed to add patch to candidates file: {e}"
            )

    def _commit_patch_to_candidates(
        self,
        patch_id: str,
        version: str,
        description: Optional[str] = None
    ) -> None:
        """
        Commit patch directory and candidates file to release branch.

        Replaces _commit_patch_directory for the new workflow. Commits both
        the Patches/PATCH_ID directory and the updated X.Y.Z-candidates.txt file.

        Args:
            patch_id: Normalized patch identifier
            version: Release version
            description: Optional description for commit message

        Raises:
            PatchManagerError: If commit fails

        Examples:
            self._commit_patch_to_candidates("456-user-auth", "0.17.0", "Add auth")
            # Commits with message: "[HOP] Add patch 456-user-auth to 0.17.0 candidates"
        """
        try:
            # Construct commit message
            msg = f"[HOP] Add patch {patch_id} to {version} candidates"
            if description:
                msg += f"\n\n{description}"

            # Commit both Patches/ directory and candidates file
            self._repo.hgit.commit("-m", msg)

        except Exception as e:
            raise PatchManagerError(
                f"Failed to commit patch to candidates: {e}"
            )

    def _find_version_for_candidate(self, patch_id: str) -> Optional[str]:
        """
        Find which release version a patch belongs to from candidates files.

        Searches all X.Y.Z-candidates.txt files in releases/ directory to find
        which release the patch is assigned to.

        Args:
            patch_id: Patch identifier to search for

        Returns:
            Version string (e.g., "0.17.0") or None if not found

        Examples:
            version = self._find_version_for_candidate("456-user-auth")
            # Returns "0.17.0" if found in 0.17.0-candidates.txt
        """
        candidates_files = self._releases_dir.glob("*-candidates.txt")

        for candidates_file in candidates_files:
            content = candidates_file.read_text(encoding='utf-8').strip()
            if not content:
                continue

            patches = [line.strip() for line in content.split('\n') if line.strip()]
            if patch_id in patches:
                # Extract version from filename (X.Y.Z-candidates.txt → X.Y.Z)
                version = candidates_file.stem.replace('-candidates', '')
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
        candidates_files = sorted(self._releases_dir.glob("*-candidates.txt"))

        if not candidates_files:
            return "No releases with candidates found."

        lines = []
        for candidates_file in candidates_files:
            version = candidates_file.stem.replace('-candidates', '')
            content = candidates_file.read_text(encoding='utf-8').strip()

            if content:
                patches = [line.strip() for line in content.split('\n') if line.strip()]
                lines.append(f"Release {version}:")
                for patch in patches:
                    lines.append(f"  - {patch}")
            else:
                lines.append(f"Release {version}: (no candidates)")

        return '\n'.join(lines)

    def _move_patch_to_stage(self, patch_id: str, version: str) -> None:
        """
        Move patch from candidates.txt to stage.txt.

        Removes the patch from X.Y.Z-candidates.txt and appends it to
        X.Y.Z-stage.txt, indicating it has been integrated.

        Args:
            patch_id: Patch identifier to move
            version: Release version

        Raises:
            PatchManagerError: If file operations fail

        Examples:
            self._move_patch_to_stage("456-user-auth", "0.17.0")
            # Removes from 0.17.0-candidates.txt, adds to 0.17.0-stage.txt
        """
        candidates_file = self._releases_dir / f"{version}-candidates.txt"
        stage_file = self._releases_dir / f"{version}-stage.txt"

        try:
            # Read candidates
            candidates_content = candidates_file.read_text(encoding='utf-8').strip()
            candidates = [line.strip() for line in candidates_content.split('\n') if line.strip()]

            # Remove patch from candidates
            if patch_id not in candidates:
                raise PatchManagerError(
                    f"Patch {patch_id} not found in {candidates_file.name}"
                )

            candidates.remove(patch_id)

            # Write back candidates (empty or updated list)
            candidates_file.write_text('\n'.join(candidates) + '\n' if candidates else '', encoding='utf-8')

            # Append to stage
            with stage_file.open('a', encoding='utf-8') as f:
                f.write(f"{patch_id}\n")

            # Stage both files for commit
            self._repo.hgit.add(str(candidates_file))
            self._repo.hgit.add(str(stage_file))

        except PatchManagerError:
            raise
        except Exception as e:
            raise PatchManagerError(
                f"Failed to move patch from candidates to stage: {e}"
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
        candidates_file = self._releases_dir / f"{version}-candidates.txt"

        if not candidates_file.exists():
            return []

        content = candidates_file.read_text(encoding='utf-8').strip()
        if not content:
            return []

        patches = [line.strip() for line in content.split('\n') if line.strip()]
        return [p for p in patches if p != exclude_patch]