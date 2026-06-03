"""
E2E tests for the 'hop recover' command.

Setup: a real patch merge creates the initial state (branches active, .hop/
up to date). We then simulate a crash at two points in a subsequent sync:

  Phase 2 crash — Phase 1 commits done, push not completed:
    - ho-release/X has a local sync commit, not pushed
    - .git/hop-sync-lock and refs/hop/sync/before/* are present

  Phase 1 crash — crash before commit, staged .hop/ changes left behind:
    - ho-release/X has staged .hop/ changes, no new commit
    - .git/hop-sync-lock and refs/hop/sync/before/* are present

In both cases, hop recover must complete or clean the operation, release the
distributed lock, and allow subsequent hop commands to run normally.
"""

import time
import pytest

from tests.e2e.conftest import run_cmd


pytestmark = pytest.mark.e2e


# ---------------------------------------------------------------------------
# Shared setup: one merged patch to get a realistic .hop/ state
# ---------------------------------------------------------------------------

@pytest.fixture
def project_with_merged_patch(project_with_release):
    """
    Extend project_with_release with one real merged patch.

    After this fixture:
    - ho-patch/1-initial-table is merged into ho-release/0.1.0
    - All active branches have been synced (.hop/ consistent)
    - The project is in a clean, normal state
    """
    env = project_with_release
    run = env['run']
    project_dir = env['project_dir']
    version = env['release_version']

    run(['git', 'checkout', f'ho-release/{version}'])
    run(['half_orm', 'dev', 'patch', 'create', '1-initial-table'])
    run(['git', 'checkout', 'ho-patch/1-initial-table'])

    patch_dir = project_dir / 'Patches' / '1-initial-table'
    (patch_dir / '01_create.sql').write_text(
        'CREATE TABLE items (id SERIAL PRIMARY KEY, label TEXT NOT NULL);'
    )
    run(['half_orm', 'dev', 'patch', 'apply'])
    run(['git', 'add', '.'])
    run(['git', 'commit', '-m', 'Add items table'])

    # Real merge — triggers the decorator, writes and then removes lock artifacts
    run(['half_orm', 'dev', 'patch', 'merge'], input_text='y\n')

    # Return to release branch (clean starting point for crash simulation)
    run(['git', 'checkout', f'ho-release/{version}'])

    yield env


# ---------------------------------------------------------------------------
# Helpers: inject the crash artefacts after the real merge
# ---------------------------------------------------------------------------

def _make_lock_tag(version: str) -> str:
    safe = version.replace('.', '-')
    timestamp_ms = int(time.time() * 1000)
    return f"lock-ho-release-{safe}-{timestamp_ms}"


def _inject_phase2_crash(run, project_dir, version):
    """
    Simulate a crash after Phase 1 completed on ho-release/{version}.

    Creates:
    - A local sync commit (not pushed) on ho-release/{version}
    - A lock tag on origin
    - refs/hop/sync/before/ho-release/{version} = before_sha
    - .git/hop-sync-lock

    Returns state dict.
    """
    branch = f'ho-release/{version}'
    run(['git', 'checkout', branch])

    before_sha = run(['git', 'rev-parse', 'HEAD']).stdout.strip()

    # Phase 1 completed for this branch: local sync commit exists, not pushed
    run(['git', 'commit', '--allow-empty',
         '-m', '[HOP] Sync .hop/ — crash simulation (Phase 2 interrupted)'])
    sync_sha = run(['git', 'rev-parse', 'HEAD']).stdout.strip()

    lock_tag = _make_lock_tag(version)
    run(['git', 'tag', '-a', lock_tag, '-m', 'Crash test lock', before_sha])
    run(['git', 'push', 'origin', lock_tag])

    run(['git', 'update-ref', f'refs/hop/sync/before/{branch}', before_sha])

    lock_file = project_dir / '.git' / 'hop-sync-lock'
    lock_file.write_text(lock_tag)

    return {
        'branch': branch,
        'lock_tag': lock_tag,
        'before_sha': before_sha,
        'sync_sha': sync_sha,
        'lock_file': lock_file,
    }


