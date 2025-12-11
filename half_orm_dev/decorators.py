"""
Decorators for half-orm-dev.

Provides common decorators for ReleaseManager and PatchManager.
"""

import sys
import inspect
from functools import wraps


def with_dynamic_branch_lock(branch_getter, timeout_minutes: int = 30):
    """
    Decorator to protect methods with a dynamic branch lock.

    Unlike with_branch_lock which uses a static branch name, this decorator
    calls a function to determine the branch name at runtime.

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
        def close_patch(self, patch_id):
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
            lock_tag = None
            locked_branch = None
            try:
                # Determine branch name dynamically
                locked_branch = branch_getter(self, *args, **kwargs)

                # Acquire lock
                lock_tag = self._repo.hgit.acquire_branch_lock(locked_branch, timeout_minutes=timeout_minutes)

                # Execute the method
                result = func(self, *args, **kwargs)

                # After success, sync .hop/ from current branch to all other active branches
                try:
                    sync_result = self._repo.sync_hop_to_active_branches(
                        reason=f"{func.__name__}"
                    )
                    # Log sync errors but don't fail the operation
                    if sync_result.get('errors'):
                        for error in sync_result['errors']:
                            print(f"Warning: .hop/ sync error: {error}", file=sys.stderr)
                except Exception as e:
                    # Don't fail the decorated method if sync fails
                    print(f"Warning: Failed to sync .hop/ to active branches: {e}", file=sys.stderr)

                return result
            finally:
                # Always release lock (even on error)
                if lock_tag:
                    self._repo.hgit.release_branch_lock(lock_tag)

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