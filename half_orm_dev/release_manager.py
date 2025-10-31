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

from git.exc import GitCommandError

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
        6. Create temporary validation branch FROM ho-prod
        7. Merge ALL patches already in release (from ho-release/X.Y.Z/* branches)
        8. Merge new patch branch (from ho-patch/{patch_id})
        9. Add patch to stage file on temp branch + commit
        10. Run validation tests (with ALL patches integrated)
        11. If tests fail: cleanup temp branch, release lock, exit with error
        12. If tests pass: return to ho-prod, delete temp branch
        13. Add patch to stage file on ho-prod + commit (file change only)
        14. Push ho-prod to origin
        16. Archive patch branch to ho-release/{version}/{patch_id}
        17. Release lock (in finally block)

        CRITICAL: ho-prod NEVER contains patch code directly. It only contains
        the releases/*.txt files that list which patches are in each release.
        The temp-valid branch is used to test the integration of ALL patches
        together, but only the release file change is committed to ho-prod.
        Actual patch code remains in archived branches (ho-release/X.Y.Z/*).

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
                - Merge conflicts during integration
                - Tests failed on temp branch
                - Push failed

        Examples:
            # Add patch to auto-detected stage (one stage exists)
            result = release_mgr.add_patch_to_release("456-user-auth")
            # → Creates temp-valid-1.3.6
            # → Merges all patches from releases/1.3.6-stage.txt
            # → Merges ho-patch/456-user-auth
            # → Tests complete integration
            # → Updates releases/1.3.6-stage.txt on ho-prod
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
                    print("Patch breaks integration, fix and retry")
                elif "Merge conflict" in str(e):
                    print("Patch conflicts with existing patches")
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

        try:
            sync_result = self._ensure_patch_branch_synced(patch_id)

            if sync_result['strategy'] != 'already-synced':
                # Log successful auto-sync
                import sys
                print(
                    f"✓ Auto-synced {sync_result['branch_name']} with ho-prod "
                    f"({sync_result['strategy']})",
                    file=sys.stderr
                )

        except ReleaseManagerError as e:
            # Manual resolution required - release lock and exit
            # Lock will be released in finally block
            raise

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

            # 6. Create temporary validation branch FROM ho-prod
            self._repo.hgit.checkout("-b", temp_branch)

            # 7. Merge ALL existing patches in the release (already validated)
            for existing_patch_id in existing_patches:
                archived_branch = f"ho-release/{target_version}/{existing_patch_id}"
                if self._repo.hgit.branch_exists(archived_branch):
                    try:
                        self._repo.hgit.merge(
                            archived_branch,
                            no_ff=True,
                            m=f"Merge {existing_patch_id} (already in release)"
                        )
                    except Exception as e:
                        # Should not happen (already validated), but handle it
                        self._repo.hgit.checkout("ho-prod")
                        self._repo.hgit._HGit__git_repo.git.branch("-D", temp_branch)
                        raise ReleaseManagerError(
                            f"Failed to merge existing patch {existing_patch_id}.\n"
                            f"This should not happen (patch already validated).\n"
                            f"Manual intervention required.\n"
                            f"Error: {e}"
                        )
                else:
                    # Branch not found - might be an old patch before archiving system
                    import sys
                    sys.stderr.write(
                        f"Warning: Branch {archived_branch} not found. "
                        f"Patch {existing_patch_id} might be from old workflow.\n"
                    )

            # 8. Merge new patch branch into temp-valid
            try:
                self._repo.hgit.merge(
                    f"ho-patch/{patch_id}",
                    no_ff=True,
                    m=f"Merge {patch_id} for validation in {target_version}-stage"
                )
            except Exception as e:
                # Merge conflict - cleanup and exit
                self._repo.hgit.checkout("ho-prod")
                self._repo.hgit._HGit__git_repo.git.branch("-D", temp_branch)
                raise ReleaseManagerError(
                    f"Merge conflict integrating {patch_id}.\n"
                    f"The patch conflicts with existing patches in the release.\n"
                    f"Resolve conflicts manually:\n"
                    f"  1. git checkout ho-patch/{patch_id}\n"
                    f"  2. git merge ho-prod\n"
                    f"  3. Resolve conflicts\n"
                    f"  4. half_orm dev apply-patch (re-test)\n"
                    f"  5. Retry add-to-release\n"
                    f"Error: {e}"
                )

            # 9. Add patch to stage file on temp branch
            self._apply_patch_change_to_stage_file(stage_file, patch_id)

            # 10. Commit release file on temp branch
            commit_msg = f"Add {patch_id} to release {target_version}-stage (validation)"
            self._repo.hgit.add(str(self._releases_dir / stage_file))
            self._repo.hgit.commit("-m", commit_msg)

            # 11. Run validation tests (ALL patches integrated)
            try:
                self._run_validation_tests()
            except ReleaseManagerError as e:
                # Tests failed - cleanup and exit
                self._repo.hgit.checkout("ho-prod")
                self._repo.hgit._HGit__git_repo.git.branch("-D", temp_branch)
                raise ReleaseManagerError(
                    f"Tests failed for patch {patch_id}. Not integrated.\n"
                    f"The patch breaks the integration with existing patches.\n"
                    f"{e}"
                )

            # 12. Tests passed! Return to ho-prod
            self._repo.hgit.checkout("ho-prod")

            # 13. Delete temp branch (validation complete, no longer needed)
            self._repo.hgit._HGit__git_repo.git.branch("-D", temp_branch)

            # 14. Add patch to stage file on ho-prod (file change ONLY)
            self._apply_patch_change_to_stage_file(stage_file, patch_id)

            # 15. Commit on ho-prod (only release file change)
            commit_msg = f"Add {patch_id} to release {target_version}-stage"
            self._repo.hgit.add(str(self._releases_dir / stage_file))
            self._repo.hgit.commit("-m", commit_msg)
            commit_sha = self._repo.hgit.last_commit()

            # 16. Push ho-prod (no conflict possible - we have lock)
            self._repo.hgit.push("origin", "ho-prod")

            # 18. Archive patch branch to ho-release namespace
            archived_branch = f"ho-release/{target_version}/{patch_id}"
            self._repo.hgit.rename_branch(
                f"ho-patch/{patch_id}",
                archived_branch,
                delete_remote_old=True
            )

            # 19. Read final patch list
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
                'lock_tag': lock_tag
            }

        finally:
            # 20. ALWAYS release lock (even on error)
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

        # Multiple stages: require explicit version
        if len(stage_files) > 1 and not to_version:
            versions = sorted([str(self.parse_version_from_filename(f.name)).replace('-stage', '') for f in stage_files])
            err_msg = "\n".join([f"Multiple stage releases found: {', '.join(versions)}",
                f"Specify target version:",
                f"  half_orm dev promote-to rc --to-version=<version>"])
            raise ReleaseManagerError(err_msg)


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

    def promote_to(self, target: str) -> dict:
        """
        Unified promotion workflow for RC and production releases.

        Handles promotion of stage releases to either RC or production with
        shared logic for validations, lock management, code merging, branch
        cleanup, and notifications. Target-specific operations (RC numbering,
        schema generation) are conditionally executed.

        Args:
            target: Either 'rc' or 'prod'
                - 'rc': Promotes stage to RC (rc1, rc2, etc.)
                - 'prod': Promotes stage (or empty) to production

        Returns:
            dict: Promotion result with target-specific fields

            Common fields:
                'status': 'success'
                'version': str (e.g., "1.3.5")
                'from_file': str or None (source filename)
                'to_file': str (target filename)
                'patches_merged': List[str] (merged patch IDs)
                'branches_deleted': List[str] (deleted branch names)
                'commit_sha': str
                'notifications_sent': List[str] (notified branches)
                'lock_tag': str

            RC-specific fields (target='rc'):
                'rc_number': int (e.g., 1, 2, 3)
                'code_merged': bool (always True)

            Production-specific fields (target='prod'):
                'patches_applied': List[str] (all patches applied to DB)
                'schema_file': Path (model/schema-X.Y.Z.sql)
                'metadata_file': Path (model/metadata-X.Y.Z.sql)

        Raises:
            ReleaseManagerError: For validation failures, lock errors, etc.
            ValueError: If target is not 'rc' or 'prod'

        Workflow:
            0. restore prod database (schema & metadata)
            1. Pre-lock validations (ho-prod branch, clean repo)
            2. Detect source and target (version-specific logic)
            3. ACQUIRE DISTRIBUTED LOCK (30min timeout)
            4. Fetch + sync with origin
            5. [PROD ONLY] Restore DB and apply all patches
            6. Merge archived patch code to ho-prod
            7. Create target release file (mv or create)
            8. [PROD ONLY] Generate schema + metadata + symlink
            9. Commit + push
            10. Push to origin
            10.5 Create new empty stage file
            11. Send rebase notifications
            12. Cleanup patch branches
            13. RELEASE LOCK (always, even on error)

        Examples:
            # Promote to RC
            result = mgr.promote_to(target='rc')
            # → Creates X.Y.Z-rc2.txt from X.Y.Z-stage.txt
            # → Merges code, cleans branches, sends notifications

            # Promote to production
            result = mgr.promote_to(target='prod')
            # → Creates X.Y.Z.txt from X.Y.Z-stage.txt (or empty)
            # → Applies all patches to DB
            # → Generates schema-X.Y.Z.sql + metadata-X.Y.Z.sql
            # → Merges code, cleans branches, sends notifications
        """
        # Validate target parameter
        if target not in ('alpha', 'beta', 'rc', 'prod'):
            raise ValueError(f"Invalid target: {target}. Must be in ['alpha', 'beta', 'rc', 'prod']")

        # 0. restore database to prod
        self._repo.restore_database_from_schema()

        # 1. Pre-lock validations (common)
        if self._repo.hgit.branch != "ho-prod":
            raise ReleaseManagerError(
                "Must be on ho-prod branch to promote release. "
                f"Current branch: {self._repo.hgit.branch}"
            )

        if not self._repo.hgit.repos_is_clean():
            raise ReleaseManagerError(
                "Repository has uncommitted changes. "
                "Commit or stash changes before promoting."
            )

        # 2. Detect source and target (target-specific)
        version, stage_file = self._detect_stage_to_promote()
        if target != 'prod':
            # RC: stage required, validate single active RC rule
            self._validate_single_active_rc(version)
            rc_number = self._determine_rc_number(version)
            target_file = f"{version}-{target}{rc_number}.txt"
            source_type = 'stage'
        else:  # target == 'prod'
            # Production: stage optional, sequential version
            stage_path = Path(self._releases_dir) / f"{version}-stage.txt"
            if stage_path.exists():
                stage_file = f"{version}-stage.txt"
                source_type = 'stage'
            else:
                stage_file = None
                source_type = 'empty'
            target_file = f"{version}.txt"

        # 3. Acquire distributed lock
        lock_tag = None
        try:
            lock_tag = self._repo.hgit.acquire_branch_lock("ho-prod", timeout_minutes=30)

            # 4. Fetch from origin and sync
            self._repo.hgit.fetch_from_origin()

            is_synced, sync_status = self._repo.hgit.is_branch_synced("ho-prod")
            if not is_synced:
                if sync_status == "behind":
                    self._repo.hgit.pull()
                elif sync_status == "diverged":
                    raise ReleaseManagerError(
                        "ho-prod has diverged from origin. "
                        "Resolve conflicts manually: git pull origin ho-prod"
                    )

            # 5. Apply patches to database (prod only)
            patches_applied = []
            if target == 'prod':
                patches_applied = self._restore_and_apply_all_patches(version)

            # 6. Merge archived patches code into ho-prod (common)
            if stage_file:
                patches_merged = self._merge_archived_patches_to_ho_prod(version, stage_file)
            else:
                patches_merged = []

            # 7. Create target release file
            stage_path = self._releases_dir / stage_file if stage_file else None
            target_path = self._releases_dir / target_file

            if stage_file:
                # Rename stage to target (git mv)
                self._repo.hgit.mv(str(stage_path), str(target_path))
            else:
                # Create empty production file (prod only)
                target_path.touch()
                self._repo.hgit.add(str(target_path))

            # 8. Generate schema and metadata (prod only)
            schema_info = {}
            if target == 'prod':
                schema_info = self._generate_schema_and_metadata(version)
                # Add generated files to commit
                self._repo.hgit.add(str(schema_info['schema_file']))
                self._repo.hgit.add(str(schema_info['metadata_file']))
                self._repo.hgit.add(str(self._repo.base_dir / Path("model") / "schema.sql"))

            # 9. Commit promotion
            full_version = version
            if target != 'prod':
                full_version = f"{version}-rc{rc_number}"
                commit_message = f"Promote {version}-stage to {full_version}"
            else:
                commit_message = f"Promote {version}-stage to production release {version}"

            self._repo.hgit.add(str(target_path))
            self._repo.hgit.commit("-m", commit_message)
            commit_sha = self._repo.hgit.last_commit()

            # 10. Push to origin
            self._repo.hgit.push()
            #     Create and push Git tag for new release
            tag_name = f"v{full_version}"
            self._repo.hgit.create_tag(tag_name, f"Release {full_version}")
            self._repo.hgit.push_tag(tag_name)

            # 10.5 Create new empty stage file ONLY for RC promotion
            new_stage_filename = None
            new_stage_commit_sha = None

            if target != 'prod':
                # Pour RC : on peut continuer à travailler sur la même version (rc2, rc3...)
                new_stage_filename = f"{version}-stage.txt"
                new_stage_path = self._releases_dir / new_stage_filename
                new_stage_path.write_text("")

                # Add + commit + push
                self._repo.hgit.add(new_stage_path)
                commit_msg = f"Create new empty stage file for {version}"
                new_stage_commit_sha = self._repo.hgit.commit('-m', commit_msg)
                self._repo.hgit.push()

            # 11. Send rebase notifications to active branches
            if target != 'prod':
                notifications_sent = self._send_rebase_notifications(version, target, rc_number=rc_number)
            else:
                notifications_sent = self._send_rebase_notifications(version, target)

            # 12. Cleanup patch branches
            if stage_file:
                branches_deleted = self._cleanup_patch_branches(version, stage_file)
            else:
                branches_deleted = []

            # Build result dict (common fields)
            result = {
                'status': 'success',
                'version': version,
                'from_file': stage_file,
                'to_file': target_file,
                'patches_merged': patches_merged,
                'branches_deleted': branches_deleted,
                'commit_sha': commit_sha,
                'notifications_sent': notifications_sent,
                'lock_tag': lock_tag,
                'new_stage_created': new_stage_filename,
                'tag_name': tag_name
            }

            # Add target-specific fields
            if target != 'prod':
                result['rc_number'] = rc_number
                result['code_merged'] = True
            else:
                result['source_type'] = source_type
                result['patches_applied'] = patches_applied
                result.update(schema_info)

            return result

        finally:
            # 13. Always release lock (even on error)
            if lock_tag:
                self._repo.hgit.release_branch_lock(lock_tag)


    def _get_next_production_version(self) -> str:
        """
        Get next sequential production version.

        Calculates the next patch version after current production.
        Used by promote-to prod to determine target version.

        Returns:
            str: Next version (e.g., "1.3.5" if current is "1.3.4")

        Raises:
            ReleaseManagerError: If cannot determine production version

        Examples:
            # Current production: 1.3.4
            next_ver = mgr._get_next_production_version()
            # → "1.3.5"
        """
        rc_files = list(self._releases_dir.glob("*-rc*.txt"))

        if rc_files:
            # Use version from RC (without -rcN suffix)
            # There should be only one due to single active RC rule
            rc_file = rc_files[0]
            version = self.parse_version_from_filename(rc_file.name)
            return re.sub('-.*', '', str(version))

        # No RC exists: increment from current production
        # This handles edge case of direct prod promotion without RC
        current_prod = self._get_production_version()
        current_version = self.parse_version_from_filename(f"{current_prod}.txt")
        return self.calculate_next_version(current_version, 'patch')


    def _restore_and_apply_all_patches(self, version: str) -> List[str]:
        """
        Restore database and apply all patches sequentially.

        Used by promote-to prod to prepare database before schema dump.
        Restores DB from current schema.sql, then applies all patches
        from RC files and stage file in order.

        Args:
            version: Target version (e.g., "1.3.5")

        Returns:
            List[str]: Patch IDs applied (in order)

        Examples:
            # Files: 1.3.5-rc1.txt [10], 1.3.5-rc2.txt [42, 12], 1.3.5-stage.txt [18]
            patches = mgr._restore_and_apply_all_patches("1.3.5")
            # → Returns ["10", "42", "12", "18"]
            # → Database now at state with all patches applied
        """
        # 1. Restore database to current production state
        self._repo.restore_database_from_schema()

        # 2. Get all patches for this version (RC1 + RC2 + ... + stage)
        all_patches = self.get_all_release_context_patches()

        # 3. Apply each patch sequentially
        for patch_id in all_patches:
            self._repo.patch_manager.apply_patch_files(patch_id, self._repo.model)

        # 4. Update database version to target production version
        # CRITICAL: Must be done before generating schema dumps
        self._repo.database.register_release(*version.split('.'))

        return all_patches


    def _generate_schema_and_metadata(self, version: str) -> dict:
        """
        Generate schema and metadata dumps, update symlink.

        Generates schema-X.Y.Z.sql and metadata-X.Y.Z.sql files via pg_dump,
        then updates schema.sql symlink to point to new version.

        Args:
            version: Version string (e.g., "1.3.5")

        Returns:
            dict: Generated file paths
                'schema_file': Path to schema-X.Y.Z.sql
                'metadata_file': Path to metadata-X.Y.Z.sql

        Raises:
            Exception: If pg_dump fails or file operations fail

        Examples:
            info = mgr._generate_schema_and_metadata("1.3.5")
            # → Creates model/schema-1.3.5.sql
            # → Creates model/metadata-1.3.5.sql
            # → Updates model/schema.sql → schema-1.3.5.sql
            # → Returns {'schema_file': Path(...), 'metadata_file': Path(...)}
        """
        from half_orm_dev.database import Database

        model_dir = Path(self._repo.base_dir) / "model"

        # Database._generate_schema_sql() creates both schema and metadata
        schema_file = Database._generate_schema_sql(
            self._repo.database,
            version,
            model_dir
        )
        metadata_file = model_dir / f"metadata-{version}.sql"

        return {
            'schema_file': schema_file,
            'metadata_file': metadata_file
        }


    def _detect_stage_to_promote(self) -> Tuple[str, str]:
        """
        Detect smallest stage release to promote.

        Finds all *-stage.txt files, parses versions, and returns the smallest
        version. This ensures sequential promotion (cannot skip versions).

        Algorithm:
        1. List all releases/*-stage.txt files
        2. Parse version from each filename (e.g., "1.3.5-stage.txt" → "1.3.5")
        3. Sort versions in ascending order
        4. Return smallest version and filename

        Returns:
            Tuple of (version, stage_filename)
            Example: ("1.3.5", "1.3.5-stage.txt")

        Raises:
            ReleaseManagerError: If no stage releases found

        Examples:
            # Single stage
            releases/1.3.5-stage.txt exists
            version, filename = mgr._detect_stage_to_promote()
            # → ("1.3.5", "1.3.5-stage.txt")

            # Multiple stages (returns smallest)
            releases/1.3.5-stage.txt, 1.4.0-stage.txt, 2.0.0-stage.txt exist
            version, filename = mgr._detect_stage_to_promote()
            # → ("1.3.5", "1.3.5-stage.txt")

            # No stages
            version, filename = mgr._detect_stage_to_promote()
            # → Raises: "No stage releases found. Create one with prepare-release"
        """
        # List all stage files
        stage_files = list(self._releases_dir.glob("*-stage.txt"))

        if not stage_files:
            raise ReleaseManagerError(
                "No stage releases found. "
                "Create a stage release first with: half_orm dev prepare-release"
            )

        # Parse versions and sort
        stage_versions = []
        for stage_file in stage_files:
            # Extract version from filename (e.g., "1.3.5-stage.txt" → "1.3.5")
            version_str = stage_file.name.replace("-stage.txt", "")
            version = self.parse_version_from_filename(stage_file.name)
            stage_versions.append((version, version_str, stage_file.name))

        # Sort by version (ascending)
        stage_versions.sort(key=lambda x: (x[0].major, x[0].minor, x[0].patch))

        # Return smallest version
        smallest = stage_versions[0]
        return smallest[1], smallest[2]  # (version_str, filename)


    def _validate_single_active_rc(self, stage_version: str) -> None:
        """
        Validate single active RC rule.

        Ensures only one version level is in RC at a time. The rule allows:
        - No RC exists → OK (promoting first RC)
        - RC of SAME version exists → OK (rc1 → rc2 → rc3)
        - RC of DIFFERENT version exists → ERROR (must deploy first)

        Args:
            stage_version: Version being promoted (e.g., "1.3.5")

        Raises:
            ReleaseManagerError: If different version RC exists

        Examples:
            # No RC exists - OK
            stage_version = "1.3.5"
            mgr._validate_single_active_rc(stage_version)
            # → No error

            # Same version RC exists - OK
            releases/1.3.5-rc1.txt exists
            stage_version = "1.3.5"
            mgr._validate_single_active_rc(stage_version)
            # → No error (promoting to rc2)

            # Different version RC exists - ERROR
            releases/1.3.5-rc1.txt exists
            stage_version = "1.4.0"
            mgr._validate_single_active_rc(stage_version)
            # → Raises: "Cannot promote 1.4.0-stage, RC 1.3.5-rc1 must be deployed first"

            # Multiple RCs of same version - OK
            releases/1.3.5-rc1.txt, 1.3.5-rc2.txt exist
            stage_version = "1.3.5"
            mgr._validate_single_active_rc(stage_version)
            # → No error (promoting to rc3)
        """
        # List all RC files
        rc_files = list(self._releases_dir.glob("*-rc*.txt"))

        if not rc_files:
            # No RC exists, promotion allowed
            return

        # Check if any RC is of a different version
        for rc_file in rc_files:
            # Extract version from RC filename (e.g., "1.3.5-rc1.txt" → "1.3.5")
            rc_filename = rc_file.name
            # Remove "-rcN.txt" suffix to get version
            rc_version = rc_filename.split("-rc")[0]

            if rc_version != stage_version:
                # Different version RC exists, block promotion
                raise ReleaseManagerError(
                    f"Cannot promote {stage_version}-stage to RC: "
                    f"RC {rc_filename.replace('.txt', '')} must be deployed to production first. "
                    f"Only one version can be in RC at a time."
                )

        # All RCs are same version as stage, promotion allowed


    def _determine_rc_number(self, version: str) -> int:
        """
        Determine next RC number for version.

        Finds all existing RC files for the version and returns next number.
        If no RCs exist, returns 1. If rc1, rc2 exist, returns 3.

        Args:
            version: Version string (e.g., "1.3.5")

        Returns:
            Next RC number (1, 2, 3, etc.)

        Examples:
            # No existing RCs
            version = "1.3.5"
            rc_num = mgr._determine_rc_number(version)
            # → 1

            # rc1 exists
            releases/1.3.5-rc1.txt exists
            rc_num = mgr._determine_rc_number(version)
            # → 2

            # rc1, rc2, rc3 exist
            releases/1.3.5-rc1.txt, 1.3.5-rc2.txt, 1.3.5-rc3.txt exist
            rc_num = mgr._determine_rc_number(version)
            # → 4

        Note:
            Uses get_rc_files() which returns sorted RC files for version.
        """
        # Use existing get_rc_files() method which returns sorted list
        rc_files = self.get_rc_files(version)

        if not rc_files:
            # No RCs exist, this will be rc1
            return 1

        # get_rc_files() returns sorted list, so last file has highest number
        # Extract RC number from last filename (e.g., "1.3.5-rc3.txt" → 3)
        last_rc_file = rc_files[-1].name

        # Extract number after "-rc" (e.g., "1.3.5-rc3.txt" → "3")
        match = re.search(r'-rc(\d+)\.txt', last_rc_file)
        if match:
            last_rc_num = int(match.group(1))
            return last_rc_num + 1

        # Fallback (shouldn't happen with valid RC files)
        return len(rc_files) + 1


    def _merge_archived_patches_to_ho_prod(self, version: str, stage_file: str) -> List[str]:
        """
        Merge all archived patch branches code into ho-prod.

        THIS IS WHERE CODE ENTERS HO-PROD. During add-to-release, patches
        are archived to ho-release/X.Y.Z/patch-id but code stays separate.
        At promote_to, all archived patches are merged into ho-prod.

        Algorithm:
        1. Read patch list from stage file (e.g., releases/1.3.5-stage.txt)
        2. For each patch in list:
           - Check if archived branch exists: ho-release/{version}/{patch_id}
           - If exists: git merge ho-release/{version}/{patch_id}
           - Handle merge conflicts (abort and raise error)
        3. Return list of merged patches

        Args:
            version: Version string (e.g., "1.3.5")
            stage_file: Stage filename (e.g., "1.3.5-stage.txt")

        Returns:
            List of merged patch IDs

        Raises:
            ReleaseManagerError: If merge conflicts occur or branch not found

        Examples:
            # Successful merge
            releases/1.3.5-stage.txt contains: ["456-user-auth", "789-security"]
            ho-release/1.3.5/456-user-auth exists
            ho-release/1.3.5/789-security exists

            patches = mgr._merge_archived_patches_to_ho_prod("1.3.5", "1.3.5-stage.txt")
            # → ["456-user-auth", "789-security"]
            # → Both branches merged into ho-prod
            # → Code now in ho-prod

            # Merge conflict
            Patch code conflicts with existing ho-prod code
            patches = mgr._merge_archived_patches_to_ho_prod("1.3.5", "1.3.5-stage.txt")
            # → Raises: "Merge conflict with patch 456-user-auth, resolve manually"

            # Missing archived branch
            releases/1.3.5-stage.txt contains: ["456-user-auth"]
            ho-release/1.3.5/456-user-auth does NOT exist

            patches = mgr._merge_archived_patches_to_ho_prod("1.3.5", "1.3.5-stage.txt")
            # → Raises: "Archived branch not found: ho-release/1.3.5/456-user-auth"

        Note:
            After this operation, ho-prod contains both metadata (releases/*.txt)
            and code (merged from ho-release/X.Y.Z/*). This is the key difference
            between stage (metadata only) and RC (metadata + code).
        """
        # Read patch list from stage file using existing method
        patch_ids = self.read_release_patches(stage_file)

        if not patch_ids:
            # Empty stage file, no patches to merge
            return []

        merged_patches = []

        for patch_id in patch_ids:
            # Construct archived branch name
            archived_branch = f"ho-release/{version}/{patch_id}"

            # Check if archived branch exists
            if not self._repo.hgit.branch_exists(archived_branch):
                raise ReleaseManagerError(
                    f"Archived branch not found: {archived_branch}. "
                    f"Patch {patch_id} was not properly archived during add-to-release."
                )

            # Merge archived branch into ho-prod with no-ff
            try:
                self._repo.hgit.merge(
                    archived_branch,
                    no_ff=True,
                    m=f"Integrate patch {patch_id}")

                merged_patches.append(patch_id)

            except GitCommandError as e:
                raise ReleaseManagerError(
                    f"Merge conflict with patch {patch_id} from {archived_branch}. "
                    f"Resolve conflicts manually and retry. Git error: {e}"
                )

        return merged_patches


    def _cleanup_patch_branches(self, version: str, stage_file: str) -> List[str]:
        """
        Delete all patch branches listed in stage file.

        Reads patch list from stage file and deletes both local and remote
        branches. This is automatic cleanup at promote_to to maintain
        clean repository state. Branches are ho-patch/* format.

        Algorithm:
        1. Read patch list from stage file
        2. For each patch:
           - Check if ho-patch/{patch_id} exists locally
           - If exists: git branch -D ho-patch/{patch_id}
           - Check if exists on remote
           - If exists: git push origin --delete ho-patch/{patch_id}
        3. Return list of deleted branches

        Args:
            version: Version string (e.g., "1.3.5")
            stage_file: Stage filename (e.g., "1.3.5-stage.txt")

        Returns:
            List of deleted branch names (e.g., ["ho-patch/456-user-auth", ...])

        Raises:
            ReleaseManagerError: If branch deletion fails (e.g., uncommitted changes)

        Examples:
            # Successful cleanup
            releases/1.3.5-stage.txt contains: ["456-user-auth", "789-security"]
            ho-patch/456-user-auth exists locally and remotely
            ho-patch/789-security exists locally and remotely

            deleted = mgr._cleanup_patch_branches("1.3.5", "1.3.5-stage.txt")
            # → ["ho-patch/456-user-auth", "ho-patch/789-security"]
            # → Both branches deleted locally and remotely

            # Branch already deleted
            releases/1.3.5-stage.txt contains: ["456-user-auth"]
            ho-patch/456-user-auth does NOT exist

            deleted = mgr._cleanup_patch_branches("1.3.5", "1.3.5-stage.txt")
            # → [] (nothing to delete, no error)

            # Branch with uncommitted changes (should not happen)
            ho-patch/456-user-auth has uncommitted changes

            deleted = mgr._cleanup_patch_branches("1.3.5", "1.3.5-stage.txt")
            # → Raises: "Cannot delete ho-patch/456-user-auth: uncommitted changes"

        Note:
            This is called AFTER merging archived branches to ho-prod, so the
            code is preserved in ho-prod even though branches are deleted.
        """
        patch_ids = self.read_release_patches(stage_file)

        if not patch_ids:
            # Empty stage file, no branches to cleanup
            return []

        deleted_branches = []

        for patch_id in patch_ids:
            # Construct branch name
            branch_name = f"ho-patch/{patch_id}"

            # Delete local branch (force delete with -D)
            try:
                self._repo.hgit.delete_branch(branch_name, force=True)
            except GitCommandError as e:
                # Best effort: continue even if deletion fails
                # (branch might already be deleted)
                pass

            # Delete remote branch
            try:
                self._repo.hgit.delete_remote_branch(branch_name)
            except GitCommandError as e:
                # Best effort: continue even if deletion fails
                # (branch might already be deleted from remote)
                pass

            # Add to deleted list (best effort reporting)
            deleted_branches.append(branch_name)

        return deleted_branches

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
        from half_orm_dev.release_manager import ReleaseManagerError

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
        from half_orm_dev.release_manager import ReleaseManagerError

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
        from half_orm_dev.release_manager import ReleaseManagerError

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
        from half_orm_dev.release_manager import ReleaseManagerError

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
