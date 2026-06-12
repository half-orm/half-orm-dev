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
            └── patch/         # Patch version (stable migrations here)
                ├── 00_migration_name.py
                ├── 01_another_migration.py
                └── a20/       # Pre-release migrations (4th level, PEP 440)
                    └── 01_migration_name.py

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

    def _version_to_path(self, version_str: str) -> Path:
        """
        Convert a version string to its migration directory path.

        For stable versions (e.g., "0.17.5") returns major/minor/patch/.
        For pre-release versions (e.g., "1.0.0a20") returns major/minor/patch/pre/
        where pre is the pre-release segment (e.g., "a20").

        Args:
            version_str: PEP 440 version string

        Returns:
            Path to migration directory
        """
        v = version.parse(version_str)
        major, minor, patch = v.release[:3]
        base = self._migrations_root / str(major) / str(minor) / str(patch)
        if v.pre:
            pre_str = ''.join(str(p) for p in v.pre)
            return base / pre_str
        return base

    def get_pending_migrations(self, current_version: str, target_version: str) -> List[Tuple[str, Path]]:
        """
        Get list of migrations that need to be applied.

        Compares current version (from .hop/config) with target version (from hop_version())
        and returns all migrations in between, sorted by PEP 440 version order.

        Directory structure:
            migrations/major/minor/patch/         ← stable version scripts
            migrations/major/minor/patch/a20/     ← pre-release scripts (4th level)

        Args:
            current_version: Current version from .hop/config (e.g., "0.17.0" or "1.0.0-a19")
            target_version: Target version from hop_version() (e.g., "0.17.1" or "1.0.0-a20")

        Returns:
            List of (version_str, migration_dir_path) tuples in PEP 440 order
        """
        current = version.parse(current_version)
        target = version.parse(target_version)

        candidates = []

        for major_dir in sorted(self._migrations_root.iterdir(), key=lambda p: int(p.name) if p.name.isdigit() else -1):
            if not major_dir.is_dir() or not major_dir.name.isdigit():
                continue
            major = int(major_dir.name)

            for minor_dir in sorted(major_dir.iterdir(), key=lambda p: int(p.name) if p.name.isdigit() else -1):
                if not minor_dir.is_dir() or not minor_dir.name.isdigit():
                    continue
                minor = int(minor_dir.name)

                for patch_dir in sorted(minor_dir.iterdir(), key=lambda p: int(p.name) if p.name.isdigit() else -1):
                    if not patch_dir.is_dir() or not patch_dir.name.isdigit():
                        continue
                    patch = int(patch_dir.name)
                    base_version_str = f"{major}.{minor}.{patch}"

                    # 4th level: pre-release subdirectories (e.g., a20/, b1/, rc2/)
                    for pre_dir in sorted(patch_dir.iterdir()):
                        if not pre_dir.is_dir() or not re.match(r'^[a-z]+\d+$', pre_dir.name):
                            continue
                        pre_version_str = f"{base_version_str}{pre_dir.name}"
                        try:
                            v = version.parse(pre_version_str)
                        except Exception:
                            continue
                        if current < v <= target and list(pre_dir.glob('*.py')):
                            candidates.append((pre_version_str, pre_dir))

                    # Stable version scripts at patch level
                    stable_files = list(patch_dir.glob('*.py'))
                    if stable_files:
                        try:
                            v = version.parse(base_version_str)
                        except Exception:
                            continue
                        if current < v <= target:
                            candidates.append((base_version_str, patch_dir))

        # Sort by PEP 440 version (pre-releases sort before their stable counterpart)
        candidates.sort(key=lambda x: version.parse(x[0]))
        return candidates

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

    def run_migrations(self, target_version: str, create_commit: bool = True) -> Dict:
        """
        Run all pending migrations from the current repo version up to target_version.

        Must be called via Repo.run_migrations_if_needed() (enforced by guard).
        Must be called while on the ho-prod branch.

        Args:
            target_version: Target version string (e.g., "1.0.0-a26")
            create_commit: Whether to create a Git commit after migration

        Returns:
            Dict with keys:
                - target_version: str
                - migrations_applied: List of per-migration result dicts
                - commit_created: bool
                - commit_message: str (only when commit_created is True)
                - sync_result: dict from commit_and_sync_to_active_branches
                - errors: List of non-fatal warning strings
        """
        if not getattr(self._repo, '_migration_running', False):
            raise MigrationManagerError(
                "run_migrations() must be called via Repo.run_migrations_if_needed()."
            )

        result = {
            'target_version': target_version,
            'migrations_applied': [],
            'errors': [],
            'commit_created': False,
            'notified_branches': []
        }

        current_version = self._repo.config.hop_version

        comparison = self._repo.compare_versions(current_version, target_version)
        if comparison >= 0:
            return result

        pending = self.get_pending_migrations(current_version, target_version)

        try:
            for version_str, migration_dir in pending:
                migration_result = self.apply_migration(version_str, migration_dir)
                result['migrations_applied'].append(migration_result)

            # hop_version setter calls write() internally — one write only
            self._repo.config.hop_version = target_version

            self._update_pyproject_dependency_version(target_version)
        except Exception:
            self._repo.hgit.rollback_to_snapshot()
            raise

        all_sync_files = ['pyproject.toml']
        for migration in result['migrations_applied']:
            all_sync_files.extend(migration.get('sync_files', []))
        all_sync_files = list(dict.fromkeys(all_sync_files))

        if create_commit and self._repo.hgit:
            commit_msg = self._create_migration_commit_message(
                current_version, target_version, result['migrations_applied']
            )

            sync_result = self._repo.commit_and_sync_to_active_branches(
                message=commit_msg,
                reason=f"migration {current_version} → {target_version}",
                files=all_sync_files
            )

            result['commit_created'] = True
            result['commit_message'] = commit_msg
            result['sync_result'] = sync_result

            try:
                self._create_migration_tag(current_version, target_version, sync_result)
            except Exception as e:
                result['errors'].append(f"Migration tag creation failed: {e}")

            try:
                self._regenerate_modules_after_migration(current_version, target_version)
            except Exception as e:
                result['errors'].append(f"Module regeneration after migration failed: {e}")

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

        prod_info = branches_status.get('prod_branch')
        prod_branches = [prod_info['name']] if prod_info else []
        patch_branches = [b['name'] for b in branches_status.get('patch_branches', [])]
        release_branches = [b['name'] for b in branches_status.get('release_branches', [])]
        # ho-staged/* branches are frozen after merge — excluded from sync checks
        active_branches = prod_branches + release_branches + patch_branches

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
        if self._repo.production:
            raise MigrationManagerError(
                "PRODUCTION SAFETY: _regenerate_modules_after_migration() is forbidden "
                "on a production server.\nModule regeneration (which includes database "
                "restoration) must never run in production."
            )
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
        # ho-patch/* branches receive .hop/ and pyproject.toml updates but skip
        # module regeneration: their schema may include tables not yet in
        # production, so generate() would delete modules for those new tables.
        # The developer re-runs `hop patch apply` to regenerate with the correct schema.
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
                    #XXX EST-CE QUE POUR ho-patch/* on ne devrait pas utiliser from_release_schema ?
                    # ho-prod and ho-patch/*: use production schema
                    repo.restore_database_from_schema(skip_bootstrap=True)

                if not branch in patch_branches:
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
        config_version = self._repo.config.hop_version

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
