"""The pkg_conf module provides the Repo class.
"""

from __future__ import annotations

import os
import sys
import shutil
import subprocess
import filecmp
import json
import urllib.request
import time
import keyword
import re
import warnings

from typing import Optional
from pathlib import Path
from configparser import ConfigParser
from psycopg2 import OperationalError
from packaging import version

import half_orm
from half_orm import utils
from half_orm_dev.database import Database
from half_orm_dev.hgit import HGit
from half_orm_dev import modules
from half_orm.model import Model
from git.exc import GitCommandError
from half_orm_dev.patch_manager import PatchManager, PatchManagerError
from half_orm_dev.release_manager import ReleaseManager, ReleaseManagerError
from half_orm_dev.migration_manager import MigrationManager, MigrationManagerError
from half_orm_dev.release_file import ReleaseFile, ReleaseFileError

from .utils import TEMPLATE_DIRS, hop_version

class RepoError(Exception):
    pass

class OutdatedHalfORMDevError(RepoError):
    """Raised when installed half_orm_dev version is older than repository requirement."""
    def __init__(self, required_version: str, installed_version: str):
        self.required_version = required_version
        self.installed_version = installed_version
        super().__init__(
            f"Repository requires half_orm_dev >= {required_version} "
            f"but {installed_version} is installed.\n"
            f"Please upgrade: pip install --upgrade half_orm_dev"
        )

class Config:
    """
    Configuration manager for half_orm_dev projects.

    Stores project configuration in .hop/config including:
    - package_name: Python package name (immutable, set at init)
    - hop_version: half_orm_dev version
    - git_origin: Git remote URL
    - devel: Development mode flag

    Note: database_name may differ from package_name when cloning with --database-name.
    The package_name is always used for Python module generation.
    """
    __package_name: Optional[str] = None
    __git_origin: str = ''
    __devel: bool = False
    __hop_version: Optional[str] = None

    def __init__(self, base_dir, **kwargs):
        Config.__file = os.path.join(base_dir, '.hop', 'config')
        # package_name from kwargs takes priority (used during init)
        self.__package_name = kwargs.get('name')
        self.__devel = kwargs.get('devel', False)
        if os.path.exists(self.__file):
            sys.path.insert(0, base_dir)
            self.read()
        # Fallback to directory name if not set (new project without config)
        if not self.__package_name:
            self.__package_name = Path(base_dir).name

    def read(self):
        "Sets __package_name and __hop_version from .hop/config"
        config = ConfigParser()
        config.read(self.__file)
        self.__hop_version = config['halfORM'].get('hop_version', '')
        self.__git_origin = config['halfORM'].get('git_origin', '')
        self.__devel = config['halfORM'].getboolean('devel', False)
        self.__allow_rc = config['halfORM'].getboolean('allow_rc', False)
        # Read package_name from config (takes priority over directory name)
        stored_package_name = config['halfORM'].get('package_name', '')
        if stored_package_name:
            self.__package_name = stored_package_name

    def write(self):
        "Helper: write file in utf8"
        config = ConfigParser()
        self.__hop_version = hop_version()
        data = {
            'hop_version': self.__hop_version,
            'git_origin': self.__git_origin,
            'devel': self.__devel,
            'package_name': self.__package_name or ''
        }
        config['halfORM'] = data
        with open(Config.__file, 'w', encoding='utf-8') as configfile:
            config.write(configfile)

    @property
    def package_name(self):
        """Returns the package name (alias for name)."""
        return self.__package_name

    @package_name.setter
    def package_name(self, name):
        self.__package_name = name

    @property
    def git_origin(self):
        return self.__git_origin
    @git_origin.setter
    def git_origin(self, origin):
        "Sets the git origin and register it in .hop/config"
        self.__git_origin = origin
        self.write()

    @property
    def hop_version(self):
        return self.__hop_version
    @hop_version.setter
    def hop_version(self, version):
        self.__hop_version = version
        self.write()

    @property
    def devel(self):
        return self.__devel
    @devel.setter
    def devel(self, devel):
        self.__devel = devel

    @property
    def allow_rc(self):
        return self.__allow_rc

    @allow_rc.setter
    def allow_rc(self, value):
        self.__allow_rc = value
        self.write()

class LocalConfig:
    """
    Manages local configuration stored in .hop/local_config (not versioned).

    This file contains machine-specific settings that should not be shared
    via Git, such as custom backup directories.
    """
    __backups_dir: Optional[str] = None

    def __init__(self, base_dir):
        self.__file = os.path.join(base_dir, '.hop', 'local_config')
        if os.path.exists(self.__file):
            self.read()

    def read(self):
        """Read local configuration from .hop/local_config"""
        config = ConfigParser()
        config.read(self.__file)
        if 'local' in config:
            self.__backups_dir = config['local'].get('backups_dir')

    def write(self):
        """Write local configuration to .hop/local_config"""
        config = ConfigParser()
        data = {}
        if self.__backups_dir:
            data['backups_dir'] = self.__backups_dir
        if data:
            config['local'] = data
            os.makedirs(os.path.dirname(self.__file), exist_ok=True)
            with open(self.__file, 'w', encoding='utf-8') as configfile:
                config.write(configfile)

    @property
    def backups_dir(self):
        """Returns the configured backups directory, or None if not set"""
        return self.__backups_dir

    @backups_dir.setter
    def backups_dir(self, path):
        """Set the backups directory and save to local_config"""
        self.__backups_dir = path
        self.write()

