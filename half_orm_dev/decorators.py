"""
Decorators for half-orm-dev.

Provides common decorators for ReleaseManager and PatchManager.
"""

import os
import signal
import sys
import inspect
from functools import wraps

from git.exc import GitCommandError


def _has_recovery_refs(repo) -> bool:
    """Return True if refs/hop/sync/before/* exist (Phase 2 incomplete for some branch)."""
    try:
        refs = repo.hgit._HGit__git_repo.git.for_each_ref('refs/hop/sync/before/')
        return bool(refs.strip())
    except GitCommandError:
        return False


def with_dynamic_branch_lock(branch_getter, timeout_minutes: int = 30):
    """
    Decorator to protect methods with a dynamic branch lock.

    IMPORTANT: Automatically syncs .hop/ directory to all other active branches
    after the decorated method completes (from locked branch to all others).

    Args:
        branch_getter: Callable that takes (self, *args, **kwargs) and returns branch name
        timeout_minutes: Lock timeout in minutes (default: 30)

    Usage:
        def _get_release_branch(self, patch_id, *args, **kwargs):
            # Logic to determine release branch from patch_id
            return f"ho-release/{version}"

        @with_dynamic_branch_lock(_get_release_branch)
        def merge_patch(self, patch_id):
            # Will lock the release branch determined by _get_release_branch
            ...

    Notes:
        - branch_getter is called with the same arguments as the decorated function
        - The lock is ALWAYS released in the finally block, even on error
        - After success, .hop/ is automatically synced from locked branch to all others
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Support both Manager classes (self._repo) and Repo itself (self)
            repo = getattr(self, '_repo', self)
            lock_tag = None
            locked_branch = None
            # Set to True when Phase 2 pushed some but not all branches.
            # In that case the lock and lock file must survive so 'hop recover'
            # can complete the work.
            _keep_lock_for_recovery = False
            try:
                # CRITICAL: Sync ho-prod with origin and validate version BEFORE acquiring any lock
                repo.sync_and_validate_ho_prod()

                # Determine branch name dynamically
                locked_branch = branch_getter(self, *args, **kwargs)

                # Acquire lock
                lock_tag = repo.hgit.acquire_branch_lock(locked_branch, timeout_minutes=timeout_minutes)

                # Write lock file so 'hop recover' can identify ownership after a crash
                _sync_lock_path = os.path.join(repo.base_dir, '.git', 'hop-sync-lock')
                try:
                    with open(_sync_lock_path, 'w') as _f:
                        _f.write(lock_tag)
                except OSError:
                    pass

                # Execute the method
                result = func(self, *args, **kwargs)

                # After success, sync .hop/ from current branch to all other active branches
                try:
                    sync_result = repo.sync_hop_to_active_branches(
                        reason=f"{func.__name__}"
                    )
                    if sync_result.get('errors'):
                        for error in sync_result['errors']:
                            print(f"Warning: .hop/ sync error: {error}", file=sys.stderr)
                        # Recovery refs remaining means Phase 2 is incomplete
                        _keep_lock_for_recovery = _has_recovery_refs(repo)
                except Exception as e:
                    print(f"Warning: Failed to sync .hop/ to active branches: {e}", file=sys.stderr)
                    _keep_lock_for_recovery = _has_recovery_refs(repo)

                if _keep_lock_for_recovery:
                    print(
                        "Warning: Sync partially failed. "
                        "Run 'hop recover' to complete the operation.",
                        file=sys.stderr
                    )

                return result
            finally:
                if lock_tag and not _keep_lock_for_recovery:
                    # Normal completion or pre-sync failure: release lock and clean up.
                    # Block SIGINT to prevent Ctrl+C from leaving an orphan lock tag.
                    interrupted = False
                    original_handler = signal.getsignal(signal.SIGINT)
                    signal.signal(signal.SIGINT, lambda s, f: setattr(
                        wrapper, '_interrupted', True) or None)
                    wrapper._interrupted = False
                    try:
                        repo.hgit.release_branch_lock(lock_tag)
                    finally:
                        interrupted = wrapper._interrupted
                        signal.signal(signal.SIGINT, original_handler)
                    if interrupted:
                        raise KeyboardInterrupt()

                    _sync_lock_path = os.path.join(repo.base_dir, '.git', 'hop-sync-lock')
                    try:
                        os.unlink(_sync_lock_path)
                    except FileNotFoundError:
                        pass

        return wrapper
    return decorator

class Node:
    def __init__(self, name):
        self.name = name
        self.children = []

class Node:
    def __init__(self, name):
        self.name = name
        self.children = []

def print_tree(node, depth=0):
    print("  " * depth + node.name)
    for child in node.children:
        print_tree(child, depth + 1)


def trace_package(package_root: str):
    def decorator(func):

        def wrapper(*args, **kwargs):
            root = Node(func.__qualname__)
            stack = [root]

            def tracer(frame, event, arg):
                filename = frame.f_code.co_filename

                # On garde uniquement les appels venant du package
                if package_root not in filename:
                    return tracer

                if event == 'call':
                    name = frame.f_code.co_qualname
                    node = Node(name)
                    stack[-1].children.append(node)
                    stack.append(node)

                elif event == 'return':
                    if len(stack) > 1:
                        stack.pop()

                return tracer

            sys.settrace(tracer)
            try:
                result = func(*args, **kwargs)
            finally:
                sys.settrace(None)

                print("\n=== Arbre d'exécution ===")
                print_tree(root)
                print("=========================\n")

            return result   # 🔥 retour normal, aucune modification

        return wrapper
    return decorator