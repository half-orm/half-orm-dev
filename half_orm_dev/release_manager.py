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
            None: 4,           # Production
            'rc': 3,           # Release candidate
            'stage': 2,        # Development stage
            'hotfix': 1        # Hotfix
        }
        
        # Extract stage type (rc1 → rc, hotfix2 → hotfix)
        self_stage_type = self._get_stage_type()
        other_stage_type = other._get_stage_type()
        
        return stage_priority.get(self_stage_type, 0) < stage_priority.get(other_stage_type, 0)
    
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
        5. Find latest version across all stages
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
                - previous_version: Previous latest version
        
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
            # Latest was 1.3.5 → creates releases/1.4.0-stage.txt
            
            # Prepare patch release
            result = release_mgr.prepare_release('patch')
            # Latest was 1.3.5-rc2 → creates releases/1.3.6-stage.txt
            
            # Error handling
            try:
                result = release_mgr.prepare_release('major')
            except ReleaseManagerError as e:
                print(f"Failed: {e}")
        """
        pass  # Implementation in next phase
    
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
        pass  # Implementation in next phase
    
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
        pass  # Implementation in next phase
    
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
        pass  # Implementation in next phase
