"""
Migration Manager for half_orm_dev

Manages migrations for half_orm_dev itself (not database schema migrations).
Similar to PatchManager but for tool migrations (directory structure changes,
configuration updates, etc.).

Directory structure:
    half_orm_dev/migrations/
    ├── log                    # List of applied migrations (version format)
    └── major/                 # Major version
        └── minor/             # Minor version
            └── patch/         # Patch version
                ├── 00_migration_name.py
                ├── 01_another_migration.py
                └── README.md

Each migration file must define:
    - migrate(repo): Execute the migration
    - get_description(): Return migration description
"""

import os
import re
import subprocess
import sys
import importlib.util
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from half_orm import utils
from half_orm_dev.decorators import with_dynamic_branch_lock


class MigrationManagerError(Exception):
    """Base exception for MigrationManager operations."""

class MigrationManager:
    """
    Manages half_orm_dev migrations (tool migrations, not DB schema).

    Handles:
    - Detecting which migrations need to run
    - Executing migrations sequentially
    - Tracking applied migrations in migrations/log
    - Creating Git commits for migrations
    - Updating hop_version in .hop/config
    """

    def __init__(self, repo):
        """
        Initialize MigrationManager.

        Args:
            repo: Repo instance
        """
        self._repo = repo

        # Path to migrations directory (in half_orm_dev package)
        self._migrations_root = Path(__file__).parent / 'migrations'

    def _parse_version(self, version_str: str) -> Tuple[int, int, int]:
        """
        Parse version string to tuple.

        Supports version formats:
        - "0.17.1"
        - "0.1.0a1" (ignores suffix)
        - "0.17.1-a1" (ignores suffix)
        - "0.17.1-rc2" (ignores suffix)

        Args:
            version_str: Version string like "0.17.1" or "0.17.1-a1"

        Returns:
            Tuple of (major, minor, patch)
        """
        # Strip any pre-release suffix (e.g., "-a1", "-rc2")
        base_version = version_str.split('-')[0]
        if not re.match(r"^\d+\.\d+\.\d+$", base_version):
            match = re.match(r"^(\d+\.\d+\.\d+)", base_version)
            if match:
                base_version = match.group(1)

        parts = base_version.split('.')
        if len(parts) != 3:
            raise MigrationManagerError(f"Invalid version format: {version_str}")

        try:
            return (int(parts[0]), int(parts[1]), int(parts[2]))
        except ValueError as e:
            raise MigrationManagerError(f"Invalid version format: {version_str}") from e

    def _version_to_path(self, version: Tuple[int, int, int]) -> Path:
        """
        Convert version tuple to migration directory path.

        Args:
            version: Tuple of (major, minor, patch)

        Returns:
            Path to migration directory
        """
        major, minor, patch = version
        return self._migrations_root / str(major) / str(minor) / str(patch)

    def get_pending_migrations(self, current_version: str, target_version: str) -> List[Tuple[str, Path]]:
        """
        Get list of migrations that need to be applied.

        Compares current version (from .hop/config) with target version (from hop_version())
        and returns all migrations in between.

        Args:
            current_version: Current version from .hop/config (e.g., "0.17.0")
            target_version: Target version from hop_version() (e.g., "0.17.1")

        Returns:
            List of (version_str, migration_dir_path) tuples in order
        """
        current = self._parse_version(current_version)
        target = self._parse_version(target_version)

        pending = []

        # Walk through version directories to find migrations between current and target
        # Start from current version + 1 up to target version
        for major in range(0, target[0] + 1):
            major_dir = self._migrations_root / str(major)
            if not major_dir.exists():
                continue

            minor_max = target[1] if major == target[0] else 999
            for minor in range(0, minor_max + 1):
                minor_dir = major_dir / str(minor)
                if not minor_dir.exists():
                    continue

                patch_max = target[2] if major == target[0] and minor == target[1] else 999
                for patch in range(0, patch_max + 1):
                    patch_dir = minor_dir / str(patch)
                    if not patch_dir.exists():
                        continue

                    version_tuple = (major, minor, patch)

                    # Skip if this version is <= current version
                    if version_tuple <= current:
                        continue

                    # Skip if this version is > target version
                    if version_tuple > target:
                        continue

                    version_str = f"{major}.{minor}.{patch}"

                    # Check if this version has any migration files
                    migration_files = list(patch_dir.glob('*.py'))
                    if migration_files:
                        pending.append((version_str, patch_dir))

        return pending

    def _load_migration_module(self, migration_file: Path):
        """
        Dynamically load a migration Python file as a module.

        Args:
            migration_file: Path to migration .py file

        Returns:
            Loaded module
        """
        spec = importlib.util.spec_from_file_location(
            migration_file.stem,
            migration_file
        )
        if spec is None or spec.loader is None:
            raise MigrationManagerError(
                f"Could not load migration file: {migration_file}"
            )

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        return module

    def apply_migration(self, version_str: str, migration_dir: Path) -> Dict:
        """
        Apply a single migration.

        Args:
            version_str: Version string (e.g., "0.17.1")
            migration_dir: Path to migration directory

        Returns:
            Dict with migration results
        """
        result = {
            'version': version_str,
            'applied_files': [],
            'errors': []
        }

        # Get all .py files in migration directory (sorted)
        migration_files = sorted(migration_dir.glob('*.py'))

        if not migration_files:
            raise MigrationManagerError(
                f"No migration files found in {migration_dir}"
            )

        # Execute each migration file
        for migration_file in migration_files:
            try:
                # Load migration module
                module = self._load_migration_module(migration_file)

                # Validate module has required functions
                if not hasattr(module, 'migrate'):
                    raise MigrationManagerError(
                        f"Migration {migration_file.name} missing migrate() function"
                    )

                # Execute migration
                module.migrate(self._repo)

                result['applied_files'].append(migration_file.name)

            except Exception as e:
                error_msg = f"Error in {migration_file.name}: {e}"
                result['errors'].append(error_msg)
                raise MigrationManagerError(error_msg) from e

        return result

    @with_dynamic_branch_lock(lambda self, *args, **kwargs: 'ho-prod')
    def run_migrations(self, target_version: str, create_commit: bool = True) -> Dict:
        """
        Run all pending migrations up to target version.

        IMPORTANT: This method acquires a lock on ho-prod branch via decorator.
        Should only be called when on ho-prod branch.

        After successful completion, the decorator automatically syncs .hop/
        directory to all active branches (ho-patch/*, ho-release/*).

        Args:
            target_version: Target version string (e.g., "0.17.1")
            create_commit: Whether to create Git commit after migration

        Returns:
            Dict with migration results including:
                - migrations_applied: List of applied migrations
                - commit_created: Whether migration commit was created
        """
        result = {
            'target_version': target_version,
            'migrations_applied': [],
            'errors': [],
            'commit_created': False,
            'notified_branches': []
        }

        # Fetch from origin to ensure we have latest refs
        try:
            self._repo.hgit.fetch_from_origin()
        except Exception as e:
            result['errors'].append(f"Failed to fetch from origin: {e}")
            raise MigrationManagerError(f"Cannot run migration: failed to fetch from origin: {e}")

        # Verify ho-prod is up to date with origin/ho-prod
        current_branch = self._repo.hgit.branch
        if current_branch == 'ho-prod':
            try:
                # Check if ho-prod is synced with origin/ho-prod
                result_check = subprocess.run(
                    ['git', 'rev-list', '--left-right', '--count', 'ho-prod...origin/ho-prod'],
                    cwd=self._repo.base_dir,
                    capture_output=True,
                    text=True,
                    check=True
                )
                ahead, behind = map(int, result_check.stdout.strip().split())
                if behind > 0:
                    raise MigrationManagerError(
                        f"ho-prod is {behind} commits behind origin/ho-prod. "
                        f"Please pull changes first: git pull origin ho-prod"
                    )
                if ahead > 0:
                    result['errors'].append(f"Warning: ho-prod is {ahead} commits ahead of origin/ho-prod")
            except subprocess.CalledProcessError as e:
                # Could not compare - maybe origin/ho-prod doesn't exist yet
                pass

        # Get current version from .hop/config
        current_version = self._repo._Repo__config.hop_version if hasattr(
            self._repo, '_Repo__config'
        ) else "0.0.0"

        # If already at target version, nothing to do
        if current_version == target_version:
            return result

        # Get pending migrations
        pending = self.get_pending_migrations(current_version, target_version)

        # Apply each migration if there are any
        if pending:
            for version_str, migration_dir in pending:
                try:
                    migration_result = self.apply_migration(version_str, migration_dir)
                    result['migrations_applied'].append(migration_result)

                except MigrationManagerError as e:
                    result['errors'].append(str(e))
                    raise

        # Update hop_version in .hop/config (current_version != target_version)
        # This ensures the version is updated even when upgrading between versions
        # that have no migration scripts (e.g., 0.17.1-a2 → 0.17.2-a3)
        if hasattr(self._repo, '_Repo__config'):
            self._repo._Repo__config.hop_version = target_version
            self._repo._Repo__config.write()

        # Create Git commit if requested
        if create_commit and self._repo.hgit:
            try:
                commit_msg = self._create_migration_commit_message(
                    current_version,
                    target_version,
                    result['migrations_applied']
                )

                # Commit and sync to active branches
                sync_result = self._repo.commit_and_sync_to_active_branches(
                    message=commit_msg,
                    reason=f"migration {current_version} → {target_version}"
                )

                result['commit_created'] = True
                result['commit_message'] = commit_msg
                result['commit_pushed'] = True
                result['sync_result'] = sync_result

            except Exception as e:
                # Don't fail migration if commit fails
                result['errors'].append(f"Failed to create commit: {e}")

        # Note: Branch synchronization is now handled automatically by the
        # @with_dynamic_branch_lock decorator when the method completes.
        # The decorator calls repo.sync_hop_to_active_branches() for all
        # operations on ho-prod, ensuring .hop/ is always synced.

        return result

    def _create_migration_commit_message(
        self,
        from_version: str,
        to_version: str,
        migrations: List[Dict]
    ) -> str:
        """
        Create commit message for migration.

        Args:
            from_version: Starting version
            to_version: Target version
            migrations: List of migration result dicts (can be empty)

        Returns:
            Commit message string
        """
        lines = [
            f"[HOP] Migration from {from_version} to {to_version}"
        ]

        if migrations:
            lines.append("")
            lines.append("Applied migrations:")
            for migration in migrations:
                version = migration['version']
                files = migration['applied_files']
                lines.append(f"  - {version}: {', '.join(files)}")
        else:
            lines.append("")
            lines.append("No migration scripts needed (version update only)")

        return '\n'.join(lines)

    def check_migration_needed(self, current_tool_version: str) -> bool:
        """
        Check if migration is needed.

        Compares current tool version with hop_version in .hop/config.

        Args:
            current_tool_version: Current half_orm_dev version

        Returns:
            True if migration is needed
        """
        if not hasattr(self._repo, '_Repo__config'):
            return False

        config_version = self._repo._Repo__config.hop_version

        # Parse versions
        current = self._parse_version(current_tool_version)
        config = self._parse_version(config_version)

        # Migration needed if current version is higher
        return current > config
