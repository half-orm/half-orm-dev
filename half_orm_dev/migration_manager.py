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
import subprocess
import sys
import importlib.util
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from half_orm import utils
from half_orm_dev.decorators import with_dynamic_branch_lock


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

    def _parse_version(self, version_str: str) -> Tuple[int, int, int]:
        """
        Parse version string to tuple.

        Supports version formats:
        - "0.17.1"
        - "0.17.1-a1" (ignores suffix)
        - "0.17.1-rc2" (ignores suffix)

        Args:
            version_str: Version string like "0.17.1" or "0.17.1-a1"

        Returns:
            Tuple of (major, minor, patch)
        """
        # Strip any pre-release suffix (e.g., "-a1", "-rc2")
        base_version = version_str.split('-')[0]

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
    def run_migrations(self, target_version: str, create_commit: bool = True, notify_branches: bool = True) -> Dict:
        """
        Run all pending migrations up to target version.

        IMPORTANT: This method acquires a lock on ho-prod branch via decorator.
        Should only be called when on ho-prod branch.

        Args:
            target_version: Target version string (e.g., "0.17.1")
            create_commit: Whether to create Git commit after migration
            notify_branches: Whether to create empty commits on active branches

        Returns:
            Dict with migration results including:
                - migrations_applied: List of applied migrations
                - commit_created: Whether migration commit was created
                - notified_branches: List of branches that were notified
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

        # Get pending migrations
        pending = self.get_pending_migrations(current_version, target_version)

        if not pending:
            # No migrations to apply
            return result

        # Apply each migration
        for version_str, migration_dir in pending:
            try:
                migration_result = self.apply_migration(version_str, migration_dir)
                result['migrations_applied'].append(migration_result)

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

                # Commit with -m flag
                self._repo.hgit.commit('-m', commit_msg)

                result['commit_created'] = True
                result['commit_message'] = commit_msg

                # Push to remote
                try:
                    self._repo.hgit.push()
                    result['commit_pushed'] = True
                except Exception as e:
                    result['errors'].append(f"Failed to push commit: {e}")
                    result['commit_pushed'] = False

            except Exception as e:
                # Don't fail migration if commit fails
                result['errors'].append(f"Failed to create commit: {e}")

        # Notify active branches if requested
        if notify_branches and create_commit and result['commit_created']:
            try:
                notified = self._notify_active_branches(current_version, target_version)
                result['notified_branches'] = notified
            except Exception as e:
                # Don't fail migration if notification fails
                result['errors'].append(f"Failed to notify branches: {e}")

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

    def _notify_active_branches(self, from_version: str, to_version: str) -> List[str]:
        """
        Apply migration to active branches (ho-patch/*, ho-release/*).

        Applies the same migrations on all active branches, creates commits,
        and pushes them to origin. This prevents merge conflicts when branches
        merge ho-prod later.

        Args:
            from_version: Starting version
            to_version: Target version

        Returns:
            List of branch names that were migrated
        """
        migrated_branches = []

        # Get active branches from origin using hgit method
        branches_status = self._repo.hgit.get_active_branches_status()

        # Extract branch names from patch_branches and release_branches
        patch_branches = [b['name'] for b in branches_status.get('patch_branches', [])]
        release_branches = [b['name'] for b in branches_status.get('release_branches', [])]

        # Combine all active branches (excluding ho-prod)
        active_branches = [b for b in patch_branches + release_branches if b != 'ho-prod']

        # Current branch (should be ho-prod)
        current_branch = self._repo.hgit.branch

        # Apply migration on each active branch
        for branch in active_branches:
            try:
                # Checkout branch
                self._repo.hgit.checkout(branch)

                # Reload config for this branch
                from half_orm_dev.repo import Config
                self._repo._Repo__config = Config(self._repo.base_dir)

                # Get pending migrations for this branch
                branch_version = self._repo._Repo__config.hop_version
                pending = self.get_pending_migrations(branch_version, to_version)

                if not pending:
                    # Already migrated or no migration needed
                    continue

                # Apply each migration
                for version_str, migration_dir in pending:
                    self.apply_migration(version_str, migration_dir)

                # Update hop_version in .hop/config
                self._repo._Repo__config.hop_version = to_version
                self._repo._Repo__config.write()

                # Create commit message
                commit_msg = self._create_migration_commit_message(
                    branch_version,
                    to_version,
                    [{'version': v, 'applied_files': []} for v, _ in pending]
                )

                # Add all changes and commit
                self._repo.hgit.add('.')
                self._repo.hgit.commit('-m', commit_msg)

                # Push the commit
                self._repo.hgit.push_branch(branch)

                migrated_branches.append(branch)

            except Exception as e:
                print(f"Warning: Failed to migrate branch {branch}: {e}", file=sys.stderr)

        # Return to original branch (ho-prod)
        if current_branch:
            try:
                self._repo.hgit.checkout(current_branch)
                # Reload config for original branch
                from half_orm_dev.repo import Config
                self._repo._Repo__config = Config(self._repo.base_dir)
            except Exception:
                pass

        return migrated_branches

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
