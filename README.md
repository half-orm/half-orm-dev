# half-orm-dev

## **WARNING!** half-orm-dev is in alpha development phase!

> **Please report any issues at [GitHub Issues](https://github.com/half-orm/half-orm-dev/issues)**

**Git-centric patch management and PostgreSQL database versioning for half-orm projects**

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: GPLv3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![half-orm](https://img.shields.io/badge/halfORM-compatible-green.svg)](https://github.com/half-orm/half-orm)
[![PyPI Downloads](https://static.pepy.tech/personalized-badge/half-orm-dev?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=downloads)](https://pepy.tech/projects/half-orm-dev)

Modern development workflow for PostgreSQL databases with automatic code generation, semantic versioning, and production-ready deployment system.

---

## 📖 What is half-orm-dev?

`half-orm-dev` provides a complete development lifecycle for database-driven applications:

- **Git-centric workflow**: Patches stored in Git branches with semantic versioning
- **Test-Driven Development**: **Automatic validation** - tests run before integration, patches blocked if tests fail
- **Code generation**: Python classes auto-generated from schema changes
- **Data bootstrapping**: Initialize reference data and configurations with tracked scripts
- **Safe deployments**: Sequential releases with automatic backups and validation
- **Team collaboration**: Distributed locks, branch management, conflict prevention
- **Cloud-friendly**: No superuser privileges required (works on AWS RDS, Azure, GCP)

Perfect for teams managing evolving PostgreSQL schemas with Python applications.

---

## ✨ Key Features

### 🧪 Systematic Test Validation (Core Safety Feature)

**Tests run automatically before patch integration and block merges if they fail.**

```bash
# When you merge a patch, half-orm-dev:
git checkout ho-patch/123-feature
half_orm dev patch merge

# Behind the scenes:
# 1. Creates temporary validation branch
# 2. Restores database from production schema
# 3. Applies ALL release patches sequentially
# 4. Runs pytest automatically
# 5. ✅ If PASS → merges into release, status → "staged"
# 6. ❌ If FAIL → nothing committed, temp branch deleted
```

**Benefits:**
- ✅ Catch integration issues early
- ✅ Prevent regressions automatically
- ✅ Only validated code reaches production
- ✅ Full release context testing (all patches together)

**Cannot be disabled** - it's a core safety feature.

### 🔧 Development Workflow

- **Patch-based development**: Isolated branches for each database change
- **Automatic code generation**: half-orm Python classes from schema
- **Complete testing**: Apply patches with full release context
- **Conflict detection**: Distributed locks prevent concurrent modifications

### 📦 Release Management

- **Semantic versioning**: patch/minor/major increments
- **Sequential promotion**: stage → rc → production workflow
- **Release candidates**: RC validation before production
- **Hotfix support**: Reopen last released version for urgent fixes
- **Branch cleanup**: Automatic deletion after promotion

### 🚀 Production

- **Safe upgrades**: Automatic database backups before changes
- **Incremental deployment**: Apply releases sequentially
- **Version tracking**: Complete release history
- **Cloud-compatible**: No superuser privileges required

---

## 🚀 Installation

### Prerequisites

- **Python**: [Active versions](https://devguide.python.org/versions/) (currently 3.9+)
- **PostgreSQL**: [Supported versions](https://www.postgresql.org/support/versioning/) (currently 13+)
- **Git** for version control

### Install

```bash
pip install half-orm-dev
```

### Verify Installation

```bash
half_orm dev --help
```

---

## 📖 Quick Start

### Initialize New Project

```bash
# Create project with database (requires git origin)
half_orm dev init myproject --database mydb --git-origin git@github.com:user/myproject.git
cd myproject
```

### Clone Existing Project

```bash
# Clone from Git
half_orm dev clone https://github.com/user/project.git
cd project
```

### Basic Development Workflow

```bash
# 1. Create a release (integration branch)
half_orm dev release create minor  # Creates ho-release/0.1.0

# 2. Create a patch
half_orm dev patch create 1-users
# → Creates ho-patch/1-users branch
# → Auto-added to 0.1.0-patches.toml as "candidate"

# 3. Add schema changes
echo "CREATE TABLE users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    username TEXT NOT NULL
);" > Patches/1-users/01_users.sql

# 4. Apply patch (generates Python code)
half_orm dev patch apply
# → Restores database from production state
# → Applies SQL patches
# → Generates Python classes (mydb/public/user.py)

# 5. Write tests (TDD approach)
cat > tests/public/user/test_user_logic.py << 'EOF'
from mydb.public.user import User

def test_user_creation():
    """Test user creation business logic."""
    user = User(username='alice').ho_insert()
    assert user['username'] == 'alice'
    assert user['id'] is not None
EOF

# 6. Run tests locally
pytest

# 7. Commit your work
git add .
git commit -m "Add users table with tests"

# 8. Merge patch - AUTOMATIC VALIDATION!
git checkout ho-patch/1-users
half_orm dev patch merge
# → Creates temp validation branch
# → Runs pytest automatically
# → If tests pass: merges into ho-release/0.1.0, status → "staged"
# → If tests fail: aborts, nothing committed

# 9. Promote to production
half_orm dev release promote rc    # Optional: create release candidate
half_orm dev release promote prod  # Merge to ho-prod + create tag
```

---

## 💻 Core Workflow

### Branch Strategy

```
ho-prod (main production branch)
│
├── ho-release/0.17.0 (integration branch, deleted after prod)
│   ├── ho-patch/6-feature-x    (temporary, deleted after merge)
│   ├── ho-patch/7-bugfix-y     (temporary, deleted after merge)
│   └── ho-patch/8-auth-z       (temporary, deleted after merge)
│
└── ho-release/0.18.0 (next version in parallel)
    └── ho-patch/10-new-api     (temporary, deleted after merge)
```

**Branch Types:**
- **ho-prod**: Stable production branch (source of truth)
- **ho-release/X.Y.Z**: Integration branches (temporary)
- **ho-patch/ID**: Patch development branches (temporary)

### Release Files

```
.hop/releases/
├── 0.17.0-patches.toml    # Development (mutable: candidate/staged status)
├── 0.17.0-rc1.txt         # Release candidate snapshot (immutable)
├── 0.17.0.txt             # Production snapshot (immutable)
├── 0.17.0-hotfix1.txt     # Hotfix snapshot (immutable)
└── 0.18.0-patches.toml    # Next version in progress
```

**Patch States:**
1. **candidate**: In development (`"patch-id" = "candidate"` in TOML)
2. **staged**: Integrated, awaiting promotion (`"patch-id" = "staged"` in TOML)
3. **released**: Deployed to production (in `X.Y.Z.txt` snapshot)

### Development Cycle

```
┌─────────────────────────────────────────────────────────────┐
│ DEVELOPMENT WORKFLOW                                        │
├─────────────────────────────────────────────────────────────┤
│ 1. release create <level>     Create ho-release/X.Y.Z       │
│ 2. patch create <id>       Create patch (auto-candidate)    │
│ 3. patch apply             Apply & test changes             │
│ 4. patch merge             Merge into release (TESTS!)      │
│                            ✅ Tests pass → integrated       │
│                            ❌ Tests fail → aborted          │
│                                                             │
│ RELEASE PROMOTION                                           │
│ 5. release promote rc      Create RC (optional)             │
│ 6. release promote prod    Merge to ho-prod + deploy        │
│                                                             │
│ PRODUCTION DEPLOYMENT                                       │
│ 7. update                  Check available releases         │
│ 8. upgrade                 Apply on production servers      │
│                                                             │
│ HOTFIX (urgent production fix)                              │
│ 9. release hotfix          Reopen last released version     │
│10. patch create/merge      Fix and validate                 │
│11. release promote hotfix  Deploy hotfix                    │
└─────────────────────────────────────────────────────────────┘
```

---

## 📖 Command Reference

### Init & Clone

```bash
# Create new project (requires git origin)
half_orm dev init <package_name> --git-origin <url>

# Clone existing project
half_orm dev clone <git_origin>
```

### Check

```bash
# Verify and update project configuration
half_orm dev check

# Preview what would be done
half_orm dev check --dry-run
```

**Note:** This command runs automatically before other commands (git hooks, configuration, stale branches cleanup).

### Release Commands

A release must be created before creating patches.

```bash
# Create new release (must be on ho-prod branch)
half_orm dev release create patch   # X.Y.(Z+1)
half_orm dev release create minor   # X.(Y+1).0
half_orm dev release create major   # (X+1).0.0

# Promote to release candidate (optional)
half_orm dev release promote rc

# Promote to production
half_orm dev release promote prod

# Hotfix workflow
half_orm dev release hotfix           # Reopen production version
half_orm dev release promote hotfix   # Deploy hotfix
```

### Patch Commands

```bash
# Create new patch (must be on ho-release/* branch)
half_orm dev patch create <patch_id>

# Apply current patch (must be on ho-patch/* branch)
half_orm dev patch apply

# Merge patch into release (AUTOMATIC VALIDATION!)
# Must be on ho-patch/* branch
half_orm dev patch merge
```

**Tip:** Patch IDs must start with a number (e.g., `123-add-users`). This number automatically closes the corresponding GitHub/GitLab issue #123 when the patch is merged.

**Patch files:** SQL (`.sql`) or Python (`.py`) files in `Patches/<patch_id>/`, executed in lexicographic order.

### Production Commands

```bash
# Check available releases
half_orm dev update

# Apply releases to production
half_orm dev upgrade [--to-release X.Y.Z]

# Dry run (simulate upgrade)
half_orm dev upgrade --dry-run
```

### Data Bootstrap

Mark patch files with `-- @HOP:bootstrap` (SQL) or `# @HOP:bootstrap` (Python) to declare reference data:

```sql
-- @HOP:bootstrap
INSERT INTO roles (name) VALUES ('admin'), ('user') ON CONFLICT DO NOTHING;
```

These files are automatically:
- Copied to `bootstrap/` during `patch merge`
- Executed during production `upgrade`
- Tracked in database (each script runs once)

**Note:** Use `half_orm dev <command> --help` for detailed help on each command.

---

## 🎯 Example: Team Collaboration

```bash
# Integration Manager: Create release
half_orm dev release create minor  # Creates ho-release/0.17.0

# Developer A: Work on feature
git checkout ho-release/0.17.0
half_orm dev patch create 456-dashboard
# ... develop and test ...
git checkout ho-patch/456-dashboard
half_orm dev patch merge  # Tests run automatically
# → Status: "staged" in 0.17.0-patches.toml

# Developer B: Sync and create patch
git checkout ho-release/0.17.0
git pull origin ho-release/0.17.0  # Get A's changes
half_orm dev patch create 789-reports
# ... develop and test ...
git merge origin/ho-release/0.17.0  # Sync again
git checkout ho-patch/789-reports
half_orm dev patch merge
# → Tests run with BOTH 456 + 789 together!
# → Both validated in full release context
```

---

## 🎓 Development Philosophy

half-orm-dev combines **Domain-Driven Design** with **Test-Driven Development**, integrated into Git:

1. **Schema as domain model** - The PostgreSQL schema defines your domain; Python classes are auto-generated
2. **Write tests first** - Define expected behavior before implementation
3. **Develop in isolation** - Each patch has its own branch and directory
4. **Validate automatically** - Tests run during `patch merge`, blocking integration if they fail
5. **Deploy with confidence** - Only validated code reaches production

This approach ensures that every schema change is tested in the full release context before integration.

---

## 📚 Documentation

- **[CONTRIBUTING.md](CONTRIBUTING.md)** - Development setup, testing, contribution guidelines
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** - Technical architecture and implementation details
- **[CLAUDE.md](CLAUDE.md)** - Quick reference for Claude Code CLI

For detailed technical documentation, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## 🔧 Troubleshooting

### Error: "Must be on ho-release/* branch"
```bash
# Create release or switch to release branch
half_orm dev release create minor
# or
git checkout ho-release/0.17.0
```

### Error: "Must be on ho-patch/* branch"

```bash
# Solution: Create or switch to patch branch
# First ensure you're on ho-release/*
git checkout ho-release/0.17.0
half_orm dev patch create <patch_id>
# or
git checkout ho-patch/<patch_id>
```

### Error: "Patch not found in candidates file"

```bash
# Solution: Patch must be created from ho-release/* branch
# to be automatically added to candidates
git checkout ho-release/0.17.0
half_orm dev patch create <patch_id>
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

### Error: "No staged releases found"

```bash
# Solution: Create a release first
half_orm dev release create patch
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
# Fix tests or code, then retry
half_orm dev patch apply  # Test locally first
pytest  # Verify tests pass

# Fix issues
vim Patches/123-feature/01_schema.sql
vim tests/test_feature.py

# Try again
git checkout ho-patch/123-feature
half_orm dev patch merge  # Tests will run again
```

For more troubleshooting, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## 🤝 Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

**Quick start for contributors:**

```bash
# Clone repository
git clone https://github.com/half-orm/half-orm-dev.git
cd half-orm-dev

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install in development mode
pip install -e .

# Run tests
pytest                      # All tests
pytest -m "not integration" # Unit tests only
pytest -m integration       # Integration tests only
```

---

## 📞 Getting Help

- **Issues**: [GitHub Issues](https://github.com/half-orm/half-orm-dev/issues)
- **Documentation**: [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- **half-orm**: [half-orm Documentation](https://half-orm.github.io/half-orm/latest/)

---

## 📄 License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

---

**Made with ❤️ by the half-orm team**
