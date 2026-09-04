"""
Migration 1.0.0a35 — drop stale release-X.Y.Z.sql on active branches

Before 1.0.0a33, restore_database_from_schema() rebuilt the database
from model/schema.sql + model/metadata-{version}.sql, and the latter
held half_orm_meta bookkeeping *only* - no application data.
generate_release_schema() then took a full pg_dump of that database, so
every model/release-{version}.sql produced this way captured the
structure plus the half_orm_meta rows and nothing else.

The a33 migration backfilled model/data-{version}.sql with the real,
complete snapshot, but left those release files untouched. They are
still what `patch apply` and `patch merge` restore from whenever a
release is in flight, so development databases come back up with no
application data at all - the symptom that motivated this migration
(a project whose release-0.3.10.sql carried 78 half_orm_meta.hop_release
rows and zero rows for its 39 other tables, against 2098 rows in
data-0.3.9.sql).

Rather than rebuilding those files here - which would mean restoring a
database and replaying every staged patch, per branch - this deletes
them. They are derived artifacts: the fallback already in
apply_patch_complete_workflow() rebuilds one from
restore_database_from_schema() (schema + full data) plus the staged
patches, then calls generate_release_schema() again. Deleting is
therefore self-healing, and costs one rebuild on the next `patch apply`.

A release schema is carried by every active branch: create_release()
commits it on ho-release/X.Y.Z, patch branches inherit a copy, and .hop/
syncing propagates it to ho-prod as well. All of them have to be
cleaned, and ho-prod in particular must not be skipped - syncing copies
.hop/ with `git checkout <source> -- .hop/`, so a copy left on ho-prod
would be restored onto every branch this migration just cleaned. For
the same reason the deletion never propagates on its own: that checkout
adds and overwrites, but never deletes.

Ordering therefore matters. Other branches are handled first, each with
its own commit, while ho-prod's copy is only staged - the migration
runner commits it, then pushes ho-prod, and only then syncs .hop/
outwards.

Committing on other branches is covered by the existing safety net:
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
    return "Delete release-X.Y.Z.sql files generated before the metadata->data.sql switch"


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


def _stale_release_schemas(repo, model_dir):
    """Repo-relative paths of the release schemas present on this branch."""
    return [
        str(path.relative_to(repo.base_dir))
        for path in sorted(model_dir.glob('release-*.sql'))
    ]


def migrate(repo):
    model_dir = Path(repo.model_dir)

    # Only projects predating the a33 metadata->data switch are affected.
    # A leftover model/metadata-*.sql is the proof: it is what the old
    # restore path loaded, so any release schema this project generated
    # was dumped from a database holding half_orm_meta rows only. A
    # project that never had those files has correct release schemas and
    # must not be forced into a needless rebuild.
    if not list(model_dir.glob('metadata-*.sql')):
        return {}

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
            stale = _stale_release_schemas(repo, model_dir)
            if not stale:
                continue

            git_repo.index.remove(stale, working_tree=True)
            git_repo.index.commit(
                '[HOP] Remove stale release schema '
                '(generated before metadata->data.sql; regenerated with '
                'full data on the next patch apply)',
                skip_hooks=True,
            )
            deleted.extend(f"{branch}:{name}" for name in stale)
            to_push.append(branch)

    # push_branch() names its target explicitly, so it does not depend on
    # the branch currently checked out.
    for branch in to_push:
        try:
            repo.hgit.push_branch(branch)
        except Exception as e:
            print(
                f"  ⚠  Could not push {branch}: {e}\n"
                f"     The stale release schema was removed locally; "
                f"push {branch} manually to share the change.",
                file=sys.stderr,
            )

    # ho-prod last, and removed from the working tree only. The migration
    # runner always stages '.hop/' before committing, and `git add` on a
    # directory records deletions inside it, so the removal lands in the
    # migration commit - which is pushed before .hop/ is synced outwards.
    # Skipping ho-prod would leave a copy here that the sync copies
    # straight back onto every branch cleaned above.
    #
    # Staging it here instead would break that runner: it feeds every
    # path it finds staged to `git add`, and `git add` on an
    # already-staged deletion fails with "did not match any files".
    stale_here = _stale_release_schemas(repo, model_dir)
    for relative in stale_here:
        (Path(repo.base_dir) / relative).unlink()
        deleted.append(f"{current_branch}:{relative}")

    return {'deleted_release_schemas': deleted}
