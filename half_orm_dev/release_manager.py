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

            # Cherche RC ou stage pour cette version
            rc_pattern = f"{next_version}-rc*.txt"
            stage_file = self._releases_dir / f"{next_version}-stage.txt"

            if list(self._releases_dir.glob(rc_pattern)) or stage_file.exists():
                return next_version

        return None

    def get_rc_files(self, version: str) -> List[str]:
        """
        Liste tous les fichiers RC pour une version, triés par numéro.

        Returns:
            Liste triée (ex: ["1.3.6-rc1.txt", "1.3.6-rc2.txt"])
        """
        pattern = f"{version}-rc*.txt"
        rc_pattern = re.compile(r'-rc(\d+)\.txt$')
        rc_files = list(self._releases_dir.glob(pattern))

        return sorted(rc_files, key=lambda f: int(re.search(rc_pattern, f.name).group(1)))

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

    def get_all_release_context_patches(self) -> List[str]:
        """
        Récupère TOUS les patches du contexte de la prochaine release.

        IMPORTANT: Application séquentielle des RC incrémentaux.
        - rc1: patches initiaux (ex: 123, 456, 789)
        - rc2: patches nouveaux (ex: 999)
        - rc3: patches nouveaux (ex: 888, 777)

        Résultat: [123, 456, 789, 999, 888, 777]

        Pas de déduplication car chaque RC est incrémental.

        Returns:
            Liste ordonnée des patch IDs (séquence complète)

        Examples:
            # Production: 1.3.5
            # 1.3.6-rc1.txt: 123, 456, 789
            # 1.3.6-rc2.txt: 999
            # 1.3.6-stage.txt: 234, 567

            patches = mgr.get_all_release_context_patches()
            # → ["123", "456", "789", "999", "234", "567"]

            # Pour apply-patch sur patch 888:
            # 1. Restore DB (1.3.5)
            # 2. Apply 123, 456, 789 (rc1)
            # 3. Apply 999 (rc2)
            # 4. Apply 234, 567 (stage)
            # 5. Apply 888 (patch courant)
        """
        next_version = self.get_next_release_version()

        if not next_version:
            return []

        all_patches = []

        # 1. Appliquer tous les RC dans l'ordre (incrémentaux)
        rc_files = self.get_rc_files(next_version)
        for rc_file in rc_files:
            patches = self.read_release_patches(rc_file)
            # Chaque RC est incrémental, pas besoin de déduplication
            all_patches.extend(patches)

        # 2. Appliquer stage (nouveaux patches en développement)
        stage_file = f"{next_version}-stage.txt"
        stage_patches = self.read_release_patches(stage_file)
        all_patches.extend(stage_patches)

        return all_patches

    def add_patch_to_release(self, patch_id: str, to_version: Optional[str] = None) -> dict:
        """
        Add patch to stage release file with validation and exclusive lock.

        Complete workflow with distributed lock to prevent race conditions:
        1. Pre-lock validations (branch, clean, patch exists)
        2. Detect target stage file (auto or explicit)
        3. Check patch not already in release
        4. Acquire exclusive lock on ho-prod (atomic via Git tag)
        5. Sync with origin (fetch + pull if needed)
        6. Create temporary validation branch
        7. Add patch to stage file on temp branch + commit
        8. Apply all patches with release context + run tests
        9. If tests fail: cleanup temp branch, release lock, exit with error
        10. If tests pass: return to ho-prod, delete temp branch
        11. Apply same change on ho-prod + commit
        12. Push ho-prod to origin
        13. Send resync notifications to other patch branches
        14. Rename patch branch to archive namespace
        15. Release lock (in finally block)

        Args:
            patch_id: Patch identifier (e.g., "456-user-auth")
            to_version: Optional explicit version (e.g., "1.3.6")
                    Required if multiple stage releases exist
                    Auto-detected if only one stage exists

        Returns:
            {
                'status': 'success',
                'patch_id': str,              # "456-user-auth"
                'target_version': str,        # "1.3.6"
                'stage_file': str,            # "1.3.6-stage.txt"
                'temp_branch': str,           # "temp-valid-1.3.6"
                'tests_passed': bool,         # True
                'archived_branch': str,       # "ho-release/1.3.6/456-user-auth"
                'commit_sha': str,            # SHA of ho-prod commit
                'patches_in_release': List[str],  # All patches after add
                'notifications_sent': List[str],  # Branches notified
                'lock_tag': str               # "lock-ho-prod-1704123456789"
            }

        Raises:
            ReleaseManagerError: If validations fail:
                - Not on ho-prod branch
                - Repository not clean
                - Patch doesn't exist (Patches/{patch_id}/)
                - Branch doesn't exist (ho-patch/{patch_id})
                - No stage release found
                - Multiple stages without --to-version
                - Specified stage doesn't exist
                - Patch already in release
                - Lock acquisition failed (another process holds lock)
                - ho-prod diverged from origin
                - Tests failed on temp branch
                - Push failed

        Examples:
            # Add patch to auto-detected stage (one stage exists)
            result = release_mgr.add_patch_to_release("456-user-auth")
            # → Adds to releases/1.3.6-stage.txt
            # → Tests on temp-valid-1.3.6
            # → Archives to ho-release/1.3.6/456-user-auth

            # Add patch to explicit version (multiple stages)
            result = release_mgr.add_patch_to_release(
                "456-user-auth",
                to_version="1.3.6"
            )

            # Error handling
            try:
                result = release_mgr.add_patch_to_release("456-user-auth")
            except ReleaseManagerError as e:
                if "locked" in str(e):
                    print("Another add-to-release in progress, retry later")
                elif "Tests failed" in str(e):
                    print("Patch breaks tests, fix and retry")
        """
        # 1. Pre-lock validations
        if self._repo.hgit.branch != "ho-prod":
            raise ReleaseManagerError(
                "Must be on ho-prod branch to add patch to release.\n"
                f"Current branch: {self._repo.hgit.branch}"
            )

        if not self._repo.hgit.repos_is_clean():
            raise ReleaseManagerError(
                "Repository has uncommitted changes. Commit or stash first."
            )

        # Check patch directory exists
        patch_dir = Path(self._repo.base_dir) / "Patches" / patch_id
        if not patch_dir.exists():
            raise ReleaseManagerError(
                f"Patch directory not found: Patches/{patch_id}/\n"
                f"Create patch first with: half_orm dev create-patch"
            )

        # Check patch branch exists
        if not self._repo.hgit.branch_exists(f"ho-patch/{patch_id}"):
            raise ReleaseManagerError(
                f"Branch ho-patch/{patch_id} not found locally.\n"
                f"Checkout branch first: git checkout ho-patch/{patch_id}"
            )

        # 2. Detect target stage file
        target_version, stage_file = self._detect_target_stage_file(to_version)

        # 3. Check patch not already in release
        existing_patches = self.read_release_patches(stage_file)
        if patch_id in existing_patches:
            raise ReleaseManagerError(
                f"Patch {patch_id} already in release {target_version}-stage.\n"
                f"Nothing to do."
            )

        # 4. ACQUIRE LOCK on ho-prod (with 30 min timeout for stale locks)
        lock_tag = self._repo.hgit.acquire_branch_lock("ho-prod", timeout_minutes=30)

        temp_branch = f"temp-valid-{target_version}"

        try:
            # 5. Sync with origin (now that we have lock)
            self._repo.hgit.fetch_from_origin()
            is_synced, status = self._repo.hgit.is_branch_synced("ho-prod")

            if status == "behind":
                self._repo.hgit.pull()
            elif status == "diverged":
                raise ReleaseManagerError(
                    "Branch ho-prod has diverged from origin.\n"
                    "Manual merge or rebase required."
                )

            # 6. Create temporary validation branch
            self._repo.hgit.checkout("-b", temp_branch)

            # 7. Add patch to stage file on temp branch
            self._apply_patch_change_to_stage_file(stage_file, patch_id)

            # 8. Commit on temp branch
            commit_msg = f"Add {patch_id} to release {target_version}-stage (validation)"
            self._repo.hgit.add(str(self._releases_dir / stage_file))
            self._repo.hgit.commit("-m", commit_msg)

            # 9. Run validation tests (apply patches + pytest)
            try:
                self._run_validation_tests()
            except ReleaseManagerError as e:
                # Tests failed - cleanup and exit
                self._repo.hgit.checkout("ho-prod")
                self._repo.hgit._HGit__git_repo.git.branch("-D", temp_branch)
                raise ReleaseManagerError(
                    f"Tests failed for patch {patch_id}. Not integrated.\n"
                    f"{e}"
                )

            # 10. Return to ho-prod
            self._repo.hgit.checkout("ho-prod")

            # 11. Delete temp branch (validation passed)
            self._repo.hgit._HGit__git_repo.git.branch("-D", temp_branch)

            # 12. Apply same change on ho-prod
            self._apply_patch_change_to_stage_file(stage_file, patch_id)

            # 13. Commit on ho-prod
            commit_msg = f"Add {patch_id} to release {target_version}-stage"
            self._repo.hgit.add(str(self._releases_dir / stage_file))
            self._repo.hgit.commit("-m", commit_msg)
            commit_sha = self._repo.hgit.last_commit()

            # 14. Push ho-prod (no conflict possible - we have lock)
            self._repo.hgit.push("origin", "ho-prod")

            # 15. Send resync notifications (non-blocking)
            notified = self._send_resync_notifications(patch_id, target_version)

            # 16. Rename branch to archive
            archived_branch = f"ho-release/{target_version}/{patch_id}"
            self._repo.hgit.rename_branch(
                f"ho-patch/{patch_id}",
                archived_branch,
                delete_remote_old=True
            )

            # 17. Read final patch list
            final_patches = self.read_release_patches(stage_file)

            return {
                'status': 'success',
                'patch_id': patch_id,
                'target_version': target_version,
                'stage_file': stage_file,
                'temp_branch': temp_branch,
                'tests_passed': True,
                'archived_branch': archived_branch,
                'commit_sha': commit_sha,
                'patches_in_release': final_patches,
                'notifications_sent': notified,
                'lock_tag': lock_tag
            }

        finally:
            # 18. ALWAYS release lock (even on error or Ctrl+C)
            self._repo.hgit.release_branch_lock(lock_tag)


    def _detect_target_stage_file(self, to_version: Optional[str] = None) -> Tuple[str, str]:
        """
        Detect target stage file (auto-detect or explicit).

        Logic:
        - If to_version provided: validate it exists
        - If no to_version: auto-detect (error if 0 or multiple stages)

        Args:
            to_version: Optional explicit version (e.g., "1.3.6")

        Returns:
            Tuple of (version, filename)
            Example: ("1.3.6", "1.3.6-stage.txt")

        Raises:
            ReleaseManagerError:
                - No stage release found (need prepare-release first)
                - Multiple stages without explicit version
                - Specified stage doesn't exist

        Examples:
            # Auto-detect (one stage exists)
            version, filename = self._detect_target_stage_file()
            # Returns: ("1.3.6", "1.3.6-stage.txt")

            # Explicit version
            version, filename = self._detect_target_stage_file("1.4.0")
            # Returns: ("1.4.0", "1.4.0-stage.txt")

            # Error cases
            # No stage: "No stage release found. Run 'prepare-release' first."
            # Multiple stages: "Multiple stages found. Use --to-version."
            # Invalid: "Stage release 1.9.9 not found"
        """
        # Find all stage files
        stage_files = list(self._releases_dir.glob("*-stage.txt"))

        # If explicit version provided
        if to_version:
            stage_file = self._releases_dir / f"{to_version}-stage.txt"

            if not stage_file.exists():
                raise ReleaseManagerError(
                    f"Stage release {to_version} not found.\n"
                    f"Available stages: {[f.stem for f in stage_files]}"
                )

            return (to_version, f"{to_version}-stage.txt")

        # Auto-detect
        if len(stage_files) == 0:
            raise ReleaseManagerError(
                "No stage release found.\n"
                "Run 'half_orm dev prepare-release <type>' first."
            )

        if len(stage_files) > 1:
            versions = [f.stem.replace('-stage', '') for f in stage_files]
            raise ReleaseManagerError(
                f"Multiple stage releases found: {versions}\n"
                f"Use --to-version to specify target release."
            )

        # Single stage file
        stage_file = stage_files[0]
        version = stage_file.stem.replace('-stage', '')

        return (version, stage_file.name)


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

    def _send_resync_notifications(
        self,
        patch_id: str,
        target_version: str
    ) -> List[str]:
        """
        Send resync notifications to all active patch branches.

        Creates empty commits on all ho-patch/* branches (except current)
        to notify developers that they should resync with ho-prod.

        Notifications are NON-BLOCKING: if one fails, logs warning and
        continues with others. Does not fail the entire workflow.

        Args:
            patch_id: Patch that was integrated (e.g., "456-user-auth")
            target_version: Release version (e.g., "1.3.6")

        Returns:
            List of branch names that successfully received notification
            Example: ["ho-patch/789-security", "ho-patch/234-reports"]

        Examples:
            # Send notifications after successful integration
            notified = self._send_resync_notifications("456-user-auth", "1.3.6")
            print(f"Notified {len(notified)} branches")

            # Notification commit message format:
            # "RESYNC REQUIRED: 456-user-auth integrated to release 1.3.6"

            # Non-blocking: continues even if some notifications fail
            # Logs warnings for failed notifications
        """
        # Get current branch to return to later
        current_branch = self._repo.hgit.branch

        # Get all active patch branches
        all_branches = self._get_active_patch_branches()

        # Filter out current patch branch
        target_branches = [
            branch for branch in all_branches
            if branch != f"ho-patch/{patch_id}"
        ]

        notified = []

        for branch in target_branches:
            try:
                # Checkout branch
                self._repo.hgit.checkout(branch)

                # Create notification commit
                message = f"RESYNC REQUIRED: {patch_id} integrated to release {target_version}"
                self._repo.hgit.commit("--allow-empty", "-m", message)

                # Push notification
                self._repo.hgit.push()

                notified.append(branch)

            except Exception as e:
                # Non-blocking: log warning and continue
                print(
                    f"⚠️  Warning: Failed to notify {branch}: {e}",
                    file=sys.stderr
                )
                continue

        # Return to original branch
        try:
            self._repo.hgit.checkout(current_branch)
        except Exception:
            pass  # Best effort

        return notified


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