def _inject_phase1_crash(run, project_dir, version):
    """
    Simulate a crash during Phase 1 on ho-release/{version}: staged .hop/
    changes present, no commit made.

    Returns state dict.
    """
    branch = f'ho-release/{version}'
    run(['git', 'checkout', branch])

    before_sha = run(['git', 'rev-parse', 'HEAD']).stdout.strip()

    # Stage a change to .hop/config without committing (crash mid-Phase 1)
    hop_config = project_dir / '.hop' / 'config'
    hop_config.write_text(hop_config.read_text() + '# crash-marker\n')
    run(['git', 'add', '.hop/config'])

    lock_tag = _make_lock_tag(version)
    run(['git', 'tag', '-a', lock_tag, '-m', 'Crash test lock (phase 1)', before_sha])
    run(['git', 'push', 'origin', lock_tag])

    run(['git', 'update-ref', f'refs/hop/sync/before/{branch}', before_sha])

    lock_file = project_dir / '.git' / 'hop-sync-lock'
    lock_file.write_text(lock_tag)

    return {
        'branch': branch,
        'lock_tag': lock_tag,
        'before_sha': before_sha,
        'lock_file': lock_file,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRecoverCommand:

    def test_recover_completes_phase2_push(self, project_with_merged_patch):
        """
        Phase 2 crash: ho-release/X has a local sync commit, not pushed.

        hop recover must push it, release the lock, clean artefacts, and
        unblock subsequent hop commands.
        """
        env = project_with_merged_patch
        run = env['run']
        project_dir = env['project_dir']
        version = env['release_version']

        state = _inject_phase2_crash(run, project_dir, version)

        # Any decorated command must be blocked while the lock file exists.
        # patch create is decorated and runs from the release branch.
        blocked = run(
            ['half_orm', 'dev', 'patch', 'create', 'blocked-patch'],
            check=False
        )
        assert blocked.returncode != 0, "Command should be blocked while lock file exists"
        assert 'hop recover' in blocked.stderr, (
            f"Expected 'hop recover' in stderr:\n{blocked.stderr}"
        )

        # Recover
        result = run(['half_orm', 'dev', 'recover'])
        assert result.returncode == 0, f"hop recover failed:\n{result.stderr}"

        # The sync commit is now on origin
        run(['git', 'fetch', 'origin'])
        origin_sha = run(
            ['git', 'rev-parse', f"origin/{state['branch']}"]
        ).stdout.strip()
        assert origin_sha == state['sync_sha'], (
            f"Expected origin/{state['branch']}={state['sync_sha']}, got {origin_sha}"
        )

        # Lock tag removed from origin
        remote_tags = run(
            ['git', 'ls-remote', '--tags', 'origin', 'lock-*']
        ).stdout
        assert state['lock_tag'] not in remote_tags, (
            f"Lock tag {state['lock_tag']} should have been removed from origin"
        )

        # Local artefacts cleaned up
        assert not state['lock_file'].exists(), ".git/hop-sync-lock should be deleted"
        refs = run(['git', 'for-each-ref', 'refs/hop/sync/']).stdout
        assert not refs.strip(), f"Recovery refs should be deleted:\n{refs}"

        # Subsequent hop command succeeds (no longer blocked)
        run(['half_orm', 'dev', 'patch', 'create', '2-post-recovery'])
        branches = run(['git', 'branch', '-l', 'ho-patch/*']).stdout
        assert 'ho-patch/2-post-recovery' in branches

    def test_recover_cleans_phase1_staged_changes(self, project_with_merged_patch):
        """
        Phase 1 crash: ho-release/X has staged .hop/ changes, no commit.

        hop recover must unstage and restore clean state, release the lock,
        and clean artefacts.
        """
        env = project_with_merged_patch
        run = env['run']
        project_dir = env['project_dir']
        version = env['release_version']

        state = _inject_phase1_crash(run, project_dir, version)

        # Confirm the branch does have staged changes
        status = run(['git', 'status', '--porcelain']).stdout
        assert '.hop/config' in status, (
            f"Expected staged .hop/config, got:\n{status}"
        )

        # Recover
        result = run(['half_orm', 'dev', 'recover'])
        assert result.returncode == 0, f"hop recover failed:\n{result.stderr}"

        # Branch is clean again
        run(['git', 'checkout', state['branch']])
        status_after = run(['git', 'status', '--porcelain']).stdout
        assert not status_after.strip(), (
            f"Expected clean working tree after recover:\n{status_after}"
        )

        # Staged change was reverted
        config_content = (project_dir / '.hop' / 'config').read_text()
        assert '# crash-marker' not in config_content, (
            "Staged change should have been reverted"
        )

        # Lock released and artefacts cleaned
        remote_tags = run(
            ['git', 'ls-remote', '--tags', 'origin', 'lock-*']
        ).stdout
        assert state['lock_tag'] not in remote_tags

        assert not state['lock_file'].exists()
        refs = run(['git', 'for-each-ref', 'refs/hop/sync/']).stdout
        assert not refs.strip()