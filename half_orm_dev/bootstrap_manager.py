"""
BootstrapManager module for half-orm-dev

Manages bootstrap scripts for data initialization. Bootstrap files are
SQL and Python scripts that initialize application data after database setup.

Files are named: <number>-<patch_id>-<version>.<ext>
Example: 1-init-users-0.1.0.sql, 2-seed-config-0.1.0.py

Scripts are executed in numeric order and tracked in half_orm_meta.bootstrap table.
"""

from __future__ import annotations

import re
import click
from pathlib import Path
from typing import List, Set, Tuple, Optional, TYPE_CHECKING

from half_orm_dev.file_executor import (
    execute_sql_file, execute_python_file, FileExecutionError
)

if TYPE_CHECKING:
    from half_orm_dev.repo import Repo


class BootstrapManagerError(Exception):
    """Base exception for BootstrapManager operations."""
    pass


class BootstrapManager:
    """
    Manages bootstrap scripts for data initialization.

    Bootstrap scripts are SQL and Python files that initialize application
    data after the database schema is created. They are tracked in the
    half_orm_meta.bootstrap table to ensure each script is executed only once.

    Attributes:
        _repo: Repository instance
        _bootstrap_dir: Path to bootstrap/ directory
    """

    def __init__(self, repo: 'Repo'):
        """
        Initialize BootstrapManager.

        Args:
            repo: Repository instance
        """
        self._repo = repo
        self._bootstrap_dir = Path(repo.base_dir) / 'bootstrap'

    @property
    def bootstrap_dir(self) -> Path:
        """Get path to bootstrap directory."""
        return self._bootstrap_dir

    def get_bootstrap_files(self) -> List[Path]:
        """
        List bootstrap files sorted by numeric prefix.

        Returns files matching pattern: <number>-<patch_id>-<version>.<ext>
        Sorted numerically on the first field (not lexicographically).

        Returns:
            List of Path objects for bootstrap files in execution order
        """
        if not self._bootstrap_dir.exists():
            return []

        files = []
        for file_path in self._bootstrap_dir.iterdir():
            if file_path.is_file() and file_path.suffix in ('.sql', '.py'):
                # Skip README or other non-bootstrap files
                if not re.match(r'^\d+-', file_path.name):
                    continue
                files.append(file_path)

        # Sort by numeric prefix
        def get_numeric_prefix(path: Path) -> int:
            match = re.match(r'^(\d+)-', path.name)
            return int(match.group(1)) if match else 0

        return sorted(files, key=get_numeric_prefix)

    def get_executed_files(self) -> Set[str]:
        """
        Get set of already executed filenames from database.

        Queries half_orm_meta.bootstrap table to get filenames
        that have already been executed.

        Returns:
            Set of filename strings that have been executed
        """
        try:
            result = self._repo.database.model.execute_query(
                "SELECT filename FROM half_orm_meta.bootstrap"
            )
            return {row[0] for row in result} if result else set()
        except Exception:
            # Table might not exist yet (pre-migration)
            return set()

    def get_pending_files(self) -> List[Path]:
        """
        Get bootstrap files not yet executed.

        Returns:
            List of Path objects for files pending execution
        """
        all_files = self.get_bootstrap_files()
        executed = self.get_executed_files()

        return [f for f in all_files if f.name not in executed]

    def execute_file(self, file_path: Path) -> None:
        """
        Execute SQL or Python bootstrap file.

        Args:
            file_path: Path to bootstrap file

        Raises:
            BootstrapManagerError: If execution fails
        """
        try:
            if file_path.suffix == '.sql':
                execute_sql_file(file_path, self._repo.database.model)
            elif file_path.suffix == '.py':
                output = execute_python_file(file_path, cwd=self._bootstrap_dir)
                if output:
                    click.echo(f"    Output: {output}")
            else:
                raise BootstrapManagerError(
                    f"Unsupported file type: {file_path.suffix}"
                )
        except FileExecutionError as e:
            raise BootstrapManagerError(str(e)) from e

    def record_execution(self, filename: str, version: str) -> None:
        """
        Record execution in half_orm_meta.bootstrap table.

        Args:
            filename: Name of the executed file
            version: Version extracted from filename
        """
        sql = """
        INSERT INTO half_orm_meta.bootstrap (filename, version)
        VALUES (%s, %s)
        ON CONFLICT (filename) DO UPDATE SET
            version = EXCLUDED.version,
            executed_at = NOW()
        """
        self._repo.database.model.execute_query(sql, (filename, version))

    def run_bootstrap(
        self,
        dry_run: bool = False,
        force: bool = False,
        exclude_patch_id: Optional[str] = None
    ) -> dict:
        """
        Execute pending bootstrap files.

        Args:
            dry_run: If True, show what would be executed without executing
            force: If True, re-execute all files (ignore tracking)
            exclude_patch_id: If provided, skip files belonging to this patch
                             (used during patch apply to avoid executing the
                             bootstrap file that was just created for the current patch)

        Returns:
            Dict with execution results:
            - 'executed': List of executed filenames
            - 'skipped': List of skipped filenames (already executed)
            - 'excluded': List of excluded filenames (matching exclude_patch_id)
            - 'errors': List of (filename, error) tuples
        """
        result = {
            'executed': [],
            'skipped': [],
            'excluded': [],
            'errors': []
        }

        if force:
            files_to_execute = self.get_bootstrap_files()
        else:
            files_to_execute = self.get_pending_files()
            # Calculate skipped
            all_files = self.get_bootstrap_files()
            executed = self.get_executed_files()
            result['skipped'] = [f.name for f in all_files if f.name in executed]

        if not files_to_execute:
            return result

        for file_path in files_to_execute:
            filename = file_path.name
            version = self._extract_version_from_filename(filename)

            # Check if this file belongs to the excluded patch
            if exclude_patch_id and self._file_belongs_to_patch(filename, exclude_patch_id):
                result['excluded'].append(filename)
                continue

            if dry_run:
                result['executed'].append(filename)
                continue

            try:
                click.echo(f"  • Executing {filename}...")
                self.execute_file(file_path)
                self.record_execution(filename, version)
                result['executed'].append(filename)
            except BootstrapManagerError as e:
                result['errors'].append((filename, str(e)))
                # Stop on first error
                break

        return result

    def _parse_filename(self, filename: str) -> Tuple[int, str, str]:
        """
        Parse bootstrap filename into components.

        Expected format: <number>-<patch_id>-<version>.<ext>
        Example: '1-init-users-0.1.0.sql' -> (1, 'init-users', '0.1.0')

        Args:
            filename: Bootstrap filename to parse

        Returns:
            Tuple of (number, patch_id, version)

        Raises:
            ValueError: If filename doesn't match expected format
        """
        # Pattern: number-patch_id-X.Y.Z.ext
        match = re.match(r'^(\d+)-(.+)-(\d+\.\d+\.\d+)\.(sql|py)$', filename)
        if not match:
            raise ValueError(f"Invalid bootstrap filename format: {filename}")

        number = int(match.group(1))
        patch_id = match.group(2)
        version = match.group(3)

        return number, patch_id, version

    def _file_belongs_to_patch(self, filename: str, patch_id: str) -> bool:
        """
        Check if a bootstrap file belongs to a specific patch.

        Args:
            filename: Bootstrap filename (e.g., '1-my-patch-0.1.0.sql')
            patch_id: Patch identifier to check against

        Returns:
            True if the file belongs to the patch, False otherwise
        """
        try:
            _, file_patch_id, _ = self._parse_filename(filename)
            return file_patch_id == patch_id
        except ValueError:
            return False

    def _extract_version_from_filename(self, filename: str) -> str:
        """
        Extract version from bootstrap filename.

        Args:
            filename: Bootstrap filename

        Returns:
            Version string or 'unknown' if parsing fails
        """
        try:
            _, _, version = self._parse_filename(filename)
            return version
        except ValueError:
            return 'unknown'

    def get_next_bootstrap_number(self) -> int:
        """
        Get next available number for bootstrap file.

        Returns:
            Next number (1-based) for naming a new bootstrap file
        """
        files = self.get_bootstrap_files()
        if not files:
            return 1

        # Get max number from existing files
        max_num = 0
        for file_path in files:
            match = re.match(r'^(\d+)-', file_path.name)
            if match:
                num = int(match.group(1))
                max_num = max(max_num, num)

        return max_num + 1

    def ensure_bootstrap_dir(self) -> None:
        """Create bootstrap directory if it doesn't exist."""
        self._bootstrap_dir.mkdir(exist_ok=True)
