"""
Module for managing TOML-based release tracking files.

This module handles the X.Y.Z-patches.toml files that track patches
during development (candidate and staged status).
"""

from pathlib import Path
from typing import List, Optional, Dict
import sys

try:
    import tomli
except ImportError:
    # Python 3.11+ has tomllib in stdlib
    import tomllib as tomli

try:
    import tomli_w
except ImportError:
    raise ImportError(
        "tomli_w is required for writing TOML files. "
        "Install it with: pip install tomli_w"
    )


class ReleaseFileError(Exception):
    """Raised when release file operations fail."""
    pass


class ReleaseFile:
    """
    Manage TOML release tracking files (X.Y.Z-patches.toml).

    This class handles the single source of truth for patch tracking during
    development, replacing the old dual-file system (candidates.txt + stage.txt).

    File format:
        [patches]
        "1-auth" = "candidate"
        "2-api" = "staged"

    The order of patches in the file is preserved and represents the application order.
    """

    def __init__(self, version: str, releases_dir: Path):
        """
        Initialize ReleaseFile for a specific version.

        Args:
            version: Release version (e.g., "0.17.0")
            releases_dir: Path to releases directory (e.g., .hop/releases/)
        """
        self.version = version
        self.releases_dir = Path(releases_dir)
        self.file_path = self.releases_dir / f"{version}-patches.toml"

    def create_empty(self) -> None:
        """
        Create empty TOML file with [patches] section.

        Raises:
            ReleaseFileError: If file creation fails
        """
        try:
            self.releases_dir.mkdir(parents=True, exist_ok=True)
            data = {"patches": {}}
            with self.file_path.open('wb') as f:
                tomli_w.dump(data, f)
        except Exception as e:
            raise ReleaseFileError(
                f"Failed to create release file {self.file_path}: {e}"
            )

    def _read(self) -> Dict:
        """
        Read TOML file and return data.

        Returns:
            Dict with 'patches' key containing ordered dict of patches

        Raises:
            ReleaseFileError: If file doesn't exist or read fails
        """
        if not self.file_path.exists():
            raise ReleaseFileError(
                f"Release file not found: {self.file_path}\n"
                f"Hint: Run 'half_orm dev release new <level>' first"
            )

        try:
            with self.file_path.open('rb') as f:
                return tomli.load(f)
        except Exception as e:
            raise ReleaseFileError(
                f"Failed to read release file {self.file_path}: {e}"
            )

    def _write(self, data: Dict) -> None:
        """
        Write data to TOML file, preserving order.

        Args:
            data: Dict with 'patches' key

        Raises:
            ReleaseFileError: If write fails
        """
        try:
            with self.file_path.open('wb') as f:
                tomli_w.dump(data, f)
        except Exception as e:
            raise ReleaseFileError(
                f"Failed to write release file {self.file_path}: {e}"
            )

    def add_patch(self, patch_id: str, before: Optional[str] = None) -> None:
        """
        Add patch as candidate, optionally before another patch.

        Args:
            patch_id: Patch identifier (e.g., "456-user-auth")
            before: Optional patch ID to insert before

        Raises:
            ReleaseFileError: If operation fails or before patch not found

        Examples:
            # Add at end
            release_file.add_patch("3-bugfix")

            # Insert before existing patch
            release_file.add_patch("3-bugfix", before="2-api")
        """
        data = self._read()
        patches = data.get("patches", {})

        # Check if patch already exists
        if patch_id in patches:
            raise ReleaseFileError(
                f"Patch {patch_id} already exists in {self.version}"
            )

        if before is None:
            # Add at end
            patches[patch_id] = "candidate"
        else:
            # Insert before specified patch
            if before not in patches:
                raise ReleaseFileError(
                    f"Cannot insert before {before}: patch not found in {self.version}"
                )

            # Create new ordered dict with insertion
            new_patches = {}
            for key, value in patches.items():
                if key == before:
                    new_patches[patch_id] = "candidate"
                new_patches[key] = value

            patches = new_patches

        data["patches"] = patches
        self._write(data)

    def move_to_staged(self, patch_id: str) -> None:
        """
        Change patch status from candidate to staged.

        This preserves the patch order in the file, unlike the old system
        where patches were removed from candidates and appended to stage.

        Args:
            patch_id: Patch identifier to move

        Raises:
            ReleaseFileError: If patch not found or operation fails

        Examples:
            release_file.move_to_staged("1-auth")
            # Changes "1-auth" = "candidate" to "1-auth" = "staged"
        """
        data = self._read()
        patches = data.get("patches", {})

        if patch_id not in patches:
            raise ReleaseFileError(
                f"Patch {patch_id} not found in {self.version}"
            )

        if patches[patch_id] == "staged":
            raise ReleaseFileError(
                f"Patch {patch_id} is already staged"
            )

        patches[patch_id] = "staged"
        data["patches"] = patches
        self._write(data)

    def get_patches(self, status: Optional[str] = None) -> List[str]:
        """
        Get patches in order, optionally filtered by status.

        Args:
            status: Optional filter ("candidate" or "staged"). If None, returns all.

        Returns:
            List of patch IDs in file order

        Examples:
            # Get all patches
            all_patches = release_file.get_patches()

            # Get only candidates
            candidates = release_file.get_patches(status="candidate")

            # Get only staged patches
            staged = release_file.get_patches(status="staged")
        """
        data = self._read()
        patches = data.get("patches", {})

        if status is None:
            return list(patches.keys())

        return [
            patch_id for patch_id, patch_status in patches.items()
            if patch_status == status
        ]

    def get_patch_status(self, patch_id: str) -> Optional[str]:
        """
        Get status of a specific patch.

        Args:
            patch_id: Patch identifier

        Returns:
            Status string ("candidate" or "staged"), or None if not found

        Examples:
            status = release_file.get_patch_status("1-auth")
            if status == "staged":
                print("Patch is integrated")
        """
        data = self._read()
        patches = data.get("patches", {})
        return patches.get(patch_id)

    def remove_patch(self, patch_id: str) -> None:
        """
        Remove a patch completely from the release.

        This is rarely used but available for cleanup/error correction.

        Args:
            patch_id: Patch identifier to remove

        Raises:
            ReleaseFileError: If patch not found or operation fails
        """
        data = self._read()
        patches = data.get("patches", {})

        if patch_id not in patches:
            raise ReleaseFileError(
                f"Patch {patch_id} not found in {self.version}"
            )

        del patches[patch_id]
        data["patches"] = patches
        self._write(data)

    def exists(self) -> bool:
        """Check if release file exists."""
        return self.file_path.exists()

    def get_all_patches_with_status(self) -> Dict[str, str]:
        """
        Get all patches with their status.

        Returns:
            Ordered dict of {patch_id: status}

        Examples:
            patches = release_file.get_all_patches_with_status()
            # → {"1-auth": "staged", "2-api": "candidate"}
        """
        data = self._read()
        return data.get("patches", {})

    def set_metadata(self, metadata: Dict) -> None:
        """
        Set metadata for the release file.

        Metadata is stored in a [metadata] section and can include migration info.

        Args:
            metadata: Dict of metadata key-value pairs

        Examples:
            release_file.set_metadata({
                "created_from_promotion": True,
                "source_version": "0.17.1",
                "migrated_at": "2025-12-09T14:23:45Z",
                "rebased_commits": {"42-feature": "a1b2c3d4"}
            })
        """
        data = self._read()
        data["metadata"] = metadata
        self._write(data)

    def get_metadata(self) -> Dict:
        """
        Get metadata from the release file.

        Returns:
            Dict of metadata, or empty dict if no metadata exists

        Examples:
            metadata = release_file.get_metadata()
            if metadata.get("created_from_promotion"):
                print("This release was created from promotion")
        """
        data = self._read()
        return data.get("metadata", {})

    def clear_metadata(self) -> None:
        """
        Remove metadata section from the release file.

        Used for cleanup after all developers have synced.
        """
        data = self._read()
        if "metadata" in data:
            del data["metadata"]
            self._write(data)
