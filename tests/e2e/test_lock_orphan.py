"""
E2E test for orphaned local lock tag cleanup.

Regression test for the scenario where release_branch_lock() successfully
deleted the remote tag but failed to delete the local tag, leaving an
orphaned local lock-ho-prod-* tag that would block subsequent operations
for up to 30 minutes.
"""
import time
import pytest


@pytest.mark.e2e
def test_orphaned_local_lock_is_cleaned_up(project_with_release):
    """
    An orphaned local lock tag (no remote counterpart) must be cleaned up
    automatically so that subsequent operations are not blocked.

    Before the fix: acquire_branch_lock() found the local tag, saw it was
    fresh (< 30 min) and raised "Branch is locked".

    After the fix: acquire_branch_lock() checks via ls-remote that the tag
    has no remote counterpart, treats it as an orphan and deletes it
    immediately — regardless of age.
    """
    env = project_with_release
    run = env['run']

    # Simulate an orphaned local lock tag:
    # create it locally only (do NOT push to remote).
    # Use a timestamp 1 minute ago so it is well within the 30-min window
    # that would previously have triggered the "Branch is locked" error.
    timestamp_ms = int(time.time() * 1000) - 60_000   # 1 min ago
    orphan_tag = f"lock-ho-prod-{timestamp_ms}"

    run(['git', 'checkout', 'ho-prod'])
    run(['git', 'tag', '-a', orphan_tag, '-m', 'Simulated orphaned lock'])

    # Confirm the orphaned tag exists locally
    result = run(['git', 'tag', '-l', 'lock-ho-prod-*'])
    assert orphan_tag in result.stdout, "Orphaned tag should exist locally before the test"

    # This would have failed with "Branch is locked" before the fix
    run(['half_orm', 'dev', 'release', 'create', 'patch'])

    # The orphaned tag must have been cleaned up
    result = run(['git', 'tag', '-l', 'lock-ho-prod-*'])
    assert orphan_tag not in result.stdout, "Orphaned local lock tag should have been removed"

    # A new release branch was created (operation completed successfully)
    result = run(['git', 'branch', '-a'])
    new_releases = [b for b in result.stdout.splitlines()
                    if 'ho-release/' in b and 'ho-release/0.1.0' not in b]
    assert new_releases, "A new release branch should have been created"
