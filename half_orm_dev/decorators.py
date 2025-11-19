"""
Decorators for half-orm-dev.

Provides common decorators for ReleaseManager and PatchManager.
"""

from functools import wraps


def with_ho_prod_lock(branch: str = "ho-prod", timeout_minutes: int = 30):
    """
    Decorator to protect methods that modify ho-prod with a lock tag.

    The lock tag allows the pre-commit hook to permit commits on ho-prod
    during the execution of the decorated method.

    Args:
        branch: Branch to lock (default: "ho-prod")
        timeout_minutes: Lock timeout in minutes (default: 30)

    Usage:
        @with_ho_prod_lock()
        def my_method(self, ...):
            # Can commit to ho-prod here
            ...

    Notes:
        - The decorator assumes `self._repo.hgit` has `acquire_branch_lock()`
          and `release_branch_lock()` methods
        - The lock is ALWAYS released in the finally block, even on error
        - If lock acquisition fails, the method is not executed
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            lock_tag = None
            try:
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
