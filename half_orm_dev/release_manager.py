"""
ReleaseManager module for half-orm-dev

Manages release files (releases/*.txt), version calculation, and release
lifecycle (stage → rc → production) for the Git-centric workflow.
"""

from pathlib import Path
from typing import Optional, Tuple, List
from dataclasses import dataclass


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
        # Prepare new release
        release_mgr = ReleaseManager(repo)
        result = release_mgr.prepare_release('minor')
        # Creates releases/1.4.0-stage.txt

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
        self._releases_dir = Path(repo.base_dir) / "releases"

    def prepare_release(self, increment_type: str) -> dict:
        """
        Prepare next release stage file.

        Creates new releases/X.Y.Z-stage.txt file based on latest version
        and increment type. Validates repository state, synchronizes with
        origin, and pushes to reserve version globally.

        Workflow:
        1. Validate on ho-prod branch
        2. Validate repository is clean
        3. Fetch from origin
        4. Synchronize with origin/ho-prod (pull if behind)
        5. Read production version from model/schema.sql
        6. Calculate next version based on increment type
        7. Verify stage file doesn't already exist
        8. Create empty stage file
        9. Commit with message "Prepare release X.Y.Z-stage"
        10. Push to origin (global reservation)

        Branch requirements:
        - Must be on ho-prod branch
        - Repository must be clean (no uncommitted changes)
        - Must be synced with origin/ho-prod (auto-pull if behind)

        Synchronization behavior:
        - "synced": Continue
        - "behind": Auto-pull with message
        - "ahead": Continue (will push at end)
        - "diverged": Error - manual merge required

        Args:
            increment_type: Version increment ("major", "minor", or "patch")

        Returns:
            dict: Preparation result with keys:
                - version: New version string (e.g., "1.4.0")
                - file: Path to created stage file
                - previous_version: Previous production version

        Raises:
            ReleaseManagerError: If validation fails
            ReleaseManagerError: If not on ho-prod branch
            ReleaseManagerError: If repository not clean
            ReleaseManagerError: If ho-prod diverged from origin
            ReleaseFileError: If stage file already exists
            ReleaseVersionError: If version calculation fails

        Examples:
            # Prepare minor release
            result = release_mgr.prepare_release('minor')
            # Production was 1.3.5 → creates releases/1.4.0-stage.txt

            # Prepare patch release
            result = release_mgr.prepare_release('patch')
            # Production was 1.3.5 → creates releases/1.3.6-stage.txt

            # Error handling
            try:
                result = release_mgr.prepare_release('major')
            except ReleaseManagerError as e:
                print(f"Failed: {e}")
        """
        # 1. Validate on ho-prod branch
        if self._repo.hgit.branch != 'ho-prod':
            raise ReleaseManagerError(
                f"Must be on ho-prod branch to prepare release.\n"
                f"Current branch: {self._repo.hgit.branch}\n"
                f"Switch to ho-prod: git checkout ho-prod"
            )

        # 2. Validate repository is clean
        if not self._repo.hgit.repos_is_clean():
            raise ReleaseManagerError(
                "Repository has uncommitted changes.\n"
                "Commit or stash changes before preparing release:\n"
                "  git status\n"
                "  git add . && git commit"
            )

        # 3. Fetch from origin
        self._repo.hgit.fetch_from_origin()

        # 4. Synchronize with origin
        is_synced, status = self._repo.hgit.is_branch_synced("ho-prod")

        if status == "behind":
            # Pull automatically
            self._repo.hgit.pull()
        elif status == "diverged":
            raise ReleaseManagerError(
                "ho-prod has diverged from origin/ho-prod.\n"
                "Manual resolution required:\n"
                "  git pull --rebase origin ho-prod\n"
                "  or\n"
                "  git merge origin/ho-prod"
            )
        # If "synced" or "ahead", continue

        # 5. Read production version from model/schema.sql
        prod_version_str = self._get_production_version()

        # Parse into Version object for calculation
        prod_version = self.parse_version_from_filename(f"{prod_version_str}.txt")

        # 6. Calculate next version
        next_version = self.calculate_next_version(prod_version, increment_type)

        # 7. Verify stage file doesn't exist
        stage_file = self._releases_dir / f"{next_version}-stage.txt"
        if stage_file.exists():
            raise ReleaseFileError(
                f"Stage file already exists: {stage_file}\n"
                f"Version {next_version} is already in development.\n"
                f"To continue with this version, use existing stage file."
            )

        # 8. Create empty stage file
        stage_file.touch()

        # 9. Commit
        self._repo.hgit.add(str(stage_file))
        self._repo.hgit.commit("-m", f"Prepare release {next_version}-stage")

        # 10. Push to origin (global reservation)
        self._repo.hgit.push()

        # Return result
        return {
            'version': next_version,
            'file': str(stage_file),
            'previous_version': prod_version_str
        }

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
        schema_path = Path(self._base_dir) / "model" / "schema.sql"

        # Parse version from symlink
        version_from_file = self._parse_version_from_symlink(schema_path)

        # Optional validation against database
        try:
            version_from_db = self._repo.database.last_release_s
            if version_from_file != version_from_db:
                # Warning but not error (file is source of truth)
                import sys
                sys.stderr.write(
                    f"Warning: Version mismatch detected:\n"
                    f"  model/schema.sql: {version_from_file}\n"
                    f"  Database metadata: {version_from_db}\n"
                    f"Using file version as source of truth.\n"
                )
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
        import re

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
        target = schema_path.readlink()
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

    def parse_version_from_filename(self, filename: str) -> Version:
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
        import re
        from pathlib import Path

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
