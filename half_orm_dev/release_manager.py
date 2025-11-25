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
from half_orm_dev.decorators import with_ho_prod_lock

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
        0. Acquire lock tag
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
        11. Release lock tag

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
        try:
            # 0. ACQUIRE LOCK on ho-prod (with 30 min timeout for stale locks)
            lock_tag = self._repo.hgit.acquire_branch_lock("ho-prod", timeout_minutes=30)

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

        finally:
            # 11. ALWAYS release lock (even on error)
            self._repo.hgit.release_branch_lock(lock_tag)


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

    def _apply_release_patches(self, version: str) -> None:
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
        rc_files = self.get_rc_files(version)
        for rc_file in rc_files:
            rc_patches = self.read_release_patches(rc_file.name)
            for patch_id in rc_patches:
                self._repo.patch_manager.apply_patch_files(patch_id, self._repo.model)

        # Apply stage patches
        stage_patches = self.read_release_patches(f"{version}-stage.txt")
        for patch_id in stage_patches:
            self._repo.patch_manager.apply_patch_files(patch_id, self._repo.model)

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
        2. Pre-lock check: detect stage file and verify patch not already in release (local state, fail-fast)
        3. **ACQUIRE LOCK on ho-prod** (prevents concurrent modifications)
        4. Fetch from origin (get latest state)
        5. Sync with origin/ho-prod (pull if behind)
        6. Re-detect target stage file (may have changed after sync)
        7. Re-check patch not already in release (may have changed after sync)
        8. Ensure patch branch synced with ho-prod
        9. Create temporary validation branch FROM ho-prod
        10. Merge ALL patches already in release (from ho-release/X.Y.Z/* branches)
        11. Merge new patch branch (from ho-patch/{patch_id})
        12. Add patch to stage file on temp branch + commit
        13. Run validation tests (with ALL patches integrated)
        14. If tests fail: cleanup temp branch, release lock, exit with error
        15. If tests pass: return to ho-prod, delete temp branch
        16. Add patch to stage file on ho-prod + commit (file change only)
        17. Push ho-prod to origin
        18. Archive patch branch to ho-release/{version}/{patch_id}
        19. **RELEASE LOCK** (in finally block, always executed)

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

        # 2. Pre-lock validations on local state (fail-fast before acquiring lock)
        target_version, stage_file = self._detect_target_stage_file(to_version)
        existing_patches = self.read_release_patches(stage_file)
        if patch_id in existing_patches:
            raise ReleaseManagerError(
                f"Patch {patch_id} already in release {target_version}-stage.\n"
                f"Nothing to do."
            )

        # 3. ACQUIRE LOCK on ho-prod (with 30 min timeout for stale locks)
        lock_tag = self._repo.hgit.acquire_branch_lock("ho-prod", timeout_minutes=30)

        try:
            # 4. Fetch from origin to get latest state
            self._repo.hgit.fetch_from_origin()

            # 5. Sync with origin/ho-prod
            is_synced, sync_status = self._repo.hgit.is_branch_synced("ho-prod")
            if not is_synced:
                if sync_status == "behind":
                    self._repo.hgit.pull()
                elif sync_status == "diverged":
                    raise ReleaseManagerError(
                        "ho-prod has diverged from origin/ho-prod.\n"
                        "Manual resolution required:\n"
                        "  git pull --rebase origin ho-prod\n"
                        "  or\n"
                        "  git merge origin/ho-prod"
                    )

            # 6. Re-detect target stage file (may have changed after sync)
            target_version, stage_file = self._detect_target_stage_file(to_version)

            # 7. Re-check patch not already in release (may have changed after sync)
            existing_patches = self.read_release_patches(stage_file)
            if patch_id in existing_patches:
                raise ReleaseManagerError(
                    f"Patch {patch_id} already in release {target_version}-stage.\n"
                    f"Nothing to do."
                )

            # 8. Ensure patch branch is synced with ho-prod
            sync_result = self._ensure_patch_branch_synced(patch_id)

            if sync_result['strategy'] != 'already-synced':
                # Log successful auto-sync
                import sys
                print(
                    f"✓ Auto-synced {sync_result['branch_name']} with ho-prod "
                    f"({sync_result['strategy']})",
                    file=sys.stderr
                )

            temp_branch = f"temp-valid-{target_version}"

            # 9. Create temporary validation branch FROM ho-prod
            self._repo.hgit.checkout("-b", temp_branch)

            # 10. Merge ALL existing patches in the release (already validated)
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

    @with_ho_prod_lock()
    def new_release(self, level: str) -> dict:
        """
        Create a new release with integration branch.

        Creates a release branch (ho-release/{version}) where patches will be
        merged. This allows patches to see each other's changes and supports
        dependencies between patches.

        Workflow:
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
        # Calculate next version
        version = self._calculate_next_version(level)
        release_branch = f"ho-release/{version}"

        # Ensure we're on ho-prod
        try:
            self._repo.hgit.checkout("ho-prod")
        except Exception as e:
            raise ReleaseManagerError(f"Failed to checkout ho-prod: {e}")

        # Create empty candidates file (NEW)
        candidates_file = self._releases_dir / f"{version}-candidates.txt"
        try:
            candidates_file.write_text("", encoding='utf-8')
        except Exception as e:
            raise ReleaseManagerError(f"Failed to create candidates file: {e}")

        # Create empty stage file
        stage_file = self._releases_dir / f"{version}-stage.txt"
        try:
            stage_file.write_text("", encoding='utf-8')
        except Exception as e:
            raise ReleaseManagerError(f"Failed to create stage file: {e}")

        # Commit both files on ho-prod
        try:
            self._repo.hgit.add(str(candidates_file))
            self._repo.hgit.add(str(stage_file))
            self._repo.hgit.commit("-m", f"[HOP] Create release %{version} branch and release files")
            self._repo.hgit.push_branch("ho-prod")
        except Exception as e:
            raise ReleaseManagerError(f"Failed to commit release files: {e}")

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
            'stage_file': str(stage_file)
        }

    @with_ho_prod_lock()
    def add_patch_to_release(self, patch_id: str, version: str) -> dict:
        """
        Add a patch to a release by merging into the release branch.

        This is the key method of the new workflow. It:
        1. Merges the patch into ho-release/{version} branch
        2. Updates {version}-stage.txt with the patch
        3. Delete ho-patch/{patch_id}

        This ensures patches in the same release can see each other's changes.

        Args:
            patch_id: Patch identifier (e.g., "001-first")
            version: Target release version (e.g., "0.1.0")

        Returns:
            dict with keys:
                - patch_id: The patch identifier
                - archived_branch: The archived branch name
                - merged: Whether merge succeeded

        Raises:
            ReleaseManagerError: If release doesn't exist or patch merge fails
            GitCommandError: If merge has conflicts (stays on release branch)

        Examples:
            # After creating release 0.1.0
            rel_mgr.add_patch_to_release("001-first", "0.1.0")
            # → Merges into ho-release/0.1.0
            # → Adds "001-first" to 0.1.0-stage.txt
            # → Delete ho-patch/001-first
        """
        # Save current branch to return to it later
        original_branch = self._repo.hgit.branch

        # Ensure we're on ho-prod to access stage file
        self._repo.hgit.checkout("ho-prod")

        # Validate release exists (stage file must be on ho-prod)
        stage_file = self._releases_dir / f"{version}-stage.txt"
        if not stage_file.exists():
            raise ReleaseManagerError(f"Release {version} not found (no stage file)")

        # Validate patch branch exists
        patch_branch = f"ho-patch/{patch_id}"
        if not self._repo.hgit.branch_exists(patch_branch):
            raise ReleaseManagerError(f"Patch branch {patch_branch} not found")

        release_branch = f"ho-release/{version}"
        patch_branch = f"ho-patch/{patch_id}"

        try:

            # 3. Checkout release branch
            self._repo.hgit.checkout(release_branch)

            # 4. Merge archived patch branch (--no-ff for merge commit)
            try:
                self._repo.hgit.merge(
                    patch_branch,
                    no_ff=True,
                    message=f"[HOP] Merge patch #{patch_id} into release %{version}"
                )
            except Exception as e:
                # Merge conflict - stay on release branch for resolution
                raise ReleaseManagerError(
                    f"Merge conflict when integrating {patch_id} into {version}.\n"
                    f"Please resolve conflicts on branch {release_branch}, then:\n"
                    f"  git add <resolved files>\n"
                    f"  git commit\n"
                    f"  git push origin {release_branch}\n"
                    f"  # Then re-run this command or manually update stage file"
                )

            # 5. Push release branch with merge
            self._repo.hgit.push_branch(release_branch)

            # 6. Add patch to stage file
            current_content = stage_file.read_text(encoding='utf-8')
            if patch_id not in current_content.split('\n'):
                with stage_file.open('a', encoding='utf-8') as f:
                    f.write(f"{patch_id}\n")

            # 7. Commit stage file update (on ho-prod)
            self._repo.hgit.checkout("ho-prod")
            self._repo.hgit.add(str(stage_file))
            self._repo.hgit.commit("-m", f"[HOP] Add patch #{patch_id} to release %{version} stage. Closes #{patch_id}")
            self._repo.hgit.push_branch("ho-prod")

            # 1. Delete patch branch
            self._repo.hgit.delete_branch(patch_branch, force=True)

            # 8. Return to original branch
            self._repo.hgit.checkout(original_branch)

            return {
                'patch_id': patch_id,
                'merged': True,
                'stage_file': stage_file                
            }

        except ReleaseManagerError:
            # Re-raise our own errors as-is
            raise
        except Exception as e:
            # Try to return to original branch on error
            try:
                self._repo.hgit.checkout(original_branch)
            except Exception:
                pass
            raise ReleaseManagerError(f"Failed to add patch to release: {e}")

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
        # Find stage files
        stage_files = list(self._releases_dir.glob("*-stage.txt"))
        if not stage_files:
            raise ReleaseManagerError(
                "No stage release found. "
                "Create a stage release first with: half_orm dev release new"
            )

        # Sort by version to get the smallest (oldest) one first
        def version_key(path):
            version_str = path.stem.replace('-stage', '')
            parts = version_str.split('.')
            try:
                return (int(parts[0]), int(parts[1]), int(parts[2]))
            except (ValueError, IndexError):
                return (0, 0, 0)

        stage_files.sort(key=version_key)
        return stage_files[0].stem.replace('-stage', '')

    @with_ho_prod_lock()
    def promote_to_rc(self, version: str = None) -> dict:
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
            rel_mgr.promote_to_rc("0.1.0")
            # → Creates tag "0.1.0-rcN" on ho-release/0.1.0
            # → Renames 0.1.0-stage.txt to 0.1.0-rcN.txt

            rel_mgr.promote_to_rc()  # Auto-detect version
            # → Promotes the smallest stage release
        """
        # Auto-detect version if not provided
        if version is None:
            version = self._detect_version_to_promote('rc')

        stage_file = self._releases_dir / f"{version}-stage.txt"
        if not stage_file.exists():
            raise ReleaseManagerError(f"Release {version} not found (no stage file)")

        release_branch = f"ho-release/{version}"
        rc_number = self._determine_rc_number(version)
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

            # Rename stage file to rc file
            rc_file = self._releases_dir / f"{version}-rc{rc_number}.txt"
            stage_file.rename(rc_file)
            try:
                stage_file.write_text("", encoding='utf-8')
            except Exception as e:
                raise ReleaseManagerError(f"Failed to create stage file: {e}")

            # Commit rename on release branch
            self._repo.hgit.add(str(stage_file))  # Old path (deleted)
            self._repo.hgit.add(str(rc_file))     # New path
            self._repo.hgit.commit("-m", f"[HOP] Promote release %{version} to RC {rc_number}")
            self._repo.hgit.push_branch(release_branch)

            return {
                'version': version,
                'tag': rc_tag,
                'branch': release_branch
            }

        except Exception as e:
            raise ReleaseManagerError(f"Failed to promote to RC: {e}")

    @with_ho_prod_lock()
    def promote_to_prod(self, version: str = None) -> dict:
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
            rel_mgr.promote_to_prod("0.1.0")
            # → Merges ho-release/0.1.0 into ho-prod
            # → Creates tag "0.1.0"
            # → Deletes candidates.txt, renames stage.txt to 0.1.0.txt
            # → Keeps RC files (0.1.0-rc1.txt, etc.) for history

            rel_mgr.promote_to_prod()  # Auto-detect version
            # → Promotes the smallest RC release
        """
        # Auto-detect version if not provided
        if version is None:
            version = self._detect_version_to_promote('prod')

        stage_file = self._releases_dir / f"{version}-stage.txt"
        if not stage_file.exists():
            raise ReleaseManagerError(f"RC release {version} not found")

        # Verify that candidates.txt is empty before promoting to production
        candidates_file = self._releases_dir / f"{version}-candidates.txt"
        if candidates_file.exists():
            candidates_content = candidates_file.read_text(encoding='utf-8').strip()
            if candidates_content:
                candidates = [c.strip() for c in candidates_content.split('\n') if c.strip()]
                raise ReleaseManagerError(
                    f"Cannot promote {version} to production: {len(candidates)} candidate patch(es) remain:\n"
                    f"  • " + "\n  • ".join(candidates) + "\n\n"
                    f"Actions required:\n"
                    f"  1. Close patches: half_orm dev patch close <patch_id>\n"
                    f"  2. OR delete branches: git branch -D ho-patch/<patch_id>\n"
                    f"  3. OR move to another release (edit candidates file manually)"
                )

        release_branch = f"ho-release/{version}"

        try:
            # Read patches from rc file
            patches = stage_file.read_text(encoding='utf-8').strip().split('\n')
            patches = [p.strip() for p in patches if p.strip()]

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

            # 3. Apply patches and generate schema
            self._apply_release_patches(version)

            # Generate schema dump for this version
            from pathlib import Path
            model_dir = Path(self._repo.base_dir) / "model"
            self._repo.database._generate_schema_sql(version, model_dir)

            # 3.5. Commit schema files
            self._repo.hgit.add(str(model_dir / f"schema-{version}.sql"))
            self._repo.hgit.add(str(model_dir / f"metadata-{version}.sql"))
            self._repo.hgit.add(str(model_dir / "schema.sql"))  # symlink

            # 4. Rename stage file to prod and delete candidates
            prod_file = self._releases_dir / f"{version}.txt"
            candidates_file = self._releases_dir / f"{version}-candidates.txt"

            stage_file.rename(prod_file)
            self._repo.hgit.add(str(stage_file))   # Old path (deleted)
            self._repo.hgit.add(str(prod_file))    # New path (created)

            # Delete candidates file if it exists
            if candidates_file.exists():
                candidates_file.unlink()
                self._repo.hgit.add(str(candidates_file))  # Mark as deleted

            self._repo.hgit.commit("-m", f"[HOP] Promote release %{version} to production")
            self._repo.hgit.push_branch("ho-prod")

            # 4. Create production tag on ho-prod
            prod_tag = f"v{version}"  # Use v prefix to match existing convention
            self._repo.hgit.create_tag(prod_tag, f"Production release %{version}")
            self._repo.hgit.push_tag(prod_tag)

            # 5. Push ho-prod
            self._repo.hgit.push_branch("ho-prod")

            deleted_branches = []

            # 7. Delete release branch (force=True because Git may not recognize the merge)
            try:
                self._repo.hgit.delete_branch(release_branch, force=True)
                self._repo.hgit.delete_remote_branch(release_branch)
                deleted_branches.append(release_branch)
            except Exception as e:
                # Log error for debugging
                import sys
                print(f"Warning: Failed to delete release branch {release_branch}: {e}", file=sys.stderr)

            return {
                'version': version,
                'tag': f"v{version}",
                'deleted_branches': deleted_branches
            }

        except ReleaseManagerError:
            raise
        except Exception as e:
            raise ReleaseManagerError(f"Failed to promote to production: {e}")

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