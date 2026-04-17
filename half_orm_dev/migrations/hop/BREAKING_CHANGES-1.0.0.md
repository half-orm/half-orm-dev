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
