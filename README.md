# half-orm-dev

## **WARNING!** half-orm-dev is still in alpha development phase!

**Git-centric patch management and database versioning for half-orm projects**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: GPLv3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![half-orm](https://img.shields.io/badge/halfORM-compatible-green.svg)](https://github.com/half-orm/half-orm)
[![PyPI Downloads](https://static.pepy.tech/personalized-badge/half-orm-dev?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=downloads)](https://pepy.tech/projects/half-orm-dev)

Modern development workflow for PostgreSQL databases with automatic code generation, semantic versioning, and production-ready deployment system.

---

## ⚠️ Breaking Changes (v0.17.0)

**This version introduces major architectural changes that completely transform how you use half-orm-dev.**

### What Changed

**1. Complete Command Reorganization**
- **OLD**: `half_orm patch new`, `half_orm patch add`, `half_orm release new`
- **NEW**: `half_orm dev patch new`, `half_orm dev patch close`, `half_orm dev release new`
- All commands now under `half_orm dev` namespace for better organization
- Note: `patch close` must be run from the `ho-patch/*` branch (no arguments)

**2. New Branch Strategy**
- **OLD**: Various branch naming conventions
- **NEW**: Strict `ho-prod`, `ho-patch/*`, `ho-release/*` hierarchy
- Previous branch structures are not compatible

**3. Unified Promotion Command**
- **OLD**: `half_orm release promote-to-rc`, `half_orm release promote-to-prod`
- **NEW**: `half_orm dev release promote rc`, `half_orm dev release promote prod`
- Single `promote` command with explicit target argument

**4. TOML-Based Patch Tracking (v0.17.0)**
- **OLD**: Separate `X.Y.Z-candidates.txt` and `X.Y.Z-stage.txt` files
- **NEW**: Single `X.Y.Z-patches.toml` file with candidate/staged status
- **Structure**: `[patches]` section with `patch-id = "candidate"` or `patch-id = "staged"`
- Order preserved in TOML file (insertion order)
- RC/prod/hotfix still use `.txt` format (immutable snapshots)

**5. Test Organization and Validation**
- **NEW**: Systematic test validation before ANY integration
- **NEW**: Temporary validation branches (`temp-valid-X.Y.Z`) for safe testing
- Tests must pass before patches are added to releases

### What Stayed the Same


- ✅ **Business Logic Code**: Your database schemas, models, and application code remain unchanged
- ✅ **Database Structure**: PostgreSQL schemas and data are not affected
- ✅ **half-orm Integration**: Code generation and ORM features work identically
- ✅ **Semantic Versioning**: MAJOR.MINOR.PATCH logic is preserved
- ✅ **SQL Patch Files**: Format and execution order unchanged

### Migration Guide

**If migrating from previous versions:**

1. **Backup your repository** before upgrading
2. **Update all scripts** to use `half_orm dev` prefix
3. **Reorganize branches** to match new `ho-prod`/`ho-patch/*` structure
4. **Convert release files** from CHANGELOG.py to releases/*.txt format
5. **Update CI/CD pipelines** with new command syntax

**For new projects:** Just follow the Quick Start guide below!

---

## 📖 Description

`half-orm-dev` provides a complete development lifecycle for database-driven applications:
- **Git-centric workflow**: Patches stored in Git branches and release files
- **Semantic versioning**: Automatic version calculation (patch/minor/major)
- **Code generation**: Python classes auto-generated from schema changes
- **Safe deployments**: Automatic backups, rollback support, validation
- **Team collaboration**: Distributed locks, branch notifications, conflict prevention
- **Test-driven development**: Systematic validation before any integration

Perfect for teams managing evolving PostgreSQL schemas with Python applications.

## ✨ Features

### 🔧 Development
- **Patch-based development**: Isolated branches for each database change
- **Automatic code generation**: half-orm Python classes created from schema
- **Complete testing**: Apply patches with full release context
- **Conflict detection**: Distributed locks prevent concurrent modifications

### 🧪 Test-Driven Development & Validation

**Systematic Testing Before Integration**

`half-orm-dev` enforces a **test-first approach** that guarantees code quality:

**1. Validation on Temporary Branches**
```bash
# When closing a patch, tests run FIRST
# You must be on the patch branch
git checkout ho-patch/456-user-auth
half_orm dev patch close

# What happens behind the scenes:
# 1. Creates temp-valid-1.3.6 branch
# 2. Merges ALL release patches + new patch
# 3. Runs pytest tests/
# 4. If merge and tests PASS → changes patch status to "staged" in TOML and commits
# 5. If anything FAILS → nothing committed (temp branch is deleted)
```

**2. No Integration Without Tests**
- ❌ **BLOCKED**: Patches cannot be added to releases if anything fails
- ✅ **SAFE**: Only validated code reaches stage/rc/production
- 🔒 **GUARANTEED**: Every release is testable before deployment

**3. Business Logic Testing (TDD Best Practice)**
```python
# Your business logic is fully testable
# Example: tests/test_user_authentication.py

def test_user_creation():
    """Test user creation through half-orm models."""
    user = User(
        username='john',
        email='john@example.com'
    ).ho_insert()

    assert user.id is not None
    assert user.username == 'john'

def test_invalid_email_rejected():
    """Test validation prevents invalid emails."""
    with pytest.raises(ValidationError):
        User(username='john', email='invalid').ho_insert()
```

**4. Full Release Context Testing**
```bash
# Test your patch with ALL previous patches
half_orm dev patch apply

# What happens:
# 1. Restores DB to production state
# 2. Applies all RC patches (if any)
# 3. Applies all stage patches
# 4. Applies YOUR patch in correct order
# 5. Generates code
# → Your tests run in realistic production-like environment
```

**5. Workflow Integration**
```
┌───────────────────────────────────────────────────────────────────┐
│ Development Cycle with Test Validation                            │
├───────────────────────────────────────────────────────────────────┤
│ 1. Create patch                                                   │
│ 2. Write tests FIRST (TDD)                                        │
│ 3. Implement feature                                              │
│ 4. Run tests locally: pytest                                      │
│ 5. Add to release → AUTOMATIC VALIDATION                          │
│    ├─ temp-valid branch created                                   │
│    | ├─ All patches merged                                        │
│    | └─ pytest runs automatically                                 │
│    └─ Only commits if everything is OK                            │
│ 6. Promote to RC → Tests validated again, code merged on ho-prod  │
│ 7. Deploy to prod → Tested code only                              │
└───────────────────────────────────────────────────────────────────┘
```

**Benefits:**
- ✅ **Catch Integration Issues Early**: Test interactions between patches
- ✅ **Prevent Regressions**: Existing tests protect against breaking changes
- ✅ **Document Behavior**: Tests serve as executable specifications
- ✅ **Safe Refactoring**: Change implementation with confidence
- ✅ **Team Collaboration**: Clear expectations for code quality

### 📦 Release Management
- **Semantic versioning**: patch/minor/major increments
- **Release candidates**: RC validation before production
- **Sequential promotion**: stage → rc → production workflow
- **Branch cleanup**: Automatic deletion after RC promotion
- **Test validation**: Automated testing at every promotion step

### 🚀 Production
- **Safe upgrades**: Automatic database backups before changes
- **Incremental deployment**: Apply releases sequentially
- **Dry-run mode**: Preview changes before applying
- **Version tracking**: Complete release history in database
- **Rollback support**: Automatic rollback on failures

### 👥 Team Collaboration
- **Distributed locks**: Prevent concurrent ho-prod modifications
- **Branch notifications**: Alert developers when rebase needed
- **Multiple stages**: Parallel development of different releases
- **Git-based coordination**: No external tools required

## 🚀 Installation

### Prerequisites

- Python 3.8+
- PostgreSQL 12+
- Git
- half-orm (`pip install half-orm`)

### Install

```bash
pip install half-orm-dev
```

### Verify Installation

```bash
half_orm dev --help
```

## 📖 Quick Start

### Initialize New Project

```bash
# Create project with database
half_orm dev init myproject --database mydb

# Navigate to project
cd myproject
```

### Clone Existing Project

```bash
# Clone from Git
half_orm dev clone https://github.com/user/project.git

# Navigate to project
cd project
```

### First Patch (TDD Development)

```bash
# First, create a release integration branch
half_orm dev release new minor  # Creates ho-release/0.1.0

# Now create patch (automatically added to candidates)
half_orm dev patch new 1-users
# → Auto-added to 0.1.0-patches.toml as "candidate"

# Add schema changes
echo "CREATE TABLE users (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), username TEXT NOT NULL);" > Patches/1-users/01_users.sql

# Apply patch - this generates Python code AND test directory structure
half_orm dev patch apply
# → Restores database
# → Applies SQL patches
# → Generates Python classes (mydb/public/user.py)
# → Creates test directory structure (tests/public/user/)

# Now write business logic tests (TDD approach)
# IMPORTANT: Test business logic, NOT ORM operations like ho_insert()
cat > tests/public/user/test_user_business_logic.py << 'EOF'
from mydb.public.user import User

def test_user_creation_with_valid_data():
    """Test creating a user with valid business logic."""
    # Assuming you implement a create() business method
    user = User.create(username='alice')
    assert user['username'] == 'alice'
    assert user['id'] is not None

def test_user_creation_rejects_empty_username():
    """Test business validation."""
    # Should raise an error if you implement validation
    with pytest.raises(ValueError):
        User.create(username='')
EOF

# Implement business logic in your User class
cat >> mydb/public/user.py << 'EOF'

@classmethod
def create(cls, username: str):
    """Business logic for creating a user."""
    if not username or not username.strip():
        raise ValueError("Username cannot be empty")
    return cls(username=username).ho_insert()
EOF

# Run tests
pytest

# Commit your work
git add .
git commit -m "Add users table with business logic and tests"

# Close patch - integrate to release (automatic validation runs here!)
# You must be on the patch branch
git checkout ho-patch/1-users
half_orm dev patch close
# → Status changed to "staged" in TOML
# → Tests validated automatically
```

## 💻 Development Workflow

### Vision: Git-Flow Release Management

The workflow follows a **Git-Flow** approach with dedicated integration branches (`ho-release/X.Y.Z`) that serve as **test sandboxes** before production.

**Motivation:**
- Patches are visible and testable on `ho-release/X.Y.Z` before production
- `ho-prod` remains stable and contains only validated versions (RC or production)
- Workflow compatible with GitLab/GitHub (milestones, merge requests, issues)
- No need to create RC just to make a patch accessible

### Complete Cycle: Patch → Release → Deploy

```
┌─────────────────────────────────────────────────────────────────┐
│ DEVELOPMENT (ho-release/X.Y.Z branch)                           │
├─────────────────────────────────────────────────────────────────┤
│ 1. release new <level>     Create ho-release/X.Y.Z              │
│ 2. patch new <id>          Create patch (auto in candidates)    │
│ 3. patch apply             Apply & test changes                 │
│ 4. patch close             Merge into ho-release (TESTS!)       │
│                            (run from ho-patch/<id> branch)      │
│                                                                 │
│ RELEASE PROMOTION                                               │
│ 5. release promote rc      Create RC (tags ho-release branch)   │
│ 6. release promote prod    Merge to ho-prod + deploy            │
│                                                                 │
│ PRODUCTION DEPLOYMENT                                           │
│ 7. update                  Check available releases             │
│ 8. upgrade                 Apply on production servers          │
│                                                                 │
│ HOTFIX WORKFLOW (urgent fixes)                                  │
│ 9. release hotfix          Reopen production version            │
│ 10. patch new/close        Same workflow on hotfix branch       │
│ 11. release promote hotfix Deploy as vX.Y.Z-hotfixN             │
└─────────────────────────────────────────────────────────────────┘
```

### Workflow Details

#### Concepts: Release Files and Patch States

**Release Files:**
```
.hop/releases/
├── 0.17.0-patches.toml     # Patches in development (TOML format with status)
├── 0.17.0-rc1.txt          # First Release Candidate (snapshot)
├── 0.17.0-rc2.txt          # Second RC (with fixes, snapshot)
├── 0.17.0.txt              # Production version (snapshot)
├── 0.17.0-hotfix1.txt      # Urgent production fix (snapshot)
└── 0.18.0-patches.toml     # Next release in progress
```

**TOML Patches File Format (0.17.0-patches.toml):**
```toml
[patches]
"1-auth" = "candidate"    # In development
"2-api" = "candidate"     # In development
"3-ui" = "staged"         # Integrated, awaiting RC
"4-tests" = "staged"      # Integrated, awaiting RC
```

**Patch States:**
1. **Candidate**: Assigned to release, in development (`"candidate"` in TOML)
2. **Staged**: Integrated in `ho-release/X.Y.Z`, awaiting promotion (`"staged"` in TOML)
3. **Released**: Included in deployed production version (in `X.Y.Z.txt` snapshot)

**Analogy with GitLab/GitHub:**

| half-orm state | File | GitLab/GitHub |
|----------------|------|---------------|
| `release new` | Creates `-patches.toml` | Create milestone |
| `patch new` (on ho-release) | Adds to TOML as "candidate" | Create issue assigned to milestone |
| Candidate | `"patch-id" = "candidate"` in TOML | Open issue assigned to milestone |
| `patch close` | Changes to `"staged"` in TOML | Merge MR and close issue |
| Stage | `"patch-id" = "staged"` in TOML | Closed issue in milestone |
| `release promote rc` | Creates `-rcN.txt` snapshot | Create pre-release |
| RC | `-rcN.txt` | GitHub pre-release |
| `release promote prod` | Creates `X.Y.Z.txt`, deletes TOML | Create stable release |
| Production | `X.Y.Z.txt` | Stable release |

#### Step 1: Create a New Release

```bash
half_orm dev release new minor
# → Detects current production version (e.g., 0.16.0)
# → Calculates next minor version: 0.17.0
# → Creates branch ho-release/0.17.0 from ho-prod
# → Creates .hop/releases/0.17.0-patches.toml (empty TOML file)
# → Commits and pushes to reserve version globally
# → Automatically switches to ho-release/0.17.0
```

**Output:**
```
✅ Release created successfully!

  Version:          0.17.0
  Release branch:   ho-release/0.17.0
  Patches file:     .hop/releases/0.17.0-patches.toml

📝 Next steps:
  1. Create patches: half_orm dev patch new <patch_id>
  2. Close patches: git checkout ho-patch/<patch_id> && half_orm dev patch close
  3. Promote to RC: half_orm dev release promote rc

ℹ️  Patches will be merged into ho-release/0.17.0 for integration testing
```

#### Step 2: Create a Candidate Patch

**Prerequisites:** Must be on `ho-release/0.17.0` branch

```bash
git checkout ho-release/0.17.0
half_orm dev patch new 6-feature-x
# → Auto-detects version 0.17.0 from current branch
# → Creates ho-patch/6-feature-x from ho-release/0.17.0
# → Adds 6-feature-x to 0.17.0-patches.toml as "candidate"
# → Switches to ho-patch/6-feature-x
```

**Output:**
```
✓ Created patch branch: ho-patch/6-feature-x
✓ Created patch directory: Patches/6-feature-x/
✓ Added to candidates: .hop/releases/0.17.0-patches.toml
✓ Switched to branch: ho-patch/6-feature-x

📝 Next steps:
  1. Add SQL/Python files to Patches/6-feature-x/
  2. Run: half_orm dev patch apply
  3. Test your changes
  4. Run: half_orm dev patch close (already on ho-patch/6-feature-x)
```

#### Step 3: Develop and Test (TDD Approach)

```bash
# Apply patch (on ho-patch/* branch)
half_orm dev patch apply
# → Restores database from production state
# → Applies all release patches + current patch
# → Generates Python code
# → Ready for testing

# FIRST: Write tests
cat > tests/public/users/test_users_feature.py << 'EOF'
def test_feature():
    # Your test here
    assert True
EOF

# Run tests
pytest

# Commit your work
git add .
git commit -m "Implement feature with tests"
```

#### Step 4: Close Patch (Integrate to Release)

```bash
# Ensure you're on the patch branch
git checkout ho-patch/6-feature-x

half_orm dev patch close
# Complete workflow:
# → Detects version from 0.17.0-patches.toml
# → Validates ho-patch/6-feature-x exists
# → Creates temporary validation branch
# → Merges ho-patch/6-feature-x into temp branch
# → Restores database and applies all patches
# → Runs tests (pytest)
# → If PASS: Merges into ho-release/0.17.0
# → Changes 6-feature-x from "candidate" to "staged" in TOML
# → Deletes branch ho-patch/6-feature-x
# → Commits and pushes changes
# → Notifies other candidate patches to sync
```

**Output:**
```
✓ Patch closed successfully!

  Patches file:    .hop/releases/0.17.0-patches.toml
  Patch status:    6-feature-x → "staged"
  Tests passed:    ✓
  Notified:        2 active branch(es)

📝 Next steps:
  • Other developers: git pull && git merge ho-release/0.17.0
  • Continue development: half_orm dev patch new <next_patch_id>
  • Promote to RC: half_orm dev release promote rc
```

**Important:** `patch close` replaces the old `patch add` command. The semantics are different:
- **OLD**: `patch add` = "I add my validated patch to release" (from ho-prod)
- **NEW**: `patch close` = "I close my work, it's integrated in release" (merge into ho-release)

#### Step 5: Synchronize with Other Integrated Patches

When another patch is integrated in the release, candidate patches must update:

```bash
git fetch origin
git merge origin/ho-release/0.17.0
```

#### Step 6: Promote to RC

**Sequentiality Rule:** Only the **smallest version** in preparation can be promoted to RC. This guarantees sequential release order.

**Example:** If releases `0.17.1`, `0.18.0` and `1.0.0` are in preparation, only `0.17.1` can be promoted to RC.

```bash
half_orm dev release promote rc
# Complete workflow:
# → Auto-detects smallest version with -patches.toml containing staged patches
# → Verifies it's sequential (follows last prod/RC)
# → Automatically switches to ho-release/X.Y.Z
# → Finds next RC number (rc1, rc2, etc.)
# → Creates tag vX.Y.Z-rc1 on ho-release/X.Y.Z (NOT on ho-prod!)
# → Creates snapshot .hop/releases/X.Y.Z-rc1.txt with staged patches
# → Resets staged patches to candidates in TOML for potential fixes
# → Commits and pushes
```

**Output:**
```
✓ Success!

  Version:  0.17.0
  Tag:      v0.17.0-rc1
  Branch:   ho-release/0.17.0

📝 Next steps:
  • Test RC thoroughly
  • Deploy to production: half_orm dev release promote prod
```

**Important Notes:**
- Tag is created on `ho-release/0.17.0`, **NOT on `ho-prod`**
- Command **auto-detects** which version to promote (smallest)
- Cannot "skip" a version: if 0.17.0 isn't in prod, can't promote 0.18.0

#### Step 7: Promote to Production

**Sequentiality Rule:** Only the **smallest version in preparation** (with a stage file) can be promoted to production.

```bash
half_orm dev release promote prod
# Complete workflow:
# → Auto-detects smallest version with -patches.toml containing staged patches
# → Verifies strict sequentiality (0.17.0 must follow last prod)
# → Automatically switches to ho-prod
# → Merges ho-release/0.17.0 into ho-prod (integrates patch code)
# → Restores database and applies all staged patches from TOML
# → Generates .hop/model/schema-0.17.0.sql and metadata-0.17.0.sql
# → Updates symlink .hop/model/schema.sql → schema-0.17.0.sql
# → Creates .hop/releases/0.17.0.txt snapshot with all patches
# → Deletes .hop/releases/0.17.0-patches.toml (no longer needed)
# → Preserves .hop/releases/0.17.0-rc*.txt for history (if any)
# → Creates tag v0.17.0 on ho-prod
# → Deletes branch ho-release/0.17.0 (mission complete)
# → Commits and pushes
```

**Output:**
```
✓ Success!

  Version:          0.17.0
  Tag:              v0.17.0
  Branches deleted: ho-release/0.17.0

📝 Next steps:
  • Deploy to production servers
  • Start next cycle: half_orm dev release new minor
```

**Important Notes:**
- This is when patch code is **actually merged into `ho-prod`**, not before
- Command **auto-detects** smallest version with stage file
- **Always uses stage file**: RC files are preserved for history but not used for promotion
- **RC is optional**: Can promote directly from stage to production without creating RC
- Sequentiality is **strictly enforced**: impossible to promote 0.18.0 if 0.17.0 isn't already in prod

#### Step 8/9: Production Upgrade

```bash
# On production server (automatically pulls from origin)
# Check available releases
half_orm dev update

# Apply upgrade (with automatic backup and git pull)
half_orm dev upgrade
```

#### Hotfix Workflow (Urgent Production Fixes)

**Scenario:** Critical bug discovered in production (v0.17.0) while new release (v0.18.0) is already in development. Production needs fixing **immediately** without waiting for v0.18.0.

**Step 1: Reopen Production Version**

```bash
half_orm dev release hotfix
# Workflow:
# → Detects production version from model/schema.sql (e.g., 0.17.0)
# → Verifies tag v0.17.0 exists
# → Reopens branch ho-release/0.17.0 from tag v0.17.0
# → Automatically switches to ho-release/0.17.0
```

**Output:**
```
✓ Reopened ho-release/0.17.0 from v0.17.0
✓ Ready for hotfix patches

📝 Next steps:
  1. half_orm dev patch new <patch_id>
  2. git checkout ho-patch/<patch_id> && half_orm dev patch close
  3. half_orm dev release promote hotfix
```

**Important Note:** This is a **break from sequential workflow** as we now have two active release branches simultaneously (`ho-release/0.17.0` and `ho-release/0.18.0`).

**Step 2: Create and Integrate Hotfix Patch**

The workflow is **identical** to normal workflow:

```bash
# On ho-release/0.17.0
half_orm dev patch new 999-critical-security-fix
# ... develop ...
half_orm dev patch apply
# ... test ...
git checkout ho-patch/999-critical-security-fix
half_orm dev patch close
```

**Step 3: Promote Hotfix to Production**

**Important:** Cannot use `promote prod` as tag `v0.17.0` already exists!

```bash
git checkout ho-prod
half_orm dev release promote hotfix
# Hotfix-specific workflow:
# → Detects hotfix context (tag vX.Y.Z already exists)
# → Finds next hotfix number (hotfix1, hotfix2, etc.)
# → Merges ho-release/0.17.0 into ho-prod
# → Generates model/schema-0.17.0-hotfix1.sql and metadata-0.17.0-hotfix1.sql
# → Updates symlink model/schema.sql → schema-0.17.0-hotfix1.sql
# → Creates releases/0.17.0-hotfix1.txt with patch list
# → Creates tag v0.17.0-hotfix1 on ho-prod
# → Deletes branch ho-release/0.17.0
# → Commits and pushes
```

**Output:**
```
✓ Hotfix deployed!

  Version:  0.17.0-hotfix1
  Tag:      v0.17.0-hotfix1
  Patches:  999-critical-security-fix

📝 Next steps:
  • Deploy to production servers immediately
  • Sync other releases: git checkout ho-release/0.18.0 && git merge ho-prod
```

**Step 4: Sync Other In-Progress Releases**

If a release is in development (e.g., 0.18.0), it **must** integrate the hotfix:

```bash
git checkout ho-release/0.18.0
git merge ho-prod
# Resolve any conflicts
git push origin ho-release/0.18.0
```

This guarantees the bugfix won't be lost in the next release.

## 📖 Command Reference

**NOTE**: use `half_orm dev command --help` for detailed help on each command

### Init & Clone

```bash
# Create new project
half_orm dev init <package_name> --database <db_name>

# Clone existing project (automatically pulls from origin)
half_orm dev clone <git_origin>
```

### Patch Commands

```bash
# Create new patch (must be on ho-release/* branch)
half_orm dev patch new <patch_id> [-d "description"] [--before <other_patch_id>]
# → Patches are ordered in the TOML file (insertion order = application order)
# → Use --before to insert a patch before an existing one
# → Order matters: patches are applied sequentially

# Apply current patch (must be on ho-patch/* branch)
half_orm dev patch apply

# Close patch - integrate to release (AUTOMATIC VALIDATION!)
# Must be on ho-patch/* branch
half_orm dev patch close
```

**Patch Ordering:**
- Patches are stored in the TOML file in **insertion order**
- This order determines the **application sequence** (critical for dependencies)
- Use `--before` option to insert a patch at a specific position
- Example: If patch B depends on patch A, ensure A is ordered before B

### Release Commands

```bash
# Prepare next release (patch/minor/major)
# Creates ho-release/X.Y.Z branch + candidates.txt + stage.txt
half_orm dev release new patch
half_orm dev release new minor
half_orm dev release new major

# Promote stage to RC (automatically pushes)
# Tags ho-release/X.Y.Z, renames stage → rc
half_orm dev release promote rc

# Promote RC to production (automatically pushes)
# Merges ho-release/X.Y.Z → ho-prod, creates tag
half_orm dev release promote prod

# Reopen production version for hotfix
half_orm dev release hotfix

# Promote hotfix to production
half_orm dev release promote hotfix
```

### Production Commands

```bash
# Fetch available releases (automatically pulls from origin)
half_orm dev update

# Apply releases to production (automatically pulls from origin)
half_orm dev upgrade [--to-release X.Y.Z]

# Dry run (simulate upgrade)
half_orm dev upgrade --dry-run
```

## 🎯 Common Patterns

### Pattern 1: Planned Development with Integration Branch

```bash
# Start by creating release integration branch
half_orm dev release new minor  # Creates ho-release/0.17.0

# Now on ho-release/0.17.0, create patch
half_orm dev patch new 123-add-users
# → Auto-added to 0.17.0-candidates.txt

# Add SQL/Python files
echo "CREATE TABLE users (id SERIAL PRIMARY KEY, username TEXT);" > Patches/123-add-users/01_users.sql

# Write tests
cat > tests/public/test_public_users.py << 'EOF'
def test_user_creation():
    user = User(username='alice').ho_insert()
    assert user['username'] == 'alice'
EOF

# Apply and test
half_orm dev patch apply
pytest  # Tests should pass

# Commit your work
git add .
git commit -m "Implement users table with tests"

# Close patch - integrate to release (tests validated automatically!)
git checkout ho-patch/123-add-users
half_orm dev patch close
# → Status changed to "staged" in TOML
# → Tests run automatically before integration
```

### Pattern 2: Team Collaboration on Same Release

```bash
# Integration Manager: Create release
half_orm dev release new minor  # Creates ho-release/0.17.0

# Developer A: Working on feature
git checkout ho-release/0.17.0
half_orm dev patch new 456-dashboard
# → Added to 0.17.0-patches.toml as candidate
# ... develop and test ...
git checkout ho-patch/456-dashboard
half_orm dev patch close
# → Status changed to "staged" in TOML

# Developer B: Must sync with A's changes first
git checkout ho-release/0.17.0
git pull origin ho-release/0.17.0  # Get A's integrated changes

# Then create patch
half_orm dev patch new 789-reports
# → Added to 0.17.0-patches.toml as candidate
# ... develop and test ...
git merge origin/ho-release/0.17.0  # Sync again before closing
git checkout ho-patch/789-reports
half_orm dev patch close
# → Tests run with 456 + 789 together!

# All patches validated together in stage
```

### Pattern 3: Parallel Development of Different Releases

```bash
# Parallel development of different versions
# 1. Create multiple release branches
half_orm dev release new minor  # Creates 0.18.0
half_orm dev release new patch  # Creates 0.17.1

# 2. Add patches to specific versions
git checkout ho-release/0.17.1
half_orm dev patch new 123-hotfix
git checkout ho-patch/123-hotfix
half_orm dev patch close

git checkout ho-release/0.18.0
half_orm dev patch new 456-feature
git checkout ho-patch/456-feature
half_orm dev patch close

# 3. Sequential promotion (must promote 0.17.1 before 0.18.0)
half_orm dev release promote rc   # Auto-promotes 0.17.1 (smallest)
# ... validate ...
half_orm dev release promote prod  # 0.17.1 to production
# Now can promote 0.18.0
half_orm dev release promote rc   # Auto-promotes 0.18.0
```

### Pattern 4: Incremental RC (Fix Issues)

```bash
# RC1 has issues discovered in testing
half_orm dev release promote rc  # Creates 0.17.0-rc1
# → Creates rc1.txt snapshot
# → Staged patches remain in TOML

# Found bug in testing, create fix patch
git checkout ho-release/0.17.0  # Back to integration branch
half_orm dev patch new 999-rc1-fix
# → Added to 0.17.0-patches.toml as candidate
half_orm dev patch apply
# ... fix and test ...

# Close patch - changes status to staged
git checkout ho-patch/999-rc1-fix
half_orm dev patch close
# → Status changed to "staged" in TOML
# → Validated automatically

# Promote again (creates rc2, automatically pushes)
half_orm dev release promote rc  # Creates 0.17.0-rc2
# → Creates rc2.txt snapshot with all staged patches
# → Staged patches remain in TOML

# Repeat until RC passes all validation
```

### Pattern 5: Hotfix on Production

```bash
# Bug discovered in production (v0.17.0)
# New release (v0.18.0) already in development

# Reopen production version
half_orm dev release hotfix
# → Reopens ho-release/0.17.0 from tag v0.17.0
# → Creates 0.17.0-patches.toml for hotfix patches

# Same workflow as normal patch
half_orm dev patch new 999-critical-fix
# → Added to 0.17.0-patches.toml as candidate (with # HOTFIX marker)
half_orm dev patch apply
# ... fix and test ...
git checkout ho-patch/999-critical-fix
half_orm dev patch close
# → Status changed to "staged" in TOML

# Promote as hotfix
git checkout ho-prod
half_orm dev release promote hotfix
# → Creates v0.17.0-hotfix1 tag
# → Creates 0.17.0-hotfix1.txt file
# → Merges into ho-prod

# Sync other in-progress releases
git checkout ho-release/0.18.0
git merge ho-prod  # Integrate the hotfix
```

### Pattern 6: Production Deployment

```bash
# On production server (commands automatically pull from origin)

# Check available releases
half_orm dev update

# Simulate upgrade
half_orm dev upgrade --dry-run

# Apply upgrade (creates backup automatically, pulls from origin)
half_orm dev upgrade

# Or apply specific version
half_orm dev upgrade --to-release 1.4.0
```

## 🏗️ Architecture

### Branch Strategy

```
ho-prod (main production)
│
├── ho-release/0.17.0 (integration branch, deleted after prod promotion)
│   ├── ho-patch/6-feature-x    (temporary, deleted after close)
│   ├── ho-patch/7-bugfix-y     (temporary, deleted after close)
│   └── ho-patch/8-auth-z       (temporary, deleted after close)
│
└── ho-release/0.18.0 (next version in parallel)
    └── ho-patch/10-new-api     (temporary, deleted after close)
```

**Branch types:**
- **ho-prod**: Main production branch (source of truth, stable)
- **ho-release/X.Y.Z**: Integration branch for version X.Y.Z (temporary, deleted after prod promotion)
- **ho-patch/\***: Patch development branches created from ho-release/* (temporary, deleted after close)

**Branch Lifecycle:**
1. `release new` creates `ho-release/X.Y.Z` from `ho-prod`
2. `patch new` creates `ho-patch/ID` from `ho-release/X.Y.Z`
3. `patch close` merges `ho-patch/ID` into `ho-release/X.Y.Z` and deletes `ho-patch/ID`
4. `release promote prod` merges `ho-release/X.Y.Z` into `ho-prod` and deletes `ho-release/X.Y.Z`

**Exception - Hotfix Branches:**
- `release hotfix` reopens `ho-release/X.Y.Z` from existing tag `vX.Y.Z`
- Multiple `ho-release/*` branches can exist temporarily (prod version + dev version)
- After `promote hotfix`, the hotfix branch is deleted

### Release Files

```
.hop/releases/
├── 0.17.0-patches.toml    (patches with status: candidate/staged, mutable)
├── 0.17.0-rc1.txt         (first RC snapshot, immutable)
├── 0.17.0-rc2.txt         (fixes from rc1 snapshot, immutable)
├── 0.17.0.txt             (production snapshot, immutable)
├── 0.17.0-hotfix1.txt     (hotfix on production snapshot, immutable)
└── 0.18.0-patches.toml    (next version patches)
```

**File lifecycle (normal workflow):**
```
patch new → X.Y.Z-patches.toml (patch added as "candidate")
                    ↓
patch close → X.Y.Z-patches.toml (status changed to "staged")
                    ↓
                    ├─→ promote rc → X.Y.Z-rc1.txt snapshot created
                    │                staged patches reset to candidates
                    │                    ↓
                    │             promote rc → X.Y.Z-rc2.txt (if fixes needed)
                    │
                    └─→ promote prod → X.Y.Z.txt snapshot created
                                       X.Y.Z-patches.toml deleted
```

**Key point:** `promote prod` creates a `.txt` snapshot from staged patches in the TOML file, then deletes the TOML file. RC files are kept for history only.

**File lifecycle (hotfix workflow):**
```
release hotfix → Reopens X.Y.Z-patches.toml
                    ↓
patch close → X.Y.Z-patches.toml (adds hotfix patches as staged)
                    ↓
promote hotfix → X.Y.Z-hotfixN.txt (snapshot created, TOML deleted)
```

**TOML file format:**
```toml
[patches]
"patch-id" = "candidate"  # or "staged"
```

**TXT snapshot format (RC/prod/hotfix):**
- Each line contains a patch ID
- Lines starting with `#` are comments
- Empty lines are ignored

### Patch Directory Structure

```
Patches/
└── 123-feature-name/
    ├── README.md           (auto-generated description)
    ├── 01_schema.sql       (schema changes)
    ├── 02_data.sql         (data migrations)
    └── 03_indexes.sql      (performance optimizations)
```

**Execution order:** Lexicographic (01, 02, 03...)

### Semantic Versioning

```
MAJOR.MINOR.PATCH
  │     │     │
  │     │     └── Bug fixes, minor changes (1.3.5 → 1.3.6)
  │     └──────── New features, backward compatible (1.3.5 → 1.4.0)
  └────────────── Breaking changes (1.3.5 → 2.0.0)
```

### Workflow Rules

1. **Sequential releases**: Must promote 0.17.0 before 0.17.1 or 0.18.0
2. **Auto-detection**: Commands automatically detect smallest version to promote
3. **Patch origin**: Must create patches from `ho-release/*` branch, not `ho-prod`
4. **Patch lifecycle**: new → candidates → close → stage → rc → prod
5. **Branch cleanup**:
   - `patch close` deletes `ho-patch/*` branch
   - `promote prod` deletes `ho-release/*` branch
6. **Database restore**: `patch apply` always restores from production state
7. **Immutable releases**: RC and production files never modified
8. **Automatic Git operations**: Push/pull handled by commands automatically
9. **⚠️ SYSTEMATIC TEST VALIDATION**: Tests run before integration (in `patch close`)
10. **Hotfix exception**: Can reopen production version while other releases in progress
11. **# HOTFIX marker**: Candidates file marked with `# HOTFIX` comment for hotfix releases

## 🔧 Troubleshooting

### Error: "Must be on ho-release/* branch"

```bash
# Solution: Create release or switch to release branch
half_orm dev release new minor
# or
git checkout ho-release/0.17.0
```

### Error: "Must be on ho-patch/* branch"

```bash
# Solution: Create or switch to patch branch
# First ensure you're on ho-release/*
git checkout ho-release/0.17.0
half_orm dev patch new <patch_id>
# or
git checkout ho-patch/<patch_id>
```

### Error: "Patch not found in candidates file"

```bash
# Solution: Patch must be created from ho-release/* branch
# to be automatically added to candidates
git checkout ho-release/0.17.0
half_orm dev patch new <patch_id>
```

### Error: "Repository is not clean"

```bash
# Solution: Commit or stash changes
git status
git add .
git commit -m "Your message"
# or
git stash
```

### Error: "Repository not synced with origin"

```bash
# This should not happen - commands handle git operations automatically
# If it does occur:
git pull origin ho-prod
```

### Error: "No stage releases found"

```bash
# Solution: Prepare a release first
half_orm dev release new patch
```

### Error: "Active RC exists"

```bash
# Cannot promote different version while RC exists
# Solution: Promote current RC to production first
half_orm dev release promote prod

# Then promote your stage
half_orm dev release promote rc
```

### Error: "Tests failed for patch integration"

```bash
# Tests ran on temp-valid branch and failed
# Solution: Fix your tests or code
half_orm dev patch apply  # Test locally first
pytest  # Verify tests pass

# Fix issues in your patch
vim Patches/123-feature/01_schema.sql
vim tests/test_feature.py

# Try again
git checkout ho-patch/123-feature
half_orm dev patch close  # Tests will run again
```

### Patch apply failed (SQL error)

```bash
# Database automatically rolled back
# Solution: Fix SQL files and re-apply
vim Patches/123-feature/01_schema.sql
half_orm dev patch apply
```

### Lost after conflicts

```bash
# View repository state
git status
git log --oneline -10

# View current branch
git branch

# View remote branches
git branch -r

# Return to safe state
git checkout ho-prod
# Commands handle git pull automatically
```

## 🎓 Best Practices

### Patch Development

✅ **DO:**
- **Write tests FIRST** (TDD approach)
- Start with exploratory patches (no release needed initially)
- Use descriptive patch IDs: `123-add-user-authentication`
- Test patches thoroughly before adding to release
- Keep patches focused (one feature per patch)
- Commit generated code with meaningful messages
- Create release when patches are ready to integrate
- Run `pytest` locally before `patch close`

❌ **DON'T:**
- Mix multiple features in one patch
- Skip `patch apply` validation
- Add untested patches to release
- Modify files outside your patch directory
- Worry about git push/pull (commands handle it automatically)
- Skip writing tests (validation will fail anyway)

### Release Management

✅ **DO:**
- Prepare releases when patches are ready to integrate
- Trust the automatic test validation system
- Test RC thoroughly before promoting to production
- Use semantic versioning consistently
- Document breaking changes in commit messages
- Let commands handle git operations automatically
- Review test failures carefully before retrying

❌ **DON'T:**
- Skip RC validation (always test before prod)
- Promote multiple RCs simultaneously
- Skip backup creation in production
- Force promote without fixing issues
- Manually push/pull (let commands handle it)
- Bypass test validation (it's there for your safety)

### Production Deployment

✅ **DO:**
- Always run `update` first to check available releases
- Use `--dry-run` to preview changes
- Verify backups exist before upgrade
- Monitor application after deployment
- Schedule deployments during low-traffic periods
- Trust commands to handle git operations
- Verify all tests passed in RC before promoting

❌ **DON'T:**
- Deploy without testing in RC first
- Skip backup verification
- Deploy during peak usage hours
- Ignore upgrade warnings
- Apply patches directly without releases
- Manually git pull (commands do it automatically)
- Promote to production if RC tests failed

### Testing Best Practices

✅ **DO:**
- Write tests for all business logic
- Test database constraints and validations
- Use fixtures for common test scenarios
- Test edge cases and error handling
- Keep tests fast and isolated
- Document test intentions clearly
- Run tests locally before pushing

❌ **DON'T:**
- Skip tests for "simple" changes
- Write tests that depend on execution order
- Ignore test failures
- Write tests without assertions
- Test implementation details instead of behavior

## 📚 Documentation

- **Quick Reference**: This README

## 🤝 Contributing

Contributions are welcome! Please read our contributing guidelines and submit pull requests to our repository.

### Development Setup

```bash
# Clone repository
git clone https://github.com/half-orm/half-orm-dev.git
cd half-orm-dev

# Install in development mode
pip install -e .

# Run tests
pytest
```

## 📞 Getting Help

```bash
# Command help
half_orm dev --help
half_orm dev patch --help
half_orm dev release --help

# Specific command help
half_orm dev patch new --help
half_orm dev release promote --help
half_orm dev update --help
half_orm dev upgrade --help
```

### Support

- **Issues**: [GitHub Issues](https://github.com/half-orm/half-orm-dev/issues)
- **Documentation**: [docs/](docs/)
- **half-orm**: [half-orm Documentation](https://half-orm.github.io/half-orm/latest/)

## 📄 License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

---

**Version**: 0.17.0
**half-orm**: Compatible with half-orm 0.17.x
**Python**: 3.8+
**PostgreSQL**: Tested with 13+ (might work with earlier versions)

Made with ❤️ by the half-orm team
