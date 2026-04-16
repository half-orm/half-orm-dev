"""
Regression test for _move_patch_to_stage idempotency.

Bug scenario:
  A first `patch merge` run completes successfully:
    - Patches/X moved to Patches/staged/X on the release branch
    - patch branch deleted (step 8 of merge_patch)

  Then two things happen:
    1. The TOML status is reset to "candidate" (e.g. by a migration sync that
       overwrites .hop/releases/X.Y.Z-patches.toml from ho-prod, where the
       patch is still "candidate").
    2. The patch branch is recreated (its deletion failed, or it was restored
       manually to unblock development).

  A second `patch merge` from the recreated patch branch:
    - git merge sees the patch already merged → "Already up to date" (no new commit)
    - Patches/staged/X exists; Patches/X does NOT
    - _move_patch_to_stage is called:
        WITHOUT fix → raises "CRITICAL: Patch directory not found: Patches/X"
        WITH fix    → detects Patches/staged/X already exists, skips mv, succeeds
"""
import tomllib
import tomli_w
import pytest


def _reset_toml_to_candidate(run, project_dir, patch_id, version, release_branch):
    """
    Overwrite the TOML entry for *patch_id* back to "candidate" status,
    commit and push on *release_branch*.

    Simulates what happens when a migration sync overwrites
    .hop/releases/ from ho-prod (where the patch is still "candidate")
    onto the release branch (where the patch was already "staged").
    """
    run(['git', 'checkout', release_branch])
    toml_path = project_dir / '.hop' / 'releases' / f'{version}-patches.toml'
    with open(toml_path, 'rb') as f:
        data = tomllib.load(f)
    data['patches'][patch_id] = {'status': 'candidate'}
    with open(toml_path, 'wb') as f:
        tomli_w.dump(data, f)
    run(['git', 'add', str(toml_path)])
    run(['git', 'commit', '--no-verify', '-m',
         f'test: reset TOML to candidate (simulate migration sync)'])
    run(['git', 'push', '--no-verify', 'origin', release_branch])


@pytest.mark.e2e
def test_patch_merge_handles_already_staged_directory(project_with_fk_patch):
    """
    _move_patch_to_stage must not fail when Patches/staged/{patch_id}/ already
    exists from a previous (complete or partial) merge run.
    """
    env = project_with_fk_patch
    run = env['run']
    project_dir = env['project_dir']
    patch_id = env['patch_id']          # '1-author-post'
    version = env['release_version']    # '0.1.0'
    release_branch = f'ho-release/{version}'
    patch_branch = f'ho-patch/{patch_id}'

    # Clean untracked/modified files from patch apply before switching branches.
    run(['git', 'stash', '-u'], check=False)

    # ── Phase 1 : complete a normal first merge ───────────────────────────────
    run(['git', 'checkout', patch_branch])

    # Save the patch branch HEAD so we can recreate it after merge deletes it.
    # (The merge may be a fast-forward, so we can't rely on finding a merge
    # commit with two parents afterwards.)
    original_patch_head = run(['git', 'rev-parse', 'HEAD']).stdout.strip()

    run(['half_orm', 'dev', 'patch', 'merge', '--force'])
    # State after phase 1:
    #   ho-release/0.1.0  → Patches/staged/1-author-post/ committed
    #   ho-patch/1-author-post → deleted (locally and on remote)

    run(['git', 'checkout', release_branch])
    assert (project_dir / 'Patches' / 'staged' / patch_id).exists(), \
        "Patches/staged should exist on release branch after first merge"

    # ── Phase 2 : recreate the patch branch at its original HEAD ────────────
    run(['git', 'branch', patch_branch, original_patch_head])
    run(['git', 'push', '--no-verify', 'origin', patch_branch])

    # ── Phase 3 : reset TOML to "candidate" (simulate migration sync) ─────────
    _reset_toml_to_candidate(run, project_dir, patch_id, version, release_branch)

    # ── Phase 4 : attempt second merge ───────────────────────────────────────
    # git merge: patch branch HEAD is an ancestor of release → "Already up to date"
    # _move_patch_to_stage is called even though no new commit was created:
    #   old_path = Patches/1-author-post  → does NOT exist
    #   new_path = Patches/staged/1-author-post → DOES exist
    #
    # WITHOUT the fix: raises PatchManagerError("CRITICAL: Patch directory not found")
    # WITH the fix:    detects staged already exists, skips mv, succeeds
    run(['git', 'checkout', patch_branch])
    run(['half_orm', 'dev', 'patch', 'merge', '--force'])

    # Verify: staged directory is still intact after the second merge
    run(['git', 'checkout', release_branch])
    assert (project_dir / 'Patches' / 'staged' / patch_id).exists(), \
        f"Patches/staged/{patch_id} should still exist after second merge"
