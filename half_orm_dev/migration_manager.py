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
from configparser import ConfigParser
from packaging import version
import click
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from half_orm import utils
from half_orm_dev.decorators import with_dynamic_branch_lock

try:
    from half_orm.migrations import get_breaking_changes_dir
except (ImportError, AttributeError):
    get_breaking_changes_dir = None  # type: ignore[assignment]


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
        current = version.parse(current_version).release
        target = version.parse(target_version).release

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
            Dict with migration results including:
            - version: Version string
            - applied_files: List of applied file names
            - sync_files: List of files to sync to active branches
            - errors: List of error messages
        """
        result = {
            'version': version_str,
            'applied_files': [],
            'sync_files': [],
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

                # Execute migration.
                # The repo is guaranteed clean before migration starts, so the
                # git index is empty here.  Everything staged by this script is
                # exclusively a migration-induced change.
                migration_result = module.migrate(self._repo)

                result['applied_files'].append(migration_file.name)

                # Auto-detect files staged by the script (via hgit.add()).
                # Since the index was empty before migration, git diff --cached
                # returns exactly the files this script modified.
                git_repo = self._repo.hgit._HGit__git_repo
                auto_staged = set(
                    git_repo.git.diff('--cached', '--name-only').splitlines()
                )

                # Merge with sync_files explicitly declared by the script.
                declared = (
                    list(migration_result.get('sync_files', []))
                    if isinstance(migration_result, dict) else []
                )
                all_sync = list(dict.fromkeys(declared + list(auto_staged)))
                if all_sync:
                    result['sync_files'].extend(all_sync)

            except Exception as e:
                error_msg = f"Error in {migration_file.name}: {e}"
                result['errors'].append(error_msg)
                raise MigrationManagerError(error_msg) from e

        # Deduplicate across all scripts (git diff --cached is cumulative)
        result['sync_files'] = list(dict.fromkeys(result['sync_files']))
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
                    # Check whether the migration was already applied on origin/ho-prod.
                    already_done = False
                    try:
                        remote_config_text = self._repo.hgit._HGit__git_repo.git.show(
                            'origin/ho-prod:.hop/config'
                        )
                        _cp = ConfigParser()
                        _cp.read_string(remote_config_text)
                        remote_version = _cp['halfORM'].get('hop_version', '')
                        if remote_version == target_version:
                            already_done = True
                    except Exception:
                        pass

                    if already_done:
                        # Another developer already ran the migration.
                        # Pull and sync all active branches, then return.
                        click.echo(
                            f"  ℹ Migration to {target_version} already applied by another developer.\n"
                            f"  Pulling and syncing all active branches..."
                        )
                        self._repo.hgit._HGit__git_repo.remotes.origin.pull('ho-prod')
                        self._repo.hgit.sync_active_branches(pattern="ho-*")
                        # Reload config so the rest of the tool sees the new version
                        self._repo._Repo__config.read()
                        result['already_synced'] = True
                        return result

                    raise MigrationManagerError(
                        f"ho-prod is {behind} commits behind origin/ho-prod. "
                        f"Please pull changes first: git pull origin ho-prod"
                    )
                if ahead > 0:
                    result['errors'].append(f"Warning: ho-prod is {ahead} commits ahead of origin/ho-prod")
            except (MigrationManagerError, subprocess.CalledProcessError):
                raise
            except Exception:
                # Could not compare — maybe origin/ho-prod doesn't exist yet
                pass

        # Get current version from .hop/config
        current_version = self._repo._Repo__config.hop_version if hasattr(
            self._repo, '_Repo__config'
        ) else "0.0.0"

        # If already at target version, nothing to do
        try:
            comparison = self._repo.compare_versions(current_version, target_version)

            if comparison >= 0:
                # Already at or past target version (0 = equal, 1 = higher)
                return result
        except Exception as e:
            # If version comparison fails (invalid format), log and continue
            # This allows migration to proceed even if version format is unexpected
            result['errors'].append(
                f"Could not compare versions {current_version} and {target_version}: {e}. "
                f"Continuing with migration attempt."
            )

        # Ensure all active branches are in sync with origin before touching anything
        self._ensure_active_branches_synced()

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

        # Update half_orm_dev version in pyproject.toml
        self._update_pyproject_dependency_version(target_version)

        # Collect all sync_files from migrations + pyproject.toml
        all_sync_files = ['pyproject.toml']  # Always sync pyproject.toml
        for migration in result['migrations_applied']:
            all_sync_files.extend(migration.get('sync_files', []))
        # Remove duplicates while preserving order
        all_sync_files = list(dict.fromkeys(all_sync_files))

        # Create Git commit if requested
        if create_commit and self._repo.hgit:
            try:
                commit_msg = self._create_migration_commit_message(
                    current_version,
                    target_version,
                    result['migrations_applied']
                )

                # Commit and sync to active branches (including migration files)
                sync_result = self._repo.commit_and_sync_to_active_branches(
                    message=commit_msg,
                    reason=f"migration {current_version} → {target_version}",
                    files=all_sync_files
                )

                result['commit_created'] = True
                result['commit_message'] = commit_msg
                result['commit_pushed'] = True
                result['sync_result'] = sync_result

                # Create annotated tag encoding all commit SHAs for potential revert
                self._create_migration_tag(
                    current_version, target_version, sync_result
                )

                # Pseudo-patch: regenerate modules and sync to active branches
                try:
                    self._regenerate_modules_after_migration(
                        current_version, target_version
                    )
                except Exception as regen_err:
                    result['errors'].append(
                        f"Module regeneration after migration failed: {regen_err}"
                    )

            except Exception as e:
                # Don't fail migration if commit fails
                result['errors'].append(f"Failed to create commit: {e}")

        # Note: Branch synchronization is now handled automatically by the
        # @with_dynamic_branch_lock decorator when the method completes.
        # The decorator calls repo.sync_hop_to_active_branches() for all
        # operations on ho-prod, ensuring .hop/ is always synced.

        return result

    @with_dynamic_branch_lock(lambda self, *args, **kwargs: 'ho-prod')
    def revert_migration(self) -> None:
        """
        Revert the most recently tagged migration.

        Acquires a lock on ho-prod (via decorator), finds the ho-migration/*
        tag with the highest version, and runs `git revert --no-edit` on each
        affected branch (active branches first, then ho-prod).  The tag is
        deleted (local + remote) after a successful revert.

        Raises:
            MigrationManagerError: if no migration tag exists (never migrated,
                or already locked by a production promotion).
        """
        git_repo = self._repo.hgit._HGit__git_repo

        migration_tags = sorted(
            [t for t in git_repo.tags if t.name.startswith('ho-migration/')],
            key=lambda t: version.parse(t.name[len('ho-migration/'):]),
            reverse=True,
        )
        if not migration_tags:
            raise MigrationManagerError(
                "No migration tag found — revert is not possible "
                "(migration was never run, or already locked by a "
                "production promotion)."
            )
        tag = migration_tags[0]

        # Parse annotation: "Migration from X to Y\nho-prod:<sha>\nbranch:<sha>…"
        shas: Dict = {}
        for line in tag.tag.message.splitlines()[1:]:
            if ':' in line:
                branch, sha = line.split(':', 1)
                shas[branch.strip()] = sha.strip()

        if 'ho-prod' not in shas:
            raise MigrationManagerError(
                f"Migration tag {tag.name} is malformed (missing ho-prod SHA)."
            )

        # Revert sync commits on active branches first
        for branch, sha in shas.items():
            if branch == 'ho-prod':
                continue
            git_repo.git.checkout(branch)
            git_repo.git.revert(sha, '--no-edit')
            self._repo.hgit.push_branch(branch)

        # Revert migration commit on ho-prod last
        git_repo.git.checkout('ho-prod')
        git_repo.git.revert(shas['ho-prod'], '--no-edit')
        self._repo.hgit.push_branch('ho-prod')

        # Remove tag (local + remote)
        self._repo.hgit.delete_local_tag(tag.name)
        try:
            self._repo.hgit.delete_remote_tag(tag.name)
        except Exception:
            pass  # remote tag may already be gone

    def _ensure_active_branches_synced(self) -> None:
        """Verify all active branches are in sync with origin before migration.

        Branches that are behind are fast-forwarded automatically (no local commits
        at risk).  Branches that are ahead or diverged block the migration — the
        developer must push or resolve before proceeding.

        Raises:
            MigrationManagerError: if any active branch is ahead or diverged.
        """
        repo = self._repo
        git_repo = repo.hgit._HGit__git_repo
        current_branch = git_repo.active_branch.name

        try:
            branches_status = repo.hgit.get_active_branches_status()
        except Exception:
            return  # can't determine status, proceed cautiously

        patch_branches = [b['name'] for b in branches_status.get('patch_branches', [])]
        release_branches = [b['name'] for b in branches_status.get('release_branches', [])]
        # ho-staged/* branches are frozen after merge — excluded from sync checks
        active_branches = release_branches + patch_branches

        blocked = []
        for branch in active_branches:
            try:
                synced, status = repo.hgit.is_branch_synced(branch)
                if synced:
                    continue
                if status == 'behind':
                    # Fast-forward: no local commits at risk
                    repo.hgit.checkout(branch)
                    git_repo.git.merge('--ff-only', f'origin/{branch}')
                elif status in ('ahead', 'diverged'):
                    blocked.append((branch, status))
            except Exception:
                pass  # branch may not exist locally, skip

        # Return to original branch
        try:
            repo.hgit.checkout(current_branch)
        except Exception:
            pass

        if blocked:
            ahead = [(b, s) for b, s in blocked if s == 'ahead']
            diverged = [(b, s) for b, s in blocked if s == 'diverged']
            parts = []
            if ahead:
                branch_list = ', '.join(b for b, _ in ahead)
                parts.append(
                    f"  Branches ahead of origin (unpushed commits) — push first:\n"
                    + '\n'.join(f"    git push origin {b}" for b, _ in ahead)
                )
            if diverged:
                parts.append(
                    f"  Branches diverged from origin (local and remote have diverged) "
                    f"— rebase or merge to resolve:\n"
                    + '\n'.join(f"    {b}" for b, _ in diverged)
                )
            raise MigrationManagerError(
                f"Migration blocked: active branches are not in sync with origin.\n"
                + '\n'.join(parts)
            )

    def _regenerate_modules_after_migration(
        self, from_version: str, to_version: str
    ) -> None:
        """Regenerate the project modules after a migration on all active branches.

        Each branch is regenerated against the DB schema that matches its state:
        - ho-prod          → production schema (schema.sql)
        - ho-release/X.Y.Z → release schema (release-X.Y.Z.sql), no bootstrap
        - ho-patch/*       → production schema (schema.sql)

        Bootstrap scripts are NOT run during this restore: the modules may be in
        an inconsistent state (that is precisely what we are fixing), and running
        bootstrap would fail trying to import them.

        Stale local branches (no longer on remote) are skipped to avoid pre-commit
        hook failures.
        """
        import re as _re
        from half_orm_dev import modules as _modules

        _RELEASE_RE = _re.compile(r'^ho-release/(.+)$')

        repo = self._repo
        git_repo = repo.hgit._HGit__git_repo
        package_name = repo.name
        package_dir = str(Path(repo.base_dir) / package_name)

        commit_msg = (
            f"[HOP] Regenerate modules (migration {from_version} → {to_version})"
        )

        # Collect active branches, filtering out stale ones (no remote counterpart)
        try:
            branches_status = repo.hgit.get_active_branches_status()
        except Exception:
            branches_status = {}

        patch_branches = [
            b['name'] for b in branches_status.get('patch_branches', [])
            if b.get('exists_on_remote', True)
        ]
        release_branches = [
            b['name'] for b in branches_status.get('release_branches', [])
            if b.get('exists_on_remote', True)
        ]
        all_branches = ['ho-prod'] + release_branches + patch_branches

        for branch in all_branches:
            try:
                repo.hgit.checkout(branch)

                # Restore the DB to the schema appropriate for this branch so
                # generate() introspects the right set of relations.
                m = _RELEASE_RE.match(branch)
                if m:
                    release_version = m.group(1)
                    release_schema = repo.get_release_schema_path(release_version)
                    if release_schema.exists():
                        repo.restore_database_from_release_schema(
                            release_version, skip_bootstrap=True
                        )
                    else:
                        repo.restore_database_from_schema(skip_bootstrap=True)
                else:
                    # ho-prod and ho-patch/*: use production schema
                    repo.restore_database_from_schema(skip_bootstrap=True)

                _modules.generate(repo)
                repo.hgit.add(package_dir)
                if not git_repo.git.diff('--cached', '--name-only').strip():
                    continue
                repo.hgit.commit('-m', commit_msg)
                try:
                    repo.hgit.push_branch(branch)
                except Exception as push_err:
                    sys.stderr.write(
                        f"Warning: could not push {branch} after module regeneration: "
                        f"{push_err}\n"
                    )
            except Exception as e:
                sys.stderr.write(
                    f"Warning: could not regenerate modules on {branch}: {e}\n"
                )

        repo.hgit.checkout('ho-prod')

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

    def _create_migration_tag(
        self, from_version: str, to_version: str, sync_result: Dict
    ) -> None:
        """
        Create annotated tag ho-migration/{to_version} encoding commit SHAs.

        The annotation stores the ho-prod commit SHA and the SHA of each sync
        commit on active branches, enabling revert_migration() to undo the
        migration precisely.

        If the tag already exists (e.g. a previous failed migration left it),
        it is deleted first.
        """
        tag_name = f"ho-migration/{to_version}"

        # Remove stale tag if present
        if self._repo.hgit.tag_exists(tag_name):
            self._repo.hgit.delete_local_tag(tag_name)
            try:
                self._repo.hgit.delete_remote_tag(tag_name)
            except Exception:
                pass  # remote tag may not exist

        ho_prod_sha = self._repo.hgit._HGit__git_repo.head.commit.hexsha
        branch_commits = (
            sync_result.get('sync_result', {}).get('branch_commits', {})
        )

        lines = [f"Migration from {from_version} to {to_version}"]
        lines.append(f"ho-prod:{ho_prod_sha}")
        for branch, sha in branch_commits.items():
            lines.append(f"{branch}:{sha}")

        self._repo.hgit.create_tag(tag_name, message='\n'.join(lines))
        self._repo.hgit.push_tag(tag_name)

    def _update_pyproject_dependency_version(self, target_version: str) -> None:
        """
        Update half_orm_dev version in pyproject.toml.

        This ensures the project's dependency on half_orm_dev always matches
        the current tool version after each migration.

        Handles both == and >= version specifiers.

        Args:
            target_version: New version to set for half_orm_dev dependency
        """
        import re

        pyproject_path = Path(self._repo.base_dir) / "pyproject.toml"

        if not pyproject_path.exists():
            return

        try:
            content = pyproject_path.read_text()

            # Only update if half_orm_dev dependency exists (== or >=)
            if 'half_orm_dev==' not in content and 'half_orm_dev>=' not in content:
                return

            # Update the version (handles both == and >=)
            new_content = re.sub(
                r'half_orm_dev[>=]=[\d.a-zA-Z-]+',
                f'half_orm_dev=={target_version}',
                content
            )

            if new_content != content:
                pyproject_path.write_text(new_content)
                if self._repo.hgit:
                    self._repo.hgit.add(str(pyproject_path))
                print(f"  Updated pyproject.toml: half_orm_dev=={target_version}")

        except Exception as e:
            # Non-critical - don't fail migration
            print(f"  Warning: Could not update pyproject.toml: {e}")

    def check_migration_needed(self, current_tool_version: str) -> bool:
        """
        Check if migration is needed.

        Compares current tool version with hop_version in .hop/config.
        Properly handles pre-release versions (alpha, beta, rc).

        Args:
            current_tool_version: Current half_orm_dev version (e.g., "0.17.2-a5")

        Returns:
            True if migration/update is needed
        """
        if not hasattr(self._repo, '_Repo__config'):
            return False

        config_version = self._repo._Repo__config.hop_version

        # If no hop_version is configured, no migration needed
        if not config_version:
            return False

        try:
            # Use Repo's centralized comparison method
            # Returns: 1 if current > config, 0 if equal, -1 if current < config
            comparison = self._repo.compare_versions(current_tool_version, config_version)

            # Migration needed if current version is higher
            # This now properly compares: 0.17.2a5 > 0.17.2a3 → returns 1 ✓
            return comparison > 0

        except Exception as e:
            # If version parsing fails, log warning and don't block
            import warnings
            warnings.warn(
                f"Could not parse versions for migration check: "
                f"current={current_tool_version}, config={config_version}. "
                f"Error: {e}",
                UserWarning
            )
            return False

    def get_breaking_changes(self, current_version: str, target_version: str) -> List[Dict]:
        """
        Collect breaking-changes documents for all versions in ]current, target].

        Looks in two subdirectories of the migrations root:
          - hop/       BREAKING_CHANGES-X.Y.Z.md  (half-orm-dev changes)
          - half_orm/  BREAKING_CHANGES-X.Y.Z.md  (half-orm library changes)

        Both are keyed by hop version (same major.minor family).

        Args:
            current_version: Current hop version (exclusive lower bound)
            target_version:  Target hop version (inclusive upper bound)

        Returns:
            List of dicts ordered by version, each with keys:
                - component: 'hop' or 'half_orm'
                - version:   version string from filename
                - content:   file content
        """
        results = []
        try:
            current = version.parse(current_version)
            target = version.parse(target_version)
            # Use base versions (major.minor.micro, no pre/post/dev) for range
            # bounds so that a file named '1.0.0' is included when migrating to
            # '1.0.0-a1' (whose base version is also '1.0.0').
            current_base = version.parse(current.base_version)
            target_base = version.parse(target.base_version)
        except Exception:
            return results

        component_dirs = {'hop': self._migrations_root / 'hop'}
        if get_breaking_changes_dir is not None:
            try:
                component_dirs['half_orm'] = get_breaking_changes_dir()
            except Exception:
                pass  # older half-orm — ignore silently

        for component, bc_dir in component_dirs.items():
            if not bc_dir.is_dir():
                continue
            for bc_file in sorted(bc_dir.glob('BREAKING_CHANGES-*.md')):
                # filename: BREAKING_CHANGES-X.Y.Z.md  (hyphens in pre-release OK)
                raw = bc_file.stem[len('BREAKING_CHANGES-'):]  # e.g. '1.0.0' or '1.0.0-rc1'
                try:
                    file_version = version.parse(raw)
                except Exception:
                    continue
                if current_base < file_version <= target_base:
                    results.append({
                        'component': component,
                        'version': raw,
                        'content': bc_file.read_text(encoding='utf-8'),
                    })

        # Sort by version, then by component for a stable display order
        results.sort(key=lambda r: (version.parse(r['version']), r['component']))
        return results
