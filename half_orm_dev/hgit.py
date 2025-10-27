"Provides the HGit class"

from __future__ import annotations

import os
import sys
import subprocess
import git
from git.exc import GitCommandError
from typing import List

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
        """
        Initialize HGit for existing repository.

        Verifies that Git remote origin matches configuration.
        For new projects, remote is configured during init().

        Raises:
            SystemExit: If no remote configured or remote mismatch detected
        """
        self.__git_repo = git.Repo(self.__base_dir)

        # Verify remote origin is configured
        try:
            git_remote_origin = self.__git_repo.git.remote('get-url', 'origin')
        except Exception:
            # No remote origin configured - this is an error
            utils.error(
                "❌ Git remote origin not configured!\n\n"
                "half_orm_dev requires a Git remote for patch management.\n"
                "The remote origin is used for:\n"
                "  • Patch ID reservation (via tags)\n"
                "  • Branch synchronization (ho-patch branches)\n"
                "  • Collaborative development workflow\n\n"
                "To fix this, add a remote origin:\n"
                f"  cd {self.__base_dir}\n"
                "  git remote add origin <your-git-url>\n"
                "  git push -u origin ho-prod\n\n"
                "Or update .hop/config with the correct git_origin.",
                exit_code=1
            )

        # Verify remote matches configuration
        if self.__origin != git_remote_origin:
            utils.error(
                f"❌ Git remote origin mismatch detected!\n\n"
                f"Configuration (.hop/config): {self.__origin}\n"
                f"Git remote (git remote -v):  {git_remote_origin}\n\n"
                "This mismatch can cause issues with patch management.\n\n"
                "To fix this, choose one:\n\n"
                "Option 1: Update Git remote to match config\n"
                f"  cd {self.__base_dir}\n"
                f"  git remote set-url origin {self.__origin}\n\n"
                "Option 2: Update config to match Git remote\n"
                f"  Edit {self.__base_dir}/.hop/config\n"
                f"  Set: git_origin = {git_remote_origin}",
                exit_code=1
            )

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

    def init(self, base_dir, git_origin):
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
            self.__git_repo.git.remote('add', 'origin', git_origin)
            self.__git_repo.git.commit(m=f'[ho] Initial commit (release: 0.0.0)')
            self.__git_repo.git.push('--set-upstream', 'origin', 'ho-prod')
            os.chdir(cur_dir)
        except GitCommandError as err:
            utils.error(
                f'Something went wrong initializing git repo in {base_dir}\n{err}\n', exit_code=1)
        return self

    @property
    def branch(self):
        "Returns the active branch"
        return str(self.__git_repo.active_branch)

    def current_branch(self):
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
        raise Exception("Deprecated legacy cherry_pick_changelog")
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
        raise Exception("Deprecated legacy rebase_devel_branches")
        for release in self.__repo.changelog.releases_in_dev:
            if release != release_s:
                self.__git_repo.git.checkout(f'hop_{release}')
                self.__git_repo.git.rebase('hop_main')

    def check_rebase_hop_main(self, current_branch):
        raise Exception("Deprecated legacy check_rebase_hop_main")
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

    def pull(self, *args, **kwargs):
        "Proxy to git.pull method"
        return self.__git_repo.git.pull(*args, **kwargs)

    def push(self, *args, **kwargs):
        "Proxy to git.push method"
        return self.__git_repo.git.push(*args, **kwargs)

    def merge(self, *args, **kwargs):
        "Proxy to git.merge method"
        return self.__git_repo.git.merge(*args, **kwargs)

    def mv(self, *args, **kwargs):
        "Proxy to git.mv method"
        return self.__git_repo.git.mv(*args, **kwargs)

    def checkout_to_hop_main(self):
        "Checkout to hop_main branch"
        self.__git_repo.git.checkout('hop_main')

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
        try:
            # Access branch from heads
            if branch_name not in self.__git_repo.heads:
                raise GitCommandError(
                    f"git rev-parse {branch_name}",
                    1,
                    stderr=f"Branch '{branch_name}' not found locally"
                )

            branch = self.__git_repo.heads[branch_name]
            return branch.commit.hexsha

        except GitCommandError:
            raise
        except Exception as e:
            raise GitCommandError(
                f"git rev-parse {branch_name}",
                1,
                stderr=str(e)
            )

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
        try:
            # Get remote
            remote_obj = self.__git_repo.remote(remote)

            # Check if branch exists in remote refs
            if branch_name not in remote_obj.refs:
                raise GitCommandError(
                    f"git ls-remote {remote} {branch_name}",
                    1,
                    stderr=f"Branch '{branch_name}' not found on remote '{remote}'"
                )

            # Get commit hash from remote ref
            remote_ref = remote_obj.refs[branch_name]
            return remote_ref.commit.hexsha

        except GitCommandError:
            raise
        except Exception as e:
            raise GitCommandError(
                f"git ls-remote {remote} {branch_name}",
                1,
                stderr=str(e)
            )

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
        # Get local and remote commit hashes
        local_hash = self.get_local_commit_hash(branch_name)
        remote_hash = self.get_remote_commit_hash(branch_name, remote)

        # If hashes are identical, branches are synced
        if local_hash == remote_hash:
            return (True, "synced")

        # Branches differ - determine if ahead, behind, or diverged
        try:
            # Get merge base (common ancestor)
            local_commit = self.__git_repo.heads[branch_name].commit
            remote_ref = self.__git_repo.remote(remote).refs[branch_name]
            remote_commit = remote_ref.commit

            merge_base_commits = self.__git_repo.merge_base(local_commit, remote_commit)

            if not merge_base_commits:
                # No common ancestor - diverged
                return (False, "diverged")

            merge_base_hash = merge_base_commits[0].hexsha

            # Compare merge base with local and remote
            if merge_base_hash == remote_hash:
                # Merge base = remote → local is ahead
                return (False, "ahead")
            elif merge_base_hash == local_hash:
                # Merge base = local → local is behind
                return (False, "behind")
            else:
                # Merge base different from both → diverged
                return (False, "diverged")

        except Exception as e:
            # If merge_base fails, assume diverged
            return (False, "diverged")

    def acquire_branch_lock(self, branch_name: str, timeout_minutes: int = 30) -> str:
        """
        Acquire exclusive lock on branch using Git tag.

        Creates lock tag with format: lock-{branch}-{utc_timestamp_ms}
        Only one process can hold lock on a branch at a time.

        Automatically cleans up stale locks (older than timeout).

        Args:
            branch_name: Branch to lock (e.g., "ho-prod", "ho-patch/456")
            timeout_minutes: Consider lock stale after this many minutes (default: 30)

        Returns:
            Lock tag name (e.g., "lock-ho-prod-1704123456789")

        Raises:
            GitCommandError: If lock acquisition fails

        Examples:
            # Lock ho-prod for release operations
            lock_tag = hgit.acquire_branch_lock("ho-prod")
            try:
                # ... do work on ho-prod ...
            finally:
                hgit.release_branch_lock(lock_tag)

            # Lock with custom timeout
            lock_tag = hgit.acquire_branch_lock("ho-prod", timeout_minutes=60)
        """
        import time
        import re
        from datetime import datetime, timedelta

        # Sanitize branch name for tag (replace / with -)
        safe_branch_name = branch_name.replace('/', '-')

        # Fetch latest tags
        self.fetch_tags()

        # Check for existing locks on this branch
        lock_pattern = f"lock-{safe_branch_name}-*"
        existing_locks = self.list_tags(pattern=lock_pattern)

        if existing_locks:
            # Extract timestamp from first lock
            match = re.search(r'-(\d+)$', existing_locks[0])
            if match:
                lock_timestamp_ms = int(match.group(1))
                lock_time = datetime.utcfromtimestamp(lock_timestamp_ms / 1000.0)
                current_time = datetime.utcnow()

                # Check if lock is stale
                age_minutes = (current_time - lock_time).total_seconds() / 60

                if age_minutes > timeout_minutes:
                    # Stale lock - delete it
                    print(f"⚠️  Cleaning up stale lock: {existing_locks[0]} (age: {age_minutes:.1f} min)")
                    try:
                        self.__git_repo.git.push("origin", "--delete", existing_locks[0])
                        self.delete_local_tag(existing_locks[0])
                    except Exception as e:
                        print(f"Warning: Failed to delete stale lock: {e}")
                    # Continue to create new lock
                else:
                    # Recent lock - respect it
                    from git.exc import GitCommandError
                    raise GitCommandError(
                        f"Branch '{branch_name}' is locked by another process.\n"
                        f"Lock: {existing_locks[0]}\n"
                        f"Age: {age_minutes:.1f} minutes\n"
                        f"Wait a few minutes and retry, or manually delete the lock tag if the process died.",
                        status=1
                    )

        # Create new lock with UTC timestamp in milliseconds
        timestamp_ms = int(time.time() * 1000)
        lock_tag = f"lock-{safe_branch_name}-{timestamp_ms}"

        # Create local tag
        self.create_tag(lock_tag, message=f"Lock on {branch_name} at {datetime.utcnow().isoformat()}")

        # Push tag (ATOMIC - this is the lock acquisition)
        try:
            self.push_tag(lock_tag)
        except Exception as e:
            # Push failed - someone else got the lock first
            # Cleanup local tag
            self.delete_local_tag(lock_tag)

            from git.exc import GitCommandError
            raise GitCommandError(
                f"Failed to acquire lock on '{branch_name}'.\n"
                f"Another process acquired it first.\n"
                f"Retry in a few seconds.",
                status=1
            )

        return lock_tag


    def release_branch_lock(self, lock_tag: str) -> None:
        """
        Release branch lock by deleting lock tag.

        Always called in finally block to ensure cleanup.
        Non-fatal if deletion fails (logs warning).

        Args:
            lock_tag: Lock tag name to release (e.g., "lock-ho-prod-1704123456789")

        Examples:
            lock_tag = hgit.acquire_branch_lock("ho-prod")
            try:
                # ... work ...
            finally:
                hgit.release_branch_lock(lock_tag)
        """
        # Best effort - continue even if fails
        try:
            # Delete remote tag
            self.__git_repo.git.push("origin", "--delete", lock_tag)
        except Exception as e:
            print(f"⚠️  Warning: Failed to delete remote lock tag {lock_tag}: {e}")

        try:
            # Delete local tag
            self.delete_local_tag(lock_tag)
        except Exception as e:
            print(f"⚠️  Warning: Failed to delete local lock tag {lock_tag}: {e}")


    def list_tags(self, pattern: Optional[str] = None) -> List[str]:
        """
        List tags matching glob pattern.

        Args:
            pattern: Optional glob pattern (e.g., "lock-*", "lock-ho-prod-*")

        Returns:
            List of tag names matching pattern

        Examples:
            # List all locks
            locks = hgit.list_tags("lock-*")

            # List locks on specific branch
            ho_prod_locks = hgit.list_tags("lock-ho-prod-*")
        """
        import fnmatch

        all_tags = [tag.name for tag in self.__git_repo.tags]

        if pattern:
            return [tag for tag in all_tags if fnmatch.fnmatch(tag, pattern)]

        return all_tags

    def rename_branch(
        self,
        old_name: str,
        new_name: str,
        delete_remote_old: bool = True
    ) -> None:
        """
        Rename local and remote branch atomically.

        Performs complete branch rename workflow: creates new branch from old,
        pushes new to remote, deletes old from remote and local. Used by
        ReleaseManager to archive patch branches after integration.

        Workflow:
        1. Fetch latest from origin (ensure we have latest state)
        2. Create new local branch from old branch (preserves history)
        3. Push new branch to remote with upstream tracking
        4. Delete old branch from remote (if delete_remote_old=True)
        5. Delete old local branch

        Args:
            old_name: Current branch name (e.g., "ho-patch/456-user-auth")
            new_name: New branch name (e.g., "ho-release/1.3.6/456-user-auth")
            delete_remote_old: If True, delete old branch on remote
                            If False, keep old branch on remote (for backup)

        Raises:
            GitCommandError: If branch operations fail:
                - Old branch doesn't exist
                - New branch already exists
                - Push/delete operations fail
                - Remote access issues

        Examples:
            # Archive patch branch after integration
            hgit.rename_branch(
                "ho-patch/456-user-auth",
                "ho-release/1.3.6/456-user-auth"
            )
            # Result:
            # - Local: ho-patch/456 deleted, ho-release/1.3.6/456 created
            # - Remote: ho-patch/456 deleted, ho-release/1.3.6/456 created

            # Restore patch branch from archive
            hgit.rename_branch(
                "ho-release/1.3.6/456-user-auth",
                "ho-patch/456-user-auth"
            )
            # Result: Branch restored to active development namespace

            # Rename without deleting old remote (keep backup)
            hgit.rename_branch(
                "ho-patch/456-user-auth",
                "ho-release/1.3.6/456-user-auth",
                delete_remote_old=False
            )
            # Result: Both branches exist on remote (old + new)

        Notes:
            - Complete Git history is preserved (new branch points to same commits)
            - If old branch is currently checked out, operation fails
            - Upstream tracking is automatically set for new branch
            - Remote operations may fail due to network or permissions
        """
        # 1. Fetch latest from origin to ensure we have up-to-date refs
        try:
            self.fetch_from_origin()
        except GitCommandError as e:
            raise GitCommandError(
                f"Failed to fetch from origin before rename: {e}",
                status=1
            )

        # 2. Check if old branch exists (local or remote)
        old_branch_exists_local = old_name in self.__git_repo.heads
        old_branch_exists_remote = False

        try:
            origin = self.__git_repo.remote('origin')
            old_branch_exists_remote = old_name in [
                ref.name.replace('origin/', '', 1)
                for ref in origin.refs
            ]
        except:
            pass  # Remote may not exist or may not have the branch

        if not old_branch_exists_local and not old_branch_exists_remote:
            raise GitCommandError(
                f"Branch '{old_name}' does not exist locally or on remote",
                status=1
            )

        # 3. Check if new branch already exists
        new_branch_exists_local = new_name in self.__git_repo.heads
        new_branch_exists_remote = False

        try:
            origin = self.__git_repo.remote('origin')
            new_branch_exists_remote = new_name in [
                ref.name.replace('origin/', '', 1)
                for ref in origin.refs
            ]
        except:
            pass

        if new_branch_exists_local or new_branch_exists_remote:
            raise GitCommandError(
                f"Branch '{new_name}' already exists. Cannot rename.",
                status=1
            )

        # 4. Create new local branch from old branch
        # If old branch only exists on remote, create from remote ref
        if not old_branch_exists_local and old_branch_exists_remote:
            # Create from remote ref
            try:
                self.__git_repo.git.branch(new_name, f"origin/{old_name}")
            except GitCommandError as e:
                raise GitCommandError(
                    f"Failed to create new branch '{new_name}' from remote '{old_name}': {e}",
                    status=1
                )
        else:
            # Create from local branch
            try:
                self.__git_repo.git.branch(new_name, old_name)
            except GitCommandError as e:
                raise GitCommandError(
                    f"Failed to create new branch '{new_name}' from local '{old_name}': {e}",
                    status=1
                )

        # 5. Push new branch to remote with upstream tracking
        try:
            origin = self.__git_repo.remote('origin')
            origin.push(f"{new_name}:{new_name}", set_upstream=True)
        except GitCommandError as e:
            # Rollback: delete local new branch
            try:
                self.__git_repo.git.branch("-D", new_name)
            except:
                pass  # Best effort

            raise GitCommandError(
                f"Failed to push new branch '{new_name}' to remote: {e}",
                status=1
            )

        # 6. Delete old branch from remote (if requested)
        if delete_remote_old and old_branch_exists_remote:
            try:
                origin = self.__git_repo.remote('origin')
                origin.push(refspec=f":{old_name}")  # Delete remote branch
            except GitCommandError as e:
                # Non-fatal: log warning but continue
                # New branch is already on remote, which is the main goal
                import sys
                print(
                    f"Warning: Failed to delete old remote branch '{old_name}': {e}",
                    file=sys.stderr
                )

        # 7. Delete old local branch (if exists and not currently checked out)
        if old_branch_exists_local:
            # Check if old branch is currently checked out
            current_branch = str(self.__git_repo.active_branch)

            if current_branch == old_name:
                # Cannot delete currently checked out branch
                # This is expected behavior - caller should checkout another branch first
                raise GitCommandError(
                    f"Cannot delete branch '{old_name}' while it is checked out. "
                    f"Checkout another branch first.",
                    status=1
                )

            try:
                self.__git_repo.git.branch("-D", old_name)
            except GitCommandError as e:
                # Non-fatal: new branch exists, which is the main goal
                import sys
                print(
                    f"Warning: Failed to delete old local branch '{old_name}': {e}",
                    file=sys.stderr
                )

    def get_remote_branches(self) -> List[str]:
        """
        Get list of all remote branches.

        Returns:
            List of remote branch names with 'origin/' prefix
            Example: ['origin/ho-prod', 'origin/ho-patch/456-user-auth']

        Examples:
            branches = hgit.get_remote_branches()
            # → ['origin/ho-prod', 'origin/ho-patch/456', 'origin/ho-patch/789']

            # Filter for patch branches
            patch_branches = [b for b in branches if 'ho-patch' in b]
        """
        try:
            result = subprocess.run(
                ["git", "branch", "-r"],
                cwd=self.__base_dir,
                capture_output=True,
                text=True,
                check=True
            )

            # Parse output: each line is a branch name
            branches = []
            for line in result.stdout.strip().split('\n'):
                branch = line.strip()
                # Skip empty lines and HEAD references
                if branch and not 'HEAD' in branch:
                    branches.append(branch)

            return branches

        except subprocess.CalledProcessError:
            # If command fails, return empty list
            return []