class Repo:
    """Reads and writes the hop repo conf file.

    Implements Singleton pattern to ensure only one instance per base directory.
    """

    # Singleton storage: base_dir -> instance
    _instances = {}

    # Instance variables
    __new = False
    __checked: bool = False
    __base_dir: Optional[str] = None
    __config: Optional[Config] = None
    __local_config: Optional[LocalConfig] = None
    database: Optional[Database] = None
    hgit: Optional[HGit] = None
    _patch_directory: Optional[PatchManager] = None
    _release_manager: Optional[ReleaseManager] = None

    def __new__(cls):
        """Singleton implementation based on current working directory"""
        # Find the base directory for this context
        base_dir = cls._find_base_dir()

        # Return existing instance if it exists for this base_dir
        if base_dir in cls._instances:
            return cls._instances[base_dir]

        # Create new instance
        instance = super().__new__(cls)
        cls._instances[base_dir] = instance
        return instance

    def __init__(self):
        # Only initialize once per instance
        if hasattr(self, '_initialized'):
            return

        self._initialized = True
        self.__check()

    @classmethod
    def _find_base_dir(cls):
        """Find the base directory for the current context (same logic as __check)"""
        base_dir = os.path.abspath(os.path.curdir)
        while base_dir:
            conf_file = os.path.join(base_dir, '.hop', 'config')
            if os.path.exists(conf_file):
                return base_dir
            par_dir = os.path.split(base_dir)[0]
            if par_dir == base_dir:
                break
            base_dir = par_dir
        return os.path.abspath(os.path.curdir)  # fallback to current dir

    @classmethod
    def clear_instances(cls):
        """Clear all singleton instances - useful for testing or cleanup"""
        for instance in cls._instances.values():
            if instance.database and instance.database.model:
                try:
                    instance.database.model.disconnect()
                except Exception:
                    pass
        cls._instances.clear()

    @property
    def new(self):
        "Returns if the repo is being created or not."
        return Repo.__new

    @property
    def checked(self):
        "Returns if the Repo is OK."
        return self.__checked

    @property
    def production(self):
        "Returns the production status of the database"
        return self.database.production

    @property
    def model(self):
        "Returns the Model (halfORM) of the database"
        return self.database.model

    def __check(self):
        """Searches the hop configuration file for the package.
        This method is called when no hop config file is provided.
        Returns True if we are in a repo, False otherwise.
        """
        base_dir = self._find_base_dir()
        while base_dir:
            if self.__set_base_dir(base_dir):
                self.database = Database(self)
                if self.devel:
                    self.hgit = HGit(self)
                self.__checked = True
                # NOTE: Migration is no longer automatic - user must run `half_orm dev migrate`
                # This prevents implicit changes and gives user control over when migration happens

                # Automatically check and update hooks/config (silent, uses cache)
                # This ensures Git hooks are always up-to-date for all commands
                self.check_and_update(silent=True)
                return
            par_dir = os.path.split(base_dir)[0]
            if par_dir == base_dir:
                break
            base_dir = par_dir

    def __set_base_dir(self, base_dir):
        conf_file = os.path.join(base_dir, '.hop', 'config')
        if os.path.exists(conf_file):
            self.__base_dir = base_dir
            self.__config = Config(base_dir)
            self.__local_config = LocalConfig(base_dir)
            self._validate_version()
            return True
        return False

    def _validate_version(self):
        """
        Validate that installed half_orm_dev version meets repository requirement.

        Raises:
            RepoError: If installed version is lower than required hop_version
        """
        required_version = self.__config.hop_version
        if not required_version:
            # No version requirement in .hop/config, skip validation
            return

        installed_version = hop_version()

        try:
            # Use centralized comparison method
            if self.compare_versions(installed_version, required_version) < 0:
                raise OutdatedHalfORMDevError(required_version, installed_version)
        except OutdatedHalfORMDevError:
            # Re-raise downgrade errors immediately
            raise
        except RepoError as e:
            # If version parsing fails, log warning but don't block
            warnings.warn(
                f"Could not parse version: installed={installed_version}, "
                f"required={required_version}. Error: {e}",
                UserWarning
            )

    def compare_versions(self, version1: str, version2: str) -> int:
        """
        Compare two version strings using packaging.version.

        Properly handles pre-release versions (alpha, beta, rc) according to PEP 440.

        Args:
            version1: First version string (e.g., "0.17.2-a5")
            version2: Second version string (e.g., "0.17.2-a3")

        Returns:
            -1 if version1 < version2
             0 if version1 == version2
             1 if version1 > version2

        Raises:
            RepoError: If either version string is invalid

        Examples:
            >>> repo.compare_versions("0.17.2-a5", "0.17.2-a3")
            1  # 0.17.2a5 > 0.17.2a3
            >>> repo.compare_versions("0.17.2", "0.17.2-a5")
            1  # 0.17.2 > 0.17.2a5 (release > pre-release)
            >>> repo.compare_versions("0.17.1", "0.17.2")
            -1  # 0.17.1 < 0.17.2
            >>> repo.compare_versions("0.17.2", "0.17.2")
            0  # Equal
        """
        try:
            v1 = version.parse(version1)
            v2 = version.parse(version2)

            if v1 < v2:
                return -1
            elif v1 > v2:
                return 1
            else:
                return 0

        except version.InvalidVersion as e:
            raise RepoError(
                f"Invalid version format: {e}"
            ) from e

    def needs_migration(self) -> bool:
        """
        Check if repository needs migration.

        Compares installed half_orm_dev version with repository's hop_version.

        Returns:
            True if installed version > repository version (migration needed)
            False otherwise

        Examples:
            >>> repo.needs_migration()
            True  # Installed 0.18.0, repo at 0.17.2
        """
        if not hasattr(self, '_Repo__config') or not self.__config:
            return False

        installed_version = hop_version()
        config_version = self.__config.hop_version

        if not config_version:
            return False

        try:
            return self.compare_versions(installed_version, config_version) > 0
        except RepoError:
            # If version comparison fails, assume no migration needed
            return False

    def run_migrations_if_needed(self, silent: bool = False) -> dict:
        """
        Run pending migrations using MigrationManager.

        Detects and runs migrations based on current half_orm_dev version
        vs hop_version in .hop/config.

        Behavior:
        - On ho-prod: Runs migration with lock, creates commit, syncs to active branches
        - On other branches: Raises RepoError directing user to checkout ho-prod

        Args:
            silent: If True, suppress informational messages (only show errors)

        Returns:
            dict with keys:
                - migration_needed: bool - True if migration was needed
                - migration_run: bool - True if migration was executed
                - target_version: str - Target version migrated to
                - errors: list - Any errors encountered

        Raises:
            RepoError: If not on ho-prod branch and migration is needed

        Examples:
            # Run migration (raises if not on ho-prod)
            result = repo.run_migrations_if_needed()

            # Check result
            if result['migration_run']:
                print(f"Migrated to {result['target_version']}")
        """
        result = {
            'migration_needed': False,
            'migration_run': False,
            'target_version': None,
            'errors': []
        }

        try:
            # Create migration manager
            migration_mgr = MigrationManager(self)

            # Get current half_orm_dev version
            current_version = hop_version()
            result['target_version'] = current_version

            # Check if migration is needed
            if not migration_mgr.check_migration_needed(current_version):
                return result

            result['migration_needed'] = True

            # Migration must be run on ho-prod branch
            # If not on ho-prod, switch automatically if working directory is clean
            current_branch = self.hgit.branch if self.hgit else 'unknown'
            switched_branch = False

            if not self.hgit or self.hgit.branch != 'ho-prod':
                # Check if working directory is clean
                if self.hgit and self.hgit.git_repo.is_dirty(untracked_files=False):
                    config_version = self.__config.hop_version if hasattr(self, '_Repo__config') else '0.0.0'
                    raise RepoError(
                        f"Repository migration required but working directory has uncommitted changes.\n\n"
                        f"  Repository version: {config_version}\n"
                        f"  Installed version:  {current_version}\n"
                        f"  Current branch:     {current_branch}\n\n"
                        f"  Please commit or stash your changes:\n"
                        f"    git stash\n"
                        f"    OR\n"
                        f"    git add . && git commit -m \"your message\"\n"
                    )

                # Working directory is clean, switch to ho-prod
                try:
                    if not silent:
                        print(f"  Switching to ho-prod...")
                    self.hgit.checkout('ho-prod')
                    switched_branch = True
                    if not silent:
                        print(f"  ✓ Now on ho-prod")
                except Exception as e:
                    raise RepoError(
                        f"Failed to switch to ho-prod: {e}\n\n"
                        f"  Please switch manually:\n"
                        f"    git checkout ho-prod\n"
                        f"    half_orm dev migrate\n"
                    ) from e

            try:
                # Run migrations on ho-prod
                # Branch sync is handled automatically by the decorator
                migration_result = migration_mgr.run_migrations(
                    target_version=current_version,
                    create_commit=True
                )

                result['migration_run'] = True
                result['errors'] = migration_result.get('errors', [])

                # Log success if not silent
                if not silent:
                    if migration_result.get('migrations_applied'):
                        print(f"✓ Applied {len(migration_result['migrations_applied'])} migration(s)")
                    else:
                        print(f"✓ Updated repository version to {current_version}")

            finally:
                # Always try to return to original branch if we switched
                if switched_branch:
                    try:
                        if not silent:
                            print(f"  Returning to {current_branch}...")
                        self.hgit.checkout(current_branch)
                        if not silent:
                            print(f"  ✓ Back on {current_branch}")
                    except Exception as e:
                        # Log warning but don't fail the migration
                        if not silent:
                            print(f"  ⚠️  Could not return to {current_branch}: {e}", file=sys.stderr)
                            print(f"  You are now on ho-prod", file=sys.stderr)

        except RepoError:
            # Re-raise RepoError (for branch check)
            raise
        except MigrationManagerError as e:
            # Log migration errors
            error_msg = f"Migration failed: {e}"
            result['errors'].append(error_msg)
            raise RepoError(error_msg) from e
        except Exception as e:
            # Catch any unexpected errors
            error_msg = f"Unexpected migration error: {e}"
            result['errors'].append(error_msg)
            raise RepoError(error_msg) from e

        return result

    def sync_hop_to_active_branches(self, reason: str = "update", additional_files: list = None) -> dict:
        """
        Synchronize .hop/ directory and optional files from current branch to all other active branches.

        This method ensures that any changes made to .hop/ on the current branch
        are propagated to all other active branches (ho-patch/*, ho-release/*, ho-prod).

        The sync logic is:
        - Source: current branch
        - Targets: all active branches + ho-prod - current branch

        Uses git checkout to copy the entire .hop/ directory from current branch,
        ensuring perfect consistency across all branches.

        Args:
            reason: Description of why sync is happening (for commit message)
            additional_files: Optional list of additional file paths to sync
                             (e.g., ['pyproject.toml'] for migration files)

        Returns:
            dict with keys:
                - synced_branches: List of branch names that were synced
                - skipped_branches: List of branches that were skipped (no changes)
                - errors: List of error messages for failed syncs

        Examples:
            # After modifying .hop/config on ho-prod
            result = repo.sync_hop_to_active_branches("migration 0.17.1 → 0.17.2")
            print(f"Synced {len(result['synced_branches'])} branches")

            # After modifying .hop/ and pyproject.toml on ho-prod
            result = repo.sync_hop_to_active_branches(
                "migration",
                additional_files=['pyproject.toml']
            )
        """
        result = {
            'synced_branches': [],
            'skipped_branches': [],
            'errors': []
        }

        if not self.hgit:
            result['errors'].append("No git repository available")
            return result

        # Source branch is the current branch
        source_branch = self.hgit.branch

        # Get all active branches (including ho-prod, release branches, and patch branches)
        try:
            branches_status = self.hgit.get_active_branches_status()
            patch_branches = [b['name'] for b in branches_status.get('patch_branches', [])]
            release_branches = [b['name'] for b in branches_status.get('release_branches', [])]

            # All branches = ho-prod + release branches + patch branches
            all_branches = ['ho-prod'] + release_branches + patch_branches

            # Filter release branches to avoid syncing to future versions
            # Extract version from source branch if it's a release branch
            source_version = None
            if source_branch.startswith('ho-release/'):
                source_version_str = source_branch.replace('ho-release/', '')
                try:
                    source_version = version.parse(source_version_str)
                except ValueError:
                    pass  # Invalid version, skip filtering

            # If source is a release branch, filter out release branches with higher versions
            filtered_branches = []
            for branch in all_branches:
                if branch == source_branch:
                    continue  # Skip source branch

                # Check if target is a release branch with higher version than source
                if source_version and branch.startswith('ho-release/'):
                    target_version_str = branch.replace('ho-release/', '')
                    try:
                        target_version = version.parse(target_version_str)
                        if target_version > source_version:
                            # Skip branches with higher version
                            result['skipped_branches'].append(f"{branch} (version > {source_version_str})")
                            continue
                    except ValueError:
                        pass  # Invalid version, include it

                filtered_branches.append(branch)

            # Target branches = filtered branches
            target_branches = filtered_branches
        except Exception as e:
            result['errors'].append(f"Failed to get active branches: {e}")
            return result

        # Sync each target branch
        for branch in target_branches:
            try:
                # Checkout to target branch
                self.hgit.checkout(branch)

                # Reset to origin (source of truth) before syncing .hop/
                # This avoids non-fast-forward push failures when another
                # actor has already synced this branch.
                remote_ref = f"origin/{branch}"
                try:
                    synced, status = self.hgit.is_branch_synced(branch)
                    if not synced and status == "diverged":
                        print(
                            f"Warning: branch {branch} has diverged from origin. "
                            f"Resetting to origin (source of truth).",
                            file=sys.stderr
                        )
                    if not synced:
                        self.hgit._HGit__git_repo.git.reset('--hard', remote_ref)
                except GitCommandError:
                    # Remote branch may not exist yet, continue without reset
                    pass

                # Reload config for this branch
                self.__config = Config(self.base_dir)

                # Use git checkout to copy .hop/ from source branch
                # This updates/adds files but doesn't remove deleted files
                self.hgit._HGit__git_repo.git.checkout(source_branch, '--', '.hop/')

                # Also checkout additional files if specified
                if additional_files:
                    for file_path in additional_files:
                        try:
                            self.hgit._HGit__git_repo.git.checkout(source_branch, '--', file_path)
                        except GitCommandError:
                            # File might not exist in source branch, skip
                            pass

                # Find files that exist in target but not in source and remove them
                # IMPORTANT: Only remove files for versions that exist in source
                # Don't remove release files (*-patches.toml, *.txt) for other versions
                try:
                    # Get list of files in .hop/ on current branch (target)
                    target_files_output = self.hgit._HGit__git_repo.git.ls_files('.hop/')
                    target_files = set(f for f in target_files_output.split('\n') if f.strip())

                    # Get list of files in .hop/ on source branch
                    source_files_output = self.hgit._HGit__git_repo.git.ls_tree('-r', '--name-only', source_branch, '.hop/')
                    source_files = set(f for f in source_files_output.split('\n') if f.strip())

                    # Get versions present in source (from .toml and .txt release files)
                    source_versions = set()
                    for file_path in source_files:
                        # Extract version from release files
                        if file_path.startswith('.hop/releases/'):
                            filename = file_path.replace('.hop/releases/', '')
                            # Match patterns: X.Y.Z-patches.toml, X.Y.Z.txt, X.Y.Z-rcN.txt, X.Y.Z-hotfixN.txt
                            match = re.match(r'^(\d+\.\d+\.\d+)[-.]', filename)
                            if match:
                                source_versions.add(match.group(1))

                    # Files to delete = in target but not in source
                    files_to_delete = target_files - source_files

                    # Filter: only delete files for versions present in source
                    # This prevents deleting release files for unrelated versions
                    safe_to_delete = []
                    for file_path in files_to_delete:
                        if not file_path:
                            continue
                        # Check if it's a release file
                        if file_path.startswith('.hop/releases/'):
                            filename = file_path.replace('.hop/releases/', '')
                            match = re.match(r'^(\d+\.\d+\.\d+)[-.]', filename)
                            if match:
                                file_version = match.group(1)
                                # Only delete if this version exists in source
                                if file_version in source_versions:
                                    safe_to_delete.append(file_path)
                            else:
                                # Not a versioned file, safe to delete
                                safe_to_delete.append(file_path)
                        else:
                            # Not in releases/, safe to delete
                            safe_to_delete.append(file_path)

                    # Remove files
                    for file_path in safe_to_delete:
                        self.hgit._HGit__git_repo.git.rm(file_path)
                except Exception as e:
                    # If something fails in deletion detection, log but continue
                    # The checkout already happened, so we have the updates
                    pass

                # Stage all changes
                self.hgit.add('.hop/')
                if additional_files:
                    for file_path in additional_files:
                        try:
                            self.hgit.add(file_path)
                        except GitCommandError:
                            pass  # File might not exist

                # Check if there are changes
                status = self.hgit._HGit__git_repo.git.status('--porcelain')
                if not status.strip():
                    # No changes, skip
                    result['skipped_branches'].append(branch)
                    continue

                # Commit changes
                commit_msg = f"[HOP] Sync .hop/ from {source_branch} ({reason})"
                self.hgit.commit('-m', commit_msg)

                # Push to remote
                self.hgit.push_branch(branch)

                result['synced_branches'].append(branch)

            except Exception as e:
                result['errors'].append(f"{branch}: {str(e)}")

        # Return to source branch
        try:
            self.hgit.checkout(source_branch)
            # Reload config for source branch
            self.__config = Config(self.base_dir)
        except Exception as e:
            result['errors'].append(f"Failed to return to {source_branch}: {e}")

        return result

    def sync_and_validate_ho_prod(self):
        """
        Synchronize ho-prod with remote origin and validate half_orm_dev version.

        This method MUST be called before any operation that acquires a branch lock
        to ensure:
        1. ho-prod is up-to-date with remote (pull)
        2. All other branches are fetched with prune
        3. The installed half_orm_dev version is compatible with repository requirements

        This is critical because:
        - Another developer may have upgraded the repository to a newer half_orm_dev version
        - The pull on ho-prod will fetch the updated .hop/config with new hop_version
        - We must block immediately if the installed version is outdated
        - This prevents dangerous operations with incompatible versions

        Raises:
            OutdatedHalfORMDevError: If repository requires newer half_orm_dev version
            RepoError: If working directory is dirty or other git errors

        Implementation:
        1. Check working directory is clean
        2. Save current branch
        3. Checkout ho-prod temporarily
        4. Pull ho-prod from origin
        5. Fetch all branches with prune
        6. Reload .hop/config
        7. Validate hop_version compatibility
        8. Checkout back to original branch

        Usage:
            Called automatically by @with_dynamic_branch_lock decorator before
            acquiring any branch lock.
        """
        if not self.hgit:
            # No git repository, skip synchronization
            return

        current_branch = None
        git_repo = None
        try:
            git_repo = self.hgit.git_repo
            current_branch = git_repo.active_branch.name

            # Check if working directory is clean
            if git_repo.is_dirty(untracked_files=False):
                raise RepoError(
                    f"Working directory has uncommitted changes.\n"
                    f"Please commit or stash your changes before running this command:\n"
                    f"  git stash\n"
                    f"  OR\n"
                    f"  git add . && git commit -m \"your message\""
                )

            # Switch to ho-prod temporarily
            git_repo.heads['ho-prod'].checkout()

            # Pull ho-prod from origin
            git_repo.remotes.origin.pull('ho-prod')

            # Fetch all other branches with prune
            git_repo.remotes.origin.fetch(prune=True)

            # Switch back to original branch
            git_repo.heads[current_branch].checkout()

            # Reload config to get the potentially updated hop_version
            self.__config = Config(self.__base_dir)
            installed_version = hop_version()
            required_version = self.__config.hop_version

            # Validate version compatibility
            if not _is_version_compatible(installed_version, required_version):
                raise OutdatedHalfORMDevError(required_version, installed_version)

        except RepoError:
            # Re-raise RepoError (dirty working directory)
            raise
        except OutdatedHalfORMDevError:
            # Re-raise version error (repository was updated to newer version)
            raise
        except Exception as e:
            # If we're in detached HEAD or any error, try to return to original state
            # and continue (offline mode, no remote, etc.)
            try:
                if current_branch and git_repo:
                    git_repo.heads[current_branch].checkout()
            except (GitCommandError, IndexError, TypeError):
                pass
            # Log but don't fail (offline mode, no remote, etc.)
            # Only critical errors (dirty repo, version mismatch) should block

    def commit_and_sync_to_active_branches(
        self,
        message: str,
        reason: str = None,
        files: list = None
    ) -> dict:
        """
        Commit files on current branch, push it, and sync .hop/ to all other active branches.

        This is a unified method that combines:
        1. Stage files (always includes .hop/)
        2. Commit on current branch with provided message
        3. Push current branch
        4. Sync .hop/ to all other active branches

        Args:
            message: Commit message
            reason: Optional reason for sync (if not provided, extracts from message)
            files: Optional list of additional files to stage (beyond .hop/)

        Returns:
            dict: {
                'commit_hash': str,
                'pushed_branch': str,
                'sync_result': dict from sync_hop_to_active_branches()
            }

        Example:
            result = repo.commit_and_sync_to_active_branches(
                message="[HOP] Create release 0.2.0 branch and patches file",
                files=['Patches/0.2.0-candidates.txt']
            )
        """
        result = {
            'commit_hash': None,
            'pushed_branch': None,
            'sync_result': None
        }

        current_branch = self.hgit.branch

        # Always include .hop/ + any additional files
        all_files = ['.hop/']
        if files:
            all_files.extend(files)

        # 1. Stage files
        for file_path in all_files:
            self.hgit.add(file_path)

        # 2. Commit on current branch
        commit_hash = self.hgit.commit("-m", message)
        result['commit_hash'] = commit_hash

        # 3. Push current branch
        self.hgit.push_branch(current_branch)
        result['pushed_branch'] = current_branch

        # 4. Extract reason from message if not provided
        if reason is None:
            # Try to extract a short reason from commit message
            # Remove common prefixes like "[HOP]" and take first part
            reason_text = message.replace('[HOP]', '').strip()
            # Take first sentence or first 50 chars
            if '.' in reason_text:
                reason = reason_text.split('.')[0]
            else:
                reason = reason_text[:50]

        # 5. Sync .hop/ (and additional files) to all other active branches
        # Filter out .hop/ since sync_hop_to_active_branches always syncs it
        additional_files = [f for f in (files or []) if not f.startswith('.hop')]
        sync_result = self.sync_hop_to_active_branches(
            reason=reason,
            additional_files=additional_files if additional_files else None
        )
        result['sync_result'] = sync_result

        return result

    @property
    def base_dir(self):
        "Returns the base dir of the repository"
        return self.__base_dir

    @property
    def name(self):
        "Returns the name of the package"
        return self.__config and self.__config.package_name or None

    @property
    def database_name(self):
        """Returns the database name for DB connection.

        Uses .hop/alt_config if present (for clones with --database-name),
        otherwise falls back to package_name.

        This is different from `name` (package_name) which is used for
        Python module generation.
        """
        alt_config_path = os.path.join(self.__base_dir, '.hop', 'alt_config')
        if os.path.exists(alt_config_path):
            with open(alt_config_path, 'r', encoding='utf-8') as f:
                alt_name = f.read().strip()
                if alt_name:
                    return alt_name
        return self.name

    @property
    def git_origin(self):
        "Returns the git origin registered in .hop/config"
        return self.__config.git_origin
    @git_origin.setter
    def git_origin(self, origin):
        self.__config.git_origin = origin

    @property
    def allow_rc(self):
        """Returns whether RC releases are allowed in production."""
        return self.__config.allow_rc

    def __hop_version_mismatch(self):
        """Returns a boolean indicating if current hop version is different from
        the last hop version used with this repository.
        """
        return hop_version() != self.__config.hop_version

    @property
    def devel(self):
        return self.__config.devel

    @property
    def releases_dir(self):
        """Returns the path to the releases directory (.hop/releases)."""
        return os.path.join(self.__base_dir, '.hop', 'releases')

    @property
    def model_dir(self):
        """Returns the path to the model directory (.hop/model)."""
        return os.path.join(self.__base_dir, '.hop', 'model')

    @property
    def backups_dir(self):
        """
        Returns the path to the backups directory.

        Priority order:
        1. Environment variable HALF_ORM_BACKUPS_DIR
        2. .hop/local_config backups_dir setting
        3. Default: .hop/backups
        """
        # Check environment variable first
        env_backups = os.environ.get('HALF_ORM_BACKUPS_DIR')
        if env_backups:
            return env_backups

        # Check local_config
        if self.__local_config and self.__local_config.backups_dir:
            return self.__local_config.backups_dir

        # Default to .hop/backups
        return os.path.join(self.__base_dir, '.hop', 'backups')

    @property
    def state(self):
        "Returns the state (str) of the repository."
        res = [f'hop version: {utils.Color.bold(hop_version())}']
        res += [f'half-orm version: {utils.Color.bold(half_orm.__version__)}\n']
        if self.__config:
            hop_version_display = utils.Color.red(self.__config.hop_version) if \
                self.__hop_version_mismatch() else \
                utils.Color.green(self.__config.hop_version)
            res += [
                '[Hop repository]',
                f'- base directory: {self.__base_dir}',
                f'- package name: {self.__config.name}',
                f'- hop version: {hop_version_display}'
            ]
            res.append(self.database.state)
            res.append(str(self.hgit))
        return '\n'.join(res)

    @property
    def patch_manager(self) -> PatchManager:
        """
        Get PatchManager instance for patch-centric operations.

        Provides access to Patches/ directory management including:
        - Creating patch directories with minimal README templates
        - Validating patch structure following KISS principles
        - Applying SQL and Python files in lexicographic order
        - Listing and managing existing patches

        Lazy initialization ensures PatchManager is only created when needed
        and cached for subsequent accesses.

        Returns:
            PatchManager: Instance for managing Patches/ operations

        Raises:
            PatchManagerError: If repository not in development mode
            RuntimeError: If repository not properly initialized

        Examples:
            # Create new patch directory
            repo.patch_manager.create_patch_directory("456-user-auth")

            # Apply patch files using repo's model
            applied = repo.patch_manager.apply_patch_files("456-user-auth", repo.model)

            # List all existing patches
            patches = repo.patch_manager.list_all_patches()

            # Get detailed patch structure analysis
            structure = repo.patch_manager.get_patch_structure("456-user-auth")
            if structure.is_valid:
                print(f"Patch has {len(structure.files)} executable files")
        """
        # Validate repository is properly initialized
        if not self.__checked:
            raise RuntimeError(
                "Repository not initialized. PatchManager requires valid repository context."
            )

        # Validate development mode requirement
        if not self.devel:
            raise PatchManagerError(
                "PatchManager operations require development mode. "
                "Enable development mode in repository configuration."
            )

        # Lazy initialization with caching
        if self._patch_directory is None:
            try:
                self._patch_directory = PatchManager(self)
            except Exception as e:
                raise PatchManagerError(
                    f"Failed to initialize PatchManager: {e}"
                ) from e

        return self._patch_directory

    def clear_patch_directory_cache(self) -> None:
        """
        Clear cached PatchManager instance.

        Forces re-initialization of PatchManager on next access.
        Useful for testing or when repository configuration changes.

        Examples:
            # Clear cache after configuration change
            repo.clear_patch_directory_cache()

            # Next access will create fresh instance
            new_patch_dir = repo.patch_manager
        """
        self._patch_directory = None

    def has_patch_directory_support(self) -> bool:
        """
        Check if repository supports PatchManager operations.

        Validates that repository is in development mode and properly
        initialized without actually creating PatchManager instance.

        Returns:
            bool: True if PatchManager operations are supported

        Examples:
            if repo.has_patch_directory_support():
                patches = repo.patch_manager.list_all_patches()
            else:
                print("Repository not in development mode")
        """
        return self.__checked and self.devel

    @property
    def release_manager(self) -> ReleaseManager:
        """
        Get ReleaseManager instance for release lifecycle operations.

        Provides access to releases/ directory management including:
        - Preparing new releases (stage files creation)
        - Version calculation and management
        - Release lifecycle (stage → rc → production)
        - Production version tracking

        Lazy initialization ensures ReleaseManager is only created when needed
        and cached for subsequent accesses.

        Returns:
            ReleaseManager: Instance for managing releases/ operations

        Raises:
            RuntimeError: If repository not properly initialized

        Examples:
            # Create new patch release
            result = repo.release_manager.create_release('patch')
            print(f"Created: {result['version']}")

            # Find latest version
            latest = repo.release_manager.find_latest_version()

            # Calculate next version
            next_ver = repo.release_manager.calculate_next_version(latest, 'minor')
        """
        # Validate repository is properly initialized
        if not self.__checked:
            raise RuntimeError(
                "Repository not initialized. ReleaseManager requires valid repository context."
            )

        # Lazy initialization with caching
        if self._release_manager is None:
            self._release_manager = ReleaseManager(self)

        return self._release_manager

    def clear_release_manager_cache(self) -> None:
        """
        Clear cached ReleaseManager instance.

        Forces re-initialization of ReleaseManager on next access.
        Useful for testing or when repository configuration changes.

        Examples:
            # Clear cache after configuration change
            repo.clear_release_manager_cache()

            # Next access will create fresh instance
            new_release_mgr = repo.release_manager
        """
        self._release_manager = None

    def init_git_centric_project(self, package_name, git_origin):
        """
        Initialize new halfORM project with Git-centric architecture.

        Creates a complete project structure with Git repository, configuration,
        and generated Python package from database schema. This is the main entry
        point for creating new projects, replacing the legacy init(package_name, devel)
        workflow.

        Args:
            package_name: Name for the project directory and Python package
            git_origin: Git remote origin URL (HTTPS, SSH, or Git protocol)

        Raises:
            ValueError: If package_name or git_origin are invalid
            FileExistsError: If project directory already exists
            OperationalError: If database connection fails

        Process:
            1. Validate package name and git origin URL
            2. Verify database is configured
            3. Connect to database and detect mode (metadata → devel=True)
            4. Create project directory structure
            5. Generate configuration files (.hop/config with git_origin)
            6. Create Git-centric directories (Patches/, releases/)
            7. Initialize Database instance (self.database)
            8. Generate Python package structure
            9. Initialize Git repository with ho-prod branch
            10. Generate template files (README, .gitignore, pyproject.toml, Pipfile)
            11. Save model/schema-0.0.0.sql

        Git-centric Architecture:
            - Main branch: ho-prod (replaces hop_main)
            - Patch branches: ho-patch/<patch-name>
            - Directory structure: Patches/<patch-name>/ for schema files
            - Release management: releases/X.Y.Z-stage.txt workflow

        Mode Detection:
            - Full development mode: Database has half_orm_meta schemas
            - Sync-only mode: Database lacks metadata (read-only package sync)

        Examples:
            # After database configuration with valid git origin
            repo = Repo()
            repo.init_git_centric_project(
                "my_blog",
                "https://github.com/user/my_blog.git"
            )
            # → Creates my_blog/ with full development mode if metadata present

            # With SSH URL
            repo.init_git_centric_project(
                "my_app",
                "git@github.com:user/my_app.git"
            )

            # Self-hosted Git server
            repo.init_git_centric_project(
                "company_project",
                "https://git.company.com/team/project.git"
            )

        Migration Notes:
            - Replaces Repo.init(package_name, devel) from legacy workflow
            - Database creation moved to separate init-database command
            - Mode detection replaces explicit --devel flag
            - Git branch naming updated (hop_main → ho-prod)
            - git_origin is now mandatory (was optional/auto-discovered)
        """
        # Step 1: Validate package name
        self._validate_package_name(package_name)

        # Step 1b: Validate git origin URL (EARLY validation)
        self._validate_git_origin_url(git_origin)

        # Step 2: Connect to database and detect mode
        devel_mode = self._detect_development_mode(package_name)

        # Step 4: Setup project directory
        self._create_project_directory(package_name)

        # Step 5: Initialize configuration (now includes git_origin)
        self._initialize_configuration(package_name, devel_mode, git_origin.strip())

        # Step 6: Create Git-centric directories
        self._create_git_centric_structure()

        # Step 7: Initialize Database instance (CRITICAL - must be before generate)
        self.database = Database(self)

        # Step 8: Generate Python package
        self._generate_python_package()

        # Step 9: Generate template files
        self._generate_template_files()

        # Step 10: Save initial schema dump
        self._dump_initial_schema()

        # Step 11: Initialize Git repository with ho-prod branch
        self._initialize_git_repository()

        # step 12: Protect ho-prod from direct commits
        self.install_git_hooks()

    def install_git_hooks(self, force: bool = False) -> dict:
        """
        Install or update Git hooks from templates.

        Copies all hooks from templates/git-hooks/ to .git/hooks/ and makes them executable.
        Only updates if hook content has changed or if force=True.

        Args:
            force: If True, always install hooks even if content is identical

        Returns:
            dict with keys:
                'installed': bool - True if any hook was installed/updated
                'action': str - Overall action: 'installed', 'updated', or 'skipped'

        Examples:
            # Install hooks (only if different)
            result = repo.install_git_hooks()
            # → {'installed': True, 'action': 'updated'}

            # Force install
            result = repo.install_git_hooks(force=True)
            # → {'installed': True, 'action': 'installed'}
        """

        hooks_source_dir = os.path.join(TEMPLATE_DIRS, 'git-hooks')
        hooks_dest_dir = os.path.join(self.__base_dir, '.git', 'hooks')

        # Create .git/hooks directory if it doesn't exist
        os.makedirs(hooks_dest_dir, exist_ok=True)

        any_installed = False
        overall_action = 'skipped'

        # Install all hooks from templates/git-hooks/
        for hook_name in os.listdir(hooks_source_dir):
            hook_source = os.path.join(hooks_source_dir, hook_name)
            hook_dest = os.path.join(hooks_dest_dir, hook_name)

            # Skip non-files
            if not os.path.isfile(hook_source):
                continue

            # Determine action for this hook
            if not os.path.exists(hook_dest):
                action = 'installed'
                should_install = True
            elif force:
                action = 'installed'
                should_install = True
            elif not filecmp.cmp(hook_source, hook_dest, shallow=False):
                action = 'updated'
                should_install = True
            else:
                action = 'skipped'
                should_install = False

            # Install if needed
            if should_install:
                shutil.copy(hook_source, hook_dest)
                os.chmod(hook_dest, 0o755)
                any_installed = True
                # Update overall action (installed > updated > skipped)
                if action == 'installed' or overall_action == 'skipped':
                    overall_action = action

        return {
            'installed': any_installed,
            'action': overall_action
        }

    def _check_version_update(self) -> dict:
        """
        Check if a new version of half_orm_dev is available on PyPI.

        Returns:
            dict with keys:
                - current_version: Current installed version
                - latest_version: Latest version on PyPI (or None if check failed)
                - update_available: bool - True if update available
                - error: Error message if check failed

        Examples:
            version_info = repo._check_version_update()
            if version_info['update_available']:
                print(f"Update available: {version_info['latest_version']}")
        """
        result = {
            'current_version': None,
            'latest_version': None,
            'update_available': False,
            'error': None
        }

        # Get current version from version.txt
        try:
            version_file = Path(__file__).parent / 'version.txt'
            if version_file.exists():
                result['current_version'] = version_file.read_text().strip()
        except Exception as e:
            result['error'] = f"Could not read current version: {e}"
            return result

        # Check PyPI for latest version
        try:
            url = "https://pypi.org/pypi/half_orm_dev/json"
            with urllib.request.urlopen(url, timeout=5) as response:
                data = json.loads(response.read().decode())
                result['latest_version'] = data['info']['version']

                # Compare versions using packaging.version for proper semantic versioning
                if result['current_version'] and result['latest_version']:
                    try:
                        current = version.parse(result['current_version'])
                        latest = version.parse(result['latest_version'])
                        if current < latest:
                            result['update_available'] = True
                    except ValueError:
                        # Fallback to string comparison if packaging fails
                        if result['current_version'] != result['latest_version']:
                            result['update_available'] = True

        except Exception as e:
            result['error'] = f"Could not check PyPI: {e}"

        return result

    def check_and_update(
        self,
        dry_run: bool = False,
        silent: bool = True,
        force_check: bool = False
    ) -> dict:
        """
        Check and update project configuration.

        Checks project health and updates components as needed. Can be called
        automatically at the start of commands (with silent=True) or explicitly
        by the user (with silent=False).

        Uses caching to avoid checking too frequently (once per day max unless force_check=True).

        Always detects stale branches (branches that no longer exist on remote).
        When not in silent mode, prompts user to delete them.

        Args:
            dry_run: If True, don't make changes, just report what would be done
            silent: If True, don't print messages (for automatic checks)
            force_check: If True, bypass cache and always check

        Returns:
            dict with keys:
                'hooks': dict from install_git_hooks()
                'stale_branches': dict with 'candidates', 'deleted', 'errors'
                'cache_hit': bool - True if cache was used

        Examples:
            # Automatic check (silent, uses cache)
            result = repo.check_and_update(silent=True)

            # Manual check with stale branch detection
            result = repo.check_and_update(silent=False)

            # Force check (bypass cache)
            result = repo.check_and_update(force_check=True)
        """

        # Check cache (only if not forced and silent mode)
        cache_file = Path(self.__base_dir) / '.git' / '.half_orm_check_cache'
        cache_hit = False

        if silent and not force_check and cache_file.exists():
            try:
                last_check = float(cache_file.read_text().strip())
                # Check once per day (86400 seconds)
                if time.time() - last_check < 86400:
                    cache_hit = True
                    return {
                        'hooks': {'installed': False, 'action': 'skipped'},
                        'branches': {},
                        'cache_hit': True
                    }
            except (ValueError, IOError):
                pass

        # Perform checks
        result = {
            'cache_hit': False
        }

        # 0. Update ho-prod from remote and fetch all branches
        # This ensures we have the latest hop_version and branch status
        # Must run in BOTH silent and non-silent modes for hop_version validation
        if self.hgit:
            current_branch = None
            git_repo = None
            try:
                git_repo = self.hgit.git_repo
                current_branch = git_repo.active_branch.name

                # Check if working directory is clean (only in non-silent mode)
                if not silent and git_repo.is_dirty(untracked_files=False):
                    raise RepoError(
                        f"Working directory has uncommitted changes.\n"
                        f"Please commit or stash your changes before running check:\n"
                        f"  git stash\n"
                        f"  OR\n"
                        f"  git add . && git commit -m \"your message\""
                    )

                # Switch to ho-prod temporarily
                git_repo.heads['ho-prod'].checkout()

                # Pull ho-prod from origin
                git_repo.remotes.origin.pull('ho-prod')

                # Fetch all other branches with prune
                git_repo.remotes.origin.fetch(prune=True)

                # Switch back to original branch
                git_repo.heads[current_branch].checkout()

            except RepoError:
                # Re-raise RepoError (dirty working directory)
                raise
            except Exception as e:
                # If we're in detached HEAD or any error, try to return to original state
                # and continue (offline mode, no remote, etc.)
                try:
                    if current_branch and git_repo:
                        git_repo.heads[current_branch].checkout()
                except (GitCommandError, IndexError, TypeError):
                    pass

        # 0b. Sync all active branches that are behind remote
        # Origin is the source of truth - always sync to match remote
        sync_result = {'synced': [], 'skipped': [], 'errors': []}
        if self.hgit and not dry_run:
            try:
                sync_result = self.hgit.sync_active_branches(pattern="ho-*")
            except GitCommandError:
                pass  # Best effort - continue even if sync fails

        result['branch_sync'] = sync_result

        # 1. Check and update Git hooks
        if not dry_run:
            result['hooks'] = self.install_git_hooks()
        else:
            # Dry run: just check if update would be needed
            hooks_source_dir = os.path.join(TEMPLATE_DIRS, 'git-hooks')
            hooks_dest_dir = os.path.join(self.__base_dir, '.git', 'hooks')

            would_install = False
            would_update = False

            for hook_name in os.listdir(hooks_source_dir):
                hook_source = os.path.join(hooks_source_dir, hook_name)
                hook_dest = os.path.join(hooks_dest_dir, hook_name)

                if not os.path.isfile(hook_source):
                    continue

                if not os.path.exists(hook_dest):
                    would_install = True
                elif not filecmp.cmp(hook_source, hook_dest, shallow=False):
                    would_update = True

            if would_install:
                result['hooks'] = {'installed': False, 'action': 'would_install'}
            elif would_update:
                result['hooks'] = {'installed': False, 'action': 'would_update'}
            else:
                result['hooks'] = {'installed': False, 'action': 'skipped'}

        # 2. Get active branches status and release files
        try:
            # Read release files directly from local filesystem (.hop/releases/)
            releases_info = {}
            if hasattr(self, 'release_manager'):
                releases_dir = Path(self.releases_dir)

                # Read TOML patches files from local filesystem
                try:
                    for toml_file in releases_dir.glob('*-patches.toml'):
                        version = toml_file.stem.replace('-patches', '')

                        try:
                            # Use ReleaseFile to parse directly from filesystem
                            release_file = ReleaseFile(version, releases_dir)
                            metadata = release_file.get_metadata()

                            releases_info[version] = {
                                'patches_file': str(toml_file.relative_to(self.__base_dir)),
                                'candidates': release_file.get_patches(status='candidate'),
                                'staged': release_file.get_patches(status='staged'),
                                'metadata': metadata
                            }
                        except (ReleaseFileError, OSError):
                            # Failed to parse TOML - skip this file
                            pass

                except OSError:
                    pass  # Silent failure - will result in empty releases_info

            result['active_branches'] = self.hgit.get_active_branches_status(
                stage_files=[]  # No longer used with TOML format
            )
            result['releases_info'] = releases_info

            # Get production version from model/schema.sql symlink
            production_version = None
            if hasattr(self, 'release_manager'):
                try:
                    production_version = self.release_manager._get_production_version()
                except ReleaseManagerError:
                    # No production version available (e.g., model/ doesn't exist yet)
                    pass
            result['production_version'] = production_version

            # Get orphaned patches (only if patch_manager already initialized)
            orphaned_patches = []
            if self._patch_directory is not None:
                try:
                    status_map = self.patch_manager.get_patch_status_map()
                    orphaned_patches = [
                        patch_id for patch_id, info in status_map.items()
                        if info.get('status') == 'orphaned'
                    ]
                except PatchManagerError:
                    pass  # Best effort
            result['orphaned_patches'] = orphaned_patches

        except Exception as e:
            print(f"⚠️  Warning: Failed to gather status info: {e}", file=sys.stderr)
            result['active_branches'] = {
                'current_branch': None,
                'patch_branches': [],
                'release_branches': []
            }
            result['releases_info'] = {}
            result['production_version'] = None
            result['orphaned_patches'] = []

        # 3. Detect and optionally prune stale branches
        # Always detect stale branches (for display), but only prompt/delete when not silent
        stale_branches_result = {
            'candidates': [],
            'deleted': [],
            'errors': []
        }

        if not silent:
            # Detect stale branches (dry_run=True to just get the list)
            detect_result = self.hgit.prune_local_branches(
                pattern="ho-*",
                dry_run=True,
                exclude_current=True
            )
            stale_branches_result['candidates'] = detect_result.get('deleted', [])

        result['stale_branches'] = stale_branches_result

        # 4. Check version (only for explicit checks, not silent)
        if not silent:
            result['version'] = self._check_version_update()
        else:
            result['version'] = None

        # Update cache
        if not dry_run and silent:
            try:
                cache_file.write_text(str(time.time()))
            except IOError:
                pass  # Best effort

        return result

    def _validate_package_name(self, package_name):
        """
        Validate package name follows Python package naming conventions.

        Args:
            package_name (str): Package name to validate

        Raises:
            ValueError: If package name is invalid

        Rules:
            - Not None or empty
            - Valid Python identifier (letters, numbers, underscore)
            - Cannot start with digit
            - Recommended: lowercase with underscores

        Examples:
            _validate_package_name("my_blog")      # Valid
            _validate_package_name("my-blog")      # Valid (converted to my_blog)
            _validate_package_name("9invalid")     # Raises ValueError
            _validate_package_name("my blog")      # Raises ValueError
        """
        # Check for None
        if package_name is None:
            raise ValueError("Package name cannot be None")

        # Check type
        if not isinstance(package_name, str):
            raise ValueError(f"Package name must be a string, got {type(package_name).__name__}")

        # Check for empty string
        if not package_name or not package_name.strip():
            raise ValueError("Package name cannot be empty")

        # Clean the name
        package_name = package_name.strip()

        # Convert hyphens to underscores (common convention)
        normalized_name = package_name.replace('-', '_')

        # Check if starts with digit
        if normalized_name[0].isdigit():
            raise ValueError(f"Package name '{package_name}' cannot start with a digit")

        # Check for valid Python identifier characters
        # Allow only letters, numbers, and underscores
        if not normalized_name.replace('_', '').isalnum():
            raise ValueError(
                f"Package name '{package_name}' contains invalid characters. "
                "Use only letters, numbers, underscore, and hyphen."
            )

        # Check for Python reserved keywords
        if keyword.iskeyword(normalized_name):
            raise ValueError(
                f"Package name '{package_name}' is a Python reserved keyword"
            )

        # Store normalized name for later use
        return normalized_name

    def _detect_development_mode(self, package_name):
        """
        Detect development mode based on metadata presence in database.

        Automatically determines if full development mode (with patch management)
        or sync-only mode based on half_orm_meta schemas presence.

        Args:
            package_name (str): Database name to check

        Returns:
            bool: True if metadata present (full mode), False if sync-only

        Detection Logic:
            - Query database for half_orm_meta.hop_release table
            - Present → devel=True (full development mode)
            - Absent → devel=False (sync-only mode)

        Examples:
            # Database with metadata
            mode = _detect_development_mode("my_blog")
            assert mode is True  # Full development mode

            # Database without metadata
            mode = _detect_development_mode("legacy_db")
            assert mode is False  # Sync-only mode
        """
        from half_orm.model import Model # Needed here for tests ?

        # Check if we already have a Model instance (from _verify_database_configured)
        if hasattr(self, 'database') and self.database and hasattr(self.database, 'model'):
            model = self.database.model
        else:
            # Create new Model instance
            model = Model(package_name)

        # Check for metadata table presence
        return model.has_relation('half_orm_meta.hop_release')

    def _create_project_directory(self, package_name):
        """
        Create project root directory with validation.

        Args:
            package_name (str): Name for project directory

        Raises:
            FileExistsError: If directory already exists
            OSError: If directory creation fails

        Process:
            1. Build absolute path from current directory
            2. Check directory doesn't already exist
            3. Create directory
            4. Store path in self.__base_dir

        Examples:
            # Success case
            _create_project_directory("my_blog")
            # Creates: /current/path/my_blog/

            # Error case
            _create_project_directory("existing_dir")
            # Raises: FileExistsError
        """
        # Build absolute path
        cur_dir = os.path.abspath(os.path.curdir)
        project_path = os.path.join(cur_dir, package_name)

        # Check if directory already exists
        if os.path.exists(project_path):
            raise FileExistsError(
                f"Directory '{package_name}' already exists at {project_path}.\n"
                "Choose a different project name or remove the existing directory."
            )

        # Create directory
        try:
            os.makedirs(project_path)
        except PermissionError as e:
            raise PermissionError(
                f"Permission denied: Cannot create directory '{project_path}'.\n"
                f"Check your write permissions for the current directory."
            ) from e
        except OSError as e:
            raise OSError(
                f"Failed to create directory '{project_path}': {e}"
            ) from e

        # Store base directory path
        self._Repo__base_dir = project_path

        return project_path


    def _initialize_configuration(self, package_name, devel_mode, git_origin):
        """
        Initialize .hop/config file with project settings.

        Creates .hop directory and config file with project metadata including
        package name, hop version, development mode, and git origin URL.

        Args:
            package_name: Name of the Python package
            devel_mode: Boolean indicating full development vs sync-only mode
            git_origin: Git remote origin URL

        Creates:
            .hop/config file with INI format containing:
            - package_name: Project/package name
            - hop_version: Current half_orm_dev version
            - devel: Development mode flag
            - git_origin: Git remote URL

        Examples:
            _initialize_configuration("my_blog", True, "https://github.com/user/my_blog.git")
            # Creates .hop/config:
            # [halfORM]
            # package_name = my_blog
            # hop_version = 0.17.0
            # devel = True
            # git_origin = https://github.com/user/my_blog.git
        """
        # Create .hop directory
        hop_dir = os.path.join(self.__base_dir, '.hop')
        os.makedirs(hop_dir, exist_ok=True)

        # Initialize Config object (stores git_origin)
        self.__config = Config(self.__base_dir, name=package_name, devel=devel_mode)

        # Set git_origin in config
        self.__config.git_origin = git_origin

        # Write config file (Config.write() handles the actual file writing)
        self.__config.write()

    def _create_git_centric_structure(self):
        """
        Create Git-centric directory structure for patch management.

        Creates directories required for Git-centric workflow:
        - Patches/ for patch development
        - .hop/releases/ for release management
        - .hop/model/ for schema snapshots
        - .hop/backups/ for database backups (or custom location)

        Only created in development mode (devel=True).

        Directory Structure:
            Patches/
            ├── README.md          # Patch development guide
            .hop/
            ├── releases/
            │   └── README.md      # Release workflow guide
            ├── model/
            └── backups/

        Examples:
            # Development mode
            _create_git_centric_structure()
            # Creates: Patches/, .hop/releases/, .hop/model/, .hop/backups/

            # Sync-only mode
            _create_git_centric_structure()
            # Skips creation (not needed for sync-only)
        """
        # Only create structure in development mode
        if not self.__config.devel:
            return

        # Create directories
        patches_dir = os.path.join(self.__base_dir, 'Patches')
        releases_dir = self.releases_dir
        model_dir = self.model_dir
        backups_dir = self.backups_dir
        bootstrap_dir = os.path.join(self.__base_dir, 'bootstrap')

        os.makedirs(patches_dir, exist_ok=True)
        os.makedirs(releases_dir, exist_ok=True)
        os.makedirs(model_dir, exist_ok=True)
        os.makedirs(backups_dir, exist_ok=True)
        os.makedirs(bootstrap_dir, exist_ok=True)

        # Create README files for guidance
        patches_readme = os.path.join(patches_dir, 'README.md')
        with open(patches_readme, 'w', encoding='utf-8') as f:
            f.write("""# Patches Directory

This directory contains schema patch files for database evolution.

## Structure

Each patch is stored in its own directory:
```
Patches/
├── 001-initial-schema/
│   ├── 01_create_users.sql
│   ├── 02_add_indexes.sql
│   └── 03_seed_data.py
├── 002-add-authentication/
│   └── 01_auth_tables.sql
```

## Workflow

1. Create release: `half_orm dev release create <level>`
2. Create patch branch: `half_orm dev patch create <patch-id>`
3. Add SQL/Python files to Patches/<patch-id>/
4. Apply patch: `half_orm dev patch apply`
5. Test your changes
6. Merge patch: `git checkout ho-patch/<patch-id> && half_orm dev patch merge`

## File Naming

- Use numeric prefixes for ordering: `01_`, `02_`, etc.
- SQL files: `*.sql`
- Python scripts: `*.py`
- Files executed in lexicographic order

See docs/half_orm_dev.md for complete documentation.
""")

        releases_readme = os.path.join(releases_dir, 'README.md')
        with open(releases_readme, 'w', encoding='utf-8') as f:
            f.write("""# Releases Directory

This directory manages release workflows through text files.

## Structure

```
releases/
├── 1.0.0-stage.txt      # Development release (stage)
├── 1.0.0-rc.txt         # Release candidate
└── 1.0.0-production.txt # Production release
```

## Release Files

Each file contains patch IDs, one per line:
```
001-initial-schema
002-add-authentication
003-user-profiles
```

## Workflow

1. **Development**: Patch development
- `half_orm dev patch create <patch-id>`
- `half_orm dev patch apply`
- `half_orm dev patch merge` (from ho-patch/<patch-id> branch)
- Patches added to X.Y.Z-patches.toml

2. **RC**: Release candidate
- `half_orm dev release promote rc`
- Creates X.Y.Z-rc.txt
- Deletes patch branches

3. **Production**: Final release
- `half_orm dev promote-to prod`
- Creates X.Y.Z-production.txt
- Apply to production: `half_orm dev deploy-to-prod`

See docs/half_orm_dev.md for complete documentation.
""")

        bootstrap_readme = os.path.join(bootstrap_dir, 'README.md')
        with open(bootstrap_readme, 'w', encoding='utf-8') as f:
            f.write("""# Bootstrap Scripts

This directory contains data initialization scripts that run after database setup.

## File Naming

Files are named: `<number>-<patch_id>-<version>.<ext>`

Examples:
- `1-init-users-0.1.0.sql`
- `2-seed-config-0.1.0.py`

Scripts are executed in numeric order (by the first number).

## Usage

Run pending bootstrap scripts:
```bash
half_orm dev bootstrap
```

Preview what would be executed:
```bash
half_orm dev bootstrap --dry-run
```

Re-execute all scripts (ignore tracking):
```bash
half_orm dev bootstrap --force
```

## Creating Bootstrap Files

Mark patch files with the `@HOP:bootstrap` marker (or `@HOP:data` alias)
on the first line to have them automatically copied here during `patch merge`.

SQL files:
```sql
-- @HOP:bootstrap
INSERT INTO roles (name) VALUES ('admin'), ('user') ON CONFLICT DO NOTHING;
```

Python files:
```python
# @HOP:bootstrap
# Your initialization script here
```

## Tracking

Executed scripts are tracked in `half_orm_meta.bootstrap` table.
Each script is executed only once unless `--force` is used.
""")

    def _generate_python_package(self):
        """
        Generate Python package structure from database schema.

        Uses modules.generate() to create Python classes for database tables.
        Creates hierarchical package structure matching database schemas.

        Process:
            1. Call modules.generate(self)
            2. Generates: <package>/<package>/<schema>/<table>.py
            3. Creates __init__.py files for each level
            4. Generates base_test.py and sql_adapter.py

        Generated Structure:
            my_blog/
            └── my_blog/
                ├── __init__.py
                ├── base_test.py
                ├── sql_adapter.py
                └── public/
                    ├── __init__.py
                    ├── user.py
                    └── post.py

        Examples:
            _generate_python_package()
            # Generates complete package structure from database
        """
        # Delegate to existing modules.generate()
        modules.generate(self)

    def _initialize_git_repository(self):
        """
        Initialize Git repository with ho-prod main branch.

        Replaces hop_main branch naming with ho-prod for Git-centric workflow.

        Process:
            1. Initialize Git repository via HGit
            2. Create initial commit
            3. Set main branch to ho-prod
            4. Configure remote origin (if available)

        Branch Naming:
            - Main branch: ho-prod (replaces hop_main)
            - Patch branches: ho-patch/<patch-name>

        Examples:
            _initialize_git_repository()
            # Creates: .git/ with ho-prod branch
        """
        # Delegate to existing hgit.HGit.init
        self.hgit = HGit().init(self.__base_dir, self.__config.git_origin)

    def _generate_template_files(self):
        """
        Generate template files for project configuration.

        Creates standard project files:
        - README.md: Project documentation
        - .gitignore: Git exclusions
        - pyproject.toml: Python packaging (PEP 517/518)
        - Pipfile: Dependencies (current template)

        Templates read from TEMPLATE_DIRS and formatted with project variables.

        Examples:
            _generate_template_files()
            # Creates: README.md, .gitignore, pyproject.toml
        """
        # Read templates
        readme_template = utils.read(os.path.join(TEMPLATE_DIRS, 'README'))
        pyproject_template = utils.read(os.path.join(TEMPLATE_DIRS, 'pyproject.toml'))
        git_ignore = utils.read(os.path.join(TEMPLATE_DIRS, '.gitignore'))

        # Format templates with project variables
        package_name = self.__config.package_name

        pyproject = pyproject_template.format(
            dbname=package_name,
            package_name=package_name,
            half_orm_dev_version=hop_version()
        )

        readme = readme_template.format(
            hop_version=hop_version(),
            dbname=package_name,
            package_name=package_name
        )

        # Write files
        utils.write(os.path.join(self.__base_dir, 'pyproject.toml'), pyproject)
        utils.write(os.path.join(self.__base_dir, 'README.md'), readme)
        utils.write(os.path.join(self.__base_dir, '.gitignore'), git_ignore)

    def _dump_initial_schema(self):
        self.database._generate_schema_sql("0.0.0", Path(self.model_dir))

    def _validate_git_origin_url(self, git_origin_url):
        """
        Validate Git origin URL format.

        Validates that the provided URL follows valid Git remote URL formats.
        Supports HTTPS, SSH (git@), and git:// protocols for common Git hosting
        services (GitHub, GitLab, Bitbucket) and self-hosted Git servers.

        Args:
            git_origin_url: Git remote origin URL to validate

        Raises:
            ValueError: If URL is None, empty, or has invalid format
            UserWarning: If URL contains embedded credentials (discouraged)

        Valid URL formats:
            - HTTPS: https://git.example.com/user/repo.git
            - SSH: git@git.example.com:user/repo.git
            - SSH with port: ssh://git@host:port/path/repo.git
            - Git protocol: git://git.example.com/user/repo.git

        Examples:
            # Valid URLs
            _validate_git_origin_url("https://git.example.com/user/repo.git")
            _validate_git_origin_url("git@git.example.com:user/repo.git")
            _validate_git_origin_url("https://git.company.com/team/project.git")

            # Invalid URLs raise ValueError
            _validate_git_origin_url("not-a-url")  # → ValueError
            _validate_git_origin_url("http://git.example.com/user/repo.git")  # → ValueError (HTTP not allowed)
            _validate_git_origin_url("")  # → ValueError

        Notes:
            - URLs with embedded credentials trigger a warning but are accepted
            - Leading/trailing whitespace is automatically stripped
            - .git extension is optional
        """
        # Type validation
        if git_origin_url is None:
            raise ValueError("Git origin URL cannot be None")

        if not isinstance(git_origin_url, str):
            raise ValueError(
                f"Git origin URL must be a string, got {type(git_origin_url).__name__}"
            )

        # Strip whitespace
        git_origin_url = git_origin_url.strip()

        # Empty check
        if not git_origin_url:
            raise ValueError("Git origin URL cannot be empty")

        # Warn about embedded credentials (security issue)
        if re.search(r'://[^@/]+:[^@/]+@', git_origin_url):
            warnings.warn(
                "Git origin URL contains embedded credentials. "
                "Consider using SSH keys or credential helpers instead.",
                UserWarning
            )

        # Define valid URL patterns
        patterns = [
            # HTTPS: https://github.com/user/repo.git or https://user:pass@github.com/user/repo.git
            r'^https://(?:[^@/]+@)?[a-zA-Z0-9._-]+(?:\.[a-zA-Z]{2,})+(?::[0-9]+)?/.+$',

            # SSH (git@): git@git.example.com:user/repo.git or git@git.example.com:user/repo
            r'^git@[a-zA-Z0-9._-]+(?:\.[a-zA-Z]{2,})+:.+$',

            # SSH with explicit protocol and port: ssh://git@host:port/path/repo.git
            r'^ssh://git@[a-zA-Z0-9._-]+(?:\.[a-zA-Z]{2,})+(?::[0-9]+)?/.+$',

            # Git protocol: git://git.example.com/user/repo.git
            r'^git://[a-zA-Z0-9._-]+(?:\.[a-zA-Z]{2,})+(?::[0-9]+)?/.+$',

            # File protocol: file:///path/to/repo
            r'^file:///[a-zA-Z0-9._/-]+|^/[a-zA-Z0-9._/-]+'
        ]

        # Check if URL matches any valid pattern
        is_valid = any(re.match(pattern, git_origin_url) for pattern in patterns)

        if not is_valid:
            raise ValueError(
                f"Invalid Git origin URL format: '{git_origin_url}'\n"
                "Valid formats:\n"
                "  - HTTPS: https://git.example.com/user/repo.git\n"
                "  - SSH: git@git.example.com:user/repo.git\n"
                "  - Git protocol: git://git.example.com/user/repo.git"
            )

        # Additional validation: ensure URL has a repository path
        # Extract path component based on URL type
        if git_origin_url.startswith('git@'):
            # SSH format: git@host:path
            parts = git_origin_url.split(':', 1)
            if len(parts) < 2 or not parts[1].strip():
                raise ValueError(
                    "Git origin URL must include repository path. "
                    f"Got: '{git_origin_url}'"
                )
        elif git_origin_url.startswith(('https://', 'git://', 'ssh://')):
            # Protocol-based format: check for path after host
            # Split on first / after protocol://host
            protocol_end = git_origin_url.index('://') + 3
            remaining = git_origin_url[protocol_end:]

            # Find first / (path separator)
            if '/' not in remaining:
                raise ValueError(
                    "Git origin URL must include repository path. "
                    f"Got: '{git_origin_url}'"
                )

            path = remaining.split('/', 1)[1]
            if not path.strip():
                raise ValueError(
                    "Git origin URL must include repository path. "
                    f"Got: '{git_origin_url}'"
                )

        # Validation passed
        return True

    def _reset_database_schemas(self) -> None:
        """Drop all user schemas with CASCADE (including half_orm_meta).

        Note: Database-level objects persist and are NOT reset:
        - Extensions (will be recreated by schema.sql with IF NOT EXISTS)
        - Foreign Data Wrappers and servers
        - Event triggers
        - Database settings (ALTER DATABASE SET)

        This is by design: these objects are typically configured once
        and should persist across schema resets.
        """
        schemas_to_drop = {'half_orm_meta', 'half_orm_meta.view'}
        # Add user schemas from half_orm metadata
        relations = self.model.desc()
        _ = [schemas_to_drop.add(rel[1][1]) for rel in relations]

        # Drop each schema with CASCADE
        for schema_name in schemas_to_drop:
            self.model.execute_query(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')

        # Recreate public schema (PostgreSQL standard schema)
        # The public schema is expected to exist by many applications and tools
        if 'public' in schemas_to_drop:
            self.model.execute_query('CREATE SCHEMA public')
            self.model.execute_query('GRANT ALL ON SCHEMA public TO public')

    def restore_database_from_schema(self, exclude_bootstrap_patch_id: Optional[str] = None, exclude_bootstrap_version: Optional[str] = None) -> None:
        """
        Restore database from model/schema.sql, metadata, and data files.

        Restores database to clean production state by dropping all user schemas
        and loading schema, metadata, and reference data. Used for from-scratch
        installations (clone) and patch development (patch apply).

        Process:
        1. Verify model/schema.sql exists (file or symlink)
        2. Drop all user schemas with CASCADE (no superuser privileges needed)
        3. Load schema structure from model/schema.sql using psql -f
        4. Load half_orm_meta data from model/metadata-X.Y.Z.sql using psql -f (if exists)
        5. Load reference data from model/data-*.sql files up to current version
        6. Reload halfORM Model metadata cache

        The method uses DROP SCHEMA CASCADE instead of dropdb/createdb, allowing
        operation without CREATEDB privilege or superuser access. This makes it
        compatible with cloud databases (RDS, Azure) and restricted environments.

        File Resolution:
        - Accepts model/schema.sql as regular file or symlink
        - Symlink typically points to versioned schema-X.Y.Z.sql file
        - Follows symlink automatically during psql execution
        - Deduces version from schema.sql symlink target for metadata and data files
        - Missing metadata/data files are silently skipped (backward compatibility)

        Data Files:
        - model/data-X.Y.Z.sql contains reference data from @HOP:data patches
        - All data files up to current version are loaded in version order
        - Example: for version 1.2.0, loads data-0.1.0.sql, data-1.0.0.sql, data-1.2.0.sql

        Error Handling:
        - Raises RepoError if model/schema.sql not found
        - Raises RepoError if schema drop fails
        - Raises RepoError if psql schema/metadata/data load fails
        - Database state rolled back on any failure

        Usage Context:
        - Called by clone_repo workflow (from-scratch installation)
        - Called by apply-patch workflow (Step 1: Database Restoration)
        - Ensures clean state with all reference data before applying patches

        Returns:
            None

        Raises:
            RepoError: If schema file not found
            RepoError: If database restoration fails at any step

        Examples:
            # Restore database from model/schema.sql before applying patch
            repo.restore_database_from_schema()
            # Database now contains: schema + metadata + reference data

            # Typical apply-patch workflow
            repo.restore_database_from_schema()  # Step 1: Clean state + all data
            patch_mgr.apply_patch_files("456-user-auth", repo.model)  # Step 2: Apply patch

            # With versioned files
            # If schema.sql → schema-1.2.3.sql exists
            # Then loads: metadata-1.2.3.sql, data-0.1.0.sql, data-1.0.0.sql, data-1.2.3.sql

        Notes:
            - Uses DROP SCHEMA CASCADE - no superuser or CREATEDB privilege required
            - Works on cloud databases (AWS RDS, Azure Database, etc.)
            - Uses Model.reconnect(reload=True) to refresh metadata cache
            - Supports both schema.sql file and schema.sql -> schema-X.Y.Z.sql symlink
            - Metadata and data files are optional (backward compatibility)
            - All PostgreSQL commands use repository connection configuration
        """
        # 1. Verify model/schema.sql exists
        schema_path = Path(self.model_dir) / "schema.sql"

        if not schema_path.exists():
            raise RepoError(
                f"Schema file not found: {schema_path}. "
                "Cannot restore database without model/schema.sql."
            )

        try:
            # 2. Drop all schemas (no superuser privileges needed)
            self._reset_database_schemas()

            # 3. Load schema from model/schema.sql
            try:
                self.database.execute_pg_command(
                    'psql', '-d', self.database_name, '-f', str(schema_path)
                )
            except Exception as e:
                raise RepoError(f"Failed to load schema from {schema_path.name}: {e}") from e

            # 4. Load metadata from model/metadata-X.Y.Z.sql (if exists)
            metadata_path, version = self._deduce_metadata_path(schema_path)

            if metadata_path and metadata_path.exists():
                try:
                    self.database.execute_pg_command(
                        'psql', '-d', self.database_name, '-f', str(metadata_path)
                    )
                except Exception as e:
                    raise RepoError(
                        f"Failed to load metadata from {metadata_path.name}: {e}"
                    ) from e
            # else: metadata file doesn't exist, continue without error (backward compatibility)

            # 5. Load data files from model/data-*.sql (all versions up to current)
            self._load_data_files(schema_path)

            # 6. Reload half_orm metadata cache
            self.model.reconnect(reload=True)

            # 7. Execute bootstrap scripts
            # In patch apply context: ALL bootstraps run (only current patch excluded).
            # In promote context: exclude_bootstrap_version skips the version being
            # promoted (its bootstraps don't run during promote, they run via upgrade).
            # up_to_version prevents bootstraps from future versions from running.
            from half_orm_dev.bootstrap_manager import BootstrapManager
            bootstrap_mgr = BootstrapManager(self)
            bootstrap_mgr.run_bootstrap(
                exclude_patch_id=exclude_bootstrap_patch_id,
                exclude_version=exclude_bootstrap_version,
                up_to_version=exclude_bootstrap_version
            )

        except RepoError:
            # Re-raise RepoError as-is
            raise
        except Exception as e:
            # Catch any unexpected errors
            raise RepoError(f"Database restoration failed: {e}") from e

    def restore_database_from_dump(self, dump_file: Path) -> None:
        """
        Restore database from a pg_dump SQL file.

        Alternative to restore_database_from_schema() for working with
        production data snapshots. Useful for testing patches against
        realistic data.

        Process:
        1. Verify dump file exists
        2. Drop all user schemas with CASCADE
        3. Load dump using psql -f
        4. Reload halfORM Model metadata cache

        Note: Bootstrap scripts are NOT executed since the dump
        already contains the data.

        Args:
            dump_file: Path to SQL dump file (plain text format from pg_dump)

        Raises:
            RepoError: If dump file not found or restoration fails

        Examples:
            # Use production dump for patch development
            repo.restore_database_from_dump(Path("/path/to/prod_dump.sql"))
            patch_mgr.apply_patch_files("456-feature", repo.model)
        """
        dump_path = Path(dump_file)

        if not dump_path.exists():
            raise RepoError(
                f"Dump file not found: {dump_path}. "
                "Please provide a valid pg_dump SQL file."
            )

        try:
            # 1. Drop all schemas (no superuser privileges needed)
            self._reset_database_schemas()

            # 2. Load dump using psql
            try:
                self.database.execute_pg_command(
                    'psql', '-d', self.database_name, '-f', str(dump_path)
                )
            except Exception as e:
                raise RepoError(f"Failed to load dump from {dump_path.name}: {e}") from e

            # 3. Reload half_orm metadata cache
            self.model.reconnect(reload=True)

            # Note: Bootstrap scripts are NOT executed - dump contains data

        except RepoError:
            raise
        except Exception as e:
            raise RepoError(f"Database restoration from dump failed: {e}") from e

    def generate_release_schema(self, version: str) -> Path:
        """
        Generate release schema SQL dump.

        Creates .hop/model/release-{version}.sql with current database structure,
        metadata, and data. This file represents the complete state of a release
        in development (prod + all staged patches).

        Used by:
        - release create: Generate initial release schema from prod baseline
        - patch merge: Update release schema after patch integration

        Args:
            version: Release version string (e.g., "0.17.1", "0.18.0")

        Returns:
            Path to generated release schema file

        Raises:
            RepoError: If pg_dump fails or model_dir doesn't exist

        Examples:
            # After merging patch into release
            schema_path = repo.generate_release_schema("0.17.1")
            # Creates: .hop/model/release-0.17.1.sql
        """
        model_dir = Path(self.model_dir)

        if not model_dir.exists():
            raise RepoError(f"Model directory does not exist: {model_dir}")

        release_schema_file = model_dir / f"release-{version}.sql"
        temp_file = model_dir / f".release-{version}.sql.tmp"

        try:
            # Dump complete database (schema + data) to temp file
            self.database.execute_pg_command(
                'pg_dump',
                self.database_name,
                '--no-owner',
                '-f',
                str(temp_file)
            )

            # Filter out version-specific lines for cross-version compatibility
            content = temp_file.read_text()
            filtered_lines = []
            version_specific_sets = (
                'SET transaction_timeout',  # PG17+
            )
            for line in content.split('\n'):
                if line.startswith('\\restrict') or line.startswith('\\unrestrict'):
                    continue
                if line.startswith('-- Dumped from') or line.startswith('-- Dumped by'):
                    continue
                if any(line.startswith(s) for s in version_specific_sets):
                    continue
                filtered_lines.append(line)

            release_schema_file.write_text('\n'.join(filtered_lines))

            return release_schema_file

        except Exception as e:
            raise RepoError(f"Failed to generate release schema: {e}") from e
        finally:
            if temp_file.exists():
                temp_file.unlink()

    def restore_database_from_release_schema(
        self,
        version: str,
        exclude_bootstrap_patch_id: Optional[str] = None,
        exclude_bootstrap_version: Optional[str] = None
    ) -> None:
        """
        Restore database from release schema file.

        Restores database from .hop/model/release-{version}.sql which contains
        the complete state of a release in development (prod + staged patches).

        If the release schema file doesn't exist, falls back to
        restore_database_from_schema() for backward compatibility.

        Args:
            version: Release version string (e.g., "0.17.1")
            exclude_bootstrap_patch_id: If provided, skip bootstrap files
                belonging to this patch (used during patch apply)
            exclude_bootstrap_version: If provided, skip bootstrap files for
                this version (used during promote)

        Raises:
            RepoError: If restoration fails

        Examples:
            # Before applying a candidate patch
            repo.restore_database_from_release_schema("0.17.1")
            # Database now has prod schema + all staged patches for 0.17.1
        """
        release_schema_path = Path(self.model_dir) / f"release-{version}.sql"

        # Fallback to production schema if release schema doesn't exist
        if not release_schema_path.exists():
            self.restore_database_from_schema(
                exclude_bootstrap_patch_id,
                exclude_bootstrap_version=exclude_bootstrap_version
            )
            return

        try:
            # Drop all user schemas
            self._reset_database_schemas()

            # Load release schema
            self.database.execute_pg_command(
                'psql', '-d', self.database_name, '-f', str(release_schema_path)
            )

            # Reload half_orm metadata cache
            self.model.reconnect(reload=True)

            # Execute bootstrap scripts
            # up_to_version prevents bootstraps from future versions from running.
            from half_orm_dev.bootstrap_manager import BootstrapManager
            bootstrap_mgr = BootstrapManager(self)
            bootstrap_mgr.run_bootstrap(
                exclude_patch_id=exclude_bootstrap_patch_id,
                exclude_version=exclude_bootstrap_version,
                up_to_version=exclude_bootstrap_version
            )

        except Exception as e:
            raise RepoError(f"Failed to restore from release schema: {e}") from e

    def get_release_schema_path(self, version: str) -> Path:
        """
        Get path to release schema file.

        Args:
            version: Release version string

        Returns:
            Path to .hop/model/release-{version}.sql (may not exist)
        """
        return Path(self.model_dir) / f"release-{version}.sql"

    def _deduce_metadata_path(self, schema_path: Path) -> Path | None:
        """
        Deduce metadata file path from schema.sql symlink target.

        If schema.sql is a symlink pointing to schema-X.Y.Z.sql,
        returns Path to metadata-X.Y.Z.sql in the same directory.

        Args:
            schema_path: Path to model/schema.sql (may be file or symlink)

        Returns:
            Path to metadata-X.Y.Z.sql if version can be deduced, None otherwise

        Examples:
            # schema.sql → schema-1.2.3.sql
            metadata_path = _deduce_metadata_path(Path("model/schema.sql"))
            # Returns: Path("model/metadata-1.2.3.sql")

            # schema.sql is regular file (not symlink)
            metadata_path = _deduce_metadata_path(Path("model/schema.sql"))
            # Returns: None
        """
        # Check if schema.sql is a symlink
        if not schema_path.is_symlink():
            return None

        # Read symlink target (e.g., "schema-1.2.3.sql")
        try:
            target = Path(os.readlink(schema_path))
        except OSError:
            return None

        # Extract version from target filename
        match = re.match(r'schema-(\d+\.\d+\.\d+)\.sql$', target.name)
        if not match:
            return None

        version = match.group(1)

        # Construct metadata file path
        metadata_path = schema_path.parent / f"metadata-{version}.sql"

        return metadata_path, version

    def _load_data_files(self, schema_path: Path) -> None:
        """
        Load all data files from model/data-*.sql up to current version.

        Data files contain reference data (DML) from patches with @HOP:data annotation.
        They are loaded in version order for from-scratch installations.

        Args:
            schema_path: Path to model/schema.sql (used to deduce current version)

        Process:
            1. Deduce current version from schema.sql symlink
            2. Find all data-*.sql files in model/
            3. Sort by version (semantic versioning)
            4. Load each file up to current version using psql -f

        Examples:
            # schema.sql → schema-1.2.0.sql
            # model/ contains: data-0.1.0.sql, data-1.0.0.sql, data-1.2.0.sql, data-2.0.0.sql
            # Loads: data-0.1.0.sql, data-1.0.0.sql, data-1.2.0.sql (skips 2.0.0)
        """
        # Deduce current version from schema.sql symlink
        if not schema_path.is_symlink():
            return  # No version info, skip data loading

        try:
            target = Path(os.readlink(schema_path))
        except OSError:
            return

        match = re.match(r'schema-(\d+\.\d+\.\d+)\.sql$', target.name)
        if not match:
            return

        current_version = match.group(1)
        current_tuple = tuple(map(int, current_version.split('.')))

        # Find all data files
        model_dir = schema_path.parent
        data_files = list(model_dir.glob("data-*.sql"))

        if not data_files:
            return  # No data files to load

        # Parse and sort by version
        versioned_files = []
        for data_file in data_files:
            match = re.match(r'data-(\d+\.\d+\.\d+)\.sql$', data_file.name)
            if match:
                version = match.group(1)
                version_tuple = tuple(map(int, version.split('.')))
                versioned_files.append((version_tuple, data_file))

        # Sort by version tuple
        versioned_files.sort(key=lambda x: x[0])

        # Load each file up to current version
        for version_tuple, data_file in versioned_files:
            if version_tuple > current_tuple:
                break  # Stop at versions beyond current

            try:
                self.database.execute_pg_command(
                    'psql', '-d', self.database_name, '-f', str(data_file)
                )
            except Exception as e:
                raise RepoError(
                    f"Failed to load data from {data_file.name}: {e}"
                ) from e

    @classmethod
    def clone_repo(cls,
                git_origin: str,
                database_name: Optional[str] = None,
                dest_dir: Optional[str] = None,
                connection_options: Optional[dict] = None,
                create_db: bool = True) -> None:
        """
        Clone existing half_orm_dev project and setup local database.

        This method clones a Git repository, checks out the ho-prod branch,
        creates/configures the local database, and restores the schema to
        the production version.

        Args:
            git_origin: Git repository URL (HTTPS, SSH, file://)
            database_name: Local database name (default: prompt or package_name)
            dest_dir: Clone destination (default: infer from git_origin)
            connection_options: Database connection parameters
                - host (str): PostgreSQL host (default: localhost)
                - port (int): PostgreSQL port (default: 5432)
                - user (str): Database user (default: $USER)
                - password (str): Database password (prompts if None)
                - production (bool): Production environment flag
            create_db: Create database if missing (default: True)

        Raises:
            RepoError: If clone fails, checkout fails, or database setup fails
            FileExistsError: If destination directory already exists

        Workflow:
            1. Determine destination directory from git_origin or dest_dir
            2. Verify destination directory doesn't exist
            3. Clone repository using git clone
            4. Checkout ho-prod branch
            5. Create .hop/alt_config if custom database_name provided
            6. Setup database (create + metadata if create_db=True)
            7. Restore database from model/schema.sql to production version
            8. Install Git hooks (pre-commit, prepare-commit-msg)

        Examples:
            # Interactive with prompts for connection params
            Repo.clone_repo("https://github.com/user/project.git")

            # With custom database name (creates .hop/alt_config)
            Repo.clone_repo(
                "https://github.com/user/project.git",
                database_name="my_local_dev_db"
            )

            # Non-interactive with explicit connection params
            Repo.clone_repo(
                "https://github.com/user/project.git",
                connection_options={'host': 'localhost', 'user': 'dev', 'password': 'secret'}
            )

        Notes:
            - Changes current working directory to cloned project
            - Empty connection_options {} triggers interactive prompts
            - restore_database_from_schema() loads production schema version
            - Returns None (command completes, no return value needed)
        """
        if connection_options is None:
            connection_options = {}
        # Step 1: Determine destination directory
        if dest_dir:
            dest_name = dest_dir
        else:
            # Extract project name from git_origin, remove .git extension
            dest_name = git_origin.rstrip('/').split('/')[-1]
            if dest_name.endswith('.git'):
                dest_name = dest_name[:-4]

        dest_path = Path.cwd() / dest_name

        # Step 2: Verify destination doesn't exist
        if dest_path.exists():
            raise FileExistsError(
                f"Directory '{dest_name}' already exists in current directory. "
                f"Choose a different destination or remove the existing directory."
            )

        # Step 3: Clone repository
        try:
            result = subprocess.run(
                ["git", "clone", git_origin, str(dest_path)],
                capture_output=True,
                text=True,
                check=True,
                timeout=300  # 5 minutes timeout for clone
            )
        except subprocess.CalledProcessError as e:
            raise RepoError(
                f"Git clone failed: {e.stderr.strip()}"
            ) from e
        except subprocess.TimeoutExpired:
            raise RepoError(
                f"Git clone timed out after 5 minutes. "
                f"Check network connection or repository size."
            )

        # Step 4: Change to cloned directory (required for Repo() singleton)
        os.chdir(dest_path)

        # Step 5: Checkout ho-prod branch
        try:
            result = subprocess.run(
                ["git", "checkout", "ho-prod"],
                capture_output=True,
                text=True,
                check=True,
                cwd=dest_path
            )
        except subprocess.CalledProcessError as e:
            raise RepoError(
                f"Git checkout ho-prod failed: {e.stderr.strip()}. "
                f"Ensure 'ho-prod' branch exists in the repository."
            ) from e

        # Step 7: Load config and setup database
        from half_orm_dev.repo import Config  # Import here to avoid circular imports
        config = Config(dest_path)

        # Step 6: Create .hop/alt_config if custom database name provided
        if database_name:
            alt_config_path = dest_path / '.hop' / 'alt_config'
            try:
                with open(alt_config_path, 'w', encoding='utf-8') as f:
                    f.write(database_name)
            except (OSError, IOError) as e:
                raise RepoError(
                    f"Failed to create .hop/alt_config: {e}"
                ) from e
        else:
            database_name = config.package_name

        try:
            Database.setup_database(
                database_name=database_name,
                connection_options=connection_options,
                create_db=create_db,
                add_metadata=create_db  # Auto-install metadata for new DB
            )
        except Exception as e:
            raise RepoError(
                f"Database setup failed: {e}"
            ) from e

        # Step 8: Create Repo instance and restore production schema
        repo = cls()

        try:
            repo.restore_database_from_schema()
        except RepoError as e:
            raise RepoError(
                f"Failed to restore database from schema: {e}"
            ) from e

        # Step 9: Install Git hooks
        repo.install_git_hooks()
