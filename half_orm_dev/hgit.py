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
            self.commit("-m", f"[ho] Set remote origin to {origin}.")
            self.__git_repo.git.push('-u', 'origin', 'ho-prod')
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
        "Initializes the git repo."
        cur_dir = os.path.abspath(os.path.curdir)
        self.__base_dir = base_dir
        try:
            git.Repo.init(base_dir)
            self.__git_repo = git.Repo(base_dir)
            os.chdir(base_dir)

            # Create ho-prod branch FIRST (before any commits)
            self.__git_repo.git.checkout('-b', 'ho-prod')

            # Then add files and commit on ho-prod
            self.__git_repo.git.add('.')
            self.__git_repo.git.commit(m=f'[ho] Initial commit (release: {release})')
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
        """
        LEGACY METHOD - No longer supported

        Branch management for releases removed in v0.16.0.
        Use new patch-centric workflow with PatchManager.
        """
        raise NotImplementedError(
            "Legacy branch-per-release system removed in v0.16.0. "
            "Use new patch-centric workflow via repo.patch_manager"
        )

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
        """
        LEGACY METHOD - No longer supported

        Release rebasing removed in v0.16.0.
        """
        raise NotImplementedError(
            "Legacy release rebasing removed in v0.16.0. "
            "Use new patch-centric workflow"
        )

    def add(self, *args, **kwargs):
        "Proxy to git.add method"
        return self.__git_repo.git.add(*args, **kwargs)

    def commit(self, *args, **kwargs):
        "Proxy to git.commit method"
        return self.__git_repo.git.commit(*args, **kwargs)

    def rebase(self, *args, **kwargs):
        "Proxy to git.commit method"
        return self.__git_repo.git.rebase(*args, **kwargs)

    def checkout(self, *args, **kwargs):
        "Proxy to git.commit method"
        return self.__git_repo.git.checkout(*args, **kwargs)

    def checkout_to_hop_main(self):
        "Checkout to hop_main branch"
        self.__git_repo.git.checkout('hop_main')

# Add these methods to the HGit class in half_orm_dev/hgit.py

    def has_remote(self) -> bool:
        """
        Check if git remote 'origin' is configured.

        Returns:
            bool: True if origin remote exists, False otherwise

        Examples:
            if hgit.has_remote():
                print("Remote configured")
            else:
                print("No remote - local repo only")
        """
        try:
            # Check if any remotes exist
            remotes = self.__git_repo.remotes

            # Look specifically for 'origin' remote
            for remote in remotes:
                if remote.name == 'origin':
                    return True

            return False
        except Exception:
            # Gracefully handle any git errors
            return False

    def push_branch(self, branch_name: str, set_upstream: bool = True) -> None:
        """
        Push branch to remote origin.

        Pushes specified branch to origin remote, optionally setting
        upstream tracking. Used for global patch ID reservation.

        Args:
            branch_name: Branch name to push (e.g., "ho-patch/456-user-auth")
            set_upstream: If True, set upstream tracking with -u flag

        Raises:
            GitCommandError: If push fails (no remote, auth issues, etc.)

        Examples:
            # Push with upstream tracking
            hgit.push_branch("ho-patch/456-user-auth")

            # Push without upstream tracking  
            hgit.push_branch("ho-patch/456-user-auth", set_upstream=False)
        """
        # Get origin remote
        origin = self.__git_repo.remote('origin')

        # Push branch with or without upstream tracking
        origin.push(branch_name, set_upstream=set_upstream)

    def fetch_tags(self) -> None:
        """
        Fetch all tags from remote.

        Updates local knowledge of remote tags for patch number reservation.

        Raises:
            GitCommandError: If fetch fails

        Examples:
            hgit.fetch_tags()
            # Local git now knows about all remote tags
        """
        try:
            origin = self.__git_repo.remote('origin')
            origin.fetch(tags=True)
        except Exception as e:
            from git.exc import GitCommandError
            if isinstance(e, GitCommandError):
                raise
            raise GitCommandError(f"git fetch --tags", 1, stderr=str(e))

    def tag_exists(self, tag_name: str) -> bool:
        """
        Check if tag exists locally or on remote.

        Args:
            tag_name: Tag name to check (e.g., "ho-patch/456")

        Returns:
            bool: True if tag exists, False otherwise

        Examples:
            if hgit.tag_exists("ho-patch/456"):
                print("Patch number 456 reserved")
        """
        try:
            # Check in local tags
            return tag_name in [tag.name for tag in self.__git_repo.tags]
        except Exception:
            return False

    def create_tag(self, tag_name: str, message: str) -> None:
        """
        Create annotated tag for patch number reservation.

        Args:
            tag_name: Tag name (e.g., "ho-patch/456")
            message: Tag message/description

        Raises:
            GitCommandError: If tag creation fails

        Examples:
            hgit.create_tag("ho-patch/456", "Patch 456: User authentication")
        """
        try:
            self.__git_repo.create_tag(tag_name, message=message)
        except Exception as e:
            from git.exc import GitCommandError
            if isinstance(e, GitCommandError):
                raise
            raise GitCommandError(f"git tag", 1, stderr=str(e))

    def push_tag(self, tag_name: str) -> None:
        """
        Push tag to remote for global reservation.

        Args:
            tag_name: Tag name to push (e.g., "ho-patch/456")

        Raises:
            GitCommandError: If push fails

        Examples:
            hgit.push_tag("ho-patch/456")
        """
        origin = self.__git_repo.remote('origin')
        origin.push(tag_name)

    def fetch_from_origin(self) -> None:
        """
        Fetch all references from origin remote.

        Updates local knowledge of all remote references including:
        - All remote branches
        - All remote tags
        - Other remote refs

        This is more comprehensive than fetch_tags() which only fetches tags.
        Used before patch creation to ensure up-to-date view of remote state.

        Raises:
            GitCommandError: If fetch fails (no remote, network, auth, etc.)

        Examples:
            hgit.fetch_from_origin()
            # Local git now has complete up-to-date view of origin
        """
        try:
            origin = self.__git_repo.remote('origin')
            origin.fetch()
        except Exception as e:
            from git.exc import GitCommandError
            if isinstance(e, GitCommandError):
                raise
            raise GitCommandError(f"git fetch origin", 1, stderr=str(e))

    def delete_local_branch(self, branch_name: str) -> None:
        """
        Delete local branch.

        Args:
            branch_name: Branch name to delete (e.g., "ho-patch/456-user-auth")

        Raises:
            GitCommandError: If deletion fails

        Examples:
            hgit.delete_local_branch("ho-patch/456-user-auth")
            # Branch deleted locally
        """
        try:
            self.__git_repo.git.branch('-D', branch_name)
        except Exception as e:
            from git.exc import GitCommandError
            if isinstance(e, GitCommandError):
                raise
            raise GitCommandError(f"git branch -D {branch_name}", 1, stderr=str(e))


    def delete_local_tag(self, tag_name: str) -> None:
        """
        Delete local tag.

        Args:
            tag_name: Tag name to delete (e.g., "ho-patch/456")

        Raises:
            GitCommandError: If deletion fails

        Examples:
            hgit.delete_local_tag("ho-patch/456")
            # Tag deleted locally
        """
        try:
            self.__git_repo.git.tag('-d', tag_name)
        except Exception as e:
            from git.exc import GitCommandError
            if isinstance(e, GitCommandError):
                raise
            raise GitCommandError(f"git tag -d {tag_name}", 1, stderr=str(e))

