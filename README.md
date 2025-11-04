# half_orm_dev

## **WARNING!** half_orm_dev is still in alpha development phase!

**Git-centric patch management and database versioning for halfORM projects**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: GPLv3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![halfORM](https://img.shields.io/badge/halfORM-compatible-green.svg)](https://github.com/halfORM/halfORM)

Modern development workflow for PostgreSQL databases with automatic code generation, semantic versioning, and production-ready deployment system.

---

## ⚠️ Breaking Changes (v0.16.0)

**This version introduces major architectural changes that completely transform how you use half_orm_dev.**

### What Changed

**1. Complete Command Reorganization**
- **OLD**: `half_orm patch new`, `half_orm patch apply`, `half_orm release new`
- **NEW**: `half_orm dev patch new`, `half_orm dev patch apply`, `half_orm dev release new`
- All commands now under `half_orm dev` namespace for better organization

**2. New Branch Strategy**
- **OLD**: Various branch naming conventions
- **NEW**: Strict `ho-prod`, `ho-patch/*`, `ho-release/*` hierarchy
- Previous branch structures are not compatible

**3. Unified Promotion Command**
- **OLD**: `half_orm release promote-to-rc`, `half_orm release promote-to-prod`
- **NEW**: `half_orm dev release promote rc`, `half_orm dev release promote prod`
- Single `promote` command with explicit target argument

**4. Different Release File Organization**
- **OLD**: CHANGELOG.py-based versioning
- **NEW**: `releases/*.txt` files with explicit patch lists
- **Structure**: `X.Y.Z-stage.txt` → `X.Y.Z-rc1.txt` → `X.Y.Z.txt`

**5. Test Organization and Validation**
- **NEW**: Systematic test validation before ANY integration
- **NEW**: Temporary validation branches (`temp-valid-X.Y.Z`) for safe testing
- Tests must pass before patches are added to releases

### What Stayed the Same

✅ **Business Logic Code**: Your database schemas, models, and application code remain unchanged
✅ **Database Structure**: PostgreSQL schemas and data are not affected
✅ **halfORM Integration**: Code generation and ORM features work identically
✅ **Semantic Versioning**: MAJOR.MINOR.PATCH logic is preserved
✅ **SQL Patch Files**: Format and execution order unchanged

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

`half_orm_dev` provides a complete development lifecycle for database-driven applications:
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
- **Automatic code generation**: halfORM Python classes created from schema
- **Complete testing**: Apply patches with full release context
- **Conflict detection**: Distributed locks prevent concurrent modifications

### 🧪 Test-Driven Development & Validation

**Systematic Testing Before Integration**

`half_orm_dev` enforces a **test-first approach** that guarantees code quality:

**1. Validation on Temporary Branches**
```bash
# When adding a patch to a release, tests run FIRST
half_orm dev patch add 456-user-auth

# What happens behind the scenes:
# 1. Creates temp-valid-1.3.6 branch
# 2. Merges ALL release patches + new patch
# 3. Runs pytest tests/
# 4. If tests PASS → commits to ho-prod
# 5. If tests FAIL → rollback, nothing committed
```

**2. No Integration Without Tests**
- ❌ **BLOCKED**: Patches cannot be added to releases if tests fail
- ✅ **SAFE**: Only validated code reaches stage/rc/production
- 🔒 **GUARANTEED**: Every release is testable before deployment

**3. Business Logic Testing (TDD Best Practice)**
```python
# Your business logic is fully testable
# Example: tests/test_user_authentication.py

def test_user_creation():
    """Test user creation through halfORM models."""
    user = User(
        username='john',
        email='john@example.com'
    ).insert()

    assert user.id is not None
    assert user.username == 'john'

def test_invalid_email_rejected():
    """Test validation prevents invalid emails."""
    with pytest.raises(ValidationError):
        User(username='john', email='invalid').insert()
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
┌───────────────────────────────────────────────────────┐
│ Development Cycle with Test Validation                │
├───────────────────────────────────────────────────────┤
│ 1. Create patch                                       │
│ 2. Write tests FIRST (TDD)                            │
│ 3. Implement feature                                  │
│ 4. Run tests locally: pytest                          │
│ 5. Add to release → AUTOMATIC VALIDATION              │
│    ├─ temp-valid branch created                       │
│    ├─ All patches merged                              │
│    ├─ pytest runs automatically                       │
│    └─ Only commits if tests PASS                      │
│ 6. Promote to RC → Tests validated again              │
│ 7. Deploy to prod → Tested code only                  │
└───────────────────────────────────────────────────────┘
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
- halfORM (`pip install halfORM`)

### Install

```bash
pip install half_orm_dev
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

### First Patch (Exploratory Development with TDD)

```bash
# Create patch FIRST (exploratory work)
half_orm dev patch new 001-users

# Write tests FIRST (TDD approach)
cat > tests/test_users.py << 'EOF'
def test_user_creation():
    """Test user creation."""
    user = User(username='alice').insert()
    assert user.id is not None
    assert user.username == 'alice'
EOF

# Add schema changes
echo "CREATE TABLE users (id SERIAL PRIMARY KEY, username TEXT);" > Patches/001-users/01_users.sql

# Apply and generate code
half_orm dev patch apply

# Run tests
pytest

# Commit your work
git add .
git commit -m "Add users table with tests"

# THEN prepare release when ready
git checkout ho-prod
half_orm dev release new minor

# Add to release (automatic validation runs here!)
half_orm dev patch add 001-users
```

## 💻 Development Workflow

### Complete Cycle: Patch → Release → Deploy

```
┌─────────────────────────────────────────────────────────────────┐
│ DEVELOPMENT (ho-prod branch)                                    │
├─────────────────────────────────────────────────────────────────┤
│ 1. patch new <id>          Create patch branch                  │
│ 2. patch apply             Apply & test changes                 │
│                                                                 │
│ RELEASE PREPARATION                                             │
│ 3. release new <level>     Prepare release container            │
│ 4. patch add <id>          Add to release (TESTS RUN HERE!)     │
│ 5. release promote rc      Create release candidate             │
│                                                                 │
│ PRODUCTION DEPLOYMENT                                           │
│ 6. release promote prod    Deploy to production                 │
│ 7. update                  Check available releases             │
│ 8. upgrade                 Apply on production servers          │
└─────────────────────────────────────────────────────────────────┘
```

### Workflow Details

#### Step 1: Create Patches (Exploratory Development)

```bash
# Create patch branch and directory
half_orm dev patch new 123-feature-name

# Now on ho-patch/123-feature-name branch
# Add SQL/Python files to Patches/123-feature-name/
```

#### Step 2: Develop and Test (TDD Approach)

```bash
# FIRST: Write tests
cat > tests/test_feature.py << 'EOF'
def test_feature():
    # Your test here
    assert True
EOF

# THEN: Apply patch (on ho-patch/* branch)
half_orm dev patch apply
# → Restores database from production state
# → Applies all release patches + current patch
# → Generates Python code
# → Ready for testing

# Run tests
pytest

# Commit your work
git add .
git commit -m "Implement feature with tests"
```

#### Step 3: Prepare Release Container (When Ready)

```bash
# When ready to integrate: Create the release file that will contain patches
half_orm dev release new patch   # Bug fixes (1.3.5 → 1.3.6)
half_orm dev release new minor   # New features (1.3.5 → 1.4.0)
half_orm dev release new major   # Breaking changes (1.3.5 → 2.0.0)

# This creates releases/X.Y.Z-stage.txt (empty, ready for patches)
```

#### Step 4: Add to Release (⚠️ AUTOMATIC VALIDATION HAPPENS HERE)

```bash
# Switch to ho-prod
git checkout ho-prod

# Add patch to prepared release
half_orm dev patch add 123-feature-name

# What happens automatically:
# 1. Creates temp-valid-1.3.6 branch
# 2. Merges ALL release patches
# 3. Merges YOUR patch
# 4. Runs pytest tests/
# 5. If PASS → commits to ho-prod, archives branch
# 6. If FAIL → cleanup, nothing committed, error reported

# Result:
# ✓ Patch validated with full integration
# ✓ Branch archived to ho-release/X.Y.Z/123-feature-name
# ✓ Only TESTED code in releases/X.Y.Z-stage.txt
```

#### Step 5: Promote to RC

```bash
# Create release candidate
half_orm dev release promote rc

# → Renames X.Y.Z-stage.txt → X.Y.Z-rc1.txt
# → Merges all patch code into ho-prod
# → Deletes patch branches (cleanup)
# → Notifies active branches to rebase
# → Automatically pushes to origin
```

#### Step 6: Deploy to Production

```bash
# After RC validation
half_orm dev release promote prod

# → Renames X.Y.Z-rc1.txt → X.Y.Z.txt
# → Generates schema-X.Y.Z.sql and metadata-X.Y.Z.sql
# → Updates schema.sql symlink
# → Commits and pushes to ho-prod automatically
```

#### Step 7/8: Production Upgrade

```bash
# On production server (automatically pulls from origin)
# Check available releases
half_orm dev update

# Apply upgrade (with automatic backup and git pull)
half_orm dev upgrade
```

## 📖 Command Reference

### Init & Clone

```bash
# Create new project
half_orm dev init <package_name> --database <db_name>

# Clone existing project (automatically pulls from origin)
half_orm dev clone <git_origin>
```

### Patch Commands

```bash
# Create new patch
half_orm dev patch new <patch_id> [-d "description"]

# Apply current patch (from ho-patch/* branch)
half_orm dev patch apply

# Add patch to stage release (AUTOMATIC VALIDATION!)
half_orm dev patch add <patch_id> [--to-version X.Y.Z]
```

### Release Commands

```bash
# Prepare next release (patch/minor/major)
half_orm dev release new patch
half_orm dev release new minor
half_orm dev release new major

# Promote stage to RC (automatically pushes)
half_orm dev release promote rc

# Promote RC to production (automatically pushes)
half_orm dev release promote prod
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

### Pattern 1: Exploratory Development with TDD

```bash
# Start exploring (no release needed yet)
half_orm dev patch new 123-add-users

# Write tests FIRST
cat > tests/test_users.py << 'EOF'
def test_user_creation():
    user = User(username='alice').insert()
    assert user.username == 'alice'
EOF

# Add SQL/Python files
echo "CREATE TABLE users (id SERIAL PRIMARY KEY, username TEXT);" > Patches/123-add-users/01_users.sql

# Apply and test
half_orm dev patch apply
pytest  # Tests should pass

# Commit your exploration
git add .
git commit -m "Explore users table design with tests"

# When satisfied, prepare release
git checkout ho-prod
half_orm dev release new minor

# Add to release (tests validated automatically!)
half_orm dev patch add 123-add-users
```

### Pattern 2: Planned Development

```bash
# Know what you want - prepare release first
half_orm dev release new minor

# Create patch
half_orm dev patch new 456-user-auth

# Develop with tests
# ... add files, write tests ...

# Apply and test locally
half_orm dev patch apply
pytest

# Add to release (automatic validation!)
git checkout ho-prod
half_orm dev patch add 456-user-auth
```

### Pattern 3: Team Collaboration

```bash
# Developer A: Working on feature
half_orm dev patch new 456-dashboard
# ... develop and test ...

# Developer B: Working on another feature
half_orm dev patch new 789-reports
# ... develop and test ...

# Integration Manager: Add both to release
git checkout ho-prod
half_orm dev patch add 456-dashboard  # Validates with tests
half_orm dev patch add 789-reports    # Validates 456 + 789 together!

# All patches validated together before RC
```

### Pattern 4: Multiple Stages

```bash
# Parallel development of different versions
# 1. Prepare multiple stages
half_orm dev release new minor  # Creates 1.4.0-stage
half_orm dev release new patch  # Creates 1.3.6-stage

# 2. Add patches to specific versions
half_orm dev patch add 123-hotfix --to-version="1.3.6"
half_orm dev patch add 456-feature --to-version="1.4.0"

# 3. Sequential promotion (must promote 1.3.6 before 1.4.0)
half_orm dev release promote rc  # Promotes 1.3.6-stage → 1.3.6-rc1
# ... validate ...
half_orm dev release promote prod  # 1.3.6-rc1 → 1.3.6.txt
# Now can promote 1.4.0
```

### Pattern 5: Incremental RC (Fix Issues)

```bash
# RC1 has issues discovered in testing
half_orm dev release promote rc  # Creates 1.3.5-rc1

# Found bug in testing, create fix patch
half_orm dev patch new 999-rc1-fix
half_orm dev patch apply
# ... fix and test ...

# Add to NEW stage (same version)
git checkout ho-prod
half_orm dev patch add 999-rc1-fix  # Validated automatically

# Promote again (creates rc2, automatically pushes)
half_orm dev release promote rc  # Creates 1.3.5-rc2

# Repeat until RC passes all validation
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
ho-prod (main)
├── ho-patch/123-feature    (development, temporary)
├── ho-patch/124-bugfix     (development, temporary)
└── ho-release/
    └── 1.3.5/
        ├── 123-feature     (archived after RC promotion)
        └── 124-bugfix      (archived after RC promotion)
```

**Branch types:**
- **ho-prod**: Main production branch (source of truth)
- **ho-patch/\***: Patch development branches (temporary, deleted after RC)
- **ho-release/\*/\***: Archived patch branches (history preservation)

### Release Files

```
releases/
├── 1.3.5-stage.txt    (development, mutable, not present if production ready)
├── 1.3.5-rc1.txt      (validation, immutable)
├── 1.3.5-rc2.txt      (fixes from rc1, immutable)
├── 1.3.5.txt          (production, immutable)
└── 1.3.6-stage.txt    (next development)
```

**File lifecycle:**
```
X.Y.Z-stage.txt → X.Y.Z-rc1.txt → X.Y.Z.txt
                       ↓
                  X.Y.Z-rc2.txt (if fixes needed)
```

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

1. **Sequential releases**: Must promote 1.3.5 before 1.3.6
2. **Single active RC**: Only one RC can exist at a time
3. **Branch cleanup**: Patch branches deleted when promoted to RC
4. **Database restore**: `patch apply` always restores from production state
5. **Immutable releases**: RC and production files never modified
6. **Automatic Git operations**: Push/pull handled by commands automatically
7. **⚠️ SYSTEMATIC TEST VALIDATION**: Tests run before ANY integration to stage

## 🔧 Troubleshooting

### Error: "Must be on ho-prod branch"

```bash
# Solution: Switch to ho-prod
git checkout ho-prod
```

### Error: "Must be on ho-patch/* branch"

```bash
# Solution: Create or switch to patch branch
half_orm dev patch new <patch_id>
# or
git checkout ho-patch/<patch_id>
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
git checkout ho-prod
half_orm dev patch add 123-feature  # Tests will run again
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
- Run `pytest` locally before `patch add`

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
- **Full Documentation**: `docs/half_orm_dev.md`
- **Development Methodology**: `docs/METHODOLOGY.md`
- **Development Log**: `docs/dev_log.md`
- **API Reference**: `python-docs/`

## 🤝 Contributing

Contributions are welcome! Please read our contributing guidelines and submit pull requests to our repository.

### Development Setup

```bash
# Clone repository
git clone https://github.com/halfORM/half_orm_dev.git
cd half_orm_dev

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

- **Issues**: [GitHub Issues](https://github.com/halfORM/half_orm_dev/issues)
- **Documentation**: [docs/](docs/)
- **halfORM**: [halfORM Documentation](https://github.com/halfORM/halfORM)

## 📄 License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

---

**Version**: 0.16.0
**halfORM**: Compatible with halfORM 0.16.x
**Python**: 3.8+
**PostgreSQL**: Tested with 13+ (might work with earlier versions)

Made with ❤️ by the halfORM team
