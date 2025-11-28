"""
Decorators for half-orm-dev.

Provides common decorators for ReleaseManager and PatchManager.
"""

from functools import wraps


def with_dynamic_branch_lock(branch_getter, timeout_minutes: int = 30):
    """
    Decorator to protect methods with a dynamic branch lock.

    Unlike with_branch_lock which uses a static branch name, this decorator
    calls a function to determine the branch name at runtime.

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
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            lock_tag = None
            try:
                # Determine branch name dynamically
                branch = branch_getter(self, *args, **kwargs)

                # Acquire lock
                lock_tag = self._repo.hgit.acquire_branch_lock(branch, timeout_minutes=timeout_minutes)

                # Execute the method
                return func(self, *args, **kwargs)
            finally:
                # Always release lock (even on error)
                if lock_tag:
                    self._repo.hgit.release_branch_lock(lock_tag)

        return wrapper
    return decorator
