# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

half-orm-dev is a Git-centric patch management and database versioning tool for PostgreSQL databases. It provides a complete development lifecycle for database-driven applications using the half-orm Python ORM.

The system enforces **Test-Driven Development** with automatic validation: tests run automatically during patch integration, and patches cannot be added to releases if tests fail.

## Core Architecture

### Branch Strategy

The repository uses a strict branching model:

- **ho-prod**: Main production branch (stable, source of truth)
- **ho-release/X.Y.Z**: Integration branches for releases (temporary, deleted after production promotion)
- **ho-patch/ID**: Patch development branches (temporary, deleted after merge)

Exception: Hotfix branches reopen existing releases from tags for urgent production fixes.

### Key Components

1. **Repo (repo.py)**: Singleton managing state and coordination
2. **PatchManager (patch_manager.py)**: Patch lifecycle (create, apply, merge)
3. **ReleaseManager (release_manager.py)**: Release versioning and promotion
4. **Database (database.py)**: PostgreSQL operations (uses DROP SCHEMA CASCADE)
5. **HGit (hgit.py)**: Git operations wrapper
6. **MigrationManager (migration_manager.py)**: Repository migrations

### Important Constraints

1. **Sequential Release**: Only smallest version can be promoted
2. **Test Validation**: `patch merge` blocks if tests fail (core safety feature)
3. **Branch Requirements**: Commands must run from correct branch types
4. **Git Remote Required**: Origin must be configured
5. **Database Reset**: Uses `DROP SCHEMA CASCADE` (no superuser needed)
6. **Immutable Releases**: RC/production files never modified after creation

---

## Development Quick Start

```bash
# Setup
git clone https://github.com/half-orm/half-orm-dev.git
cd half-orm-dev
python -m venv .venv
source .venv/bin/activate
pip install -e .

# Run tests
pytest                      # All tests
pytest -m "not integration" # Unit tests only
pytest -m integration       # Integration tests only

# Run CLI
half_orm dev --help
```

---

## Test Validation Workflow

**Critical Feature:** Tests run automatically during `patch merge` and block the merge if they fail.

**Workflow:**
1. User runs `half_orm dev patch merge` from patch branch
2. System creates temp validation branch (`ho-validate/{patch_id}`)
3. System merges patch and runs `patch apply` (idempotency check)
4. **System runs pytest automatically** (if configured)
5. If all pass → merge into release branch, status → "staged"
6. If anything fails → abort, nothing committed

**Test Context:** Full release context with all staged patches + current patch.

**Cannot be disabled** - it's a core safety feature preventing broken code integration.

---

## Important Files

### Core Components
- `half_orm_dev/repo.py` - Repository singleton and coordination
- `half_orm_dev/patch_manager.py` - Patch operations and validation
- `half_orm_dev/release_manager.py` - Release lifecycle
- `half_orm_dev/database.py` - PostgreSQL operations (cloud-friendly, no superuser)
- `half_orm_dev/hgit.py` - Git operations wrapper
- `half_orm_dev/version.txt` - Single source of truth for version

### CLI
- `half_orm_dev/cli/main.py` - CLI entry point
- `half_orm_dev/cli/commands/` - Command implementations
  - `patch.py` - patch create, apply, merge
  - `release.py` - release create, promote
  - `upgrade.py` - Production deployment

### Configuration
- `.hop/config` - Repository config (hop_version, git_origin, devel)
- `.hop/releases/*.toml` - Development releases (mutable)
- `.hop/releases/*.txt` - RC/production releases (immutable)
- `.hop/model/schema.sql` - Production schema (symlink)

---

## Key Patterns

### Error Handling
```python
RepoError → OutdatedHalfORMDevError
PatchManagerError → PatchStructureError, PatchFileError
ReleaseManagerError → ReleaseVersionError, ReleaseFileError
```

### Security
- **DROP SCHEMA CASCADE** instead of dropdb (no superuser, cloud-compatible)
- **Version detection** via existing connection (no `postgres` database access)
- **Minimal privileges** design principle
- **Input validation** for all user inputs

### Testing
- Tests mirror source structure (`tests/patch_manager/` → `patch_manager.py`)
- Fixtures in `conftest.py` (`tmp_repo`, `test_db`)
- `@pytest.mark.integration` for database tests

---

## Common Tasks

### Adding a New Command

1. Create function in `half_orm_dev/cli/commands/mycommand.py`
2. Register in `ALL_COMMANDS` dict (`cli/commands/__init__.py`)
3. Update `create_cli_group()` in `cli/main.py`
4. Add tests in `tests/cli/test_mycommand.py`

### Modifying Release Workflow

Update `ReleaseManager` methods and corresponding CLI commands:
- `_calculate_next_version()` - Version calculation
- `create_release()` - Release creation
- `promote_stage_to_rc()` - Stage → RC promotion
- `promote_stage_to_production()` - RC → Production

### Adding Database Operations

Add methods to `Database` class (`database.py`):
- Use `psycopg2` for connections
- Use transactions for schema changes
- Support both production/development modes
- **Avoid requiring superuser privileges**

---

## Dependencies

- **Python 3.9+** required
- **PostgreSQL 12+** recommended
- **GitPython** - Git operations
- **click** - CLI framework
- **pytest** - Testing
- **half_orm** - ORM layer (version constraint calculated dynamically)

---

## Release File Formats

### TOML (Mutable - Development)
```toml
# .hop/releases/0.17.0-patches.toml
[patches]
"456-user-auth" = "candidate"   # In development
"457-email" = "staged"           # Ready for RC/prod
```

### TXT (Immutable - RC/Production)
```
# .hop/releases/0.17.0.txt
456-user-auth
457-email
```

---

## Resources

- **CONTRIBUTING.md** - Development setup, testing, contribution guidelines
- **docs/ARCHITECTURE.md** - Technical architecture and implementation details
- **Repository**: https://github.com/half-orm/half-orm-dev
- **Issues**: https://github.com/half-orm/half-orm-dev/issues
- **half-orm**: https://github.com/half-orm/half-orm

---

**Alpha Software Notice:** half-orm-dev is in alpha development. Breaking changes may occur. Please report issues!
