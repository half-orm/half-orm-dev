# half-orm-dev Architecture

Technical architecture and implementation details for half-orm-dev.

---

## Table of Contents

- [Project Overview](#project-overview)
- [Core Architecture](#core-architecture)
- [Branch Strategy](#branch-strategy)
- [Key Components](#key-components)
- [Release File Format](#release-file-format)
- [Command Structure](#command-structure)
- [Test Validation Workflow](#test-validation-workflow)
- [Important Constraints](#important-constraints)
- [Dependencies](#dependencies)

---

## Project Overview

half-orm-dev is a Git-centric patch management and database versioning tool for PostgreSQL databases. It provides a complete development lifecycle for database-driven applications using the half-orm Python ORM.

The system enforces **Test-Driven Development** with automatic validation: tests run automatically during patch integration, and patches cannot be added to releases if tests fail.

**Key Features:**
- Git-centric workflow with dedicated branch types
- Semantic versioning with automatic calculation
- Patch-based development with isolated testing
- Automatic code generation from schema changes
- Sequential release enforcement for deployment safety
- Systematic test validation before integration

---

## Core Architecture

### Singleton Pattern

The `Repo` class implements a singleton pattern based on the current working directory. This ensures only one instance exists per repository context, preventing state conflicts.

### Component Overview

```
Repo (Singleton)
├── Config                # .hop/config management
├── Database              # PostgreSQL operations
├── HGit                  # Git operations wrapper
├── PatchManager          # Patch lifecycle management
├── ReleaseManager        # Release versioning and promotion
└── MigrationManager      # Repository version migrations
```

---

## Branch Strategy

The repository uses a **strict branching model**:

### Branch Types

#### ho-prod
- **Purpose**: Main production branch (stable, source of truth)
- **Lifetime**: Permanent
- **Protected**: Direct commits forbidden
- **Updates**: Only via `release promote prod`

#### ho-release/X.Y.Z
- **Purpose**: Integration branches for releases
- **Lifetime**: Temporary (deleted after production promotion)
- **Creation**: `release create <level>`
- **Merges**: Receives patches via `patch merge`

#### ho-patch/ID
- **Purpose**: Patch development branches
- **Lifetime**: Temporary (deleted after merge)
- **Creation**: `patch create <id>`
- **Merges**: Into release branch via `patch merge`

### Exception: Hotfix Branches

Hotfix branches reopen existing releases from tags for urgent production fixes. They follow the same pattern but start from a tag instead of `ho-prod`.

---

## Key Components

### 1. Repo (repo.py)

**Singleton** managing repository state, configuration, and component coordination.

#### Config Class

Manages `.hop/config` file:

```ini
[halfORM]
hop_version = 0.17.3-a3
git_origin = https://github.com/user/repo.git
devel = True
```

**Responsibilities:**
- Version validation (installed vs required)
- Git origin management
- Development mode flag

#### Repository Initialization

```python
repo = Repo()  # Automatically finds .hop/config up the directory tree
repo.database  # Access to Database instance
repo.hgit      # Access to HGit instance
repo.patch_manager  # Access to PatchManager
repo.release_manager  # Access to ReleaseManager
```

---

### 2. PatchManager (patch_manager.py)

Handles patch lifecycle and `Patches/patch-id/` directory structure.

#### Key Methods

**`create_patch(patch_id)`**
- Creates `Patches/patch-id/` directory
- Creates `ho-patch/patch-id` branch
- Adds patch as "candidate" in release TOML

**`apply_patch()`**
- Restores database from production state (`model/schema.sql`)
- Applies all staged patches + current patch in order
- Generates half-orm code
- Validates idempotency

**`merge_patch()`**
- Creates temporary validation branch (`ho-validate/{patch_id}`)
- Merges patch into temp branch
- Runs `apply_patch()` to verify idempotency
- **Runs pytest automatically** (if configured)
- If all pass → merges into release branch
- Changes patch status to "staged" in TOML
- Deletes patch branch and temp validation branch
- **Auto-closes GitHub/GitLab issues**: Patch IDs must start with a number (e.g., `123-feature`). The merge commit automatically closes issue #123

#### Patch Directory Structure

```
Patches/
└── 456-user-auth/
    ├── 1-create-users-table.sql
    ├── 2-add-email-constraint.sql
    └── 3-seed-admin.py           # Optional Python migration
```

**Execution order:** Files executed in lexicographic order (1, 2, 3, ...).

---

### 3. ReleaseManager (release_manager.py)

Manages release lifecycle and semantic versioning.

#### Key Methods

**`create_release(level)`**
- Calculates next version from `ho-prod` latest tag
- Creates `ho-release/X.Y.Z` branch
- Creates `.hop/releases/X.Y.Z-patches.toml` file
- Levels: `patch`, `minor`, `major`

**`promote_stage_to_rc()`**
- Converts TOML to TXT snapshot
- Creates `.hop/releases/X.Y.Z-rc1.txt`
- Tags `ho-release-X.Y.Z-rc1`
- Increments RC number if multiple candidates

**`promote_stage_to_production()`**
- Creates `.hop/releases/X.Y.Z.txt` (immutable)
- Merges release branch into `ho-prod`
- Tags `production-X.Y.Z`
- Generates `model/schema-X.Y.Z.sql` snapshot
- Updates `model/schema.sql` symlink
- Deletes release branch

#### Version Calculation

```python
# Current ho-prod: X.Y.Z
release create patch  → X.Y.Z+1
release create minor  → X.Y+1.0
release create major  → X+1.0.0
```

#### Sequential Release Enforcement

**Only the smallest version** in preparation can be promoted to RC or production. This guarantees releases are deployed in order.

Example:
- Releases in preparation: 0.17.0, 0.18.0, 1.0.0
- ✅ Can promote: 0.17.0 (smallest)
- ❌ Cannot promote: 0.18.0, 1.0.0 (must wait)

---

### 4. HGit (hgit.py)

Git operations wrapper using GitPython.

#### Key Operations

**Branch Management:**
- `checkout(branch)`: Switch branches
- `create_branch(name)`: Create new branch
- `delete_branch(name)`: Delete branch
- `merge(branch)`: Merge branch

**Remote Operations:**
- `fetch()`: Fetch from origin
- `pull()`: Pull changes
- `push()`: Push changes
- `push_tags()`: Push tags

**Repository Validation:**
- `is_clean()`: Check for uncommitted changes
- `is_synced()`: Check sync with origin
- `get_current_branch()`: Get active branch name

---

### 5. Database (database.py)

PostgreSQL database operations with **cloud-friendly** design.

#### Key Features

**Connection Management:**
- Production vs development detection
- Docker container support
- Trust authentication support (Unix sockets)

**Schema Restoration (Cloud-Friendly):**

Uses `DROP SCHEMA CASCADE` instead of `dropdb`/`createdb`:

```python
def restore_database_from_schema(self):
    # No superuser or CREATEDB privilege needed!
    self._reset_database_schemas()  # DROP SCHEMA CASCADE
    # Load schema.sql via psql
    # Reload metadata
```

**Why DROP SCHEMA CASCADE?**
- ✅ Works on AWS RDS, Azure Database, GCP Cloud SQL
- ✅ No CREATEDB privilege required
- ✅ No superuser access needed
- ✅ Preserves database-level objects (extensions, FDW)

**Security Improvements:**
- Version detection via existing connection (no `postgres` database access)
- Uses half_orm API (`model.execute_query()`)
- Minimal privilege principle

#### Database-Level Objects Persistence

These objects persist across schema resets:
- **Extensions**: Will be recreated by `schema.sql` with `IF NOT EXISTS`
- **Foreign Data Wrappers** and servers
- **Event triggers**
- **Database settings** (`ALTER DATABASE SET`)

This is by design - these objects are configured once and should persist.

---

### 6. ReleaseFile (release_file.py)

Release file parsing and management.

#### TOML Format (Mutable)

For releases in development (`.hop/releases/X.Y.Z-patches.toml`):

```toml
[patches]
"456-user-auth" = "candidate"   # In development
"457-email-validation" = "staged"  # Integrated, ready for promotion
```

**States:**
- `candidate`: Patch branch exists, work in progress
- `staged`: Merged into release, tests passed, ready for RC/prod

#### TXT Format (Immutable)

For RC and production snapshots (`.hop/releases/X.Y.Z.txt`, `X.Y.Z-rcN.txt`):

```
# Release 0.17.0
456-user-auth
457-email-validation
# End of release
```

**Properties:**
- One patch ID per line
- Comments start with `#`
- Empty lines ignored
- **Immutable**: Never modified after creation

---

## Command Structure

CLI uses **Click framework** with dynamic command availability based on context.

### Context Detection

| Context | Available Commands |
|---------|-------------------|
| Outside repo | `init`, `clone` |
| Inside repo + needs migration | `migrate` |
| Inside repo + dev mode + prod DB | `update`, `upgrade`, `check` |
| Inside repo + dev mode + dev DB | `patch`, `release`, `check` |
| Inside repo + sync-only mode | `sync-package`, `check` |

### Command Organization

Commands are organized in `half_orm_dev/cli/commands/`:

```
cli/commands/
├── __init__.py          # ALL_COMMANDS registry
├── patch.py             # patch create, apply, merge
├── release.py           # release create, promote, hotfix
├── upgrade.py           # upgrade (production deployment)
└── update.py            # update (check available releases)
```

---

## Test Validation Workflow

### Overview

half-orm-dev enforces **systematic test validation** before patch integration. Tests run automatically during `patch merge` and **block the merge if tests fail**.

This is a **core safety feature** that ensures code quality and prevents regressions.

### When Tests Run

Tests execute automatically during `half_orm dev patch merge`:

1. User runs `half_orm dev patch merge` from their patch branch
2. System creates temporary validation branch (`ho-validate/{patch_id}`)
3. System merges patch into temp branch
4. System runs `patch apply` to verify idempotency
5. **System runs pytest automatically** (if test configuration detected)
6. If all validations pass → merge into release branch
7. If anything fails → abort, temp branch deleted, nothing committed

### Implementation Details

Test validation is in `PatchManager._validate_patch_before_merge()` (patch_manager.py:1939-2061).

#### Temporary Validation Branch

```python
# Creates ho-validate/{patch_id} from release branch
temp_branch = f"ho-validate/{patch_id}"
self._repo.hgit.checkout(release_branch)
self._repo.hgit.checkout('-b', temp_branch)
```

This branch is **always deleted** after validation (success or failure).

#### Test Detection

System automatically detects test configuration by checking:
- `pytest.ini`
- `pyproject.toml` (with pytest config)
- `setup.cfg` (with pytest config)
- `tox.ini`
- `tests/` directory existence

If no test configuration found → **silently skipped** (project may not have tests yet).

#### Test Execution

```python
subprocess.run(
    ["pytest", "-v", "--tb=short"],
    cwd=str(base_dir),
    capture_output=True,
    text=True
)
```

#### Test Failure Behavior

If tests fail (returncode != 0):
- **BLOCKS the merge completely**
- Raises `PatchManagerError` with test output (last 20 lines)
- Temporary validation branch deleted
- Distributed lock released
- User must fix tests before trying again

### Testing Full Release Context

Validation runs tests with **full release context** - all staged patches + current patch:

```python
# Get staged patches from TOML file
staged_patches = release_file.get_patches(status="staged")

# Apply ALL patches including current one
all_patches = staged_patches + [patch_id]

# Restore database from production state
self._repo.restore_database_from_schema()

# Apply all patches in order
for pid in all_patches:
    self.apply_patch_files(pid, self._repo.model)

# Generate code
modules.generate(self._repo)

# Run tests in this complete context
```

This ensures:
- Tests verify integration between patches
- Tests run against realistic production-like state
- Catches conflicts between patches early

### Idempotency Verification

Before running tests, system verifies patch idempotency:

1. Applies all staged patches + current patch
2. Generates code
3. Checks if any files were modified
4. If files modified → raises error (patch not idempotent)

This catches patches that:
- Use non-idempotent SQL (`INSERT` without `ON CONFLICT`)
- Have schema drift from `model/schema.sql`
- Generate different code than expected

### Edge Cases

1. **pytest not installed**: Warning, merge continues (not blocking)
2. **Test execution error**: Warning, merge continues (environment issue)
3. **KeyboardInterrupt (Ctrl+C)**: Properly handled - lock released, temp branch deleted
4. **No test config**: Silent skip - projects without tests work normally

---

## Important Constraints

### 1. Sequential Release Enforcement

Only the smallest version in preparation can be promoted to RC or production. This **guarantees releases are deployed in order**.

### 2. Branch Requirements

- `patch create`: Must run from `ho-release/X.Y.Z` branch
- `patch apply`: Must run from `ho-patch/ID` branch
- `patch merge`: Must run from `ho-patch/ID` branch
- `release promote prod`: Must have staged patches in TOML file

### 3. Test Validation

`patch merge` runs pytest automatically on temporary validation branch. If tests fail, merge is aborted and nothing is committed.

**Cannot be disabled** - it's a core safety feature.

### 4. Git Remote Required

Repository must have origin remote configured. Used for:
- Patch ID reservation via tags
- Branch synchronization
- Release tracking

### 5. Database State Management

`patch apply` always restores database from production state (`model/schema.sql`) before applying patches using `DROP SCHEMA CASCADE`.

### 6. Immutable Release Files

Once RC or production TXT snapshots are created, they are **never modified**. Only TOML patches files are mutable.

---

## Dependencies

Core dependencies (see `setup.py`):

- **GitPython**: Git operations
- **click**: CLI framework
- **pydash**: Utility functions
- **pytest**: Testing framework
- **half_orm**: ORM layer (version constraint calculated dynamically)
- **tomli/tomli_w**: TOML parsing (tomli only for Python < 3.11)
- **psycopg2**: PostgreSQL adapter

### Version Constraints

Version is stored in `half_orm_dev/version.txt` (single source of truth).

`setup.py` dynamically calculates half_orm dependency:
- For half_orm_dev `X.Y.Z` → requires `half_orm>=X.Y.MIN,<X.(Y+1).0`
- Special minimum versions defined in `HALF_ORM_MIN_VERSIONS` list

---

## Design Principles

### Security

- **Minimal privileges**: Features work without superuser access
- **No command injection**: Never use `shell=True` with subprocess
- **Input validation**: Sanitize branch names, patch IDs, versions
- **SQL injection prevention**: Use parameterized queries

### Reliability

- **Idempotency**: All operations can be run multiple times safely
- **Atomic operations**: Changes committed only if all validations pass
- **Distributed locks**: Prevent concurrent modifications
- **Automatic cleanup**: Temporary branches/files always deleted

### Maintainability

- **Single responsibility**: Each component has one clear purpose
- **Separation of concerns**: CLI, business logic, and data access separated
- **Type hints**: All public APIs have type annotations
- **Comprehensive tests**: Unit and integration test coverage

---

For contributing guidelines and development workflow, see [CONTRIBUTING.md](../CONTRIBUTING.md).
