"Provides the HGit class"

import os
import sys
import subprocess
import git
from git.exc import GitCommandError

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

    def set_branch(self, release_s):
        """Checks the branch

        Either hop_main or hop_<release>.
        """
        rel_branch = f'hop_{release_s}'
        self.add(self.__repo.changelog.file)
        if str(self.branch) == 'hop_main' and rel_branch != 'hop_main':
            # creates the new branch
            self.__git_repo.git.commit('-m', f'[hop][main] Add {release_s} to Changelog')
            self.__git_repo.create_head(rel_branch)
            self.__git_repo.git.checkout(rel_branch)
            self.__git_repo.git.add('Patches')
            self.__git_repo.git.commit('-m', f'[hop][{release_s}] Patch skeleton')
            self.cherry_pick_changelog(release_s)
            print(f'NEW branch {rel_branch}')
        elif str(self.branch) == rel_branch:
            print(f'On branch {rel_branch}')

    def cherry_pick_changelog(self, release_s):
        "Sync CHANGELOG on all hop_x.y.z branches in devel different from release_s"
        branch = self.__git_repo.active_branch
        self.__git_repo.git.checkout('hop_main')
        commit_sha = self.__git_repo.head.commit.hexsha[0:8]
        for release in self.__repo.changelog.releases_in_dev:
            if release != release_s:
                self.__git_repo.git.checkout(f'hop_{release}')
                self.__git_repo.git.cherry_pick(commit_sha)
                # self.__git_repo.git.commit('--amend', '-m', f'[hop][{release_s}] CHANGELOG')
        self.__git_repo.git.checkout(branch)

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
        "Rebase a hop_X.Y.Z branch to hop_main"
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

    def _is_hop_branch(self, branch_name):
        """Check if a branch name follows HOP conventions
        
        Args:
            branch_name (str): Branch name to check
            
        Returns:
            bool: True if it's a HOP branch (hop_main, hop_X.Y.Z, hop_X.Y.x)
        """
        if branch_name == 'hop_main':
            return True
        
        if branch_name.startswith('hop_'):
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
            
            # Check for development branch pattern (X.Y.Z)
            else:
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