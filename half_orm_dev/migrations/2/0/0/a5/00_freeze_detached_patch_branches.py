"""
Migration 2.0.0a5 — the branch of a detached patch is ho-detached/<id> (#61)

A detached (orphaned) patch used to keep its ho-patch/<id> branch. Still
an "active" branch, it received a .hop/ sync commit on every hop operation,
and nothing told it apart from a patch in development.

`patch detach` (and `release promote prod` for the candidates it leaves
out) now renames it ho-detached/<id>: out of the sync, refused by the
pre-commit hook, renamed back to ho-patch/<id> by `release attach-patch`.

This migration renames the branches of the patches already orphaned,
locally and on origin. A branch that diverged from origin is left as it
is and reported: renaming it would publish one history and drop the other.
"""

from half_orm_dev.patch_manager import (
    DETACHED_BRANCH_PREFIX, PATCH_BRANCH_PREFIX, PatchManagerError,
)


def get_description():
    return "rename the branches of detached patches ho-patch/ → ho-detached/ (#61)"


def migrate(repo):
    patch_manager = repo.patch_manager
    orphaned = sorted(
        patch_id
        for patch_id, info in patch_manager.get_patch_status_map().items()
        if info.get('status') == 'orphaned'
    )

    renamed, left = [], []
    for patch_id in orphaned:
        old = f"{PATCH_BRANCH_PREFIX}{patch_id}"
        new = f"{DETACHED_BRANCH_PREFIX}{patch_id}"
        if not patch_manager._branch_exists_anywhere(old):
            continue
        if patch_manager._branch_exists_anywhere(new):
            left.append(f"{old}: {new} already exists")
            continue
        try:
            # Unpushed local commits are kept: the rename publishes them.
            patch_manager._check_patch_branch_movable(old, allow_ahead=True)
        except PatchManagerError as e:
            left.append(f"{old}: {e}")
            continue
        if patch_manager._rename_patch_branch(old, new):
            renamed.append(f"{old} → {new}")
        else:
            left.append(f"{old}: rename failed (see above)")

    if renamed:
        print("  Branches of detached patches, now frozen:")
        for line in renamed:
            print(f"    • {line}")
    if left:
        print("  ⚠️  Left as they are (rename them by hand once fixed):")
        for line in left:
            print(f"    • {line}")
    return {'renamed': renamed, 'left': left}
