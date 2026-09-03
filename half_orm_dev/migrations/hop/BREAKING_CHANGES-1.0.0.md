# half-orm-dev 1.0.0 — Breaking Changes

## Branch lifecycle: ho-patch/X renamed to ho-staged/X after merge

`patch merge` no longer deletes the patch branch. Instead it renames it
from `ho-patch/<id>` to `ho-staged/<id>`. The branch is deleted
automatically when the release is promoted to production.

**Impact:** Any script or workflow that expected `ho-patch/<id>` to
disappear after `patch merge` must be updated to handle `ho-staged/<id>`.

## patch merge is now idempotent

Re-running `patch merge` after an interrupted execution (e.g. following a
`migrate`) no longer raises "CRITICAL: Patch directory not found". The
command detects the partially applied state and completes safely.

**Impact:** None — strictly backwards compatible behaviour improvement.

## model/metadata-X.Y.Z.sql renamed to model/data-X.Y.Z.sql

`_generate_schema_sql()` now writes an unrestricted `pg_dump --data-only`
snapshot — half_orm_meta bookkeeping *and* all application data — to
`model/data-{version}.sql`, replacing the old `model/metadata-{version}.sql`
(half_orm_meta tables only). `restore_database_from_schema()` and
`restore_database_from_version_schema()` look for `data-{version}.sql`, not
`metadata-{version}.sql`.

**Impact:** A migration (`hop migrate`) automatically backfills
`data-{version}.sql` for a project's current published version from the
existing `metadata-{version}.sql` plus a fresh dump of the live database,
the first time the project upgrades past this version. Older,
already-superseded `metadata-*.sql` files are left on disk untouched but
are no longer read.

## bootstrap/ scripts only run at clone, never at patch merge or release promote

`bootstrap/` scripts used to also execute during `patch merge` validation
and RC/production `release promote` — with no database reset between
runs, a source of failures for any script that wasn't independently
idempotent. They now run exactly once: when a brand-new instance is
created via `clone`.

Reference/system data that should ship to every instance (e.g. a new
system role) no longer needs `bootstrap/` at all — write it as ordinary
idempotent DML in a patch instead. It reaches existing instances through
the normal `hop upgrade` path and is captured automatically in
`data-X.Y.Z.sql` for fresh installs.

**Impact:** Any `bootstrap/` script relied upon to run during `patch
merge` or `release promote` (e.g. to seed data before running tests) no
longer does. Move that data into a patch (idempotent DML) instead; keep
`bootstrap/` only for data that is genuinely specific to one instance
(e.g. an initial admin account, a per-site secret).
