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
from half_orm_dev.patch_manager import PatchManager, PatchManagerError
from half_orm_dev.release_manager import ReleaseManager
from half_orm_dev.migration_manager import MigrationManager, MigrationManagerError
from half_orm_dev.release_file import ReleaseFile

from .utils import TEMPLATE_DIRS, hop_version, resolve_database_config_name

class RepoError(Exception):
    pass

class Config:
    """
    """
    __name: Optional[str] = None
    __git_origin: str = ''
    __devel: bool = False
    __hop_version: Optional[str] = None
    def __init__(self, base_dir, **kwargs):
        Config.__file = os.path.join(base_dir, '.hop', 'config')
        self.__name = kwargs.get('name') or resolve_database_config_name(base_dir)
        self.__devel = kwargs.get('devel', False)
        if os.path.exists(self.__file):
            sys.path.insert(0, base_dir)
            self.read()

    def read(self):
        "Sets __name and __hop_version"
        config = ConfigParser()
        config.read(self.__file)
        self.__hop_version = config['halfORM'].get('hop_version', '')
        self.__git_origin = config['halfORM'].get('git_origin', '')
        self.__devel = config['halfORM'].getboolean('devel', False)
        self.__allow_rc = config['halfORM'].getboolean('allow_rc', False)

    def write(self):
        "Helper: write file in utf8"
        config = ConfigParser()
        self.__hop_version = hop_version()
        data = {
            'hop_version': self.__hop_version,
            'git_origin': self.__git_origin,
            'devel': self.__devel
        }
        config['halfORM'] = data
        with open(Config.__file, 'w', encoding='utf-8') as configfile:
            config.write(configfile)

    @property
    def name(self):
        return self.__name
    @name.setter
    def name(self, name):
        self.__name = name

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
                except:
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
                # Perform automatic migration if needed (after hgit is initialized)
                self._run_pending_migrations()
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
            if version.parse(installed_version) < version.parse(required_version):
                raise RepoError(
                    f"Repository requires half_orm_dev >= {required_version} "
                    f"but {installed_version} is installed.\n"
                    f"Please upgrade: pip install --upgrade half_orm_dev"
                )
        except version.InvalidVersion as e:
            # If version parsing fails, log warning but don't block
            warnings.warn(
                f"Could not parse version: installed={installed_version}, "
                f"required={required_version}. Error: {e}",
                UserWarning
            )

    def _run_pending_migrations(self):
        """
        Run pending migrations using MigrationManager.

        Automatically detects and runs migrations based on current
        half_orm_dev version vs hop_version in .hop/config.

        Behavior:
        - On ho-prod: Runs migration with lock, creates commit, notifies active branches
        - On other branches: Warns user to merge ho-prod to get migration

        Silent by default - only logs errors.
        """
        try:
            # Create migration manager
            migration_mgr = MigrationManager(self)

            # Get current half_orm_dev version
            current_version = hop_version()

            # Check if migration is needed
            if not migration_mgr.check_migration_needed(current_version):
                return

            # Only run migrations on ho-prod branch
            if not self.hgit or self.hgit.branch != 'ho-prod':
                # Warn user to switch to ho-prod to run migration
                current_branch = self.hgit.branch if self.hgit else 'unknown'
                config_version = self.__config.hop_version if hasattr(self, '_Repo__config') else '0.0.0'
                print(f"\n{utils.Color.bold('⚠️  Migration needed:')}", file=sys.stderr)
                print(f"  half_orm_dev {config_version} → {current_version}", file=sys.stderr)
                print(f"  Current branch: {current_branch}", file=sys.stderr)
                print(f"\n  To apply migration, checkout to ho-prod branch and rerun:", file=sys.stderr)
                print(f"    git checkout ho-prod", file=sys.stderr)
                print(f"    half_orm dev check\n", file=sys.stderr)
                return

            # Run migrations on ho-prod
            # Branch sync is handled automatically by the decorator
            result = migration_mgr.run_migrations(
                target_version=current_version,
                create_commit=True
            )

            # Log errors if any
            if result.get('errors'):
                for error in result['errors']:
                    print(f"Migration error: {error}", file=sys.stderr)

        except MigrationManagerError as e:
            # Log migration errors but don't fail repo initialization
            print(f"Migration failed: {e}", file=sys.stderr)
        except Exception as e:
            # Catch any unexpected errors
            print(f"Unexpected migration error: {e}", file=sys.stderr)

    def sync_hop_to_active_branches(self, reason: str = "update") -> dict:
        """
        Synchronize .hop/ directory from current branch to all other active branches.

        This method ensures that any changes made to .hop/ on the current branch
        are propagated to all other active branches (ho-patch/*, ho-release/*, ho-prod).

        The sync logic is:
        - Source: current branch
        - Targets: all active branches + ho-prod - current branch

        Uses git checkout to copy the entire .hop/ directory from current branch,
        ensuring perfect consistency across all branches.

        Args:
            reason: Description of why sync is happening (for commit message)

        Returns:
            dict with keys:
                - synced_branches: List of branch names that were synced
                - skipped_branches: List of branches that were skipped (no changes)
                - errors: List of error messages for failed syncs

        Examples:
            # After modifying .hop/config on ho-prod
            result = repo.sync_hop_to_active_branches("migration 0.17.1 → 0.17.2")
            print(f"Synced {len(result['synced_branches'])} branches")

            # After modifying .hop/ on ho-release/0.17.0
            result = repo.sync_hop_to_active_branches("new patch")
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
                except Exception:
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
                    except Exception:
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

                # Reload config for this branch
                self.__config = Config(self.base_dir)

                # Use git checkout to copy .hop/ from source branch
                # This updates/adds files but doesn't remove deleted files
                self.hgit._HGit__git_repo.git.checkout(source_branch, '--', '.hop/')

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

        # 5. Sync .hop/ to all other active branches
        sync_result = self.sync_hop_to_active_branches(reason=reason)
        result['sync_result'] = sync_result

        return result

    @property
    def base_dir(self):
        "Returns the base dir of the repository"
        return self.__base_dir

    @property
    def name(self):
        "Returns the name of the package"
        return self.__config and self.__config.name or None

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
            result = repo.release_manager.new_release('patch')
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

        # Step 2: Check database configuration exists
        self._verify_database_configured(package_name)

        # Step 3: Connect to database and detect mode
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
                    except Exception:
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
                        except Exception:
                            # Failed to parse TOML - skip this file
                            pass

                except Exception:
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
                except Exception:
                    # No production version available (e.g., model/ doesn't exist yet)
                    pass
            result['production_version'] = production_version

        except Exception:
            result['active_branches'] = {
                'current_branch': None,
                'patch_branches': [],
                'release_branches': []
            }
            result['releases_info'] = {}
            result['production_version'] = None

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


    def _verify_database_configured(self, package_name):
        """
        Verify database is configured via init-database command.

        Checks that database configuration file exists and is accessible.
        Does NOT create the database - assumes init-database was run first.

        Args:
            package_name (str): Database name to verify

        Raises:
            DatabaseNotConfiguredError: If configuration file doesn't exist
            DatabaseConnectionError: If cannot connect to configured database

        Process:
            1. Check ~/.half_orm/<package_name> exists
            2. Attempt connection to verify database is accessible
            3. Store connection for later use

        Examples:
            # Database configured
            _verify_database_configured("my_blog")  # Success

            # Database not configured
            _verify_database_configured("unconfigured_db")
            # Raises: DatabaseNotConfiguredError with helpful message
        """
        # Try to load database configuration
        config = Database._load_configuration(package_name)

        if config is None:
            raise ValueError(
                f"Database '{package_name}' is not configured.\n"
                f"Please run: half_orm dev init-database {package_name} [OPTIONS]\n"
                f"See 'half_orm dev init-database --help' for more information."
            )

        # Try to connect to verify database is accessible
        try:
            model = Model(package_name)
            # Store model for later use
            return model
        except OperationalError as e:
            raise OperationalError(
                f"Cannot connect to database '{package_name}'.\n"
                f"Database may not exist or connection parameters may be incorrect.\n"
                f"Original error: {e}"
            )

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

        os.makedirs(patches_dir, exist_ok=True)
        os.makedirs(releases_dir, exist_ok=True)
        os.makedirs(model_dir, exist_ok=True)
        os.makedirs(backups_dir, exist_ok=True)

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

1. Create patch branch: `half_orm dev create-patch <patch-id>`
2. Add SQL/Python files to Patches/<patch-id>/
3. Apply patch: `half_orm dev apply-patch`
4. Test your changes
5. Add to release: `half_orm dev add-to-release <patch-id>`

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

1. **Stage**: Development work
- `half_orm dev add-to-release <patch-id>`
- Patches added to X.Y.Z-stage.txt

2. **RC**: Release candidate
- `half_orm dev promote-to rc`
- Creates X.Y.Z-rc.txt
- Deletes patch branches

3. **Production**: Final release
- `half_orm dev promote-to prod`
- Creates X.Y.Z-production.txt
- Apply to production: `half_orm dev deploy-to-prod`

See docs/half_orm_dev.md for complete documentation.
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
            # Creates: README.md, .gitignore, pyproject.toml, Pipfile
        """
        # Read templates
        readme_template = utils.read(os.path.join(TEMPLATE_DIRS, 'README'))
        pyproject_template = utils.read(os.path.join(TEMPLATE_DIRS, 'pyproject.toml'))
        git_ignore = utils.read(os.path.join(TEMPLATE_DIRS, '.gitignore'))
        pipfile_template = utils.read(os.path.join(TEMPLATE_DIRS, 'Pipfile'))

        # Format templates with project variables
        package_name = self.__config.name

        pyproject = pyproject_template.format(
            dbname=package_name,
            package_name=package_name,
            half_orm_version=half_orm.__version__
        )

        pipfile = pipfile_template.format(
            half_orm_version=half_orm.__version__,
            hop_version=hop_version()
        )

        readme = readme_template.format(
            hop_version=hop_version(),
            dbname=package_name,
            package_name=package_name
        )

        # Write files
        utils.write(os.path.join(self.__base_dir, 'pyproject.toml'), pyproject)
        utils.write(os.path.join(self.__base_dir, 'Pipfile'), pipfile)
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

    def restore_database_from_schema(self) -> None:
        """
        Restore database from model/schema.sql and model/metadata-X.Y.Z.sql.

        Restores database to clean production state by dropping and recreating
        database, then loading schema structure and half_orm_meta data. This provides
        a clean baseline before applying patch files during patch development.

        Process:
        1. Verify model/schema.sql exists (file or symlink)
        2. Disconnect halfORM Model from database
        3. Drop existing database using dropdb command
        4. Create fresh empty database using createdb command
        5. Load schema structure from model/schema.sql using psql -f
        5b. Load half_orm_meta data from model/metadata-X.Y.Z.sql using psql -f (if exists)
        6. Reconnect halfORM Model to restored database

        The method uses Database.execute_pg_command() for all PostgreSQL
        operations (dropdb, createdb, psql) with connection parameters from
        repository configuration.

        File Resolution:
        - Accepts model/schema.sql as regular file or symlink
        - Symlink typically points to versioned schema-X.Y.Z.sql file
        - Follows symlink automatically during psql execution
        - Deduces metadata file version from schema.sql symlink target
        - If metadata-X.Y.Z.sql doesn't exist, continues without error (backward compatibility)

        Error Handling:
        - Raises RepoError if model/schema.sql not found
        - Raises RepoError if dropdb fails
        - Raises RepoError if createdb fails
        - Raises RepoError if psql schema load fails
        - Raises RepoError if psql metadata load fails (when file exists)
        - Database state rolled back on any failure

        Usage Context:
        - Called by apply-patch workflow (Step 1: Database Restoration)
        - Ensures clean state before applying patch SQL files
        - Part of isolated patch testing strategy

        Returns:
            None

        Raises:
            RepoError: If schema file not found
            RepoError: If database restoration fails at any step

        Examples:
            # Restore database from model/schema.sql before applying patch
            repo.restore_database_from_schema()
            # Database now contains clean production schema + half_orm_meta data

            # Typical apply-patch workflow
            repo.restore_database_from_schema()  # Step 1: Clean state + metadata
            patch_mgr.apply_patch_files("456-user-auth", repo.model)  # Step 2: Apply patch

            # With versioned schema and metadata
            # If schema.sql → schema-1.2.3.sql exists
            # Then metadata-1.2.3.sql is loaded automatically (if it exists)

            # Error handling
            try:
                repo.restore_database_from_schema()
            except RepoError as e:
                print(f"Database restoration failed: {e}")
                # Handle error: check schema.sql exists, verify permissions

        Notes:
            - Silences psql output using stdout=subprocess.DEVNULL
            - Uses Model.ping() for reconnection after restoration
            - Supports both schema.sql file and schema.sql -> schema-X.Y.Z.sql symlink
            - Metadata file is optional (backward compatibility with older schemas)
            - All PostgreSQL commands use repository connection configuration
            - Version deduction: schema.sql → schema-1.2.3.sql ⇒ metadata-1.2.3.sql
        """
        # 1. Verify model/schema.sql exists
        schema_path = Path(self.model_dir) / "schema.sql"

        if not schema_path.exists():
            raise RepoError(
                f"Schema file not found: {schema_path}. "
                "Cannot restore database without model/schema.sql."
            )

        try:
            # 2. Disconnect Model from database
            self.model.disconnect()
            pg_version = self.database.get_postgres_version()
            drop_cmd = ['dropdb', self.name]
            if pg_version > (13, 0):
                drop_cmd.append('--force')

            # 3. Drop existing database
            try:
                self.database.execute_pg_command(*drop_cmd)
            except Exception as e:
                raise RepoError(f"Failed to drop database: {e}") from e

            # 4. Create fresh empty database
            try:
                self.database.execute_pg_command('createdb', self.name)
            except Exception as e:
                raise RepoError(f"Failed to create database: {e}") from e

            # 5. Load schema from model/schema.sql
            try:
                self.database.execute_pg_command(
                    'psql', '-d', self.name, '-f', str(schema_path)
                )
            except Exception as e:
                raise RepoError(f"Failed to load schema from {schema_path.name}: {e}") from e

            # 5b. Load metadata from model/metadata-X.Y.Z.sql (if exists)
            metadata_path = self._deduce_metadata_path(schema_path)

            if metadata_path and metadata_path.exists():
                try:
                    self.database.execute_pg_command(
                        'psql', '-d', self.name, '-f', str(metadata_path)
                    )
                    # Optional: Log success (can be removed if too verbose)
                    # print(f"✓ Loaded metadata from {metadata_path.name}")
                except Exception as e:
                    raise RepoError(
                        f"Failed to load metadata from {metadata_path.name}: {e}"
                    ) from e
            # else: metadata file doesn't exist, continue without error (backward compatibility)

            # 6. Reconnect Model to restored database
            self.model.ping()

        except RepoError:
            # Re-raise RepoError as-is
            raise
        except Exception as e:
            # Catch any unexpected errors
            raise RepoError(f"Database restoration failed: {e}") from e

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

        return metadata_path

    @classmethod
    def clone_repo(cls,
                git_origin: str,
                database_name: Optional[str] = None,
                dest_dir: Optional[str] = None,
                production: bool = False,
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
            production: Production mode flag (passed to Database.setup_database)
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

        Examples:
            # Interactive with prompts for connection params
            Repo.clone_repo("https://github.com/user/project.git")

            # With custom database name (creates .hop/alt_config)
            Repo.clone_repo(
                "https://github.com/user/project.git",
                database_name="my_local_dev_db"
            )

            # Production mode
            Repo.clone_repo(
                "https://github.com/user/project.git",
                production=True,
                create_db=False  # DB must already exist
            )

        Notes:
            - Changes current working directory to cloned project
            - Empty connection_options {} triggers interactive prompts
            - restore_database_from_schema() loads production schema version
            - Returns None (command completes, no return value needed)
        """
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

        # Step 7: Load config and setup database
        from half_orm_dev.repo import Config  # Import here to avoid circular imports
        config = Config(dest_path)

        connection_options = {
            'host': None,
            'port': None,
            'user': None,
            'password': None,
            'production': production
        }

        try:
            Database.setup_database(
                database_name=config.name,
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
