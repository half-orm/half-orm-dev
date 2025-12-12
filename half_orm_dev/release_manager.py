"""
ReleaseManager module for half-orm-dev

Manages release files (releases/*.txt), version calculation, and release
lifecycle (stage → rc → production) for the Git-centric workflow.
"""

import fnmatch
import os
import re
import sys
import subprocess

from pathlib import Path
from typing import Optional, Tuple, List, Dict
from dataclasses import dataclass
from datetime import datetime, timezone

import click

from git.exc import GitCommandError
from half_orm_dev.decorators import with_dynamic_branch_lock
from half_orm import utils
from half_orm_dev.release_file import ReleaseFile

class ReleaseManagerError(Exception):
    """Base exception for ReleaseManager operations."""
    pass


class ReleaseVersionError(ReleaseManagerError):
    """Raised when version calculation or parsing fails."""
    pass


class ReleaseFileError(ReleaseManagerError):
    """Raised when release file operations fail."""
    pass


@dataclass
class Version:
    """Semantic version with stage information."""
    major: int
    minor: int
    patch: int
    stage: Optional[str] = None  # None, "stage", "rc1", "rc2", "hotfix1", etc.

    def __str__(self) -> str:
        """String representation of version."""
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.stage:
            return f"{base}-{self.stage}"
        return base

    def __lt__(self, other: 'Version') -> bool:
        """Compare versions for sorting."""
        # Compare base version first
        if (self.major, self.minor, self.patch) != (other.major, other.minor, other.patch):
            return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

        # If base versions equal, compare stages
        # Priority: production (None) > rc > stage > hotfix
        stage_priority = {
            None: 4,           # Production (highest)
            'rc': 3,           # Release candidate
            'stage': 2,        # Development stage
            'hotfix': 1        # Hotfix (lowest)
        }

        # Extract stage type (rc1 → rc, hotfix2 → hotfix)
        self_stage_type = self._get_stage_type()
        other_stage_type = other._get_stage_type()

        self_priority = stage_priority.get(self_stage_type, 0)
        other_priority = stage_priority.get(other_stage_type, 0)

        # If different stage types, compare by priority
        if self_priority != other_priority:
            return self_priority < other_priority

        # Same stage type - compare stage strings for RC/hotfix numbers
        # rc2 > rc1, hotfix2 > hotfix1
        if self.stage and other.stage:
            return self.stage < other.stage

        return False

    def _get_stage_type(self) -> Optional[str]:
        """Extract stage type from stage string."""
        if not self.stage:
            return None

        if self.stage == 'stage':
            return 'stage'
        elif self.stage.startswith('rc'):
            return 'rc'
        elif self.stage.startswith('hotfix'):
            return 'hotfix'

        return None


