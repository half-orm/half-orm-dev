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
import importlib.util
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from half_orm import utils


class MigrationManagerError(Exception):
    """Base exception for MigrationManager operations."""
    pass


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

        # Path to log file
        self._log_file = self._migrations_root / 'log'

    def get_applied_migrations(self) -> List[str]:
        """
        Read list of applied migrations from log file.

        Returns:
            List of version strings (e.g., ['0.17.0', '0.17.1'])
        """
        if not self._log_file.exists():
            return []

        with open(self._log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # Parse version strings (ignore empty lines and comments)
        versions = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                # Support format like "0.17.1" or "0.17.1 <git-hash>"
                version = line.split()[0]
                versions.append(version)

        return versions

    def _parse_version(self, version_str: str) -> Tuple[int, int, int]:
        """
        Parse version string to tuple.

        Args:
            version_str: Version string like "0.17.1"

        Returns:
            Tuple of (major, minor, patch)
        """
        parts = version_str.split('.')
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

    def get_pending_migrations(self, target_version: str) -> List[Tuple[str, Path]]:
        """
        Get list of migrations that need to be applied.

        Args:
            target_version: Target version string (e.g., "0.17.1")

        Returns:
            List of (version_str, migration_dir_path) tuples in order
        """
        applied = set(self.get_applied_migrations())
        target = self._parse_version(target_version)

        pending = []

        # Walk through version directories to find unapplied migrations
        # Start from 0.0.0 up to target version
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

                    version_str = f"{major}.{minor}.{patch}"

                    # Skip if already applied
                    if version_str in applied:
                        continue

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

    def mark_migration_applied(self, version_str: str):
        """
        Mark a migration as applied in the log file.

        Args:
            version_str: Version string (e.g., "0.17.1")
        """
        # Ensure migrations directory exists
        self._migrations_root.mkdir(parents=True, exist_ok=True)

        # Append to log file
        with open(self._log_file, 'a', encoding='utf-8') as f:
            f.write(f"{version_str}\n")

    def run_migrations(self, target_version: str, create_commit: bool = True) -> Dict:
        """
        Run all pending migrations up to target version.

        Args:
            target_version: Target version string (e.g., "0.17.1")
            create_commit: Whether to create Git commit after migration

        Returns:
            Dict with migration results
        """
        result = {
            'target_version': target_version,
            'migrations_applied': [],
            'errors': [],
            'commit_created': False
        }

        # Get pending migrations
        pending = self.get_pending_migrations(target_version)

        if not pending:
            # No migrations to apply
            return result

        # Get current version from .hop/config
        current_version = self._repo._Repo__config.hop_version if hasattr(
            self._repo, '_Repo__config'
        ) else "0.0.0"

        # Apply each migration
        for version_str, migration_dir in pending:
            try:
                migration_result = self.apply_migration(version_str, migration_dir)
                result['migrations_applied'].append(migration_result)

                # Mark as applied
                self.mark_migration_applied(version_str)

            except MigrationManagerError as e:
                result['errors'].append(str(e))
                raise

        # Update hop_version in .hop/config
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

                # Add all changes
                self._repo.hgit.add('.')

                # Commit
                self._repo.hgit.commit(commit_msg)

                result['commit_created'] = True
                result['commit_message'] = commit_msg

            except Exception as e:
                # Don't fail migration if commit fails
                result['errors'].append(f"Failed to create commit: {e}")

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
            migrations: List of migration result dicts

        Returns:
            Commit message string
        """
        lines = [
            f"[HOP] Migration from {from_version} to {to_version}",
            "",
            "Applied migrations:"
        ]

        for migration in migrations:
            version = migration['version']
            files = migration['applied_files']
            lines.append(f"  - {version}: {', '.join(files)}")

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