def get_local_commit_hash(self, branch_name: str) -> str:
        """
        Get the commit hash of a local branch.

        Retrieves the SHA-1 hash of the HEAD commit for the specified
        local branch. Used to compare local state with remote state.

        Args:
            branch_name: Local branch name (e.g., "ho-prod", "ho-patch/456")

        Returns:
            str: Full SHA-1 commit hash (40 characters)

        Raises:
            GitCommandError: If branch doesn't exist locally

        Examples:
            # Get commit hash of ho-prod
            hash_prod = hgit.get_local_commit_hash("ho-prod")
            print(f"Local ho-prod at: {hash_prod[:8]}")

            # Get commit hash of patch branch
            hash_patch = hgit.get_local_commit_hash("ho-patch/456")
        """
        pass

    def get_remote_commit_hash(self, branch_name: str, remote: str = 'origin') -> str:
        """
        Get the commit hash of a remote branch.

        Retrieves the SHA-1 hash of the HEAD commit for the specified
        branch on the remote repository. Requires prior fetch to have
        up-to-date information.

        Args:
            branch_name: Branch name (e.g., "ho-prod", "ho-patch/456")
            remote: Remote name (default: "origin")

        Returns:
            str: Full SHA-1 commit hash (40 characters)

        Raises:
            GitCommandError: If remote or branch doesn't exist on remote

        Examples:
            # Get remote commit hash (after fetch)
            hgit.fetch_from_origin()
            hash_remote = hgit.get_remote_commit_hash("ho-prod")
            print(f"Remote ho-prod at: {hash_remote[:8]}")

            # Compare with local
            hash_local = hgit.get_local_commit_hash("ho-prod")
            if hash_local == hash_remote:
                print("Branch is synced")
        """
        pass

    def is_branch_synced(self, branch_name: str, remote: str = 'origin') -> tuple[bool, str]:
        """
        Check if local branch is synchronized with remote branch.

        Compares local and remote commit hashes to determine sync status.
        Returns both a boolean indicating if synced and a status message.

        Requires fetch_from_origin() to be called first for accurate results.

        Sync states:
        - "synced": Local and remote at same commit
        - "ahead": Local has commits not on remote (need push)
        - "behind": Remote has commits not in local (need pull)
        - "diverged": Both have different commits (need merge/rebase)

        Args:
            branch_name: Branch name to check (e.g., "ho-prod")
            remote: Remote name (default: "origin")

        Returns:
            tuple[bool, str]: (is_synced, status_message)
                - is_synced: True only if "synced", False otherwise
                - status_message: One of "synced", "ahead", "behind", "diverged"

        Raises:
            GitCommandError: If branch doesn't exist locally or on remote

        Examples:
            # Basic sync check
            hgit.fetch_from_origin()
            is_synced, status = hgit.is_branch_synced("ho-prod")

            if is_synced:
                print("✅ ho-prod is synced with origin")
            else:
                print(f"⚠️  ho-prod is {status}")
                if status == "behind":
                    print("Run: git pull")
                elif status == "ahead":
                    print("Run: git push")
                elif status == "diverged":
                    print("Run: git pull --rebase or git merge")

            # Use in validation
            def validate_branch_synced(branch):
                is_synced, status = hgit.is_branch_synced(branch)
                if not is_synced:
                    raise ValidationError(
                        f"Branch {branch} is {status}. "
                        f"Sync required before creating patch."
                    )
        """
        pass
