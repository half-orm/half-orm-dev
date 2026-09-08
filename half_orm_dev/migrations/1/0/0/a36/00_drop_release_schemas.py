"""
Migration 1.0.0a36 — drop every model/release-X.Y.Z.sql

The release schema mechanism is gone. Nothing generates, reads or
updates model/release-{version}.sql any more: a development database is
rebuilt by restoring the production baseline (model/schema.sql +
model/data-X.Y.Z.sql) and replaying the patches staged for the release.

The files left behind are therefore dead weight - a full pg_dump each -
and worse than inert. They are still tracked by git on the branches that
carry them, so they keep producing conflicts: the release branch drops
its copy while a patch branch cut earlier still carries one, and the
next `patch merge` stops on a modify/delete conflict over a file neither
side reads. That is exactly what the a35 migration triggered on projects
it cleaned, and it is what this deletes for good.

Unlike a35, which only touched projects predating the metadata->data
switch (their release schemas held no application data), this one is
unconditional: no project has a use for these files any more.

The branch walk mirrors a35, and for the same reasons. A release schema
is carried by every active branch - it used to be committed on
ho-release/X.Y.Z, inherited by the patch branches cut from it, and
propagated to ho-prod by .hop/ syncing - so all of them have to be
visited. ho-prod in particular must not be skipped: syncing copies .hop/
with `git checkout <source> -- .hop/`, which adds and overwrites but
never deletes, so a copy left there would be restored onto every branch
this migration just cleaned.

Hence the ordering. Other branches are handled first, each with its own
commit, while ho-prod's copy is only removed from the working tree - the
migration runner stages '.hop/', commits it, pushes ho-prod, and only
then syncs .hop/ outwards. Staging it here instead would break that
runner: it feeds every path it finds staged to `git add`, which fails on
an already-staged deletion.

Committing on the other branches is covered by the existing safety net:
capture_branches_snapshot() records ho-prod, release and patch branches
alike, and rollback_to_snapshot() resets each one should the migration
fail later. Following the convention in
Repo.sync_hop_to_active_branches(), those local commits are the
transaction (a failure propagates and triggers that rollback) while push
failures are reported rather than raised - the deletion is already
recorded locally, and an unpushed branch is recoverable.
"""

import sys
from pathlib import Path


def get_description():
    return "Delete model/release-X.Y.Z.sql files (release schema mechanism removed)"


def _affected_branches(repo):
    """Active release and patch branches, both of which carry release schemas."""
    status = repo.hgit.get_active_branches_status()
    names = []
    for key in ('release_branches', 'patch_branches'):
        for branch in status.get(key) or []:
            name = branch.get('name')
            if name and name not in names:
                names.append(name)
    return names


def _release_schemas(repo, model_dir):
    """Repo-relative paths of the release schemas present on this branch."""
    return [
        str(path.relative_to(repo.base_dir))
        for path in sorted(model_dir.glob('release-*.sql'))
    ]


def migrate(repo):
    model_dir = Path(repo.model_dir)
    git_repo = repo.hgit.git_repo
    current_branch = repo.hgit.branch
    deleted = []
    to_push = []

    # Other active branches first, each committed on the spot: the
    # current branch has to stay clean while switching away from it.
    for branch in _affected_branches(repo):
        if branch == current_branch:
            continue
        with repo.hgit.on_branch(branch, silent=True):
            schemas = _release_schemas(repo, model_dir)
            if not schemas:
                continue

            git_repo.index.remove(schemas, working_tree=True)
            git_repo.index.commit(
                '[HOP] Remove release schema '
                '(the release schema mechanism no longer exists; the release '
                'context is replayed from the production baseline)',
                skip_hooks=True,
            )
            deleted.extend(f"{branch}:{name}" for name in schemas)
            to_push.append(branch)

    # push_branch() names its target explicitly, so it does not depend on
    # the branch currently checked out.
    for branch in to_push:
        try:
            repo.hgit.push_branch(branch)
        except Exception as e:
            print(
                f"  ⚠  Could not push {branch}: {e}\n"
                f"     The release schema was removed locally; "
                f"push {branch} manually to share the change.",
                file=sys.stderr,
            )

    # ho-prod last, and removed from the working tree only (see module
    # docstring): the runner stages '.hop/' and `git add` on a directory
    # records deletions inside it, so the removal lands in the migration
    # commit - which is pushed before .hop/ is synced outwards.
    for relative in _release_schemas(repo, model_dir):
        (Path(repo.base_dir) / relative).unlink()
        deleted.append(f"{current_branch}:{relative}")

    return {'deleted_release_schemas': deleted}
