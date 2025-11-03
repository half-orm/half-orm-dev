# half_orm_dev

## **WARNING!** half_orm_dev is still in alpha development phase!

**Git-centric patch management and database versioning for halfORM projects**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![halfORM](https://img.shields.io/badge/halfORM-compatible-green.svg)](https://github.com/halfORM/halfORM)

Modern development workflow for PostgreSQL databases with automatic code generation, semantic versioning, and production-ready deployment system.

## 📖 Description

`half_orm_dev` provides a complete development lifecycle for database-driven applications:
- **Git-centric workflow**: Patches stored in Git branches and release files
- **Semantic versioning**: Automatic version calculation (patch/minor/major)
- **Code generation**: Python classes auto-generated from schema changes
- **Safe deployments**: Automatic backups, rollback support, validation
- **Team collaboration**: Distributed locks, branch notifications, conflict prevention

Perfect for teams managing evolving PostgreSQL schemas with Python applications.

## ✨ Features

### 🔧 Development
- **Patch-based development**: Isolated branches for each database change
- **Automatic code generation**: halfORM Python classes created from schema
- **Complete testing**: Apply patches with full release context
- **Conflict detection**: Distributed locks prevent concurrent modifications

### 📦 Release Management
- **Semantic versioning**: patch/minor/major increments
- **Release candidates**: RC validation before production
- **Sequential promotion**: stage → rc → production workflow
- **Branch cleanup**: Automatic deletion after RC promotion

### 🚀 Production
- **Safe upgrades**: Automatic database backups before changes
- **Incremental deployment**: Apply releases sequentially
- **Dry-run mode**: Preview changes before applying
- **Version tracking**: Complete release history in database

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

### First Patch

```bash
# Prepare release (FIRST - create the container)
half_orm dev release new minor

# Create patch (THEN - create the feature)
half_orm dev patch new 001-users

# Add schema changes
echo "CREATE TABLE users (id SERIAL PRIMARY KEY, username TEXT);" > Patches/001-users/01_users.sql

# Apply and generate code
half_orm dev patch apply

# Test
pytest

# Add to release
git checkout ho-prod
half_orm dev patch add 001-users
```

## 💻 Development Workflow

### Complete Cycle: Release → Patch → Deploy

```
┌─────────────────────────────────────────────────────────────────┐
│ DEVELOPMENT (ho-prod branch)                                    │
├─────────────────────────────────────────────────────────────────┤
│ 1. patch new <id>          Create patch branch                  │
│ 2. patch apply             Apply & test changes                 │
│                                                                 │
│ RELEASE PREPARATION                                             │
│ 3. release new <level>     Prepare release container            │
│ 4. patch add <id>          Add to prepared release              │
│ 5. release promote rc      Create release candidate             │
│                                                                 │
│ PRODUCTION DEPLOYMENT                                           │
│ 6. release promote prod    Deploy to production                 │
│ 7. db upgrade              Apply on production servers          │
└─────────────────────────────────────────────────────────────────┘
```

### Workflow Details

#### Step 1: Prepare Release Container

```bash
# FIRST: Create the release file that will contain patches
half_orm dev release new patch   # Bug fixes (1.3.5 → 1.3.6)
half_orm dev release new minor   # New features (1.3.5 → 1.4.0)
half_orm dev release new major   # Breaking changes (1.3.5 → 2.0.0)

# This creates releases/X.Y.Z-stage.txt (empty, ready for patches)
```

#### Step 2: Create Patches

```bash
# Create patch branch and directory
half_orm dev patch new 123-feature-name

# Now on ho-patch/123-feature-name branch
# Add SQL/Python files to Patches/123-feature-name/
```

#### Step 3: Develop and Test

```bash
# Apply patch (on ho-patch/* branch)
half_orm dev patch apply
# → Restores database from production state
# → Applies all release patches + current patch
# → Generates Python code
# → Ready for testing

# Run tests
pytest

# Commit your work
git add .
git commit -m "Implement feature"
```

#### Step 4: Add to Release

```bash
# Switch to ho-prod
git checkout ho-prod

# Add patch to prepared release
half_orm dev patch add 123-feature-name

# Patch is now in releases/X.Y.Z-stage.txt
# Branch archived to ho-release/X.Y.Z/123-feature-name
```

#### Step 5: Promote to RC

```bash
# Create release candidate
half_orm dev release promote rc

# → Renames X.Y.Z-stage.txt → X.Y.Z-rc1.txt
# → Merges all patch code into ho-prod
# → Deletes patch branches (cleanup)
# → Notifies active branches to rebase
```

#### Step 6: Deploy to Production

```bash
# After RC validation
half_orm dev release promote prod

# → Renames X.Y.Z-rc1.txt → X.Y.Z.txt
# → Generates schema-X.Y.Z.sql and metadata-X.Y.Z.sql
# → Updates schema.sql symlink
# → Commits to ho-prod
```

#### Step 7: Production Upgrade

```bash
# On production server
git checkout ho-prod
git pull

# Check available releases
half_orm dev db update

# Apply upgrade (with automatic backup)
half_orm dev db upgrade
```

## 📖 Command Reference

### Init & Clone

```bash
# Create new project
half_orm dev init <package_name> --database <db_name>

# Clone existing project
half_orm dev clone <git_origin>
```

### Patch Commands

```bash
# Create new patch
half_orm dev patch new <patch_id> [-d "description"]

# Apply current patch (from ho-patch/* branch)
half_orm dev patch apply

# Add patch to stage release
half_orm dev patch add <patch_id> [--to-version X.Y.Z]
```

### Release Commands

```bash
# Prepare next release (patch/minor/major)
half_orm dev release new patch
half_orm dev release new minor
half_orm dev release new major

# Promote stage to RC
half_orm dev release promote rc

# Promote RC to production
half_orm dev release promote prod
```

### Database Commands (Production)

```bash
# Fetch available releases
half_orm dev db update

# Apply releases to production
half_orm dev db upgrade [--to-release X.Y.Z]

# Dry run (simulate upgrade)
half_orm dev db upgrade --dry-run
```

## 🎯 Common Patterns

### Pattern 1: Single Patch Development

```bash
# Prepare release FIRST
half_orm dev release new minor

# Create patch
half_orm dev patch new 123-add-users

# Add SQL/Python files
echo "CREATE TABLE users (id SERIAL PRIMARY KEY);" > Patches/123-add-users/01_users.sql

# Apply and test
half_orm dev patch apply
pytest

# Commit
git add .
git commit -m "Implement users table"

# Add to release
git checkout ho-prod
half_orm dev patch add 123-add-users
```

### Pattern 2: Multiple Patches in Parallel

```bash
# Prepare release ONCE
half_orm dev release new minor

# Developer A creates patch 001
half_orm dev patch new 001-auth
# ... develop and test ...
git checkout ho-prod
half_orm dev patch add 001-auth

# Developer B creates patch 002 (parallel development)
half_orm dev patch new 002-reporting
# ... develop and test ...
git checkout ho-prod
half_orm dev patch add 002-reporting

# Both patches in same release
half_orm dev release promote rc
```

### Pattern 3: Complete Release Cycle

```bash
# 1. Prepare release
half_orm dev release new minor

# 2. Add multiple patches
half_orm dev patch add 123-users
half_orm dev patch add 124-posts
half_orm dev patch add 125-comments

# 3. Promote to RC
half_orm dev release promote rc

# 4. Test RC thoroughly
# ... integration tests ...

# 5. Deploy to production
half_orm dev release promote prod

# 6. Tag release
git tag v1.4.0
git push --tags
```

### Pattern 4: Incremental RC (Fix Issues)

```bash
# RC1 has issues
half_orm dev release promote rc  # Creates 1.3.5-rc1

# Found bug, create fix patch
half_orm dev patch new 999-rc1-fix
half_orm dev patch apply
# ... fix and test ...

# Add to NEW stage (same version)
git checkout ho-prod
half_orm dev patch add 999-rc1-fix

# Promote again (creates rc2)
half_orm dev release promote rc  # Creates 1.3.5-rc2

# Repeat until RC passes
```

### Pattern 5: Production Deployment

```bash
# On production server
git checkout ho-prod
git pull

# Check available releases
half_orm dev db update

# Simulate upgrade
half_orm dev db upgrade --dry-run

# Apply upgrade (creates backup automatically)
half_orm dev db upgrade

# Or apply specific version
half_orm dev db upgrade --to-release 1.4.0
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
├── 1.3.5-stage.txt    (development, mutable)
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
# Solution: Pull latest changes
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
git pull
```

## 🎓 Best Practices

### Patch Development

✅ **DO:**
- Prepare release BEFORE creating patches
- Use descriptive patch IDs: `123-add-user-authentication`
- Test patches thoroughly before adding to release
- Keep patches focused (one feature per patch)
- Commit generated code with meaningful messages

❌ **DON'T:**
- Create patches without prepared release
- Mix multiple features in one patch
- Skip `patch apply` validation
- Add untested patches to release
- Modify files outside your patch directory

### Release Management

✅ **DO:**
- Prepare releases at the START of development cycle
- Test RC thoroughly before promoting to production
- Use semantic versioning consistently
- Tag production releases: `git tag v1.4.0`
- Document breaking changes in commit messages

❌ **DON'T:**
- Skip RC validation (always test before prod)
- Promote multiple RCs simultaneously
- Skip backup creation in production
- Force promote without fixing issues

### Production Deployment

✅ **DO:**
- Always run `db update` first to check available releases
- Use `--dry-run` to preview changes
- Verify backups exist before upgrade
- Monitor application after deployment
- Schedule deployments during low-traffic periods

❌ **DON'T:**
- Deploy without testing in RC first
- Skip backup verification
- Deploy during peak usage hours
- Ignore upgrade warnings
- Apply patches directly without releases

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
half_orm dev db --help

# Specific command help
half_orm dev patch new --help
half_orm dev release promote --help
```

### Support

- **Issues**: [GitHub Issues](https://github.com/halfORM/half_orm_dev/issues)
- **Documentation**: [docs/](docs/)
- **halfORM**: [halfORM Documentation](https://github.com/halfORM/halfORM)

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

**Version**: 0.16.0  
**halfORM**: Compatible with halfORM 0.16.x 
**Python**: 3.8+
**PostgreSQL**: tested with 13+ (might work with earlier versions)

Made with ❤️ by the halfORM team