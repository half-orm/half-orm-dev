"Provides the HGit class"

import os
import sys
import subprocess
import git
from git.exc import GitCommandError
from datetime import datetime

from half_orm import utils
from half_orm_dev.manifest import Manifest

class HGit:
    "Manages the git operations on the repo."
    def __init__(self, repo=None):
        self.__origin = None
        self.__repo = repo
        self.__base_dir = None
        self.__git_repo: git.Repo = None
        if repo:
            self.__origin = repo.git_origin
            self.__base_dir = repo.base_dir
            self.__post_init()

    def __post_init(self):
        self.__git_repo = git.Repo(self.__base_dir)
        origin = None
        try:
            origin = self.__git_repo.git.remote('get-url', 'origin')
        except Exception as err:
            utils.warning(utils.Color.red(f"No origin\n{err}\n"))
        if self.__origin == '' and origin:
            self.__repo.git_origin = origin
            self.add(os.path.join('.hop', 'config'))
            self.commit("-m", f"[hop] Set remote for origin: {origin}.")
            self.__git_repo.git.push('-u', 'origin', 'hop_main')
            self.__origin = origin
        elif origin and self.__origin != origin:
            utils.error(f'Git remote origin should be {self.__origin}. Got {origin}\n', 1)
        self.__current_branch = self.branch

    def __str__(self):
        res = ['[Git]']
        res.append(f'- origin: {self.__origin or utils.Color.red("No origin")}')
        res.append(f'- current branch: {self.__current_branch}')
        clean = self.repos_is_clean()
        clean = utils.Color.green(clean) \
            if clean else utils.Color.red(clean)
        res.append(f'- repo is clean: {clean}')
        res.append(f'- last commit: {self.last_commit()}')
        return '\n'.join(res)

    def init(self, base_dir, release='0.0.0'):
        "Initiazes the git repo."
        cur_dir = os.path.abspath(os.path.curdir)
        self.__base_dir = base_dir
        try:
            git.Repo.init(base_dir)
            self.__git_repo = git.Repo(base_dir)
            os.chdir(base_dir)
            self.__git_repo.git.add('.')
            self.__git_repo.git.commit(m=f'[{release}] hop new {os.path.basename(base_dir)}')
            self.__git_repo.git.checkout('-b', 'hop_main')
            os.chdir(cur_dir)
            self.__post_init()
        except GitCommandError as err:
            utils.error(
                f'Something went wrong initializing git repo in {base_dir}\n{err}\n', exit_code=1)
        return self

    @property
    def branch(self):
        "Returns the active branch"
        return str(self.__git_repo.active_branch)

    @property
    def current_release(self):
        "Returns the current branch name without 'hop_'"
        return self.branch.replace('hop_', '')

    @property
    def is_hop_patch_branch(self):
        "Returns True if we are on a hop patch branch hop_X.Y.Z."
        try:
            major, minor, patch = self.current_release.split('.')
            return bool(1 + int(major) + int(minor) + int(patch))
        except ValueError:
            return False

    def repos_is_clean(self):
        "Returns True if the git repository is clean, False otherwise."
        return not self.__git_repo.is_dirty(untracked_files=True)

    def last_commit(self):
        """Returns the last commit
        """
        commit = str(list(self.__git_repo.iter_commits(self.branch, max_count=1))[0])[0:8]
        assert self.__git_repo.head.commit.hexsha[0:8] == commit
        return commit

    def branch_exists(self, branch):
        "Returns True if branch is in branches"
        return branch in self.__git_repo.heads

    def set_branch(self, release_s, message=None):
        """
        Creates a new version branch with patch directory structure.
        
        This method:
        1. Creates the version branch
        2. Creates the patch directory structure
        3. Adds a placeholder/message file
        4. Updates changelog
        5. Commits everything
        6. Pushes for version reservation
        
        Args:
            release_s (str): Version string (e.g., "1.2.3")
            message (str, optional): Commit message for the release
        """
        rel_branch = f"hop_{release_s}"
        
        if not self.check_version_conflict(release_s):
            # Create branch
            self.__git_repo.create_head(rel_branch)
            self.__git_repo.heads[rel_branch].checkout()
            
            # Parse version for patch directory structure
            version_parts = release_s.split('.')
            if len(version_parts) != 3:
                utils.error(f"Invalid version format: {release_s}. Expected X.Y.Z")
                return False
            
            major, minor, patch = version_parts
            
            # Create patch directory structure
            patch_dir = os.path.join(
                self.__repo.base_dir, 
                'Patches', 
                major, 
                minor, 
                patch
            )
            os.makedirs(patch_dir, exist_ok=True)
            
            # Create placeholder file so directory gets committed
            placeholder_file = os.path.join(patch_dir, 'README.md')
            with open(placeholder_file, 'w', encoding='utf-8') as f:
                f.write(f"""# Patch {release_s}

{message or 'Patch preparation'}

## Instructions
1. Add your SQL migration files to this directory
2. Files are applied in alphabetical order
3. Use naming convention: 01_description.sql, 02_another.sql, etc.

## Example
```sql
-- 01_add_user_table.sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
```
""")
            
            # Update changelog (Git-centric version)
            self.cherry_pick_changelog(release_s)
            
            # Commit everything (patch directory + changelog)
            self.__git_repo.git.add('--all')
            self.__git_repo.git.commit('-m', f'[hop][{release_s}] {message or "Prepare patch"}')
            
            print(f'✅ Created patch structure: {patch_dir}')
            
            # Immediate push for version reservation (if remote exists)
            if self.__repo.git_origin:
                self.immediate_branch_push(rel_branch)
                print(f'NEW branch {rel_branch} - pushed to origin for version reservation')
            else:
                utils.warning("No remote origin configured - branch created locally only")
                print(f'NEW branch {rel_branch} - created locally (no remote push)')
        
        elif str(self.branch) == rel_branch:
            print(f'On branch {rel_branch}')
        
        else:
            utils.error(f"Version {release_s} already exists")
            return False
        
        return True

    def cherry_pick_changelog(self, release_s):
        """
        Updates changelog for Git-centric workflow.
        
        Adds minimal entry without SHA (Git branches are source of truth).
        """
        changelog_file = self.__repo.changelog.file
        
        # Read current changelog
        with open(changelog_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Add entry for this version
        new_entry = f"""
## [{release_s}] - {datetime.now().strftime('%Y-%m-%d')} - In Development
- Branch: hop_{release_s}
- Patch directory: Patches/{release_s.replace('.', '/')}
- Status: Ready for SQL patches

"""
        
        # Insert after the first line (usually "# Changelog")
        lines = content.split('\n')
        if len(lines) > 0:
            # Find insertion point (after header)
            insert_pos = 1
            for i, line in enumerate(lines[1:], 1):
                if line.strip() and not line.startswith('#'):
                    insert_pos = i
                    break
            
            lines.insert(insert_pos, new_entry.strip())
            
            # Write back
            with open(changelog_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            
            print(f"✅ Updated CHANGELOG for {release_s}")
        
        # No automatic commit - let set_branch handle it

    def rebase_devel_branches(self, release_s):
        "Rebase all hop_x.y.z branches in devel different from release_s on hop_main:HEAD"
        for release in self.__repo.changelog.releases_in_dev:
            if release != release_s:
                self.__git_repo.git.checkout(f'hop_{release}')
                self.__git_repo.git.rebase('hop_main')

    def check_rebase_hop_main(self, current_branch):
        git = self.__git_repo.git
        try:
            git.branch("-D", "hop_temp")
        except GitCommandError:
            pass
        for release in self.__repo.changelog.releases_in_dev:
            git.checkout(f'hop_{release}')
            git.checkout("HEAD", b="hop_temp")
            try:
                git.rebase('hop_main')
            except GitCommandError as exc:
                git.rebase('--abort')
                git.checkout(current_branch)
                utils.error(f"Can't rebase {release} on hop_main.\n{exc}\n", exit_code=1)
            git.checkout(current_branch)
            git.branch("-D", "hop_temp")

    def rebase_to_hop_main(self, push=False):
        "Rebase a hop_X.Y.Z branch to hop_main with Git-centric enhancements"
        release = self.current_release
        if push and not self.__repo.git_origin:
            utils.error("Git: No remote specified for \"origin\". Can't push!\n", 1)
        try:
            if self.__origin:
                self.__git_repo.git.pull('origin', 'hop_main')
            hop_main_last_commit = self.__git_repo.commit('hop_main').hexsha[0:8]
            self.__git_repo.git.rebase('hop_main')
            self.__git_repo.git.checkout('hop_main')
            self.__git_repo.git.rebase(f'hop_{release}')
            self.__repo.changelog.update_release(
                self.__repo.database.last_release_s,
                self.__repo.hgit.last_commit(),
                hop_main_last_commit)
            patch_dir = os.path.join(self.__base_dir, 'Patches', *release.split('.'))
            manifest = Manifest(patch_dir)
            message = f'[{release}] {manifest.changelog_msg}'
            self.__git_repo.git.commit('-m', message)
            self.__git_repo.git.tag(release, '-m', release)
            
            # NEW: Create maintenance branch for minor/major releases
            parts = release.split('.')
            if len(parts) >= 3 and parts[2] == '0':  # X.Y.0 release
                self.create_maintenance_branch(release)
            
            self.cherry_pick_changelog(release)
            if push:
                self.__git_repo.git.push()
                self.__git_repo.git.push('-uf', 'origin', release)
        except GitCommandError as err:
            utils.error(f'Something went wrong rebasing hop_main\n{err}\n', exit_code=1)

    def add(self, *args, **kwargs):
        "Proxy to git.add method"
        return self.__git_repo.git.add(*args, **kwargs)

    def commit(self, *args, **kwargs):
        "Proxy to git.commit method"
        return self.__git_repo.git.commit(*args, **kwargs)

    def rebase(self, *args, **kwargs):
        "Proxy to git.commit method"
        return self.__git_repo.git.rebase(*args, **kwargs)

    def checkout_to_hop_main(self):
        "Checkout to hop_main branch"
        self.__git_repo.git.checkout('hop_main')

    # ============================================================================
    # NEW GIT-CENTRIC WORKFLOW METHODS (Test-Driven Implementation)
    # ============================================================================

    def get_hop_branches(self):
        """Returns all HOP branches (local + remote)
        
        Returns:
            set: Set of branch names that follow HOP convention (hop_main, hop_X.Y.Z, hop_X.Y.x)
        """
        hop_branches = set()
        
        # Get local HOP branches
        for head in self.__git_repo.heads:
            branch_name = head.name
            if self._is_hop_branch(branch_name):
                hop_branches.add(branch_name)
        
        # Get remote HOP branches
        try:
            for remote in self.__git_repo.remotes:
                for ref in remote.refs:
                    # Remote refs are like 'origin/hop_main', extract the branch name
                    branch_name = ref.name.split('/')[-1]
                    if self._is_hop_branch(branch_name):
                        hop_branches.add(branch_name)
        except Exception:
            # If no remotes or other issues, just continue with local branches
            pass
        
        return hop_branches

    def get_development_branches(self):
        """Returns development branches (hop_X.Y.Z)
        
        Development branches follow the pattern hop_X.Y.Z where X, Y, Z are integers.
        These branches are used for developing specific versions.
        
        Returns:
            set: Set of development branch names
        """
        hop_branches = self.get_hop_branches()
        development_branches = set()
        
        for branch in hop_branches:
            if self._is_development_branch(branch):
                development_branches.add(branch)
        
        return development_branches

    def get_maintenance_branches(self):
        """Returns maintenance branches (hop_X.Y.x)
        
        Maintenance branches follow the pattern hop_X.Y.x where X, Y are integers.
        These branches are used for maintaining specific major.minor version lines.
        
        Returns:
            set: Set of maintenance branch names
        """
        hop_branches = self.get_hop_branches()
        maintenance_branches = set()
        
        for branch in hop_branches:
            if self._is_maintenance_branch(branch):
                maintenance_branches.add(branch)
        
        return maintenance_branches

    def _is_hop_branch(self, branch_name):
        """Check if a branch name follows HOP conventions
        
        Args:
            branch_name (str): Branch name to check
            
        Returns:
            bool: True if it's a HOP branch (hop_main, hop_X.Y.Z, hop_X.Y.x)
        """
        if branch_name == 'hop_main':
            return True
        
        return self._is_development_branch(branch_name) or self._is_maintenance_branch(branch_name)

    def _is_development_branch(self, branch_name):
        """Check if a branch is a development branch (hop_X.Y.Z)
        
        Args:
            branch_name (str): Branch name to check
            
        Returns:
            bool: True if it's a development branch
        """
        if not branch_name.startswith('hop_'):
            return False
        
        # Extract version part after 'hop_'
        version_part = branch_name[4:]  # Remove 'hop_' prefix
        
        # Check for development branch pattern (X.Y.Z)
        parts = version_part.split('.')
        if len(parts) == 3:
            try:
                int(parts[0])  # major
                int(parts[1])  # minor  
                int(parts[2])  # patch
                return True
            except ValueError:
                pass
        
        return False

    def _is_maintenance_branch(self, branch_name):
        """Check if a branch is a maintenance branch (hop_X.Y.x)
        
        Args:
            branch_name (str): Branch name to check
            
        Returns:
            bool: True if it's a maintenance branch
        """
        if not branch_name.startswith('hop_'):
            return False
        
        # Extract version part after 'hop_'
        version_part = branch_name[4:]  # Remove 'hop_' prefix
        
        # Check for maintenance branch pattern (X.Y.x)
        if version_part.endswith('.x'):
            version_without_x = version_part[:-2]  # Remove '.x'
            parts = version_without_x.split('.')
            if len(parts) == 2:
                try:
                    int(parts[0])  # major
                    int(parts[1])  # minor
                    return True
                except ValueError:
                    pass
        
        return False

    # ============================================================================
    # LEVEL 3: CONFLICT DETECTION
    # ============================================================================

    def check_version_conflict(self, version):
        """Checks if version already exists (local or remote)
        
        This method prevents duplicate version development by checking if a branch
        for the given version already exists locally or remotely.
        
        Args:
            version (str): Version string (e.g., "1.2.3")
            
        Returns:
            bool: True if version conflict exists, False if version is available
        """
        branch_name = f'hop_{version}'
        
        # Check local branches
        for head in self.__git_repo.heads:
            if head.name == branch_name:
                return True
        
        # Check remote branches
        try:
            for remote in self.__git_repo.remotes:
                for ref in remote.refs:
                    # Remote refs are like 'origin/hop_1.2.3'
                    remote_branch_name = ref.name.split('/')[-1]
                    if remote_branch_name == branch_name:
                        return True
        except Exception:
            # If no remotes or other issues, continue with local check only
            pass
        
        return False

    def check_rebase_needed(self, branch):
        """Compares local vs remote commit SHA to detect if rebase is needed
        
        This method checks if the local branch is behind the remote branch
        by comparing their commit SHAs.
        
        Args:
            branch (str): Branch name to check (e.g., "hop_1.2.3")
            
        Returns:
            bool: True if rebase is needed (local behind remote), False if up to date
        """
        try:
            # Get local commit SHA
            local_commit = self.__git_repo.commit(branch)
            local_sha = local_commit.hexsha
            
            # Get remote commit SHA
            remote_branch = f'origin/{branch}'
            try:
                remote_commit = self.__git_repo.commit(remote_branch)
                remote_sha = remote_commit.hexsha
                
                # If SHAs are different, rebase is needed
                return local_sha != remote_sha
                
            except Exception:
                # If remote branch doesn't exist, no rebase needed
                return False
                
        except Exception:
            # If local branch doesn't exist or other error, no rebase needed
            return False

    # ============================================================================
    # LEVEL 4: GIT ACTIONS
    # ============================================================================

    def immediate_branch_push(self, branch_name):
        """Pushes branch immediately for version reservation
        
        This method pushes a branch immediately to the remote to reserve a version
        and prevent conflicts between developers. Fails fast on conflicts.
        
        Args:
            branch_name (str): Branch name to push (e.g., "hop_1.2.3")
            
        Raises:
            SystemExit: If no origin configured or push conflicts
        """
        # Check if origin is configured
        if not self.__repo.git_origin:
            utils.error("Git: No remote specified for \"origin\". Can't push!\n", 1)
        
        try:
            # Push branch with upstream tracking
            self.__git_repo.git.push('-u', 'origin', branch_name)
            print(f'✅ Reserved version: {branch_name} pushed to origin')
            
        except GitCommandError as err:
            # Handle push conflicts (branch already exists on remote)
            if 'already exists' in str(err) or 'rejected' in str(err):
                utils.error(
                    f'Version conflict: {branch_name} already exists on remote!\n'
                    f'Another developer is already working on this version.\n', 1)
            else:
                utils.error(f'Failed to push {branch_name}: {err}\n', 1)

    def apply_with_rebase_warning(self):
        """Shows intelligent rebase notifications
        
        This method checks if the current branch needs rebasing and provides
        intelligent warnings to help developers understand what actions are needed.
        """
        current_branch = self.branch
        
        # Check if current branch needs rebase against remote
        if self.check_rebase_needed(current_branch):
            utils.warning(
                f'⚠️  WARNING: {current_branch} is behind remote\n'
                f'💡 Consider rebasing: git rebase origin/{current_branch}\n'
            )
        
        # Check if current branch is a development branch (hop_X.Y.Z)
        if self._is_development_branch(current_branch):
            # Extract version to find corresponding maintenance branch
            version_part = current_branch[4:]  # Remove 'hop_' prefix
            parts = version_part.split('.')
            if len(parts) == 3:
                major, minor = parts[0], parts[1]
                maintenance_branch = f'hop_{major}.{minor}.x'
                
                # Check if maintenance branch has advanced
                if self.check_rebase_needed(maintenance_branch):
                    utils.warning(
                        f'⚠️  WARNING: {maintenance_branch} has advanced\n'
                        f'💡 Consider rebasing against maintenance: git rebase {maintenance_branch}\n'
                    )

    # ============================================================================
    # LEVEL 5: ADVANCED BUSINESS LOGIC
    # ============================================================================

    def _validate_version_format(self, version):
        """
        Validates semantic version format for maintenance branch creation.
        
        Valid formats:
        - X.Y.Z (e.g., "1.2.3", "10.0.5")
        - Must have exactly 3 numeric components
        - Each component must be a non-negative integer
        
        Args:
            version (str): Version string to validate
            
        Returns:
            bool: True if valid, False otherwise
            
        Examples:
            >>> _validate_version_format("1.2.3")    # True
            >>> _validate_version_format("1.2")      # False (missing patch)
            >>> _validate_version_format("1.2.3.4")  # False (too many parts)
            >>> _validate_version_format("invalid")  # False (not numeric)
            >>> _validate_version_format("")         # False (empty)
        """
        if not version or not isinstance(version, str):
            return False
        
        # Split by dots
        parts = version.split('.')
        
        # Must have exactly 3 parts (major.minor.patch)
        if len(parts) != 3:
            return False
        
        # Each part must be a non-negative integer
        try:
            for part in parts:
                # Check that it's a valid integer
                num = int(part)
                if num < 0:
                    return False
                # Check that there are no leading zeros (except for "0")
                if len(part) > 1 and part[0] == '0':
                    return False
        except ValueError:
            return False
        
        return True

    def create_maintenance_branch(self, version):
        """
        Creates a maintenance branch for the given version.
        
        Enhanced with version validation for Git-centric workflow.
        
        Args:
            version (str): Version in format "X.Y.Z"
            
        Returns:
            bool: True if branch created successfully, False otherwise
        """
        # Validate version format first
        if not self._validate_version_format(version):
            utils.warning(f"Invalid version format: '{version}'. Expected format: X.Y.Z (e.g., '1.2.3')")
            return False
        
        # Parse version components
        major, minor, patch = version.split('.')
        maintenance_branch = f'hop_{major}.{minor}.x'
        
        # Check if maintenance branch already exists
        existing_branches = self.get_maintenance_branches()
        if maintenance_branch in existing_branches:
            utils.warning(f"Maintenance branch {maintenance_branch} already exists")
            return False
        
        try:
            # Create maintenance branch from current position
            current_branch = self.__git_repo.active_branch
            
            # Create the maintenance branch
            maint_branch = self.__git_repo.create_head(maintenance_branch)
            
            # Push to reserve the branch
            if self.__repo.git_origin:
                self.immediate_branch_push(maintenance_branch)
                print(f"✅ Created maintenance branch: {maintenance_branch}")
                print(f"✅ Reserved version: {maintenance_branch} pushed to origin")
            else:
                print(f"✅ Created maintenance branch: {maintenance_branch} (local only)")
            
            # Return to original branch
            current_branch.checkout()
            
            return True
            
        except Exception as e:
            utils.error(f"Failed to create maintenance branch {maintenance_branch}: {e}")
            return False

    def _extract_maintenance_version(self, version):
        """
        Extracts maintenance branch version from a release version.
        
        Args:
            version (str): Release version (e.g., "1.2.3")
            
        Returns:
            str: Maintenance branch version (e.g., "1.2.x") or None if invalid
        """
        if not self._validate_version_format(version):
            return None
        
        major, minor, patch = version.split('.')
        return f"{major}.{minor}.x"

    def cleanup_merged_branches(self):
        """Removes development branches that are tagged (released)
        
        This method cleans up development branches (hop_X.Y.Z) that have been
        tagged, indicating they were released. Preserves maintenance branches
        and branches still in development.
        """
        # Get all tags in the repository
        tags = set()
        try:
            for tag in self.__git_repo.tags:
                tags.add(tag.name)
        except Exception:
            # If no tags or error accessing tags, nothing to clean
            return
        
        branches_to_delete = []
        
        # Check each local branch
        for head in self.__git_repo.heads:
            branch_name = head.name
            
            # Only consider development branches (hop_X.Y.Z)
            if self._is_development_branch(branch_name):
                # Extract version (remove 'hop_' prefix)
                version = branch_name[4:]
                
                # If there's a tag for this version, the branch can be cleaned up
                if version in tags:
                    branches_to_delete.append(branch_name)
        
        # Delete the tagged development branches
        for branch_name in branches_to_delete:
            try:
                # Don't delete if it's the current branch
                if branch_name == self.branch:
                    utils.warning(f'⚠️  Skipping cleanup of current branch: {branch_name}\n')
                    continue
                
                # Delete local branch
                self.__git_repo.delete_head(branch_name, force=True)
                print(f'🧹 Cleaned up tagged branch: {branch_name}')
                
                # Try to delete remote branch too
                try:
                    self.__git_repo.git.push('origin', '--delete', branch_name)
                    print(f'🧹 Cleaned up remote branch: origin/{branch_name}')
                except Exception:
                    # Remote branch might not exist or other error, continue
                    pass
                    
            except Exception as err:
                utils.warning(f'Failed to cleanup branch {branch_name}: {err}\n')