class ReleaseManager:
    """
    Manages release files and version lifecycle.

    Handles creation, validation, and management of releases/*.txt files
    following the Git-centric workflow specifications.

    Release stages:
    - X.Y.Z-stage.txt: Development stage (mutable)
    - X.Y.Z-rc[N].txt: Release candidate (immutable)
    - X.Y.Z.txt: Production release (immutable)
    - X.Y.Z-hotfix[N].txt: Emergency hotfix (immutable)

    Examples:
        # Create new release
        release_mgr = ReleaseManager(repo)
        result = release_mgr.new_release('minor')
        # Creates branch ho-release/1.4.0

        # Find latest version
        version = release_mgr.find_latest_version()
        print(f"Latest: {version}")  # "1.3.5-rc2"

        # Calculate next version
        next_ver = release_mgr.calculate_next_version(version, 'patch')
        print(f"Next: {next_ver}")  # "1.3.6"
    """

    def __init__(self, repo):
        """
        Initialize ReleaseManager.

        Args:
            repo: Repo instance providing access to repository state
        """
        self._repo = repo
        self._base_dir = str(repo.base_dir)
        self._releases_dir = Path(repo.releases_dir)



    def _get_production_version(self) -> str:
        """
        Get production version from model/schema.sql symlink.

        Reads the version from model/schema.sql symlink target filename.
        Validates consistency with database metadata if accessible.

        Returns:
            str: Production version (e.g., "1.3.5")

        Raises:
            ReleaseFileError: If model/ directory or schema.sql missing
            ReleaseFileError: If symlink target has invalid format

        Examples:
            # schema.sql -> schema-1.3.5.sql
            version = mgr._get_production_version()
            # Returns: "1.3.5"
        """
        schema_path = Path(self._base_dir) / ".hop" / "model" / "schema.sql"

        # Parse version from symlink
        version_from_file = self._parse_version_from_symlink(schema_path)

        # Optional validation against database
        try:
            version_from_db = self._repo.database.last_release_s
            if version_from_file != version_from_db:
                self._repo.restore_database_from_schema()
        except Exception:
            # Database not accessible or no metadata: OK, continue
            pass

        return version_from_file

    def _parse_version_from_symlink(self, schema_path: Path) -> str:
        """
        Parse version from model/schema.sql symlink target.

        Extracts version number from symlink target filename following
        the pattern schema-X.Y.Z.sql.

        Args:
            schema_path: Path to model/schema.sql symlink

        Returns:
            str: Version string (e.g., "1.3.5")

        Raises:
            ReleaseFileError: If symlink missing, broken, or invalid format

        Examples:
            # schema.sql -> schema-1.3.5.sql
            version = mgr._parse_version_from_symlink(Path("model/schema.sql"))
            # Returns: "1.3.5"
        """
        # Check model/ directory exists
        model_dir = schema_path.parent
        if not model_dir.exists():
            raise ReleaseFileError(
                f"Model directory not found: {model_dir}\n"
                "Run 'half_orm dev init-project' first."
            )

        # Check schema.sql exists
        if not schema_path.exists():
            raise ReleaseFileError(
                f"Production schema file not found: {schema_path}\n"
                "Run 'half_orm dev init-project' to generate initial schema."
            )

        # Check it's a symlink
        if not schema_path.is_symlink():
            raise ReleaseFileError(
                f"Expected symlink but found regular file: {schema_path}"
            )

        # Get symlink target
        target = Path(os.readlink(schema_path))
        target_name = target.name if hasattr(target, 'name') else str(target)

        # Parse version from target filename: schema-X.Y.Z.sql
        pattern = r'^schema-(\d+\.\d+\.\d+)\.sql$'
        match = re.match(pattern, target_name)

        if not match:
            raise ReleaseFileError(
                f"Invalid schema symlink target format: {target_name}\n"
                f"Expected: schema-X.Y.Z.sql (e.g., schema-1.3.5.sql)"
            )

        # Extract version from capture group
        version = match.group(1)

        return version

    def _check_and_init_from_database(self) -> bool:
        """
        Check for legacy project and offer to initialize from database.

        For projects migrating from half_orm 0.13.x, this method detects when ALL
        three required elements are missing (releases/, model/, ho-prod branch) and
        offers to initialize them from the existing database metadata.

        Workflow:
        1. Check if releases/, model/, and ho-prod all exist
        2. If ALL THREE are missing, prompt user to initialize from database
        3. Create ho-prod branch from current branch
        4. Read production version from half_orm_meta.view.hop_last_release
        5. Create releases/ and model/ directories
        6. Generate schema and metadata files using Database._generate_schema_sql()
        7. Create releases/X.Y.Z.txt EMPTY (production release)
        8. Commit the initialization

        Returns:
            bool: True if initialization was performed, False if skipped

        Raises:
            ReleaseManagerError: If database not accessible or initialization fails
            ReleaseManagerError: If project is in inconsistent state (only some parts exist)

        Examples:
            # Migrating old project
            if release_mgr._check_and_init_from_database():
                print("Initialized from database")
            else:
                print("Already initialized")
        """
        # Check what exists
        releases_exists = self._releases_dir.exists()
        model_dir = Path(self._repo.model_dir)
        model_exists = model_dir.exists() and (model_dir / "schema.sql").exists()
        ho_prod_exists = self._repo.hgit.branch_exists("ho-prod")

        # If all three exist, no initialization needed
        if releases_exists and model_exists and ho_prod_exists:
            return False

        # If only some exist, the project is in an inconsistent state
        if releases_exists or model_exists or ho_prod_exists:
            missing = []
            if not releases_exists:
                missing.append("releases/")
            if not model_exists:
                missing.append("model/")
            if not ho_prod_exists:
                missing.append("ho-prod branch")

            existing = []
            if releases_exists:
                existing.append("releases/")
            if model_exists:
                existing.append("model/")
            if ho_prod_exists:
                existing.append("ho-prod branch")

            raise ReleaseManagerError(
                f"Project in inconsistent state.\n\n"
                f"Missing: {', '.join(missing)}\n"
                f"Present: {', '.join(existing)}\n\n"
                f"For legacy migration, all three must be missing.\n"
                f"Please either:\n"
                f"  • Complete the setup manually, or\n"
                f"  • Remove existing elements to start fresh initialization"
            )

        # All three missing - offer to initialize from database
        click.echo(f"\n{utils.Color.bold('⚠ Legacy project detected')}")
        click.echo("The releases/ and model/ directories are missing.")
        click.echo("This appears to be a project from half_orm 0.13.x or earlier.")
        click.echo()
        click.echo("I can initialize the workflow from your existing database:")
        click.echo("  • Create ho-prod branch (if needed)")
        click.echo("  • Read production version from half_orm_meta.view.hop_last_release")
        click.echo("  • Create releases/ and model/ directories")
        click.echo("  • Generate schema and metadata files")
        click.echo("  • Create initial production release file")
        click.echo()

        if not click.confirm("Initialize from database?", default=True):
            raise ReleaseManagerError(
                "Cannot proceed without releases/ directory.\n"
                "Run this command again and confirm initialization, or\n"
                "manually create the releases/ directory structure."
            )

        try:
            # Ensure ho-prod branch exists
            click.echo(f"\n{utils.Color.bold('Checking ho-prod branch...')}")
            current_branch = self._repo.hgit.branch
            if not self._repo.hgit.branch_exists("ho-prod"):
                click.echo(f"  Creating ho-prod branch from {current_branch}...")
                try:
                    self._repo.hgit.create_branch("ho-prod", from_branch=current_branch)
                    click.echo(f"  {utils.Color.green('✓ Created ho-prod branch')}")

                    # Push to remote if exists
                    if self._repo.hgit.has_remote():
                        self._repo.hgit.push_branch("ho-prod")
                        click.echo(f"  {utils.Color.green('✓ Pushed ho-prod to origin')}")

                    # Switch to ho-prod
                    self._repo.hgit.checkout("ho-prod")
                except Exception as e:
                    raise ReleaseManagerError(f"Failed to create ho-prod branch: {e}")
            else:
                click.echo(f"  ✓ ho-prod branch already exists")
                # Switch to ho-prod
                if current_branch != "ho-prod":
                    self._repo.hgit.checkout("ho-prod")

            # Read production version from database
            click.echo(f"\n{utils.Color.bold('Reading version from database...')}")
            try:
                version_str = self._repo.database.last_release_s
                click.echo(f"  Production version: {utils.Color.green(version_str)}")
            except Exception as e:
                raise ReleaseManagerError(
                    f"Failed to read version from database.\n"
                    f"Error: {e}\n\n"
                    f"Ensure:\n"
                    f"  • Database is accessible\n"
                    f"  • half_orm_meta schema exists\n"
                    f"  • hop_last_release view is populated"
                )

            # Create directories
            click.echo(f"\n{utils.Color.bold('Creating directories...')}")
            self._releases_dir.mkdir(parents=True, exist_ok=True)
            click.echo(f"  ✓ Created {self._releases_dir}")
            model_dir.mkdir(parents=True, exist_ok=True)
            click.echo(f"  ✓ Created {model_dir}")

            # Generate schema and metadata files using existing method
            click.echo(f"\n{utils.Color.bold('Generating schema files...')}")
            try:
                self._repo.database._generate_schema_sql(version_str, model_dir)
                click.echo(f"  ✓ Generated schema-{version_str}.sql")
                click.echo(f"  ✓ Generated metadata-{version_str}.sql")
                click.echo(f"  ✓ Created symlink: schema.sql -> schema-{version_str}.sql")
            except Exception as e:
                raise ReleaseManagerError(f"Failed to generate schema files: {e}")

            # Create empty production release file
            click.echo(f"\n{utils.Color.bold('Creating release file...')}")
            release_file = self._releases_dir / f"{version_str}.txt"
            release_file.touch()
            click.echo(f"  ✓ Created {release_file.name} (empty - production release)")

            # Commit initialization
            click.echo(f"\n{utils.Color.bold('Committing initialization...')}")
            self._repo.hgit.add(str(self._releases_dir))
            self._repo.hgit.add(str(model_dir))
            self._repo.hgit.commit(
                "-m",
                f"chore: initialize releases/ and model/ from database (version {version_str})"
            )
            click.echo(f"  {utils.Color.green('✓ Initialization committed')}")

            # Create production tag for this version
            click.echo(f"\n{utils.Color.bold('Creating production tag...')}")
            prod_tag = f"v{version_str}"
            self._repo.hgit.create_tag(prod_tag, f"Production release {version_str} (migrated from database)")
            click.echo(f"  {utils.Color.green(f'✓ Created tag {prod_tag}')}")

            # Push if remote exists
            if self._repo.hgit.has_remote():
                click.echo(f"\n{utils.Color.bold('Pushing to origin...')}")
                self._repo.hgit.push()
                self._repo.hgit.push_tag(prod_tag)
                click.echo(f"  {utils.Color.green('✓ Pushed to origin')}")
                click.echo(f"  {utils.Color.green(f'✓ Pushed tag {prod_tag}')}")

            click.echo(f"\n{utils.Color.green('✓ Successfully initialized from database!')}")
            click.echo()

            return True

        except Exception as e:
            # Clean up on error
            if self._releases_dir.exists() and not any(self._releases_dir.iterdir()):
                self._releases_dir.rmdir()
            if model_dir.exists() and not any(model_dir.iterdir()):
                model_dir.rmdir()
            raise ReleaseManagerError(f"Initialization failed: {e}")

    def find_latest_version(self) -> Optional[Version]:
        """
        Find latest version across all release stages.

        Scans releases/ directory for all .txt files and identifies the
        highest version considering stage priority:
        - Production releases (X.Y.Z.txt) have highest priority
        - RC releases (X.Y.Z-rc[N].txt) have second priority
        - Stage releases (X.Y.Z-stage.txt) have third priority
        - Hotfix releases (X.Y.Z-hotfix[N].txt) have fourth priority

        Returns None if no release files exist (first release).

        Version comparison:
        - Base version compared first (1.4.0 > 1.3.9)
        - Stage priority used for same base (1.3.5.txt > 1.3.5-rc2.txt)
        - RC number compared within RC stage (1.3.5-rc2 > 1.3.5-rc1)

        Returns:
            Optional[Version]: Latest version or None if no releases exist

        Raises:
            ReleaseVersionError: If version parsing fails
            ReleaseFileError: If releases/ directory not found

        Examples:
            # With releases/1.3.4.txt, releases/1.3.5-stage.txt
            version = release_mgr.find_latest_version()
            print(version)  # "1.3.5-stage"

            # With releases/1.3.4.txt, releases/1.3.5-rc2.txt
            version = release_mgr.find_latest_version()
            print(version)  # "1.3.5-rc2"

            # No release files
            version = release_mgr.find_latest_version()
            print(version)  # None
        """
        # Check releases/ directory exists
        if not self._releases_dir.exists():
            raise ReleaseFileError(
                f"Releases directory not found: {self._releases_dir}"
            )

        # Get all .txt files in releases/
        release_files = list(self._releases_dir.glob("*.txt"))

        if not release_files:
            return None

        # Parse all valid versions
        versions = []
        for release_file in release_files:
            try:
                version = self.parse_version_from_filename(release_file.name)
                versions.append(version)
            except ReleaseVersionError:
                # Ignore files with invalid format
                continue

        if not versions:
            return None

        # Sort versions and return latest
        # Version.__lt__ handles sorting with stage priority
        return max(versions)


    def calculate_next_version(
        self,
        current_version: Optional[Version],
        increment_type: str
    ) -> str:
        """
        Calculate next version based on increment type.

        Computes the next semantic version from current version and
        increment type. Handles first release (0.0.1) when no current
        version exists.

        Increment rules:
        - "major": Increment major, reset minor and patch to 0
        - "minor": Keep major, increment minor, reset patch to 0
        - "patch": Keep major and minor, increment patch

        Examples with current version 1.3.5:
        - major → 2.0.0
        - minor → 1.4.0
        - patch → 1.3.6

        First release (current_version is None):
        - Any increment type → 0.0.1

        Args:
            current_version: Current version or None for first release
            increment_type: "major", "minor", or "patch"

        Returns:
            str: Next version string (e.g., "1.4.0", "2.0.0")

        Raises:
            ReleaseVersionError: If increment_type invalid

        Examples:
            # From 1.3.5 to major
            version = Version(1, 3, 5)
            next_ver = release_mgr.calculate_next_version(version, 'major')
            print(next_ver)  # "2.0.0"

            # From 1.3.5 to minor
            next_ver = release_mgr.calculate_next_version(version, 'minor')
            print(next_ver)  # "1.4.0"

            # From 1.3.5 to patch
            next_ver = release_mgr.calculate_next_version(version, 'patch')
            print(next_ver)  # "1.3.6"

            # First release
            next_ver = release_mgr.calculate_next_version(None, 'minor')
            print(next_ver)  # "0.0.1"
        """
        # Validate increment type
        valid_types = ['major', 'minor', 'patch']
        if not increment_type or increment_type not in valid_types:
            raise ReleaseVersionError(
                f"Invalid increment type: '{increment_type}'. "
                f"Must be one of: {', '.join(valid_types)}"
            )

        # Calculate next version based on increment type
        if increment_type == 'major':
            return f"{current_version.major + 1}.0.0"
        elif increment_type == 'minor':
            return f"{current_version.major}.{current_version.minor + 1}.0"
        elif increment_type == 'patch':
            return f"{current_version.major}.{current_version.minor}.{current_version.patch + 1}"

        # Should never reach here due to validation above
        raise ReleaseVersionError(f"Unexpected increment type: {increment_type}")

    @classmethod
    def parse_version_from_filename(cls, filename: str) -> Version:
        """
        Parse version from release filename.

        Extracts semantic version and stage from release filename.

        Supported formats:
        - X.Y.Z.txt → Version(X, Y, Z, stage=None)
        - X.Y.Z-stage.txt → Version(X, Y, Z, stage="stage")
        - X.Y.Z-rc1.txt → Version(X, Y, Z, stage="rc1")
        - X.Y.Z-hotfix1.txt → Version(X, Y, Z, stage="hotfix1")

        Args:
            filename: Release filename (e.g., "1.3.5-rc2.txt")

        Returns:
            Version: Parsed version object

        Raises:
            ReleaseVersionError: If filename format invalid

        Examples:
            ver = release_mgr.parse_version_from_filename("1.3.5.txt")
            # Version(1, 3, 5, stage=None)

            ver = release_mgr.parse_version_from_filename("1.4.0-stage.txt")
            # Version(1, 4, 0, stage="stage")

            ver = release_mgr.parse_version_from_filename("1.3.5-rc2.txt")
            # Version(1, 3, 5, stage="rc2")
        """
        # Extract just filename if path provided
        filename = Path(filename).name

        # Validate not empty
        if not filename:
            raise ReleaseVersionError("Invalid format: empty filename")

        # Must end with .txt
        if not filename.endswith('.txt'):
            raise ReleaseVersionError(f"Invalid format: missing .txt extension in '{filename}'")

        # Remove .txt extension
        version_str = filename[:-4]

        # Pattern: X.Y.Z or X.Y.Z-stage or X.Y.Z-rc1 or X.Y.Z-hotfix1
        pattern = r'^(\d+)\.(\d+)\.(\d+)(?:-(stage|rc\d+|hotfix\d+))?$'

        match = re.match(pattern, version_str)

        if not match:
            raise ReleaseVersionError(
                f"Invalid format: '{filename}' does not match X.Y.Z[-stage].txt pattern"
            )

        major, minor, patch, stage = match.groups()

        # Convert to integers
        try:
            major = int(major)
            minor = int(minor)
            patch = int(patch)
        except ValueError:
            raise ReleaseVersionError(f"Invalid format: non-numeric version components in '{filename}'")

        # Validate non-negative
        if major < 0 or minor < 0 or patch < 0:
            raise ReleaseVersionError(f"Invalid format: negative version numbers in '{filename}'")

        return Version(major, minor, patch, stage)

    def get_next_release_version(self) -> Optional[str]:
        """
        Détermine LA prochaine release à déployer.

        Returns:
            Version string ou None
        """
        production_str = self._get_production_version()

        for level in ['patch', 'minor', 'major']:
            next_version = self.calculate_next_version(
                self.parse_version_from_filename(f"{production_str}.txt"), level)

            # Cherche RC ou patches TOML pour cette version
            rc_pattern = f"{next_version}-rc*.txt"
            patches_file = self._releases_dir / f"{next_version}-patches.toml"

            if list(self._releases_dir.glob(rc_pattern)) or patches_file.exists():
                return next_version

        return None

    def _get_label_files(self, version: str, label: str) -> List[str]:
        """
        Liste tous les fichiers <label> pour une version, triés par numéro.

        Returns:
            Liste triée (ex: ["1.3.6-rc1.txt", "1.3.6-rc2.txt"])
        """
        pattern = f"{version}-{label}*.txt"
        reg_ex = rf'-{label}(\d+)\.txt$'
        label_pattern = re.compile(reg_ex)
        files = list(self._releases_dir.glob(pattern))

        return sorted(files, key=lambda f: int(re.search(label_pattern, f.name).group(1)))

    def read_release_patches(self, filename: str) -> List[str]:
        """
        Lit les patch IDs d'un fichier de release.

        Ignore:
        - Lignes vides
        - Commentaires (#)
        - Whitespace
        """
        file_path = self._releases_dir / filename

        if not file_path.exists():
            return []

        patch_ids = []
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    patch_ids.append(line)

        return patch_ids

    def _apply_release_patches(self, version: str, hotfix=False) -> None:
        """
        Apply all patches for a release version to the database.

        Restores database from baseline and applies patches in order:
        1. All RC patches (rc1, rc2, etc.)
        2. Stage patches

        Args:
            version: Release version (e.g., "0.1.0")

        Raises:
            ReleaseManagerError: If patch application fails
        """
        # Restore database from baseline
        self._repo.restore_database_from_schema()

        # Apply all RC patches in order
        if not hotfix:
            rc_files = self._get_label_files(version, 'rc')
            for rc_file in rc_files:
                rc_patches = self.read_release_patches(rc_file.name)
                for patch_id in rc_patches:
                    self._repo.patch_manager.apply_patch_files(patch_id, self._repo.model)

        # Apply staged patches from TOML file (if in development) or from snapshot (if released)
        # Try TOML file first (development)
        release_file = ReleaseFile(version, self._releases_dir)
        if release_file.exists():
            # Development: read from TOML
            stage_patches = release_file.get_patches(status="staged")
        else:
            # Production: read from hotfix snapshot if it exists
            # This handles the case where we're applying a hotfix release
            hotfix_files = sorted(self._releases_dir.glob(f"{version}-hotfix*.txt"))
            if hotfix_files:
                # Apply the latest hotfix
                stage_patches = self.read_release_patches(hotfix_files[-1].name)
            else:
                # No patches to apply
                stage_patches = []

        for patch_id in stage_patches:
            self._repo.patch_manager.apply_patch_files(patch_id, self._repo.model)

    def _generate_data_sql_file(self, patch_list: List[str], output_filename: str) -> Optional[Path]:
        """
        Generate data-X.Y.Z.sql file from patches with @HOP:data annotation.

        Collects all SQL files marked with `-- @HOP:data` from the patch list
        and concatenates them into a single data SQL file for from-scratch
        installations.

        Args:
            patch_list: List of patch IDs to process
            output_filename: Name of the output file (e.g., "data-0.17.0-rc1.sql")

        Returns:
            Path to generated file, or None if no data files found

        Examples:
            self._generate_data_sql_file(
                ["456-auth", "457-roles"],
                "data-0.17.0-rc1.sql"
            )
            # Generates releases/data-0.17.0-rc1.sql with data from both patches
        """
        if not patch_list:
            return None

        try:
            # Collect all data files from patches
            data_files = self._repo.patch_manager._collect_data_files_from_patches(patch_list)

            if not data_files:
                # No data files found - skip generation
                return None

            # Generate output file
            output_path = self._releases_dir / output_filename

            with output_path.open('w', encoding='utf-8') as out_file:
                # Write header
                out_file.write(f"-- Data file for {output_filename.replace('.sql', '')}\n")
                out_file.write(f"-- Generated from patches: {', '.join(patch_list)}\n")
                out_file.write(f"-- This file contains reference data (DML) for from-scratch installations\n")
                out_file.write(f"--\n")
                out_file.write(f"-- Usage: psql -f {output_filename}\n")
                out_file.write(f"--\n\n")

                # Concatenate all data files
                for data_file in data_files:
                    # Write separator comment
                    out_file.write(f"-- ========================================\n")
                    out_file.write(f"-- Source: {data_file}\n")
                    out_file.write(f"-- ========================================\n\n")

                    # Write file content (skip first line which is -- @HOP:data)
                    content = data_file.read_text(encoding='utf-8')
                    lines = content.split('\n')

                    # Skip first line if it's the annotation
                    if lines and lines[0].strip() == "-- @HOP:data":
                        lines = lines[1:]

                    out_file.write('\n'.join(lines))
                    out_file.write('\n\n')

            return output_path

        except Exception as e:
            raise ReleaseManagerError(
                f"Failed to generate data SQL file {output_filename}: {e}"
            )

    def get_all_release_context_patches(self) -> List[str]:
        """
        Récupère TOUS les patches du contexte de la prochaine release.

        IMPORTANT: Application séquentielle des RC incrémentaux + TOML patches.
        - rc1: patches initiaux (ex: 123, 456, 789)
        - rc2: patches nouveaux (ex: 999)
        - rc3: patches nouveaux (ex: 888, 777)
        - TOML: TOUS les patches (candidates + staged) dans l'ordre

        Résultat: [123, 456, 789, 999, 888, 777, ...]

        Pas de déduplication car chaque RC est incrémental.

        Returns:
            Liste ordonnée des patch IDs (séquence complète)
            Inclut RC files + TOUS les patches du TOML (candidates + staged)

        Examples:
            # Production: 1.3.5
            # 1.3.6-rc1.txt: 123, 456, 789
            # 1.3.6-rc2.txt: 999
            # 1.3.6-patches.toml: {"234": "candidate", "567": "staged"}

            patches = mgr.get_all_release_context_patches()
            # → ["123", "456", "789", "999", "234", "567"]

            # Pour apply-patch sur patch 888:
            # 1. Restore DB (1.3.5)
            # 2. Apply 123, 456, 789 (rc1)
            # 3. Apply 999 (rc2)
            # 4. Apply 234, 567 (from TOML, all patches)
            # 5. Apply 888 (patch courant)
        """
        next_version = self.get_next_release_version()

        if not next_version:
            return []

        all_patches = []

        # 1. Appliquer tous les RC dans l'ordre (incrémentaux)
        rc_files = self._get_label_files(next_version, 'rc')
        for rc_file in rc_files:
            patches = self.read_release_patches(rc_file)
            # Chaque RC est incrémental, pas besoin de déduplication
            all_patches.extend(patches)

        # 2. Appliquer TOUS les patches du TOML (candidates + staged)
        # Pour les tests et la synchronisation, on veut tous les patches dans l'ordre
        release_file = ReleaseFile(next_version, self._releases_dir)
        if release_file.exists():
            # get_patches() sans argument retourne TOUS les patches dans l'ordre d'insertion
            all_toml_patches = release_file.get_patches()
            all_patches.extend(all_toml_patches)

        return all_patches


    def _detect_target_stage_file(self, to_version: Optional[str] = None) -> Tuple[str, str]:
        """
        Detect target patches file (auto-detect or explicit).

        Logic:
        - If to_version provided: validate it exists
        - If no to_version: auto-detect (error if 0 or multiple in development)

        Args:
            to_version: Optional explicit version (e.g., "1.3.6")

        Returns:
            Tuple of (version, filename)
            Example: ("1.3.6", "1.3.6-patches.toml")

        Raises:
            ReleaseManagerError:
                - No development release found (need prepare-release first)
                - Multiple releases without explicit version
                - Specified release doesn't exist

        Examples:
            # Auto-detect (one release exists)
            version, filename = self._detect_target_stage_file()
            # Returns: ("1.3.6", "1.3.6-patches.toml")

            # Explicit version
            version, filename = self._detect_target_stage_file("1.4.0")
            # Returns: ("1.4.0", "1.4.0-patches.toml")

            # Error cases
            # No release: "No development release found. Run 'prepare-release' first."
            # Multiple releases: "Multiple releases found. Use --to-version."
            # Invalid: "Release 1.9.9 not found"
        """
        # Find all TOML patches files (development releases)
        patches_files = list(self._releases_dir.glob("*-patches.toml"))

        # Multiple releases: require explicit version
        if len(patches_files) > 1 and not to_version:
            versions = sorted([f.stem.replace('-patches', '') for f in patches_files])
            err_msg = "\n".join([f"Multiple development releases found: {', '.join(versions)}",
                f"Specify target version:",
                f"  half_orm dev promote-to rc --to-version=<version>"])
            raise ReleaseManagerError(err_msg)

        # If explicit version provided
        if to_version:
            patches_file = self._releases_dir / f"{to_version}-patches.toml"

            if not patches_file.exists():
                raise ReleaseManagerError(
                    f"Development release {to_version} not found.\n"
                    f"Available releases: {[f.stem.replace('-patches', '') for f in patches_files]}"
                )

            return (to_version, f"{to_version}-patches.toml")

        # Auto-detect
        if len(patches_files) == 0:
            raise ReleaseManagerError(
                "No development release found.\n"
                "Run 'half_orm dev prepare-release <type>' first."
            )

        if len(patches_files) > 1:
            versions = [f.stem.replace('-patches', '') for f in patches_files]
            raise ReleaseManagerError(
                f"Multiple development releases found: {versions}\n"
                f"Use --to-version to specify target release."
            )

        # Single patches file
        patches_file = patches_files[0]
        version = patches_file.stem.replace('-patches', '')

        return (version, patches_file.name)


    def _get_active_patch_branches(self) -> List[str]:
        """
        Get list of all active ho-patch/* branches from remote.

        Reads remote refs after fetch to find all branches matching
        the ho-patch/* pattern. Used for sending resync notifications.

        Prerequisite: fetch_from_origin() must be called first to have
        up-to-date remote refs.

        Returns:
            List of branch names (e.g., ["ho-patch/456-user-auth", "ho-patch/789-security"])
            Empty list if no patch branches exist

        Examples:
            # Get active patch branches
            branches = self._get_active_patch_branches()
            # Returns: [
            #   "ho-patch/456-user-auth",
            #   "ho-patch/789-security",
            #   "ho-patch/234-reports"
            # ]

            # Used for notifications
            for branch in self._get_active_patch_branches():
                if branch != f"ho-patch/{current_patch_id}":
                    # Send notification to this branch
                    ...
        """
        git_repo = self._repo.hgit._HGit__git_repo

        try:
            remote = git_repo.remote('origin')
        except Exception:
            return []  # No remote or remote not accessible

        pattern = "origin/ho-patch/*"

        branches = [
            ref.name.replace('origin/', '', 1)
            for ref in remote.refs
            if fnmatch.fnmatch(ref.name, pattern)
        ]

        return branches

    def _send_rebase_notifications(
        self,
        version: str,
        release_type: str,
        rc_number: int = None) -> List[str]:
        """
        Send merge notifications to all active patch branches.

        After code is merged to ho-prod (promote-to rc or promote-to prod),
        active development branches must merge changes from ho-prod.
        This sends notifications (empty commits) to all ho-patch/* branches.

        Note: We use "merge" not "rebase" because branches are shared between
        developers. Rebase would rewrite history and cause conflicts.

        Args:
            version: Version string (e.g., "1.3.5")
            release_type: one of ['alpha', 'beta', 'rc', 'prod']
            rc_number: RC number (required if release_type != 'prod')

        Returns:
            List[str]: Notified branch names (without origin/ prefix)

        Examples:
            # RC promotion
            notified = mgr._send_rebase_notifications("1.3.5", 'rc', rc_number=1)
            # → Message: "[ho] 1.3.5-rc1 promoted (MERGE REQUIRED)"

            # Production deployment
            notified = mgr._send_rebase_notifications("1.3.5", 'prod')
            # → Message: "[ho] Production 1.3.5 deployed (MERGE REQUIRED)"
        """
        # Get all active patch branches
        remote_branches = self._repo.hgit.get_remote_branches()

        # Filter for active ho-patch/* branches
        active_branches = []
        for branch in remote_branches:
            # Strip 'origin/' prefix if present
            branch_name = branch.replace("origin/", "")

            # Only include ho-patch/* branches
            if branch_name.startswith("ho-patch/"):
                active_branches.append(branch_name)

        if not active_branches:
            return []

        notified_branches = []
        current_branch = self._repo.hgit.branch

        # Build release identifier for message
        if release_type and release_type != 'prod':
            if rc_number is None:
                rc_number = ''
            release_id = f"{version}-{release_type}{rc_number}"
            event = "promoted"
        else:  # prod
            release_id = f"production {version}"
            event = "deployed"

        for branch in active_branches:
            try:
                # Checkout branch
                self._repo.hgit.checkout(branch)

                # Create notification message
                message = (
                    f"[ho] {release_id.capitalize()} {event} (MERGE REQUIRED)\n\n"
                    f"Version {release_id} has been {event} with code merged to ho-prod.\n"
                    f"Active patch branches MUST merge these changes.\n\n"
                    f"Action required (branches are shared):\n"
                    f"  git checkout {branch}\n"
                    f"  git pull  # Get this notification\n"
                    f"  git merge ho-prod\n"
                    f"  # Resolve conflicts if any\n"
                    f"  git push\n\n"
                    f"Status: Action required (merge from ho-prod)"
                )

                # Create empty commit with notification
                self._repo.hgit.commit("--allow-empty", "-m", message)

                # Push notification
                self._repo.hgit.push()

                notified_branches.append(branch)

            except Exception as e:
                # Non-blocking: continue with other branches
                print(f"Warning: Failed to notify {branch}: {e}")
                continue

        # Return to original branch
        self._repo.hgit.checkout(current_branch)

        return notified_branches

    def _run_validation_tests(self) -> None:
        """
        Run pytest tests on current branch for validation.

        Executes pytest in tests/ directory and checks return code.
        Used to validate patch integration on temporary branch before
        committing to ho-prod.

        Prerequisite: Must be on temp validation branch with patch
        applied and code generated.

        Raises:
            ReleaseManagerError: If tests fail (non-zero exit code)
                Error message includes pytest output for debugging

        Examples:
            # On temp-valid-1.3.6 after applying patches
            try:
                self._run_validation_tests()
                print("✅ All tests passed")
            except ReleaseManagerError as e:
                print(f"❌ Tests failed:\n{e}")
                # Cleanup and exit
        """
        try:
            result = subprocess.run(
                ["pytest", "tests/"],
                cwd=str(self._repo.base_dir),
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                raise ReleaseManagerError(
                    f"Tests failed for patch integration:\n"
                    f"{result.stdout}\n"
                    f"{result.stderr}"
                )

        except FileNotFoundError:
            raise ReleaseManagerError(
                "pytest not found. Install pytest to run validation tests."
            )
        except subprocess.TimeoutExpired:
            raise ReleaseManagerError(
                "Tests timed out. Check for hanging tests."
            )
        except Exception as e:
            raise ReleaseManagerError(
                f"Failed to run tests: {e}"
            )



    def _apply_patch_change_to_stage_file(
        self,
        stage_file: str,
        patch_id: str
    ) -> None:
        """
        Add patch ID to stage release file (append to end).

        Appends patch_id as new line at end of releases/{stage_file}.
        Creates file if it doesn't exist (should not happen in normal flow).

        Does NOT commit - caller is responsible for staging and committing.

        Args:
            stage_file: Stage filename (e.g., "1.3.6-stage.txt")
            patch_id: Patch identifier to add (e.g., "456-user-auth")

        Raises:
            ReleaseManagerError: If file write fails

        Examples:
            # Add patch to stage file
            self._apply_patch_change_to_stage_file("1.3.6-stage.txt", "456-user-auth")

            # File content before:
            # 123-initial
            # 789-security

            # File content after:
            # 123-initial
            # 789-security
            # 456-user-auth

            # Caller must then:
            # self._repo.hgit.add("releases/1.3.6-stage.txt")
            # self._repo.hgit.commit("-m", "Add 456-user-auth to release")
        """
        stage_path = self._releases_dir / stage_file

        try:
            # Append patch to file (create if doesn't exist)
            with open(stage_path, 'a', encoding='utf-8') as f:
                f.write(f"{patch_id}\n")

        except Exception as e:
            raise ReleaseManagerError(
                f"Failed to update stage file {stage_file}: {e}"
            )

    def _ensure_patch_branch_synced(self, patch_id: str) -> dict:
        """
        Ensure patch branch is synced with ho-prod before integration.

        Automatically syncs patch branch by merging ho-prod INTO the patch branch.
        This ensures the patch branch has all latest changes from ho-prod before
        being integrated back into the release.

        Direction: ho-prod → ho-patch/{patch_id}
                (update patch branch with latest production changes)

        Simple merge strategy: ho-prod is merged INTO the patch branch using
        standard git merge. No fast-forward or rebase needed since full commit
        history is preserved during promote_to (no squash).

        Sync Strategy:
            1. Check if already synced → return immediately
            2. Merge ho-prod into patch branch (standard merge)
            3. If merge conflicts, block for manual resolution

        This simple approach is appropriate because:
        - Full history is preserved at promote_to (no squash)
        - Merge commits in patch branches are acceptable
        - Individual commit history matters for traceability

        Args:
            patch_id: Patch identifier (e.g., "456-user-auth")

        Returns:
            dict: Sync result with keys:
                - 'strategy': Strategy used for sync
                    * "already-synced": No action needed
                    * "fast-forward": Clean fast-forward merge
                    * "rebase": Linear history via rebase
                    * "merge": Safe merge with merge commit
                - 'branch_name': Full branch name (e.g., "ho-patch/456-user-auth")

        Raises:
            ReleaseManagerError: If automatic sync fails due to conflicts
                requiring manual resolution. Error message includes specific
                instructions for manual conflict resolution.

        Examples:
            # Already synced
            result = self._ensure_patch_branch_synced("456-user-auth")
            # Returns: {'strategy': 'already-synced', 'branch_name': 'ho-patch/456-user-auth'}

            # Behind - fast-forward successful
            result = self._ensure_patch_branch_synced("789-security")
            # Returns: {'strategy': 'fast-forward', 'branch_name': 'ho-patch/789-security'}

            # Diverged - rebase successful
            result = self._ensure_patch_branch_synced("234-reports")
            # Returns: {'strategy': 'rebase', 'branch_name': 'ho-patch/234-reports'}

            # Conflicts require manual resolution
            try:
                result = self._ensure_patch_branch_synced("999-bugfix")
            except ReleaseManagerError as e:
                # Error with manual resolution instructions
                pass

        Side Effects:
            - Checks out patch branch temporarily
            - May create commits (merge) or rewrite history (rebase)
            - Pushes changes to remote (may require force push for rebase)
            - Returns to original branch after sync

        Notes:
            - Fast-forward is preferred (cleanest, no extra commits)
            - Rebase is acceptable for ephemeral ho-patch/* branches
            - Merge is fallback when rebase has conflicts
            - Manual resolution required only for unresolvable conflicts
            - Non-blocking: continues workflow after successful sync
        """
        branch_name = f"ho-patch/{patch_id}"

        # 1. Check if already synced
        is_synced, status = self._repo.hgit.is_branch_synced(branch_name)

        if is_synced:
            return {
                'strategy': 'already-synced',
                'branch_name': branch_name
            }

        # 2. Save current branch to return to later
        current_branch = self._repo.hgit.branch

        try:
            # 3. Checkout patch branch
            self._repo.hgit.checkout(branch_name)

            # 4. Merge ho-prod into patch branch (standard merge)
            try:
                self._repo.hgit.merge("ho-prod")

                # 5. Push changes to remote
                self._repo.hgit.push()

                # Success - return merge strategy
                return {
                    'strategy': 'merge',
                    'branch_name': branch_name
                }

            except GitCommandError as e:
                # Merge conflicts - manual resolution required
                raise ReleaseManagerError(
                    f"Branch {branch_name} has conflicts with ho-prod.\n"
                    f"Manual resolution required:\n\n"
                    f"  git checkout {branch_name}\n"
                    f"  git merge ho-prod\n"
                    f"  # Resolve conflicts in your editor\n"
                    f"  git add .\n"
                    f"  git commit\n"
                    f"  git push\n\n"
                    f"Then retry: half_orm dev add-to-release {patch_id}\n\n"
                    f"Git error: {e}"
                )

        finally:
            # 6. Always return to original branch (best effort)
            try:
                self._repo.hgit.checkout(current_branch)
            except Exception:
                # Best effort - don't fail if checkout back fails
                pass

    def update_production(self) -> dict:
        """
        Fetch tags and list available releases for production upgrade (read-only).

        Equivalent to 'apt update' - synchronizes with origin and shows available
        releases but makes NO modifications to database or repository.

        Workflow:
            1. Fetch tags from origin (git fetch --tags)
            2. Read current production version from database (hop_last_release)
            3. List available release tags (v1.3.6, v1.3.6-rc1, v1.4.0)
            4. Calculate sequential upgrade path
            5. Return structured results for CLI display

        Returns:
            dict: Update information with structure:
                {
                    'current_version': str,  # e.g., "1.3.5"
                    'available_releases': List[dict],  # List of available tags
                    'upgrade_path': List[str],  # Sequential path
                    'has_updates': bool  # True if updates available
                }

                Each item in 'available_releases':
                {
                    'tag': str,  # e.g., "v1.3.6"
                    'version': str,  # e.g., "1.3.6"
                    'type': str,  # 'production', 'rc', or 'hotfix'
                    'patches': List[str]  # Patch IDs in release
                }

        Raises:
            ReleaseManagerError: If cannot fetch tags or read database version

        Examples:
            # List available production releases
            result = mgr.update_production()
            print(f"Current: {result['current_version']}")
            for rel in result['available_releases']:
                print(f"  → {rel['version']} ({len(rel['patches'])} patches)")

            # Include RC releases
            result = mgr.update_production()
            # → Shows v1.3.6-rc1, v1.3.6, v1.4.0
        """
        allow_rc = self._repo.allow_rc

        # 1. Get available release tags from origin
        available_tags = self._get_available_release_tags(allow_rc=allow_rc)

        # 2. Read current production version from database
        try:
            current_version = self._repo.database.last_release_s
        except Exception as e:
            raise ReleaseManagerError(
                f"Cannot read current production version from database: {e}"
            )

        # 3. Build list of available releases with details
        available_releases = []

        for tag in available_tags:
            # Extract version from tag (remove 'v' prefix)
            version = tag[1:]

            # Determine release type
            if '-rc' in version:
                release_type = 'rc'
            elif '-hotfix' in version:
                release_type = 'hotfix'
            else:
                release_type = 'production'

            # Extract base version for file lookup (remove suffix)
            base_version = version.split('-')[0]

            # Read patches from release file
            release_file = self._releases_dir / f"{version}.txt"
            patches = []

            if release_file.exists():
                content = release_file.read_text().strip()
                if content:
                    patches = [line.strip() for line in content.split('\n') if line.strip()]

            # Only include releases newer than current version
            if self._version_is_newer(version, current_version):
                available_releases.append({
                    'tag': tag,
                    'version': version,
                    'type': release_type,
                    'patches': patches
                })

        # 4. Calculate upgrade path (implemented in Artefact 3B)
        upgrade_path = []
        if available_releases:
            # Extract production versions only for upgrade path
            production_versions = [
                rel['version'] for rel in available_releases
                if rel['type'] == 'production'
            ]

            if production_versions:
                # Use last production version as target
                target_version = production_versions[-1]
                upgrade_path = self._calculate_upgrade_path(current_version, target_version)

        # 5. Return results
        return {
            'current_version': current_version,
            'available_releases': available_releases,
            'upgrade_path': upgrade_path,
            'has_updates': len(available_releases) > 0
        }

    def _get_available_release_tags(self, allow_rc: bool = False) -> List[str]:
        """
        Get available release tags from Git repository.

        Fetches tags from origin and filters for release tags (v*.*.*).
        Excludes RC tags unless allow_rc=True.

        Args:
            allow_rc: If True, include RC tags (v1.3.6-rc1)

        Returns:
            List[str]: Sorted list of tag names (e.g., ["v1.3.6", "v1.4.0"])

        Raises:
            ReleaseManagerError: If fetch fails

        Examples:
            # Production only
            tags = mgr._get_available_release_tags()
            # → ["v1.3.6", "v1.4.0"]

            # Include RC
            tags = mgr._get_available_release_tags(allow_rc=True)
            # → ["v1.3.6-rc1", "v1.3.6", "v1.4.0"]
        """
        try:
            # Fetch tags from origin
            self._repo.hgit.fetch_tags()
        except Exception as e:
            raise ReleaseManagerError(f"Failed to fetch tags from origin: {e}")

        # Get all tags from repository
        try:
            all_tags = self._repo.hgit._HGit__git_repo.tags
        except Exception as e:
            raise ReleaseManagerError(f"Failed to read tags from repository: {e}")

        # Filter for release tags (v*.*.*) with optional -rc or -hotfix suffix
        release_pattern = re.compile(r'^v\d+\.\d+\.\d+(-rc\d+|-hotfix\d+)?$')
        release_tags = []

        for tag in all_tags:
            tag_name = tag.name
            if release_pattern.match(tag_name):
                # Filter RC tags unless explicitly allowed
                if '-rc' in tag_name and not allow_rc:
                    continue
                release_tags.append(tag_name)

        # Sort tags by version (semantic versioning)
        def version_key(tag_name):
            """Extract sortable version tuple from tag name."""
            # Remove 'v' prefix
            version_str = tag_name[1:]

            # Split version and suffix
            if '-rc' in version_str:
                base_ver, rc_suffix = version_str.split('-rc')
                rc_num = int(rc_suffix)
                suffix_weight = (1, rc_num)  # RC comes before production
            elif '-hotfix' in version_str:
                base_ver, hotfix_suffix = version_str.split('-hotfix')
                hotfix_num = int(hotfix_suffix)
                suffix_weight = (2, hotfix_num)  # Hotfix comes after production
            else:
                base_ver = version_str
                suffix_weight = (1.5, 0)  # Production between RC and hotfix

            # Parse base version
            major, minor, patch = map(int, base_ver.split('.'))

            return (major, minor, patch, suffix_weight)

        release_tags.sort(key=version_key)

        return release_tags

    def _calculate_upgrade_path(
        self,
        current: str,
        target: str
    ) -> List[str]:
        """
        Calculate sequential upgrade path between two versions.

        Determines all intermediate versions needed to upgrade from
        current to target version. Versions must be applied sequentially.

        Args:
            current: Current production version (e.g., "1.3.5")
            target: Target version (e.g., "1.4.0")

        Returns:
            List[str]: Ordered list of versions to apply

        Examples:
            # Direct upgrade
            path = mgr._calculate_upgrade_path("1.3.5", "1.3.6")
            # → ["1.3.6"]

            # Multi-step upgrade
            path = mgr._calculate_upgrade_path("1.3.5", "1.4.0")
            # → ["1.3.6", "1.4.0"]

            # No upgrades needed
            path = mgr._calculate_upgrade_path("1.4.0", "1.4.0")
            # → []
        """
        # Parse versions
        current_version = self.parse_version_from_filename(f"{current}.txt")
        target_version = self.parse_version_from_filename(f"{target}.txt")

        # If same version, no upgrade needed
        if current == target:
            return []

        # Get all available release tags (production only)
        available_tags = self._get_available_release_tags(allow_rc=False)

        # Extract versions from tags and parse them
        available_versions = []
        for tag in available_tags:
            # Remove 'v' prefix: v1.3.6 → 1.3.6
            version_str = tag[1:] if tag.startswith('v') else tag

            # Skip if not a valid production version format
            if not re.match(r'^\d+\.\d+\.\d+$', version_str):
                continue

            try:
                version = self.parse_version_from_filename(f"{version_str}.txt")
                available_versions.append((version_str, version))
            except Exception:
                continue

        # Sort versions
        available_versions.sort(key=lambda x: (x[1].major, x[1].minor, x[1].patch))

        # Build sequential path from current to target
        path = []
        for version_str, version in available_versions:
            # Skip versions <= current
            if (version.major, version.minor, version.patch) <= \
               (current_version.major, current_version.minor, current_version.patch):
                continue

            # Add versions <= target
            if (version.major, version.minor, version.patch) <= \
               (target_version.major, target_version.minor, target_version.patch):
                path.append(version_str)

        return path

    def _version_is_newer(self, version1: str, version2: str) -> bool:
        """
        Compare two version strings to check if version1 is newer than version2.

        Args:
            version1: First version (e.g., "1.3.6", "1.3.6-rc1")
            version2: Second version (e.g., "1.3.5")

        Returns:
            bool: True if version1 > version2

        Examples:
            _version_is_newer("1.3.6", "1.3.5")  # → True
            _version_is_newer("1.3.5", "1.3.6")  # → False
            _version_is_newer("1.3.6-rc1", "1.3.5")  # → True
        """
        # Extract base versions (remove suffix)
        base1 = version1.split('-')[0]
        base2 = version2.split('-')[0]

        # Parse versions
        parts1 = tuple(map(int, base1.split('.')))
        parts2 = tuple(map(int, base2.split('.')))

        return parts1 > parts2

    def upgrade_production(
        self,
        to_version: Optional[str] = None,
        dry_run: bool = False,
        force_backup: bool = False,
        skip_backup: bool = False
    ) -> dict:
        """
        Upgrade production database to target version.

        Applies releases sequentially to production database. This is the
        production-safe upgrade workflow that NEVER destroys the database,
        working incrementally on existing data.

        CRITICAL: This method works on EXISTING production database.
        It does NOT use restore_database_from_schema() which would destroy data.

        Workflow:
            1. CREATE BACKUP (first action, before any validation)
            2. Validate production environment (ho-prod branch, clean repo)
            3. Fetch available releases via update_production()
            4. Calculate upgrade path (all or to specific version)
            5. Apply each release sequentially on existing database
            6. Update database version after each release

        Args:
            to_version: Stop at specific version (e.g., "1.3.6")
                    If None, apply all available releases
            dry_run: Simulate without modifying database or creating backup
            force_backup: Overwrite existing backup file without confirmation
            skip_backup: Skip backup creation (DANGEROUS - for testing only)

        Returns:
            dict: Upgrade result with detailed information

            Structure:
                'status': 'success' or 'dry_run'
                'dry_run': bool
                'backup_created': Path or None (if dry_run or skip_backup)
                'current_version': str (version before upgrade)
                'target_version': str or None (explicit target or None for "all")
                'releases_applied': List[str] (versions applied)
                'patches_applied': Dict[str, List[str]] (patches per release)
                'final_version': str (version after upgrade)

        Raises:
            ReleaseManagerError: For validation failures or application errors

        Examples:
            # Upgrade to latest (all available releases)
            result = mgr.upgrade_production()
            # Current: 1.3.5
            # Applies: 1.3.6 → 1.3.7 → 1.4.0
            # Result: {
            #   'status': 'success',
            #   'backup_created': Path('backups/1.3.5.sql'),
            #   'current_version': '1.3.5',
            #   'target_version': None,
            #   'releases_applied': ['1.3.6', '1.3.7', '1.4.0'],
            #   'patches_applied': {
            #       '1.3.6': ['456-auth', '789-security'],
            #       '1.3.7': ['999-bugfix'],
            #       '1.4.0': ['111-feature']
            #   },
            #   'final_version': '1.4.0'
            # }

            # Upgrade to specific version
            result = mgr.upgrade_production(to_version="1.3.7")
            # Current: 1.3.5
            # Applies: 1.3.6 → 1.3.7 (stops here)
            # Result: {
            #   'status': 'success',
            #   'target_version': '1.3.7',
            #   'releases_applied': ['1.3.6', '1.3.7'],
            #   'final_version': '1.3.7'
            # }

            # Dry run (no changes)
            result = mgr.upgrade_production(dry_run=True)
            # Result: {
            #   'status': 'dry_run',
            #   'dry_run': True,
            #   'backup_would_be_created': 'backups/1.3.5.sql',
            #   'releases_would_apply': ['1.3.6', '1.3.7'],
            #   'patches_would_apply': {...}
            # }

            # Already up to date
            result = mgr.upgrade_production()
            # Result: {
            #   'status': 'success',
            #   'current_version': '1.4.0',
            #   'releases_applied': [],
            #   'message': 'Production already at latest version'
            # }
        """
        # Get current version
        current_version = self._repo.database.last_release_s

        # === 1. BACKUP FIRST (unless dry_run or skip_backup) ===
        backup_path = None
        if not dry_run and not skip_backup:
            backup_path = self._create_production_backup(
                current_version,
                force=force_backup
            )

        # === 2. Validate environment ===
        self._validate_production_upgrade()

        # === 3. Get available releases ===
        update_info = self.update_production()

        # Check if already up to date
        if not update_info['has_updates']:
            return {
                'status': 'success',
                'dry_run': False,
                'backup_created': backup_path,
                'current_version': current_version,
                'target_version': to_version,
                'releases_applied': [],
                'patches_applied': {},
                'final_version': current_version,
                'message': 'Production already at latest version'
            }

        # === 4. Calculate upgrade path ===
        if to_version:
            # Upgrade to specific version
            full_path = update_info['upgrade_path']

            # Validate target version exists
            if to_version not in full_path:
                raise ReleaseManagerError(
                    f"Target version {to_version} not in upgrade path. "
                    f"Available versions: {', '.join(full_path)}"
                )

            # Truncate path to target
            upgrade_path = []
            for version in full_path:
                upgrade_path.append(version)
                if version == to_version:
                    break
        else:
            # Upgrade to latest (all releases)
            upgrade_path = update_info['upgrade_path']

        # === DRY RUN - Stop here and return simulation ===
        if dry_run:
            # Build patches_would_apply dict
            patches_would_apply = {}
            for version in upgrade_path:
                patches = self.read_release_patches(f"{version}.txt")
                patches_would_apply[version] = patches

            return {
                'status': 'dry_run',
                'dry_run': True,
                'backup_would_be_created': f'backups/{current_version}.sql',
                'current_version': current_version,
                'target_version': to_version,
                'releases_would_apply': upgrade_path,
                'patches_would_apply': patches_would_apply,
                'final_version': upgrade_path[-1] if upgrade_path else current_version
            }

        # === 5. Apply releases sequentially ===
        patches_applied = {}

        try:
            for version in upgrade_path:
                # Apply release and collect patches
                applied_patches = self._apply_release_to_production(version)
                patches_applied[version] = applied_patches

        except Exception as e:
            # On error, provide rollback instructions
            raise ReleaseManagerError(
                f"Failed to apply release {version}: {e}\n\n"
                f"ROLLBACK INSTRUCTIONS:\n"
                f"1. Restore database: psql -d {self._repo.database.name} -f {backup_path}\n"
                f"2. Verify restoration: SELECT * FROM half_orm_meta.hop_release ORDER BY id DESC LIMIT 1;\n"
                f"3. Fix the failing patch and retry upgrade"
            ) from e

        # === 6. Build success result ===
        final_version = upgrade_path[-1] if upgrade_path else current_version

        return {
            'status': 'success',
            'dry_run': False,
            'backup_created': backup_path,
            'current_version': current_version,
            'target_version': to_version,
            'releases_applied': upgrade_path,
            'patches_applied': patches_applied,
            'final_version': final_version
        }


    def _create_production_backup(
        self,
        current_version: str,
        force: bool = False
    ) -> Path:
        """
        Create production database backup before upgrade.

        Creates backups/{version}.sql using pg_dump with full database dump
        (schema + data + metadata). This is the rollback point if upgrade fails.

        Args:
            current_version: Current database version (e.g., "1.3.5")
            force: Overwrite existing backup without confirmation

        Returns:
            Path: Backup file path (e.g., Path("backups/1.3.5.sql"))

        Raises:
            ReleaseManagerError: If backup creation fails or user declines overwrite

        Examples:
            # Create new backup
            path = mgr._create_production_backup("1.3.5")
            # → Creates backups/1.3.5.sql
            # → Returns Path('backups/1.3.5.sql')

            # Backup exists, user confirms overwrite
            path = mgr._create_production_backup("1.3.5", force=False)
            # → Prompt: "Backup exists. Overwrite? [y/N]"
            # → User enters 'y'
            # → Overwrites backups/1.3.5.sql

            # Backup exists, force=True
            path = mgr._create_production_backup("1.3.5", force=True)
            # → Overwrites without prompt

            # Backup exists, user declines
            path = mgr._create_production_backup("1.3.5", force=False)
            # → User enters 'n'
            # → Raises: "Backup exists and user declined overwrite"
        """
        # Create backups directory if doesn't exist
        backups_dir = Path(self._repo.base_dir) / "backups"
        backups_dir.mkdir(exist_ok=True)

        # Build backup filename
        backup_file = backups_dir / f"{current_version}.sql"

        # Check if backup already exists
        if backup_file.exists() and not force:
            # Prompt user for confirmation
            response = input(
                f"Backup {backup_file} already exists. "
                f"Overwrite? [y/N]: "
            ).strip().lower()

            if response != 'y':
                raise ReleaseManagerError(
                    f"Backup {backup_file} already exists. "
                    f"Use --force to overwrite or remove the file manually."
                )

        # Create backup using pg_dump
        try:
            self._repo.database.execute_pg_command(
                'pg_dump',
                '-f', str(backup_file),
            )
        except Exception as e:
            raise ReleaseManagerError(
                f"Failed to create backup {backup_file}: {e}"
            ) from e

        return backup_file


    def _validate_production_upgrade(self) -> None:
        """
        Validate production environment before upgrade.

        Checks:
        1. Current branch is ho-prod (production branch)
        2. Repository is clean (no uncommitted changes)

        Raises:
            ReleaseManagerError: If validation fails

        Examples:
            # Valid state
            # Branch: ho-prod
            # Status: clean
            mgr._validate_production_upgrade()
            # → Returns without error

            # Wrong branch
            # Branch: ho-patch/456-test
            mgr._validate_production_upgrade()
            # → Raises: "Must be on ho-prod branch"

            # Uncommitted changes
            # Branch: ho-prod
            # Status: modified files
            mgr._validate_production_upgrade()
            # → Raises: "Repository has uncommitted changes"
        """
        # Check branch
        if self._repo.hgit.branch != "ho-prod":
            raise ReleaseManagerError(
                f"Must be on ho-prod branch for production upgrade. "
                f"Current branch: {self._repo.hgit.branch}"
            )

        # Check repo is clean
        if not self._repo.hgit.repos_is_clean():
            raise ReleaseManagerError(
                "Repository has uncommitted changes. "
                "Commit or stash changes before upgrading production."
            )


    def _apply_release_to_production(self, version: str) -> List[str]:
        """
        Apply single release to existing production database.

        Reads patches from releases/{version}.txt and applies them sequentially
        to the existing database using PatchManager.apply_patch_files().
        Updates database version after successful application.

        CRITICAL: Works on EXISTING database. Does NOT restore/recreate.

        Args:
            version: Release version (e.g., "1.3.6")

        Returns:
            List[str]: Patch IDs applied (e.g., ["456-auth", "789-security"])

        Raises:
            ReleaseManagerError: If patch application fails

        Examples:
            # Apply release with multiple patches
            # releases/1.3.6.txt contains: 456-auth, 789-security
            patches = mgr._apply_release_to_production("1.3.6")
            # → Applies 456-auth to existing DB
            # → Applies 789-security to existing DB
            # → Updates DB version to 1.3.6
            # → Returns ["456-auth", "789-security"]

            # Apply release with no patches (empty release)
            # releases/1.3.6.txt is empty
            patches = mgr._apply_release_to_production("1.3.6")
            # → Updates DB version to 1.3.6
            # → Returns []

            # Patch application fails
            # 789-security has SQL error
            patches = mgr._apply_release_to_production("1.3.6")
            # → Applies 456-auth successfully
            # → 789-security fails
            # → Raises exception with error details
        """
        # Read patches from release file
        release_file = f"{version}.txt"
        patches = self.read_release_patches(release_file)

        # Apply each patch sequentially
        for patch_id in patches:
            try:
                self._repo.patch_manager.apply_patch_files(
                    patch_id,
                    self._repo.model
                )
            except Exception as e:
                raise ReleaseManagerError(
                    f"Failed to apply patch {patch_id} from release {version}: {e}"
                ) from e

        # Update database version
        version_parts = version.split('.')
        if len(version_parts) != 3:
            raise ReleaseManagerError(
                f"Invalid version format: {version}. Expected X.Y.Z"
            )

        major, minor, patch = map(int, version_parts)
        self._repo.database.register_release(major, minor, patch)

        return patches

    # ========================================================================
    # NEW INTEGRATION WORKFLOW WITH RELEASE BRANCHES
    # ========================================================================

    def _calculate_next_version(self, level: str) -> str:
        """
        Calculate the next version number based on increment level.

        Args:
            level: Version increment level ('major', 'minor', or 'patch')

        Returns:
            Next version number (e.g., "0.1.0")

        Raises:
            ReleaseManagerError: If level is invalid

        Examples:
            # Current prod: 0.0.5
            _calculate_next_version("patch")  # → "0.0.6"
            _calculate_next_version("minor")  # → "0.1.0"
            _calculate_next_version("major")  # → "1.0.0"
        """
        # Get current production version
        try:
            current_version = self._get_current_production_version()
        except Exception as e:
            # No production version yet, start at 0.0.0
            current_version = "0.0.0"

        # Parse version
        parts = current_version.split('.')
        if len(parts) != 3:
            raise ReleaseManagerError(f"Invalid version format: {current_version}")

        major, minor, patch = map(int, parts)

        # Increment based on level
        if level == 'major':
            major += 1
            minor = 0
            patch = 0
        elif level == 'minor':
            minor += 1
            patch = 0
        elif level == 'patch':
            patch += 1
        else:
            raise ReleaseManagerError(
                f"Invalid version level: {level}. Must be 'major', 'minor', or 'patch'"
            )

        return f"{major}.{minor}.{patch}"

    def _get_current_production_version(self) -> str:
        """
        Get the current production version from tags.

        Returns:
            Current production version (e.g., "0.0.5")

        Raises:
            ReleaseManagerError: If no production version found
        """
        # Fetch tags from remote to ensure we have the latest
        try:
            self._repo.hgit.fetch_from_origin()
        except Exception:
            # If fetch fails, continue with local tags
            pass

        # Get all production tags (X.Y.Z format, no -rc suffix)
        tags = self._repo.hgit.list_tags()
        version_tags = []

        for tag in tags:
            # Match vX.Y.Z pattern (with v prefix, no -rc suffix)
            if tag.startswith('v') and tag.count('.') == 2 and '-rc' not in tag:
                try:
                    # Remove 'v' prefix and validate
                    version = tag[1:]  # Remove 'v'
                    parts = version.split('.')
                    # Validate it's numeric
                    int(parts[0])
                    int(parts[1])
                    int(parts[2])
                    version_tags.append(version)  # Store without 'v' prefix
                except (ValueError, IndexError):
                    continue

        if not version_tags:
            raise ReleaseManagerError("No production version found")

        # Sort versions and return the latest
        def version_key(v):
            parts = v.split('.')
            return (int(parts[0]), int(parts[1]), int(parts[2]))

        version_tags.sort(key=version_key, reverse=True)
        return version_tags[0]

    @with_dynamic_branch_lock(lambda self, level: "ho-prod")
    def new_release(self, level: str) -> dict:
        """
        Create a new release with integration branch.

        Creates a release branch (ho-release/{version}) where patches will be
        merged. This allows patches to see each other's changes and supports
        dependencies between patches.

        Workflow:
        0. Check for legacy project migration (auto-initialize if needed)
        1. Calculate next version based on level (major/minor/patch)
        2. Create release branch ho-release/{version} from ho-prod
        3. Push release branch to remote
        4. Create empty {version}-candidates.txt file (NEW)
        5. Create empty {version}-stage.txt file
        6. Commit and push files
        7. Switch to release branch

        Args:
            level: Version increment level ('major', 'minor', or 'patch')

        Returns:
            dict with keys:
                - version: The new version number
                - branch: The release branch name
                - stage_file: Path to stage file

        Raises:
            ReleaseManagerError: If release creation fails

        Examples:
            result = rel_mgr.new_release("minor")
            # → version: "0.1.0"
            # → branch: "ho-release/0.1.0"
            # → Creates empty 0.1.0-candidates.txt
            # → Creates empty 0.1.0-stage.txt
            # → Switches to ho-release/0.1.0
        """
        # 0. Check for legacy project migration
        was_initialized = self._check_and_init_from_database()

        # Calculate next version
        version = self._calculate_next_version(level)
        release_branch = f"ho-release/{version}"

        # Ensure we're on ho-prod (unless we just initialized and are already there)
        if not was_initialized or self._repo.hgit.branch != "ho-prod":
            try:
                self._repo.hgit.checkout("ho-prod")
            except Exception as e:
                raise ReleaseManagerError(f"Failed to checkout ho-prod: {e}")

        # Create empty patches file (TOML format)
        release_file = ReleaseFile(version, self._releases_dir)
        try:
            release_file.create_empty()
        except Exception as e:
            raise ReleaseManagerError(f"Failed to create patches file: {e}")

        # Commit patches file on ho-prod and sync to active branches
        try:
            sync_result = self._repo.commit_and_sync_to_active_branches(
                message=f"[HOP] Create release %{version} branch and patches file",
                reason=f"new release {version}"
            )
        except Exception as e:
            raise ReleaseManagerError(f"Failed to commit patches file: {e}")

        # Create release branch from ho-prod
        try:
            self._repo.hgit.create_branch(release_branch, from_branch="ho-prod")
        except Exception as e:
            raise ReleaseManagerError(f"Failed to create release branch: {e}")

        # Push release branch
        try:
            self._repo.hgit.push_branch(release_branch)
        except Exception as e:
            raise ReleaseManagerError(f"Failed to push release branch: {e}")

        # Switch to release branch (NEW)
        try:
            self._repo.hgit.checkout(release_branch)
        except Exception as e:
            raise ReleaseManagerError(f"Failed to checkout release branch: {e}")

        return {
            'version': version,
            'branch': release_branch,
            'patches_file': str(release_file.file_path)
        }


    def _detect_version_to_promote(self, target: str) -> str:
        """
        Detect which version to promote (smallest version for sequential promotion).

        Args:
            target: Either 'rc' or 'prod'

        Returns:
            Version string (e.g., "0.1.0")

        Raises:
            ReleaseManagerError: If no release found to promote
        """
        # Find TOML patches files
        patches_files = list(self._releases_dir.glob("*-patches.toml"))
        if not patches_files:
            raise ReleaseManagerError(
                "No stage release found. "
                "Create a stage release first with: half_orm dev release new"
            )

        # Sort by version to get the smallest (oldest) one first
        def version_key(path):
            version_str = path.stem.replace('-patches', '')
            parts = version_str.split('.')
            try:
                return (int(parts[0]), int(parts[1]), int(parts[2]))
            except (ValueError, IndexError):
                return (0, 0, 0)

        patches_files.sort(key=version_key)
        return patches_files[0].stem.replace('-patches', '')

    @with_dynamic_branch_lock(lambda self: "ho-prod")
    def promote_to_rc(self) -> dict:
        """
        Promote a stage release to RC by tagging the release branch.

        Creates an RC tag on the release branch (ho-release/{version}).
        The release branch contains all merged patches.

        Args:
            version: Version to promote (e.g., "0.1.0"). If None, auto-detects
                    the smallest (oldest) stage release for sequential promotion.

        Returns:
            dict with keys:
                - version: The version
                - tag: The RC tag name
                - branch: The release branch

        Raises:
            ReleaseManagerError: If promotion fails

        Examples:
            rel_mgr.promote_to_rc()
            # → Creates tag "0.1.0-rcN" on ho-release/0.1.0
            # → Renames 0.1.0-stage.txt to 0.1.0-rcN.txt

            rel_mgr.promote_to_rc()  # Auto-detect version
            # → Promotes the smallest stage release
        """
        # Auto-detect version if not provided
        label = 'rc'
        version = self._detect_version_to_promote(label)

        # Check TOML patches file exists
        release_file = ReleaseFile(version, self._releases_dir)
        if not release_file.exists():
            raise ReleaseManagerError(f"Release {version} not found (no patches file)")

        release_branch = f"ho-release/{version}"
        rc_number = self._get_latest_label_number(version, label)
        rc_tag = f"v{version}-rc{rc_number}"  # Use v prefix and rc1 for first RC

        try:
            # 1. Apply patches to database (for validation)
            self._apply_release_patches(version)

            # 2. Checkout release branch
            self._repo.hgit.checkout(release_branch)

            # 3. Create RC tag on release branch
            self._repo.hgit.create_tag(rc_tag, f"Release Candidate %{version}")

            # Push tag
            self._repo.hgit.push_tag(rc_tag)

            # Stay on release branch for rename operations
            # (allows continued development on this release)

            # Create RC snapshot from staged patches
            rc_file = self._releases_dir / f"{version}-rc{rc_number}.txt"
            staged_patches = release_file.get_patches(status="staged")
            rc_file.write_text("\n".join(staged_patches) + "\n" if staged_patches else "", encoding='utf-8')

            # Keep TOML file for continued development (don't delete it)

            # Generate data-X.Y.Z-rcN.sql if any patches have @HOP:data files
            rc_patches = self.read_release_patches(rc_file.name)
            data_file = self._generate_data_sql_file(
                rc_patches,
                f"data-{version}-rc{rc_number}.sql"
            )

            # Commit RC snapshot and data file (both in .hop/releases/)
            # This also syncs .hop/ to all active branches automatically
            self._repo.commit_and_sync_to_active_branches(
                message=f"[HOP] Promote release %{version} to RC {rc_number}"
            )

            return {
                'version': version,
                'tag': rc_tag,
                'branch': release_branch
            }

        except Exception as e:
            raise ReleaseManagerError(f"Failed to promote to RC: {e}")

    @with_dynamic_branch_lock(lambda self: "ho-prod")
    def promote_to_prod(self) -> dict:
        """
        Promote stage release to production.

        Merges the release branch into ho-prod and finalizes:
        1. Merge ho-release/{version} into ho-prod
        2. Apply all patches (RCs + stage) and generate schema
        3. Rename stage.txt to X.Y.Z.txt (incremental patches after last RC)
        4. Delete candidates.txt file
        5. Create production tag on ho-prod
        6. Delete release branch (ho-release/{version})

        RC files are preserved for historical tracking.

        Args:
            version: Version to promote (e.g., "0.1.0"). If None, auto-detects
                    the smallest (oldest) RC release for sequential promotion.

        Returns:
            dict with keys:
                - version: The version
                - tag: The production tag
                - deleted_branches: List of deleted branches

        Raises:
            ReleaseManagerError: If promotion fails

        Examples:
            rel_mgr.promote_to_prod()
            # → Merges ho-release/0.1.0 into ho-prod
            # → Creates tag "0.1.0"
            # → Deletes candidates.txt, renames stage.txt to 0.1.0.txt
            # → Keeps RC files (0.1.0-rc1.txt, etc.) for history

            rel_mgr.promote_to_prod()  # Auto-detect version
            # → Promotes the smallest RC release
        """
        # Auto-detect version
        version = self._detect_version_to_promote('prod')

        # Check TOML patches file exists
        release_file = ReleaseFile(version, self._releases_dir)
        if not release_file.exists():
            raise ReleaseManagerError(f"RC release {version} not found")

        # Check for candidate patches - offer to migrate to next patch version
        candidates = release_file.get_patches(status="candidate")
        migrate_candidates = False
        next_patch_version = None

        if candidates:
            # Calculate next patch version (X.Y.Z → X.Y.Z+1)
            parts = version.split('.')
            if len(parts) != 3:
                raise ReleaseManagerError(f"Invalid version format: {version}")

            major, minor, patch = map(int, parts)
            next_patch_version = f"{major}.{minor}.{patch + 1}"

            # Prompt user for migration
            print(f"\n{utils.Color.bold('⚠️  Candidate patches detected:')}")
            print(f"  Release {version} has {len(candidates)} candidate patch(es):")
            for patch_id in candidates:
                print(f"    • {patch_id}")
            print()
            print(f"{utils.Color.bold('Migration to new release ' + utils.Color.green(next_patch_version) + '?')}")
            print(f"  → Current release {version} will be promoted to production")
            print(f"  → Candidates will be rebased onto new release {next_patch_version}")
            print(f"  → Patch branches will be force-pushed to origin")
            print()

            response = input(f"Migrate candidates to {next_patch_version}? [y/N]: ").strip().lower()

            if response in ('y', 'yes'):
                migrate_candidates = True
                print(f"\n✓ Will migrate {len(candidates)} candidate(s) to {next_patch_version}")
            else:
                raise ReleaseManagerError(
                    f"Promotion cancelled.\n"
                    f"To proceed, either:\n"
                    f"  1. Close candidate patches: half_orm dev patch close <patch_id>\n"
                    f"  2. Accept candidate migration when prompted"
                )

        release_branch = f"ho-release/{version}"

        try:
            # Read staged patches from TOML file
            patches = release_file.get_patches(status="staged")

            # 1. Checkout ho-prod
            self._repo.hgit.checkout("ho-prod")

            # 2. Merge release branch into ho-prod (fast-forward only)
            try:
                self._repo.hgit.merge(
                    release_branch,
                    ff_only=True,
                    message=f"[HOP] Merge release %{version} into production"
                )
            except Exception:
                try:
                    self._repo.hgit.merge(
                        release_branch,
                        message=f"[HOP] Merge release %{version} into production"
                    )
                except Exception as e:
                    # Abort merge to restore clean state
                    try:
                        self._repo.hgit.merge_abort()
                    except Exception:
                        pass  # Ignore if no merge in progress
                    raise ReleaseManagerError(
                        f"Failed to merge {release_branch} into ho-prod: {e}\n"
                        "ho-prod has been restored to its previous state."
                    )

            # 3. Apply only NEW patches from TOML file (if any) and generate schema
            # Note: RC patches have already been applied during promote_to_rc
            stage_patches = release_file.get_patches(status="staged")

            if stage_patches:
                # There are new patches after RC - apply them
                # First, restore from latest RC schema
                latest_rc = self._get_latest_label_number(version, "rc")
                rc_schema_version = f"{version}-rc{latest_rc}" if latest_rc > 0 else "0.0.0"

                # Restore from RC schema if it exists, otherwise from baseline
                try:
                    self._repo.restore_database_from_schema(rc_schema_version)
                except:
                    self._repo.restore_database_from_schema()

                # Apply new stage patches
                for patch_id in stage_patches:
                    self._repo.patch_manager.apply_patch_files(patch_id, self._repo.model)
            else:
                # No new patches - just restore from latest RC
                # The database should already be in the correct state from RC
                pass

            # Generate schema dump for this production version
            model_dir = Path(self._repo.model_dir)
            self._repo.database._generate_schema_sql(version, model_dir)

            # 4. Create production snapshot and delete TOML patches file
            prod_file = self._releases_dir / f"{version}.txt"
            toml_file = self._releases_dir / f"{version}-patches.toml"

            # Write all staged patches to production snapshot
            prod_file.write_text("\n".join(patches) + "\n" if patches else "", encoding='utf-8')

            # Delete TOML patches file (no longer needed)
            if toml_file.exists():
                toml_file.unlink()

            # Generate data-X.Y.Z.sql if any patches have @HOP:data files
            # This includes patches from stage (incremental after last RC)
            prod_patches = self.read_release_patches(prod_file.name)
            self._generate_data_sql_file(
                prod_patches,
                f"data-{version}.sql"
            )

            self._repo.commit_and_sync_to_active_branches(
                message=f"[HOP] Promote release %{version} to production",
                reason=f"promote {version} to production"
            )

            # 4. Create production tag on ho-prod
            prod_tag = f"v{version}"  # Use v prefix to match existing convention
            self._repo.hgit.create_tag(prod_tag, f"Production release %{version}")
            self._repo.hgit.push_tag(prod_tag)

            deleted_branches = []

            # 7. Delete release branch (force=True because Git may not recognize the merge)
            try:
                self._repo.hgit.delete_branch(release_branch, force=True)
                self._repo.hgit.delete_remote_branch(release_branch)
                deleted_branches.append(release_branch)
            except Exception as e:
                # Log error for debugging
                print(f"Warning: Failed to delete release branch {release_branch}: {e}", file=sys.stderr)

            # 8. If candidate migration was requested, create new release and migrate patches
            if migrate_candidates and next_patch_version:
                print(f"\n{utils.Color.bold('🔄 Migrating candidates to ' + next_patch_version + '...')}")
                self._migrate_candidates_to_new_release(
                    candidates,
                    version,
                    next_patch_version
                )

            return {
                'version': version,
                'tag': f"v{version}",
                'deleted_branches': deleted_branches,
                'migrated_to': next_patch_version if migrate_candidates else None,
                'migrated_patches': candidates if migrate_candidates else []
            }

        except ReleaseManagerError:
            raise
        except Exception as e:
            raise ReleaseManagerError(f"Failed to promote to production: {e}")

    def _migrate_candidates_to_new_release(
        self,
        candidates: list,
        source_version: str,
        target_version: str
    ) -> None:
        """
        Migrate candidate patches to a new release version.

        This method:
        1. Creates new release branch from ho-prod
        2. Rebases each candidate patch branch onto the new release
        3. Force-pushes rebased branches to origin
        4. Creates new TOML file with migrated candidates and metadata
        5. Deletes old TOML file

        Args:
            candidates: List of candidate patch IDs
            source_version: Source release version (e.g., "0.17.1")
            target_version: Target release version (e.g., "0.17.2")

        Raises:
            ReleaseManagerError: If migration fails
        """

        source_release_branch = f"ho-release/{source_version}"
        target_release_branch = f"ho-release/{target_version}"

        try:
            # 1. Create new release branch from ho-prod
            print(f"  → Creating release branch {target_release_branch}...")
            self._repo.hgit.checkout("ho-prod")
            self._repo.hgit.checkout("-b", target_release_branch)
            self._repo.hgit.push_branch(target_release_branch, set_upstream=True)
            print(f"    {utils.Color.green('✓')} Created {target_release_branch}")

            # 2. Rebase each candidate patch branch
            rebased_commits = {}
            print(f"\n  → Rebasing {len(candidates)} candidate patch(es)...")

            for patch_id in candidates:
                patch_branch = f"ho-patch/{patch_id}"
                print(f"    • {patch_id}...", end=" ", flush=True)

                try:
                    # Checkout patch branch
                    self._repo.hgit.checkout(patch_branch)

                    # Rebase onto new release: git rebase --onto target source patch_branch
                    # This moves commits from source to target
                    self._repo.hgit.rebase(
                        "--onto",
                        target_release_branch,
                        source_release_branch,
                        patch_branch
                    )

                    # Get SHA of rebased commit
                    sha = self._repo.hgit.get_repo().head.commit.hexsha[:8]
                    rebased_commits[patch_id] = sha

                    # Force-push rebased branch to origin
                    self._repo.hgit.push_branch(patch_branch, force=True)

                    print(f"{utils.Color.green('✓')} (SHA: {sha})")

                except Exception as e:
                    # Try to abort rebase if it failed
                    try:
                        self._repo.hgit.rebase("--abort")
                    except:
                        pass

                    print(f"{utils.Color.red('✗ FAILED')}")
                    raise ReleaseManagerError(
                        f"Failed to rebase patch {patch_id}: {e}\n"
                        f"Please resolve conflicts manually and run:\n"
                        f"  git rebase --continue\n"
                        f"  git push origin {patch_branch} --force"
                    )

            # 3. Create new TOML file with candidates and metadata
            print(f"\n  → Creating {target_version}-patches.toml...")
            target_release_file = ReleaseFile(target_version, self._releases_dir)
            target_release_file.create_empty()

            # Add all candidates to new release
            for patch_id in candidates:
                target_release_file.add_patch(patch_id)

            # Set migration metadata
            metadata = {
                "created_from_promotion": True,
                "source_version": source_version,
                "migrated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "rebased_commits": rebased_commits
            }
            target_release_file.set_metadata(metadata)
            print(f"    {utils.Color.green('✓')} Created with {len(candidates)} candidate(s)")

            # 4. Commit the new TOML file
            self._repo.hgit.checkout(target_release_branch)
            self._repo.hgit.add(str(target_release_file.file_path))

            # 5. Delete old TOML file
            source_release_file = ReleaseFile(source_version, self._releases_dir)
            if source_release_file.file_path.exists():
                source_release_file.file_path.unlink()
                self._repo.hgit.add(str(source_release_file.file_path))
                print(f"    {utils.Color.green('✓')} Deleted {source_version}-patches.toml")

            # 6. Commit changes
            self._repo.hgit.commit(
                "-m",
                f"[HOP] Migrate {len(candidates)} candidate(s) from %{source_version} to %{target_version}"
            )
            self._repo.hgit.push_branch(target_release_branch)

            print(f"\n{utils.Color.green('✓ Migration complete!')}")
            print(f"  • {len(candidates)} patch(es) migrated to {target_version}")
            print(f"  • All patch branches rebased and force-pushed to origin")
            print(f"\n{utils.Color.bold('⚠️  IMPORTANT:')}")
            print(f"  Developers working on these patches must sync their local branches:")
            print(f"  Run: {utils.Color.bold('half_orm dev check')}")

        except ReleaseManagerError:
            raise
        except Exception as e:
            raise ReleaseManagerError(f"Failed to migrate candidates: {e}")

    def _get_latest_label_number(self, version: str, label: str) -> int:
        """
        Determine next <label> number for version.

        Finds all existing <label> files for the version and returns next number.
        If label is rc and no RCs exist, returns 1. If rc1, rc2 exist, returns 3.

        Args:
            version: Version string (e.g., "1.3.5")

        Returns:
            Next <label> number (1, 2, 3, etc.)

        Examples:
            # No existing RCs
            version = "1.3.5"
            rc_num = mgr._get_latest_label_number(version, 'rc')
            # → 1
        """
        files = self._get_label_files(version, label)

        if not files:
            # No RCs exist, this will be rc1
            return 1

        last_file = files[-1].name
        reg_ex = rf'-{label}(\d+)\.txt'
        match = re.search(reg_ex, last_file)
        if match:
            last_num = int(match.group(1))
            return last_num + 1

        raise Exception("Unable to determine next release number")

    @with_dynamic_branch_lock(lambda self: "ho-prod")
    def reopen_for_hotfix(self) -> dict:
        """
        Reopen a production version for hotfix development.

        Recreates the ho-release/X.Y.Z branch from the production tag vX.Y.Z
        and creates empty candidates.txt and stage.txt files to enable
        emergency patches.

        Args:
            version: Production version to reopen (e.g., "1.3.5")
                    If None, uses current production version from model/schema.sql

        Returns:
            dict with:
                - version: Version reopened
                - branch: Branch name created
                - candidates_file: Path to candidates file
                - stage_file: Path to stage file

        Raises:
            ReleaseManagerError: If validation fails or reopening errors occur

        Examples:
            # Reopen current production version
            result = mgr.reopen_for_hotfix()
            # → {'version': '1.3.5', 'branch': 'ho-release/1.3.5', ...}

            # Reopen specific version
            result = mgr.reopen_for_hotfix('1.3.4')
            # → {'version': '1.3.4', 'branch': 'ho-release/1.3.4', ...}

        Workflow:
            1. Detect production version (from model/schema.sql or parameter)
            2. Verify production tag vX.Y.Z exists
            3. Delete existing ho-release/X.Y.Z branch if exists
            4. Create branch from production tag
            5. Create empty X.Y.Z-candidates.txt file
            6. Create empty X.Y.Z-stage.txt file
            7. Commit and push
            8. Switch to branch
        """
        try:
            # Get current production version from model/schema.sql
            version = self._get_production_version()

            # Validate version format
            if not re.match(r'^\d+\.\d+\.\d+$', version):
                raise ReleaseManagerError(
                    f"Invalid version format: {version}\n"
                    f"Expected format: X.Y.Z (e.g., 1.3.5)"
                )

            # 2. Verify production tag exists
            prod_tag = f"v{version}"
            if not self._repo.hgit.tag_exists(prod_tag):
                raise ReleaseManagerError(
                    f"Production tag {prod_tag} does not exist.\n"
                    f"Cannot reopen version {version} for hotfix.\n"
                    f"Available tags: {', '.join(self._repo.hgit.list_tags())}"
                )

            # 3. Check if branch already exists
            release_branch = f"ho-release/{version}"
            branch_exists = self._repo.hgit.branch_exists(release_branch)

            if branch_exists:
                # Verify branch is clean before recreating
                current_branch = self._repo.hgit.branch
                if current_branch == release_branch:
                    raise ReleaseManagerError(
                        f"Cannot reopen: Already on {release_branch}\n"
                        f"Switch to another branch first: git checkout ho-prod"
                    )

                # Delete existing branch (local and remote)
                try:
                    self._repo.hgit.delete_branch(release_branch, force=True)
                except Exception as e:
                    raise ReleaseManagerError(
                        f"Failed to delete existing branch {release_branch}: {e}"
                    )

                try:
                    self._repo.hgit.delete_remote_branch(release_branch)
                except Exception:
                    # Remote branch might not exist, ignore error
                    pass

            # 4. Create branch from production tag
            self._repo.hgit.create_branch_from_tag(release_branch, prod_tag)
            self._repo.hgit.push_branch(release_branch, set_upstream=True)
            self._repo.hgit.checkout(release_branch)

            # 5. Create TOML patches file for hotfix development
            release_file = ReleaseFile(version, self._releases_dir)
            release_file.create_empty()

            # Note: HOTFIX marker is no longer needed in TOML format
            # The fact that we're on ho-release/X.Y.Z indicates hotfix development

            # 7. Commit and push (TOML file is in .hop/releases/)
            # This also syncs .hop/ to all active branches automatically
            toml_file = self._releases_dir / f"{version}-patches.toml"
            commit_msg = f"[release] Reopen %{version} for hotfix development"
            self._repo.commit_and_sync_to_active_branches(message=commit_msg)

            return {
                'version': version,
                'branch': release_branch,
                'patches_file': str(toml_file)
            }

        except ReleaseManagerError:
            raise
        except Exception as e:
            raise ReleaseManagerError(f"Failed to reopen version for hotfix: {e}")

    # from half_orm_dev.decorators import trace_package
    # @trace_package("half_orm_dev")
    @with_dynamic_branch_lock(lambda self: "ho-prod")
    def promote_to_hotfix(self) -> dict:
        """
        Promote hotfix release to production with hotfix tag.

        Similar to promote_to_prod() but:
        - Works from ho-release/X.Y.Z branch (not ho-prod)
        - Creates hotfix tag vX.Y.Z-hotfixN (not vX.Y.Z)
        - Renames stage.txt to X.Y.Z-hotfixN.txt
        - Merges ho-release/X.Y.Z into ho-prod
        - Deletes ho-release/X.Y.Z branch after promotion

        Returns:
            dict with:
                - version: Base version (e.g., "1.3.5")
                - hotfix_tag: Tag created (e.g., "v1.3.5-hotfix1")
                - branch: Branch used (e.g., "ho-release/1.3.5")
                - deleted_branches: List of deleted branches

        Raises:
            ReleaseManagerError: If validation fails or promotion errors occur

        Workflow:
            1. Verify on ho-release/X.Y.Z branch
            2. Verify candidates.txt is empty
            3. Determine next hotfix number
            4. Merge ho-release/X.Y.Z into ho-prod
            5. Rename stage.txt to X.Y.Z-hotfixN.txt and delete candidates.txt
            6. Apply release patches and generate SQL dumps on ho-prod
            7. Commit release file changes
            8. Create hotfix tag vX.Y.Z-hotfixN on ho-prod
            9. Push ho-prod
            10. Delete ho-release/X.Y.Z branch
        """
        try:
            # 1. Verify on ho-release/* branch
            current_branch = self._repo.hgit.branch
            if not current_branch.startswith('ho-release/'):
                raise ReleaseManagerError(
                    f"Must be on ho-release/* branch for hotfix promotion.\n"
                    f"Current branch: {current_branch}\n"
                    f"Use: git checkout ho-release/X.Y.Z"
                )

            # Extract version from branch name
            version = current_branch.replace('ho-release/', '')

            # 2. Verify no candidate patches remain (check TOML file)
            release_file = ReleaseFile(version, self._releases_dir)
            if release_file.exists():
                candidates = release_file.get_patches(status="candidate")
                if candidates:
                    raise ReleaseManagerError(
                        f"Cannot promote hotfix: {len(candidates)} candidate patch(es) remain:\n"
                        f"  • " + "\n  • ".join(candidates) + "\n\n"
                        f"Actions required:\n"
                        f"  1. Close patches: half_orm dev patch close <patch_id>\n"
                        f"  2. OR delete branches: git branch -D ho-patch/<patch_id>\n"
                        f"  3. OR move to another release (edit patches file manually)"
                    )

            # 3. Determine next hotfix number
            hotfix_num = self._get_latest_label_number(version, 'hotfix')
            hotfix_tag = f"v{version}-hotfix{hotfix_num}"

            # 4. Switch to ho-prod and merge
            self._repo.hgit.checkout("ho-prod")

            # Merge ho-release/X.Y.Z into ho-prod
            merge_msg = f"[release] Merge hotfix %{version}-hotfix{hotfix_num}"
            self._repo.hgit.merge(current_branch, message=merge_msg)

            # 5. Create hotfix snapshot file from staged patches
            toml_file = self._releases_dir / f"{version}-patches.toml"
            hotfix_file = self._releases_dir / f"{version}-hotfix{hotfix_num}.txt"

            if release_file.exists():
                # Get staged patches from TOML file
                staged_patches = release_file.get_patches(status="staged")

                # Write snapshot to hotfix TXT file (production format)
                hotfix_file.write_text("\n".join(staged_patches) + "\n" if staged_patches else "", encoding='utf-8')
                # Delete TOML patches file (no longer needed)
                if toml_file.exists():
                    self._repo.hgit.rm(str(toml_file))

            # Generate data-X.Y.Z-hotfixN.sql if any patches have @HOP:data files
            hotfix_patches = self.read_release_patches(hotfix_file.name)
            data_file = self._generate_data_sql_file(
                hotfix_patches,
                f"data-{version}-hotfix{hotfix_num}.sql"
            )
            if data_file:
                self._repo.hgit.add(str(data_file))  # Add data file if generated

            # 6. Apply release patches and generate SQL dumps
            self._apply_release_patches(version, True)

            # 7. Commit release file changes and sync to active branches
            sync_result = self._repo.commit_and_sync_to_active_branches(
                message=f"[HOP] Finalize hotfix %{version}-hotfix{hotfix_num} release files",
                reason=f"hotfix {version}-hotfix{hotfix_num}"
            )

            # 8. Create hotfix tag on ho-prod
            self._repo.hgit.create_tag(hotfix_tag, f"Hotfix release %{version}-hotfix{hotfix_num}")
            self._repo.hgit.push_tag(hotfix_tag)

            deleted_branches = []

            # 10. Delete release branch (force=True because Git may not recognize the merge)
            try:
                self._repo.hgit.delete_branch(current_branch, force=True)
                self._repo.hgit.delete_remote_branch(current_branch)
                deleted_branches.append(current_branch)
            except Exception as e:
                # Log error for debugging
                print(f"Warning: Failed to delete release branch {current_branch}: {e}", file=sys.stderr)

            return {
                'version': version,
                'hotfix_tag': hotfix_tag,
                'branch': current_branch,
                'deleted_branches': deleted_branches
            }

        except ReleaseManagerError:
            raise
        except Exception as e:
            raise ReleaseManagerError(f"Failed to promote hotfix: {e}")
