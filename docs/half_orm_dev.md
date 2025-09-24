# half-orm-dev - Git-Centric Documentation

## Overview

half-orm-dev is a Git-centric SQL patch management system for halfORM using an ultra-simplified approach. It manages database schema evolution in a controlled and traceable manner with direct patch development and flexible release composition.

## Core Principles

### 1. Git as Single Source of Truth
- **File-based releases** - `releases/X.Y.Z.txt` files contain patch lists
- **Chronological order** determined by Git history
- **Standard Git workflow** for all modifications

### 2. Ultra-Simplified Workflow
```
Patch Development → Release Integration → Production
create-patch → add-to-release → deploy-to-prod
```

### 3. Minimal Branch Architecture
- **ho-prod**: Production and main branch (always at latest applicable version)
- **ho-patch/patch-name**: Individual patch development branches (for all types of changes)

### 4. Unified Development Process
- All changes (features, fixes, security, performance) follow the same workflow
- Emergency fixes handled via hotfix mechanism for critical situations
- Direct development on patch branches, no intermediate containers

### 5. Version 0 - Evolutionary Metadata Base
- **Initial version 0.0.0**: When creating the project, generates a base version containing only half-orm-dev metadata
- **Evolutionary base**: `model/schema.sql` always points to the latest production version
- **Metadata only**: No business data, only base structure + half-orm-dev metadata
- **Universal starting point**: All patch branches start from current production state

### 6. Multi-Environment Support with Release Stages
- **Stage releases**: `releases/X.Y.Z-stage.txt` for development and staging validation
- **Release Candidates**: `releases/X.Y.Z-rc1.txt`, `releases/X.Y.Z-rc2.txt` for production validation
- **Production releases**: `releases/X.Y.Z.txt` for final deployment
- **Hotfix releases**: `releases/X.Y.Z-hotfix1.txt` for emergency fixes
- **Sequential promotion**: stage → rc → production with validation at each step

### 7. Single Active Development Branch
- **One active release at a time**: Only one RC can exist at any moment
- **Sequential requirement**: RC must be promoted to production before next RC creation
- **No parallel RCs**: Cannot have 1.3.4-rc1 and 1.4.0-rc1 simultaneously
- **Clear progression**: Ensures focused development and testing efforts

### 8. Developer Responsibility for Conflicts
- **No automatic conflict detection**: System does not prevent or detect patch conflicts
- **Manual conflict resolution**: Developers responsible for ensuring patch compatibility
- **Error-based feedback**: Conflicts discovered during patch application or testing
- **No patch dependencies**: System does not enforce or track patch dependencies
- **Team coordination**: Development teams manage patch interactions manually

### 9. Automatic Branch Lifecycle Management
- **Development phase**: Branches preserved for modifications and rollbacks during stage development
- **Release Candidate**: Branches automatically deleted when stage is promoted to RC (immutable releases)
- **Emergency situations**: `remove-from-release` command available only for stage releases

## Branch Flow Diagram

```
Timeline:    0.0.0 ──→ 0.1.0 ──→ 1.0.0 ──→ 1.3.0 ──→ 1.3.1 ──→ 1.3.2 ──→ 1.3.3 ──→ 1.3.4

ho-prod:     ●─────────●─────────●─────────●─────────●─────────●─────────●─────────●
                       │         │         │                   │                   │
                       └─ho-patch/234-performance──────────────┘                   |
                                 |         |                                       |
                                 └─ho-patch/456-feature────────────────────────────┤
                                           |                                       |
                                           └─ho-patch789-security──────────────────┘

Hotfix Flow:
ho-prod (1.3.4) ─→ ho-patch/critical-fix ─→ 1.3.4-hotfix1 ─→ auto-integration to 1.3.5-stage

Release Flow with Single File Evolution:
releases/1.3.4-stage.txt → git mv → 1.3.4-rc1.txt → git mv → 1.3.4.txt
(development)                      (validation)              (production)
                                   ↑ branches deleted       

Git History Preservation:
- Complete audit trail via git log --follow
- Single file evolution reduces duplication
- Natural progression tracking

Legend:
● = Applied release in production
─ = Patch development from ho-prod base
┘ = Patch integration into release and merge to ho-prod
┘ = Branch deletion point (promote-to-rc)
```

### Branch States and Lifecycle

```
Branch States:
- DEVELOPMENT: ho-patch/* (individual patch development, preserved until RC promotion)
- INTEGRATED: Patch merged to ho-prod and included in stage release file
- FROZEN: Patch in RC release (branches deleted, immutable)
- DEPLOYED: Release applied to production database

Patch Lifecycle:
ho-patch/patch-name (DEVELOPMENT) → add-to-release → ho-patch/patch-name (INTEGRATED) → promote-to-rc → (BRANCHES DELETED) → deploy-to-prod → (DEPLOYED)

Release Lifecycle:
X.Y.Z-stage (DEVELOPMENT) → promote-to-rc → X.Y.Z-rc1 (VALIDATION) → promote-to-prod → X.Y.Z (PRODUCTION)

Single Active Development Rule:
ONLY ONE RC can exist at any time
RC must be promoted to production before creating next RC
Example: 1.3.4-rc1 must become 1.3.4.txt before 1.3.5-rc1 can be created

Branch Cleanup:
Stage releases: Branches preserved (mutable, remove-from-release possible)
RC promotion: All branches from stage release automatically deleted
Production: No branches exist (immutable releases only)
```

## Emergency Hotfix Management

### Hotfix Workflow for Critical Issues

#### Creating and Deploying Hotfixes
```bash
# Emergency situation requiring immediate fix
half_orm dev create-hotfix "critical-security-fix"
# → Creates ho-patch/critical-security-fix from current ho-prod
# → Creates releases/1.3.4-hotfix1.txt (if current prod = 1.3.4)
# → Bypasses normal release sequence for emergency deployment

# Development process (same as normal patches)
half_orm dev apply-patch
# → Apply and test hotfix in isolation

half_orm dev test
# → Run complete test suite

# Integration to hotfix release
half_orm dev add-to-hotfix "critical-security-fix"
# → Merge ho-patch/critical-security-fix → ho-prod
# → Add to releases/1.3.4-hotfix1.txt
# → Delete branch immediately (emergency deployment workflow)
# → Commit: "Add critical-security-fix to hotfix release 1.3.4-hotfix1"

# Immediate deployment
half_orm dev deploy-to-prod "1.3.4-hotfix1"
# → Deploy hotfix immediately to production
# → Production version remains 1.3.4 (with hotfix applied)
# → Create backup: backups/1.3.4.sql (pre-hotfix state)
```

#### Hotfix Numbering and Sequencing
```bash
# Multiple hotfixes on same production version:
releases/1.3.4-hotfix1.txt  # First emergency fix
releases/1.3.4-hotfix2.txt  # Second emergency fix (based on hotfix1)
releases/1.3.4-hotfix3.txt  # Third emergency fix (based on hotfix2)

# Automatic integration into normal sequence:
# When 1.3.5-stage is created, all 1.3.4 hotfixes are automatically included
# since they are part of ho-prod history
```

#### Hotfix vs Normal Release Priority
```bash
# Normal development continues in parallel:
releases/1.3.5-stage.txt:   # Normal development (includes hotfixes automatically)
  - 456-user-dashboard
  - 789-performance-improvement
  - critical-security-fix    # Auto-included from hotfix
  - other-security-fix       # Auto-included from hotfix2

# Emergency takes precedence:
# 1.3.4-hotfix1 can be deployed immediately
# while 1.3.5-stage continues development
```

## Technical Architecture

### Branch-Based Patch Development

#### Individual Patch Branches (`ho-patch/patch-name`)
- **Format**: `ho-patch/456-user-authentication`
- **Usage**: Develop complete patches (schema + code + tests)
- **Base**: Always created from current ho-prod state
- **Visibility**: Remote branch visible to all developers
- **Conflict Detection**: Git native error if branch already exists
- **Lifecycle**: Preserved until promote-to-rc, then automatically deleted

### Release Files Structure with Stage Evolution

#### Single evolving release file per version
```
releases/
├── 1.3.3.txt                  # Production release (deployed)
├── 1.3.4.txt                  # Production release (current)
├── 1.3.4-hotfix1.txt          # Emergency hotfix
├── 1.3.5-stage.txt            # Stage release (in development)
└── README.md                  # Documentation

# File evolution through git mv:
# 1.3.5-stage.txt → 1.3.5-rc1.txt → 1.3.5-rc2.txt → 1.3.5.txt
# Git preserves complete history with --follow
# Branches deleted at stage → rc1 transition
```

#### File evolution example with branch cleanup
```bash
# Stage development (branches preserved)
releases/1.3.5-stage.txt:
456-user-authentication      # ho-patch/456-user-authentication exists
789-security-fix            # ho-patch/789-security-fix exists

# Promotion to RC (branches deleted)
half_orm dev promote-to-rc
# → git mv releases/1.3.5-stage.txt releases/1.3.5-rc1.txt
# → Automatic cleanup: 
#   git branch -d ho-patch/456-user-authentication
#   git push origin --delete ho-patch/456-user-authentication
#   git branch -d ho-patch/789-security-fix
#   git push origin --delete ho-patch/789-security-fix

# RC with additional fix (new branch required)
half_orm dev create-patch "999-rc1-bugfix"
half_orm dev add-to-release-rc "999-rc1-bugfix"
# → git mv releases/1.3.5-rc1.txt releases/1.3.5-rc2.txt
# → Add 999-rc1-bugfix to content
# → Delete ho-patch/999-rc1-bugfix immediately (RC immutable)

# Final production release (no branches exist)
git mv releases/1.3.5-rc2.txt releases/1.3.5.txt
```

### Directory Structure

#### On production branch (ho-prod) - Main Branch
```
model/
└── schema.sql              # Clean schema for new production instances

releases/
├── 1.3.3.txt               # Production releases
├── 1.3.4-hotfix1.txt       # Hotfix releases
├── 1.3.4-rc1.txt           # Release candidates
├── 1.3.5-stage.txt         # Stage releases
├── 2.0.0-stage.txt
└── README.md

Patches/
├── 456-user-authentication/    # Complete integrated patches
│   ├── README.md
│   ├── 01_create_user_table.sql
│   ├── 02_add_indexes.sql
│   └── 03_update_permissions.py
├── 789-security-fix/           # Security patches (same workflow)
│   ├── README.md
│   └── 01_fix_sql_injection.sql
├── critical-security-fix/      # Hotfix patches (same structure)
│   ├── README.md
│   └── 01_patch_vulnerability.sql
└── 234-performance-optimization/
    ├── README.md
    ├── 01_add_indexes.sql
    └── 02_optimize_queries.sql

<dbname>/                   # halfORM generated structure
├── <dbname>/               # Database package
│   ├── public/             # public schema
│   │   ├── user.py         # Generated halfORM classes
│   │   ├── order.py
│   │   └── __init__.py
│   ├── auth/               # auth schema (if exists)
│   │   ├── session.py
│   │   └── __init__.py
│   └── __init__.py
└── tests/                  # Generated halfORM tests
    ├── public/
    │   ├── test_user.py
    │   ├── test_order.py
    │   └── __init__.py
    ├── auth/
    │   ├── test_session.py
    │   └── __init__.py
    └── __init__.py

README.md                   # Project documentation
.gitignore                  # Git configuration
pyproject.toml              # Project configuration
```

#### On individual patch branches (ho-patch/456-user-authentication)
```
Patches/
└── 456-user-authentication/    # Only this patch during development
    ├── README.md
    ├── 01_create_user_table.sql
    ├── 02_add_indexes.sql
    └── 03_update_permissions.py

<dbname>/                   # halfORM structure (inherited + new)
└── <dbname>/
    ├── public/
    │   ├── user.py         # Generated class + custom methods
    │   ├── order.py        # Existing classes
    │   └── __init__.py
    ├── auth/               # New schema from this patch
    │   ├── session.py      # New generated class
    │   └── __init__.py
    └── __init__.py
└── tests/                  # Tests
    ├── public/
    │   ├── test_user.py    # Generated + custom tests
    │   ├── test_order.py
    │   └── __init__.py
    ├── auth/
    │   ├── test_session.py
    │   └── __init__.py
    └── __init__.py

README.md                   # Project documentation (inherited)
.gitignore                  # Git configuration (inherited)
pyproject.toml              # Project configuration (inherited)
```

**Patch Development Process:**
1. **Schema modifications**: SQL/Python files in Patches/patch-name/
2. **Code generation**: halfORM classes updated automatically in `<dbname>/<dbname>/<schemaname>/` structure
3. **Business logic**: Custom methods added to generated classes
4. **Testing**: Complete test suite for the patch functionality
5. **Integration**: Patch merged to ho-prod and added to release file
6. **Branch cleanup**: Automatic deletion when stage is promoted to RC

## Detailed Workflow

### Phase 1: Patch Development

**Create patch branch:**

1. **Create patch from production**
   ```bash
   git checkout ho-prod  # Ensure we're on main branch
   half_orm dev create-patch "456"  # Check ticket 456 on github or gitlab
   ```
   
2. **Result**
   - Creates branch `ho-patch/456-user-authentication` from `ho-prod`
   - Automatic checkout to `ho-patch/456-user-authentication`
   - Directory `Patches/456-user-authentication/` created
   - `README.md` file added automatically  
   - Commit: "Add Patches/456-user-authentication directory"
   - Push branch to remote for global visibility and reservation
   - Git native conflict detection (fails if branch already exists)

3. **Develop complete patch**
   ```bash
   # On ho-patch/456-user-authentication
   
   # Add schema modifications
   echo "CREATE TABLE users (id SERIAL PRIMARY KEY, username VARCHAR(50) UNIQUE);" > Patches/456-user-authentication/01_create_users.sql
   echo "CREATE INDEX idx_users_username ON users(username);" > Patches/456-user-authentication/02_add_indexes.sql
   
   # Apply schema changes and generate code
   half_orm dev apply-patch
   # → Detailed step-by-step execution with full visibility
   # → Restore database from model/schema.sql
   # → Execute SQL files in lexicographic order
   # → Auto-generate halfORM classes using modules.py integration
   # → COMMIT: "Auto-update: Generated code for patch 456-user-authentication"
   # → Report code generation results and business logic changes needed
   
   # Run all tests
   half_orm dev test
   # → Run complete test suite including new patch tests
   # → Report test results
   
   # Develop business logic based on apply-patch feedback
   # Edit <dbname>/<dbname>/public/user.py (add custom methods to generated class)
   # Create tests/test_*.py (comprehensive tests)
   
   git add <dbname>/ tests/
   git commit -m "Add user authentication business logic and tests"
   
   # Final validation
   half_orm dev apply-patch  # Re-apply patch with all changes
   half_orm dev test         # Run complete test suite
   ```

### Phase 2: Release Preparation

**Prepare next release stage:**

4. **Prepare release stage**
   ```bash
   half_orm dev prepare-release minor  # Creates next minor release stage
   # or
   half_orm dev prepare-release patch  # Creates next patch release stage
   ```
   
5. **Result**
   - Finds latest version across all stages (stage > rc > production)
   - Calculates next version based on increment type:
     - Latest is 1.3.4-rc2 → prepare-release patch → creates 1.3.5-stage.txt
     - Latest is 1.3.4.txt (prod) → prepare-release minor → creates 1.4.0-stage.txt
     - Latest is 1.3.4-stage → prepare-release major → creates 2.0.0-stage.txt
   - Creates empty stage file ready for patch integration
   - Commit: "Prepare release X.Y.Z-stage"

### Phase 3: Release Integration

**Integrate patch into stage release:**

6. **Add patch to stage release**
   ```bash
   half_orm dev add-to-release "456" --to-version="1.3.5"
   # → Specifies target stage release when multiple stages exist
   # → If only one stage exists, --to-version can be omitted
   ```
   
7. **Result**
   - Merge `ho-patch/456-user-authentication` → `ho-prod`
   - Version X.Y.Z calculated from latest existing release
   - Creates/updates `releases/1.3.4-stage.txt`:
     ```
     789-security-fix
     456-user-authentication
     ```
   - Commit: "Add 456-user-authentication to release 1.3.4-stage"
   - **Resync notification** via commit --allow-empty to active patch branches
   - Push to remote (standard Git workflow)
   - Branch `ho-patch/456-user-authentication` preserved until RC promotion

8. **Resync notification system**
   ```bash
   # System automatically notifies other development branches using commit --allow-empty
   # All active ho-patch/* branches receive notification commits
   
   # Example: ho-patch/789-performance gets notification
   git checkout ho-patch/789-performance
   git pull
   # → New commit: "RESYNC REQUIRED: 456-user-authentication integrated"
   # → If multiple patches integrated: "RESYNC REQUIRED: 456-user-auth, 789-security integrated"
   
   # Developer decides when to resync manually
   git merge ho-prod
   # → 789-performance now has user authentication as base
   # → Developer resolves conflicts when ready
   
   # Re-validation after manual resync
   half_orm dev apply-patch  # Ensure no conflicts in combined state
   half_orm dev test         # Run complete test suite
   ```

### Phase 4: Release Management and Branch Cleanup

**Stage Management with Branch Preservation:**

9. **Remove patch from stage release (if needed)**
   ```bash
   # Only possible for stage releases (mutable)
   half_orm dev remove-from-release "456-user-authentication"
   # → Remove patch from releases/X.Y.Z-stage.txt
   # → Preserve ho-patch/456-user-authentication for modifications
   # → Allow re-integration after fixes: add-to-release "456"
   
   # Not possible for RC or production releases (immutable)
   ```

**Promote to Release Candidate with Branch Cleanup:**

10. **Promote to release candidate**
    ```bash
    half_orm dev promote-to-rc
    # → Automatically promotes the next sequential release from stage to rc1
    # → git mv releases/1.3.4-stage.txt releases/1.3.4-rc1.txt
    # → Preserves complete Git history with --follow
    # → **AUTOMATIC BRANCH CLEANUP**: Deletes all branches from this stage release
    #   git branch -d ho-patch/456-user-authentication
    #   git branch -d ho-patch/789-security-fix  
    #   git push origin --delete ho-patch/456-user-authentication
    #   git push origin --delete ho-patch/789-security-fix
    # → Freezes content for validation (immutable RC)
    ```

11. **Test release candidate**
    ```bash
    half_orm dev apply-release "1.3.4-rc1"
    # → Restore database from model/schema.sql (clean production state)
    # → Apply ALL patches from releases/1.3.4-rc1.txt in order
    # → Global validation of final state
    # → Comprehensive testing (schema + code + business logic)
    ```

**Release Candidate Fixes (if needed):**

12. **Handle RC issues**
    ```bash
    # If issues found during RC validation
    half_orm dev create-patch "999-rc1-bugfix"
    # → Develop fix on ho-patch/999-rc1-bugfix
    
    half_orm dev add-to-release-rc "999-rc1-bugfix"
    # → git mv releases/1.3.4-rc1.txt releases/1.3.4-rc2.txt
    # → Add fix to the moved file content
    # → **IMMEDIATE BRANCH CLEANUP**: Delete ho-patch/999-rc1-bugfix
    # → Preserves history: stage → rc1 → rc2
    # → RC releases are immutable, no further modifications possible
    ```

**Production Deployment:**

13. **Deploy to production**
    ```bash
    half_orm dev promote-to-prod
    # → Automatically promotes the validated RC to production
    # → git mv releases/1.3.4-rc2.txt releases/1.3.4.txt
    # → Preserves complete Git history
    # → No branches exist at this point (all cleaned up at RC promotion)
    
    half_orm dev deploy-to-prod "1.3.4"
    # → Create backup of current production state
    # → Apply all patches from releases/1.3.4.txt sequentially
    # → Update model/schema.sql with final clean state
    # → Verify deployment success
    # → Update database version to 1.3.4
    ```

### Phase 5: Emergency Hotfix Workflow

**Critical Issue Requiring Immediate Fix:**

14. **Create and deploy hotfix**
    ```bash
    # Emergency hotfix creation
    half_orm dev create-hotfix "critical-security-vulnerability"
    # → Creates ho-patch/critical-security-vulnerability from ho-prod
    # → Creates releases/1.3.4-hotfix1.txt (based on current production)
    # → Bypasses normal release sequence
    
    # Development and testing (same as normal patches)
    half_orm dev apply-patch
    # → Validate hotfix in isolation
    
    half_orm dev test
    # → Run complete test suite
    
    # Integration to hotfix release
    half_orm dev add-to-hotfix "critical-security-vulnerability"
    # → Merge ho-patch/critical-security-vulnerability → ho-prod
    # → Add to releases/1.3.4-hotfix1.txt
    # → Delete branch immediately (hotfix deployment imminent)
    
    # Immediate deployment to production
    half_orm dev deploy-to-prod "1.3.4-hotfix1"
    # → Deploy emergency fix immediately
    # → Production version: 1.3.4 (with hotfix1 applied)
    # → Automatic integration: hotfix changes now part of ho-prod for future releases
    ```

**Hotfix Integration into Normal Sequence:**

15. **Automatic integration**
    ```bash
    # When next normal release is created:
    half_orm dev prepare-release patch
    # → Creates releases/1.3.5-stage.txt
    # → Hotfix changes automatically included (part of ho-prod history)
    
    # Content of 1.3.5-stage.txt will naturally include hotfix changes
    # since all patches are developed from current ho-prod state
    ```

## Resync Notification System

### Commit-Based Notification with --allow-empty

When a patch is integrated into a release, all other active patch branches receive notifications to signal the need for resynchronization:

```bash
def notify_branches_for_resync():
    """
    Notification system using git commit --allow-empty
    Informs developers of integration events requiring resync
    """
    
    integrated_patch = "456-user-authentication"
    active_patch_branches = get_active_patch_branches()
    
    for patch_branch in active_patch_branches:
        if patch_branch != f"ho-patch/{integrated_patch}":
            try:
                git_checkout(patch_branch)
                
                # Create notification commit using --allow-empty
                notification_message = f"RESYNC REQUIRED: {integrated_patch} integrated"
                git_commit_allow_empty(notification_message)
                log.info(f"📬 Notification sent to {patch_branch}")
                
                git_push(patch_branch)
                
            except GitError as e:
                log.warning(f"⚠️ Could not notify {patch_branch}: {e}")

# Example notification evolution:
# Commit 1: "RESYNC REQUIRED: 456-user-auth integrated"
# Commit 2: "RESYNC REQUIRED: 789-security-fix integrated"  
# Commit 3: "RESYNC REQUIRED: 234-performance integrated"
```

### Developer Notification Workflow
```bash
# Developer sees notifications on git pull
git checkout ho-patch/my-feature
git pull
# → New commits: "RESYNC REQUIRED: 456-user-auth integrated"
# →              "RESYNC REQUIRED: 789-security integrated"

# Developer resyncs when ready
git merge ho-prod
# → Integrates all missing changes at once
# → Resolves conflicts manually if any

half_orm dev apply-patch
# → Re-apply patch after resync
half_orm dev test
# → Re-validate after resync

# Clean up notification commits (optional)
git rebase -i HEAD~3  # Remove notification commits from history
# → Clean branch history with only meaningful development commits
```

## Multi-Environment Release Management

### Release Stage Workflow

#### Development Stage (`X.Y.Z-stage.txt`)
- **Purpose**: Active development, patch integration
- **Content**: Patches ready for staging validation
- **Mutability**: Can be modified, patches can be added/reordered/removed
- **Branch Management**: All branches preserved for flexibility
- **Usage**: Development teams add/remove patches here

#### Release Candidate (`X.Y.Z-rc[N].txt`)
- **Purpose**: Validation and testing phase
- **Content**: Frozen patch list for business validation
- **Mutability**: Immutable once created (fixes create new RC)
- **Branch Management**: All stage branches deleted on promotion to RC
- **Usage**: Business teams validate functionality

#### Production Release (`X.Y.Z.txt`)
- **Purpose**: Final deployment to production
- **Content**: Validated and approved patch list
- **Mutability**: Immutable, represents production state
- **Branch Management**: No branches exist (all cleaned up)
- **Usage**: Operations teams deploy to production

#### Hotfix Release (`X.Y.Z-hotfix[N].txt`)
- **Purpose**: Emergency fixes bypassing normal sequence
- **Content**: Critical patches requiring immediate deployment
- **Mutability**: Immutable once created (emergency deployment)
- **Branch Management**: Branches deleted immediately after integration
- **Usage**: Emergency response team deploys critical fixes

### Single Active Development Rule

**CRITICAL: Only one RC can exist at any time**

```bash
# CORRECT sequence:
1.3.4-stage.txt → promote-to-rc → 1.3.4-rc1.txt → promote-to-prod → 1.3.4.txt
# Only then can 1.3.5-stage.txt be promoted to RC

# INVALID attempts:
# Having both 1.3.4-rc1.txt and 1.3.5-rc1.txt simultaneously
# System will block: "Cannot promote 1.3.5-stage: 1.3.4-rc1 must be promoted first"

# Exception: Hotfixes can coexist with RC
1.3.4-rc1.txt + 1.3.3-hotfix1.txt  # ALLOWED (different base versions)
```

### Version Calculation Logic

```bash
def find_latest_version_anywhere():
    """
    Find the latest version across all release stages
    Priority: hotfix > rc > stage > production
    """
    all_releases = glob("releases/*.txt")
    versions = []
    
    for file in all_releases:
        version = parse_version_from_filename(file)
        priority = get_stage_priority(file)  # hotfix=4, rc=3, stage=2, prod=1
        versions.append((version, priority, file))
    
    # Return highest version with highest priority
    return sorted(versions, key=lambda x: (x[0], x[1]))[-1]

def calculate_next_version(increment_type):
    """
    Calculate next version based on latest existing release
    """
    latest_version, _, _ = find_latest_version_anywhere()
    
    if increment_type == "major":
        return f"{latest_version.major + 1}.0.0"
    elif increment_type == "minor":
        return f"{latest_version.major}.{latest_version.minor + 1}.0"
    elif increment_type == "patch":
        return f"{latest_version.major}.{latest_version.minor}.{latest_version.patch + 1}"
```

### Sequential Promotion Rules

```bash
def can_promote_to_rc():
    """
    Only the next sequential version after production can be promoted to RC
    AND no other RC can exist simultaneously
    """
    current_prod_version = get_latest_production_version()  # "1.3.3"
    next_version = increment_patch_version(current_prod_version)  # "1.3.4"
    
    # Check if stage exists for next version
    stage_file = f"releases/{next_version}-stage.txt"
    if not exists(stage_file):
        return False
    
    # Check if any RC already exists (single active rule)
    existing_rcs = glob("releases/*-rc*.txt")
    if len(existing_rcs) > 0:
        return False, f"Cannot promote: {existing_rcs[0]} must be promoted to production first"
    
    return True

def can_promote_to_prod():
    """
    Only validated RC can be promoted to production
    """
    current_prod_version = get_latest_production_version()  # "1.3.3"
    next_version = increment_patch_version(current_prod_version)  # "1.3.4"
    
    # Find latest RC for next version
    rc_files = glob(f"releases/{next_version}-rc*.txt")
    return len(rc_files) > 0
```

### Multiple Stage Management

#### Concurrent Stage Development
```bash
# Multiple stages can exist simultaneously for different release types:
releases/1.3.5-stage.txt    # Patch release (bug fixes, minor features)
releases/1.4.0-stage.txt    # Minor release (new features)
releases/2.0.0-stage.txt    # Major release (breaking changes)

# Patches are added to specific stage releases:
half_orm dev add-to-release "456-bugfix" --to-version="1.3.5"
half_orm dev add-to-release "789-feature" --to-version="1.4.0"
half_orm dev add-to-release "123-breaking" --to-version="2.0.0"
```

#### Version Auto-Detection Rules
```bash
# When only one stage exists, version can be omitted:
releases/1.3.5-stage.txt    # Only stage file
half_orm dev add-to-release "456"  # Auto-adds to 1.3.5-stage

# When multiple stages exist, version is required:
releases/1.3.5-stage.txt
releases/1.4.0-stage.txt
half_orm dev add-to-release "456"  # ERROR: Multiple stages found, specify --to-version

# Clear error message guides user:
# "Multiple stage releases found: 1.3.5-stage, 1.4.0-stage"
# "Please specify target version: --to-version='1.3.5' or --to-version='1.4.0'"
```

#### Sequential Promotion with Multiple Stages
```bash
# Only the next sequential version after production can be promoted to RC:
Current production: 1.3.4.txt
Available stages: 1.3.5-stage.txt, 1.4.0-stage.txt, 2.0.0-stage.txt

# ALLOWED: Only 1.3.5-stage can be promoted to RC
half_orm dev promote-to-rc  # Promotes 1.3.5-stage → 1.3.5-rc1

# BLOCKED: Cannot promote 1.4.0 or 2.0.0 until 1.3.5 is in production
# This maintains sequential version progression
```

## Unified Patch Management

### All Changes Follow Same Workflow

Whether it's a new feature, bug fix, security patch, or performance optimization, the process is identical:

```bash
# New feature
half_orm dev create-patch "456-user-dashboard"

# Critical security fix (normal workflow)
half_orm dev create-patch "789-sql-injection-fix"

# Emergency security fix (hotfix workflow)
half_orm dev create-hotfix "critical-vulnerability"

# Performance optimization
half_orm dev create-patch "234-database-indexes"

# Bug fix
half_orm dev create-patch "567-calculation-error"

# Normal patches follow: develop → add-to-release → promote-to-rc → promote-to-prod
# Hotfixes follow: develop → add-to-hotfix → deploy-to-prod
```

### Urgency Handled by Release Type Selection

```bash
# Normal release with multiple patches
releases/1.3.4-stage.txt:
  - 456-user-dashboard
  - 234-database-indexes
  - 567-calculation-error

# Emergency release with critical patch (hotfix)
releases/1.3.4-hotfix1.txt:
  - critical-vulnerability    # Deploy immediately, bypass normal sequence

# Continue normal development (hotfix auto-included)
releases/1.3.5-stage.txt:
  - 891-new-reports  
  - 345-ui-improvements
  - critical-vulnerability     # Auto-included from ho-prod history
```

## Production Application and Database Management

### Release Application Logic

#### Patch Application Order and Process
- **Order determination**: Patches applied in order of appearance in release file `releases/X.Y.Z.txt`
- **File order within patch**: SQL/Python files executed in lexicographic order within each patch directory
- **Clean database restoration**: Always start from `model/schema.sql` (clean production schema)
- **Sequential execution**: Each patch applied completely before next patch begins
- **Rollback on failure**: Any failure triggers complete rollback to pre-application state

#### Database Environment Strategy
```bash
# Development Environment:
# → Clean database from model/schema.sql (no production data)
# → Apply individual patches for isolated testing
# → Generate code using modules.py integration
# → Run comprehensive test suite

# Pre-production Environment:
# → Copy of production database (with real data)
# → Apply RC patches for realistic validation
# → CI/CD rules determine when and how patches are applied
# → Business validation with real data scenarios

# Production Environment:
# → Create backup before any changes
# → Apply validated patches from production releases only
# → Update model/schema.sql to reflect final state
# → Never apply stage or RC releases directly
```

### Model Schema Management

#### model/schema.sql Lifecycle
```bash
# Content: Clean production schema (identical to production database structure)
# Updates: Only during production releases via deploy-to-prod
# Usage: Base for all patch development and testing
# Maintenance: Automatically updated to reflect latest production state

# Update process during production deployment:
half_orm dev deploy-to-prod "1.3.4"
# → Create backup: backups/1.3.3.sql (current production state)
# → Apply patches from releases/1.3.4.txt
# → Extract clean schema: pg_dump --schema-only → model/schema.sql
# → Commit: "Update model/schema.sql to version 1.3.4"
# → Database and schema file now synchronized
```

### Production Database Upgrade Scenarios

#### Scenario 1: Sequential Version Upgrade
```bash
# Database at 1.3.3, applying 1.3.4
half_orm dev deploy-to-prod "1.3.4"

# Content of releases/1.3.4.txt:
# 456-user-authentication
# 789-security-fix
# 234-performance-optimization

# Execution process:
# → Create rollback point: backups/1.3.3.sql
# → Apply patch 456-user-authentication (all files in lexicographic order)
# → Apply patch 789-security-fix (all files in lexicographic order)
# → Apply patch 234-performance-optimization (all files in lexicographic order)
# → Update model/schema.sql to final state
# → Database becomes 1.3.4
```

#### Scenario 2: Multi-Version Gap Upgrade
```bash
# Database at 1.2.1, latest available is 1.3.4
# System finds all intermediate release files automatically

Current DB: 1.2.1
Available releases: 1.2.2, 1.2.3, 1.3.0, 1.3.1, 1.3.2, 1.3.3, 1.3.4

# Automatic sequential application (NO VERSION SKIPPING):
Step 1: Deploy 1.2.2 (1.2.1 → 1.2.2)
Step 2: Deploy 1.2.3 (1.2.2 → 1.2.3)  
Step 3: Deploy 1.3.0 (1.2.3 → 1.3.0)
Step 4: Deploy 1.3.1 (1.3.0 → 1.3.1)
Step 5: Deploy 1.3.2 (1.3.1 → 1.3.2)
Step 6: Deploy 1.3.3 (1.3.2 → 1.3.3)
Step 7: Deploy 1.3.4 (1.3.3 → 1.3.4)
```

#### Scenario 3: New Production Instance
```bash
# Clean deployment to new production environment
half_orm dev deploy-to-prod --new-instance "1.3.4"
# → Use model/schema.sql directly (clean schema at version 1.3.4)
# → Skip patch-by-patch application
# → Deploy clean, optimized schema
```

#### Scenario 4: Hotfix Deployment
```bash
# Emergency hotfix deployment
half_orm dev deploy-to-prod "1.3.4-hotfix1"
# → Apply hotfix patches on top of current production (1.3.4)
# → Production version remains 1.3.4 (with hotfix applied)
# → Faster deployment, no sequential requirement
```

### Automatic Backup Creation

```bash
# Before each deployment, automatic backup creation
half_orm dev deploy-to-prod "1.3.4"
# → Create backups/1.3.3.sql (current production state before upgrade)
# → Apply release 1.3.4 patches
# → Update model/schema.sql to final state
# → Verify deployment success

# Hotfix backup strategy
half_orm dev deploy-to-prod "1.3.4-hotfix1"
# → Create backups/1.3.4.sql (pre-hotfix state)
# → Apply hotfix patches only
# → Keep model/schema.sql at clean 1.3.4 state (no hotfix pollution)
```

## Integration with halfORM and Code Generation

### halfORM Code Generation Integration

The system integrates with halfORM's `modules.py` for automatic code generation during patch application:

#### Code Generation Process
```bash
# During apply-patch execution:
half_orm dev apply-patch
# → Restore database from model/schema.sql
# → Apply patch SQL files in lexicographic order
# → Trigger halfORM code generation via modules.py
# → Generate/update model classes in <dbname>/<dbname>/<schema>/
# → Create method stubs for new business logic requirements
# → Auto-commit generated code changes
# → Report what business logic needs manual implementation
```

#### Code Generation Process Details
```python
# Integration with existing halfORM modules.py functionality:
# 1. Schema introspection via repo.database.model._relations()
# 2. Model class generation using templates (module_template_1/2/3)
# 3. Relationship detection and method generation via inheritance_import
# 4. Field validation and Python type mapping via SQL_ADAPTER
# 5. Custom method preservation using utils.BEGIN_CODE/END_CODE markers
# 6. Dataclass generation for DC_Relation integration via _gen_dataclass()
# 7. Test file generation in tests/<dbname>/<schema>/test_<table>.py structure
```

#### Generated Code Structure and Preservation
```bash
# Generated class template structure:
# → Class definition with inheritance from MODEL.get_relation_class()
# → Documentation from database schema
# → Field definitions with type annotations
# → Custom code sections marked with BEGIN_CODE/END_CODE
# → Dataclass integration for DC_Relation functionality

# Custom code preservation mechanism:
# → User code sections preserved between utils.BEGIN_CODE and utils.END_CODE
# → Three preservation areas: global imports, class attributes, class methods
# → Automatic escaping of braces to prevent template conflicts
# → Re-generation preserves all custom business logic
```

#### Test File Generation Integration
```bash
# Automatic test structure creation during apply-patch:
# → tests/ root directory for pytest discovery
# → tests/<dbname>/ for database-specific auto-generated tests
# → tests/<dbname>/<schema>/ for schema organization
# → test_<table>.py files following pytest conventions
# → Custom test sections preserved with BEGIN_CODE/END_CODE markers
# → pytest.ini configuration for automatic test discovery

# Test file template includes:
# → Basic instantiation tests
# → Field access validation
# → Custom test method sections for business logic testing
# → Proper imports and class structure
```

#### Generated Code Management
```bash
# Generated code handling during patch development:
# → Generated classes: <dbname>/<dbname>/<schema>/<table>.py
# → Preserved custom methods: Existing business logic maintained
# → New method stubs: Created for new functionality, require implementation
# → Test files: Automatic test generation for new models
# → Relationship methods: Generated based on foreign key constraints

# Example generated class update:
# Before patch: user.py with basic user model
# After patch (adding authentication): 
# → user.py updated with new columns
# → user.authenticate() method stub created
# → user.change_password() method stub created
# → Existing custom methods preserved
```

#### Code Generation Template System
```bash
# Template-based code generation process:
# → module_template_1: Imports and global code section
# → module_template_2: Class definition and inheritance
# → module_template_3: Constructor with field parameters
# → Automatic field type detection via SQL_ADAPTER mapping
# → Custom code insertion points using template formatting

# Field generation with type safety:
# → PostgreSQL types mapped to Python types via SQL_ADAPTER
# → Array types handled with default_factory=list
# → Missing type adapters reported for manual SQL_ADAPTER updates
# → Field validation with utils.check_attribute_name()

# Dataclass integration for halfORM:
# → DC_Relation inheritance for enhanced functionality
# → Field definitions with dataclasses.field() configuration
# → Foreign key relationship method generation
# → Post-init field initialization for halfORM Field objects
```

#### Business Logic Development Flow
```bash
# Complete development cycle with code generation:
1. Create patch branch: half_orm dev create-patch "456"
2. Add schema changes: Edit SQL files in Patches/456-*/
3. Apply patch: half_orm dev apply-patch
   → Schema applied via SQL files in lexicographic order
   → Code generated using modules.py template system
   → Model classes created/updated in <dbname>/<dbname>/<schema>/<table>.py
   → Test files generated in tests/<dbname>/<schema>/test_<table>.py
   → Custom code preserved in BEGIN_CODE/END_CODE sections
   → Method stubs created for new functionality requiring implementation
   → SQL_ADAPTER warnings for unmapped PostgreSQL types
4. Implement business logic: Edit generated classes, add custom methods
5. Write tests: Create comprehensive test coverage
6. Validate: half_orm dev apply-patch (re-run), half_orm dev test
7. Integrate: half_orm dev add-to-release "456"
```

#### Development Mode Test Generation
```bash
# When repo.devel is True (development mode):
# → Automatic test file generation for all database relations
# → Standard Python test structure: tests/<dbname>/<schema>/
# → pytest.ini configuration with appropriate test discovery settings
# → Test file preservation: existing test files not overwritten
# → Hierarchical organization prevents naming conflicts between schemas
# → Custom tests can be placed in tests/ root without conflicts

# Test generation statistics and feedback:
# → Count of generated test files reported
# → Test directory structure displayed for verification
# → Clear separation between auto-generated and custom tests
# → Integration with pytest for standard Python testing workflow
```

## Version Management

### Database-Driven Version Calculation
- **Version source**: Queried from `half_orm_meta.hop_release` table
- **Current database version**: Latest record in hop_release table  
- **Version calculation**: Automatic increment based on metadata (NO SKIPPING)
- **Sequential requirement**: Next version MUST be current_version + 1 (except hotfixes)

```sql
-- Version query (always deterministic)
SELECT version FROM half_orm_meta.hop_release 
ORDER BY created_date DESC LIMIT 1;
-- Result: "1.3.3" or "1.3.3-hotfix2"
-- Next allowed version: "1.3.4" (automatic calculation)
-- Next allowed hotfix: "1.3.3-hotfix3" (emergency only)
```

### Release File Collaboration
```bash
# Natural Git workflow for release modifications

# Developer A adds patch to stage release
echo "456-user-authentication" >> releases/1.3.4-stage.txt
git add releases/1.3.4-stage.txt
git commit -m "Add 456-user-authentication to release 1.3.4-stage"
git push

# Developer B synchronizes automatically
git pull  # Standard Git synchronization

# Developer B modifies patch order in stage
vim releases/1.3.4-stage.txt
# Reorder lines as needed
git add releases/1.3.4-stage.txt
git commit -m "Reorder patches in release 1.3.4-stage"
git push

# Developer C removes problematic patch from stage
half_orm dev remove-from-release "problematic-patch"
# → Only works on stage releases
# → Preserves branch for later re-integration

# Merge conflicts handled by standard Git workflow
```

## CLI Commands

### Project Initialization

#### `init-project`
```bash
# Initialize new half-orm-dev project
half_orm dev init-project <dbname>
# → Creates database with half-orm-dev metadata
# → Inserts version 0.0.0 in hop_release table
# → Generates initial model/schema.sql (metadata only)
# → Creates <dbname>/<dbname>/ directory structure
# → Creates Git repository with ho-prod as main branch
# → Creates releases/ directory with README.md
# → Adds project configuration files (README.md, .gitignore, pyproject.toml)
# → Ready for first patch development
```

### Adaptive CLI System
The CLI automatically adapts based on environment:
- **Development environment**: Shows development commands
- **Production environment**: Shows production commands
- **Branch context**: Commands vary based on current branch type

### Command Matrix by Branch Context

| Branch Type | Available Commands | Behavior |
|-------------|-------------------|-----------|
| **ho-prod** | `create-patch`, `create-hotfix`, `prepare-release`, `promote-to-rc`, `promote-to-prod`, `apply-release`, `deploy-to-prod`, `remove-from-release`, `rollback` | Main development and production operations |
| **ho-patch/***| `apply-patch`, `test`, `add-to-release`, `add-to-release-rc`, `add-to-hotfix`, `mark-resync-complete`, standard git commands | Patch development and integration |

### Development Commands

#### `create-patch`
```bash
# Create new patch branch from current production state
half_orm dev create-patch "456"
# → Creates ho-patch/456-user-authentication branch from ho-prod
# → Checkout to patch branch
# → Global patch ID reservation via remote branch
# → Creates Patches/456-user-authentication/ directory
# → Branch preserved until promote-to-rc
```

#### `create-hotfix`
```bash
# Create emergency hotfix branch for critical issues
half_orm dev create-hotfix "critical-vulnerability"
# → Creates ho-patch/critical-vulnerability branch from ho-prod
# → Creates releases/X.Y.Z-hotfix1.txt (based on current production)
# → Checkout to hotfix branch
# → Emergency workflow, bypasses normal release sequence
```

#### `apply-patch`
```bash
# Apply current patch and generate code (must be run from ho-patch/* branch)
# On ho-patch/456-user-authentication:
half_orm dev apply-patch

# Explicit step-by-step process:
# 1. 🔄 Restore database from model/schema.sql (latest production state)
# 2. 📁 Apply patch files from Patches/456-user-authentication/ in lexicographic order:
#    → Execute 01_create_user_table.sql
#    → Execute 02_add_indexes.sql
#    → Execute 03_update_permissions.py
# 3. 🔧 Generate halfORM code using modules.py integration
#    → Update <dbname>/<dbname>/public/user.py (if table structure changed)
#    → Create new model classes (if new tables)
#    → COMMIT: "Auto-update: Generated code for patch 456-user-authentication"
# 4. 📊 Report business logic changes needed:
#    → "⚠️ New table 'users' requires business logic implementation"
#    → "⚠️ Method user.authenticate() stub created - needs implementation"
#    → "✅ All existing business logic still compatible"
# 5. 📋 Summary report:
#    → Database schema: ✅ Applied successfully
#    → Generated code: ✅ Updated 3 files
#    → Business logic: ⚠️ 2 methods need implementation
```

#### Detailed Apply-Patch Output Example

```bash
half_orm dev apply-patch
# Running on ho-patch/456-user-authentication

🔄 Step 1: Database Restoration
   ✅ Restored database from model/schema.sql (version 1.3.3)
   ✅ Database clean state confirmed

📁 Step 2: Applying Patch Files
   ✅ Executing 01_create_user_table.sql
      → Created table 'users' with 5 columns
      → Added primary key constraint
   ✅ Executing 02_add_indexes.sql  
      → Created index 'idx_users_username'
      → Created index 'idx_users_email'
   ✅ Executing 03_update_permissions.py
      → Updated 15 user permissions
      → No errors detected

🔧 Step 3: Code Generation (modules.py integration)
   ✅ Generated <dbname>/<dbname>/public/user.py
      → Added class User with 5 properties
      → Added relationship methods: user.orders(), user.sessions()
   ✅ Updated <dbname>/<dbname>/public/__init__.py
      → Added User import
   ⚠️  Method stubs created (need implementation):
      → user.authenticate(password) in <dbname>/<dbname>/public/user.py:45
      → user.change_password(old, new) in <dbname>/<dbname>/public/user.py:52
   📝 Auto-committed: "Generated code for patch 456-user-authentication"

📊 Step 4: Business Logic Analysis
   ✅ Schema changes: All applied successfully
   ✅ Generated code: 3 files updated, no conflicts
   ⚠️  Business logic required:
      → Implement user.authenticate() method
      → Implement user.change_password() method
      → Add password hashing utilities in <dbname>/<dbname>/public/user.py
   ✅ Existing code: No breaking changes detected

📋 SUMMARY
   Database: ✅ Schema updated successfully
   Generated Code: ✅ 3 files updated
   Business logic: ⚠️ 2 methods need implementation
   Next Steps: 
   1. Implement user.authenticate() in <dbname>/<dbname>/public/user.py:45
   2. Implement user.change_password() in <dbname>/<dbname>/public/user.py:52
   3. Run 'half_orm dev test' to validate
```

#### `test`
```bash
# Run complete test suite (standard halfORM command)
half_orm dev test
# → Run all tests including new patch tests
# → For specific test files, use pytest directly
```

#### `add-to-release`
```bash
# Integrate patch into specified stage release (version required when multiple stages exist)
git checkout ho-patch/456-user-authentication
half_orm dev add-to-release "456" --to-version="1.3.5"

# Or from any branch with explicit version:
half_orm dev add-to-release "456" --to-version="1.4.0"

# If only one stage exists, version can be omitted (auto-detected):
half_orm dev add-to-release "456"  # Uses the single existing stage

# Actions:
# → Merge ho-patch/456-user-authentication → ho-prod
# → Add "456-user-authentication" to current stage release file
# → Send resync notifications via commit --allow-empty to all other active patch branches
# → Commit: "Add 456-user-authentication to release X.Y.Z-stage"
# → Preserve branch until promote-to-rc
```

#### `add-to-hotfix`
```bash
# Add patch to hotfix release (emergency workflow)
git checkout ho-patch/critical-vulnerability
half_orm dev add-to-hotfix "critical-vulnerability"

# Actions:
# → Merge ho-patch/critical-vulnerability → ho-prod
# → Add to current hotfix release file (e.g., releases/1.3.4-hotfix1.txt)
# → Delete branch immediately (emergency deployment workflow)
# → Commit: "Add critical-vulnerability to hotfix release 1.3.4-hotfix1"
# → Ready for immediate production deployment
```

#### `add-to-release-rc`
```bash
# Add fix to current release candidate (creates new RC via git mv)
git checkout ho-patch/999-rc-bugfix
half_orm dev add-to-release-rc "999-rc-bugfix"

# Actions:
# → Merge ho-patch/999-rc-bugfix → ho-prod
# → Find current RC file (e.g., releases/1.3.5-rc1.txt)
# → git mv releases/1.3.5-rc1.txt releases/1.3.5-rc2.txt
# → Add "999-rc-bugfix" to the moved file content
# → Delete ho-patch/999-rc-bugfix immediately (RC immutable)
# → Commit: "Add 999-rc-bugfix to release 1.3.5-rc2"
# → Preserves complete history: stage → rc1 → rc2
```

#### `remove-from-release`
```bash
# Remove patch from stage release (stage releases only)
half_orm dev remove-from-release "problematic-patch"

# Actions:
# → Remove "problematic-patch" from current stage release file
# → Preserve ho-patch/problematic-patch branch for modifications
# → Commit: "Remove problematic-patch from release X.Y.Z-stage"
# → Allow later re-integration after fixes

# Validation:
# ✅ ALLOWED: Stage releases (mutable)
# ❌ BLOCKED: RC and production releases (immutable)
# ❌ ERROR: "Cannot remove from immutable release 1.3.5-rc1"
```

### Release Management Commands

#### `prepare-release`
```bash
# Prepare next release stage file
half_orm dev prepare-release minor
# → Finds latest version across all stages (stage, rc, prod, hotfix)
# → Calculates next version based on increment type
# → Creates empty releases/X.Y.Z-stage.txt file
# → Commit: "Prepare release X.Y.Z-stage"

# Examples:
# Latest is 1.3.4-rc2 → prepare-release patch → creates 1.3.5-stage.txt
# Latest is 1.3.4.txt (prod) → prepare-release minor → creates 1.4.0-stage.txt
# Latest is 1.3.4-stage → prepare-release major → creates 2.0.0-stage.txt
# Latest is 1.3.4-hotfix2 → prepare-release patch → creates 1.3.5-stage.txt
```

#### `promote-to-rc`
```bash
# Promote current stage release to release candidate
half_orm dev promote-to-rc
# → No arguments needed - automatically finds current stage file
# → Validates single active development rule (no existing RC allowed)
# → Current stage: releases/1.3.5-stage.txt
# → git mv releases/1.3.5-stage.txt releases/1.3.5-rc1.txt
# → Preserves complete Git history with --follow
# → **AUTOMATIC BRANCH CLEANUP**: Deletes all branches from stage release
#   → Reads patch list from moved file
#   → git branch -d ho-patch/[each-patch-in-release]
#   → git push origin --delete ho-patch/[each-patch-in-release]
# → If rc1 exists, creates rc2, etc.
# → Commit: "Promote 1.3.5-stage to 1.3.5-rc1"

# Sequential promotion validation:
# ✅ ALLOWED: 1.3.4 (prod) → 1.3.5-stage exists → promote to 1.3.5-rc1
# ❌ BLOCKED: 1.3.4 (prod) → no 1.3.5-stage → cannot promote
# ❌ BLOCKED: 1.3.4-rc1 exists → cannot promote any other stage until 1.3.4 in production

# RC numbering with git mv:
# If 1.3.5-rc1.txt already exists → git mv stage to 1.3.5-rc2.txt
# Automatic increment ensures no conflicts
```

#### `promote-to-prod`
```bash
# Promote current release candidate to production
half_orm dev promote-to-prod
# → No arguments needed - automatically finds latest RC
# → Current RC: releases/1.3.5-rc2.txt
# → git mv releases/1.3.5-rc2.txt releases/1.3.5.txt
# → Preserves complete Git history
# → No branch cleanup needed (already done at RC promotion)
# → Commit: "Promote 1.3.5-rc2 to production release 1.3.5"

# Validation rules:
# ✅ ALLOWED: 1.3.4 (prod) + 1.3.5-rc2.txt exists → git mv to 1.3.5.txt
# ❌ BLOCKED: No RC exists for next sequential version
```

#### `apply-release`
```bash
# Test complete release before deployment
half_orm dev apply-release "1.3.4-rc1"
# → Restore database from model/schema.sql (clean production state)
# → Apply ALL patches from releases/1.3.4-rc1.txt in order
# → Global validation of final state
# → Comprehensive testing (schema + code + business logic)
# → Prepare for production deployment

# Can test any release stage:
half_orm dev apply-release "1.3.4-stage"    # Test development stage
half_orm dev apply-release "1.3.4-rc2"      # Test release candidate
half_orm dev apply-release "1.3.4"          # Test production release
half_orm dev apply-release "1.3.4-hotfix1"  # Test hotfix release
```

#### `status`
```bash
# General development status
half_orm dev status

# Show current patch status (when on patch branch)
half_orm dev status --patch

# Show notification status
half_orm dev status --notifications
# → Lists branches with pending notifications
# → Shows what changes need to be integrated

# Example output:
# ho-patch/789-performance: ⚠️  Resync needed (user-authentication, security-fix)
# ho-patch/234-reports: ✅ Up to date  
# ho-patch/567-bugfix: ⚠️  Resync needed (user-authentication)

# Show release status
half_orm dev status --releases
# → Shows current release files and their stages
# → Indicates branch cleanup status
# → Enforces single active development rule

# Example output:
# 1.3.5-stage.txt: 3 patches, 3 branches active
# 1.3.4-rc1.txt: 2 patches, branches cleaned up ⚠️ BLOCKING further RC creation
# 1.3.4.txt: 2 patches, deployed (no branches)
# 1.3.4-hotfix1.txt: 1 patch, deployed (no branches)

# Show complete release history
half_orm dev status --release-history "1.3.5"
# → git log --follow --oneline releases/1.3.5*
# → Shows complete evolution: stage → rc1 → rc2 → production

# Show all active patches
half_orm dev status --patches
# → Lists all ho-patch/* branches on remote
# → Shows integration status for each patch
# → Indicates which patches have pending notifications
```

#### `mark-resync-complete`
```bash
# Clean up notification commits after manual resync
half_orm dev mark-resync-complete
# → Optional cleanup of notification commits from branch history
# → git rebase -i to remove "RESYNC REQUIRED" commits
# → Keeps branch history clean with only meaningful development commits
# → Used when developer has completed manual merge from ho-prod
```

### Production Commands

#### `deploy-to-prod`
```bash
# Deploy production release to database
half_orm dev deploy-to-prod "1.3.4"
# → Create rollback point: backups/1.3.3.sql (current production state)
# → Apply all patches from releases/1.3.4.txt sequentially in file order
# → Update model/schema.sql with final clean state (pg_dump --schema-only)
# → Verify deployment success
# → Update database version to 1.3.4

# Deploy hotfix release to database
half_orm dev deploy-to-prod "1.3.4-hotfix1"
# → Create backup of current production state (backups/1.3.4.sql)
# → Apply hotfix patches only (faster deployment)
# → Keep model/schema.sql at clean 1.3.4 state (no hotfix pollution)
# → Update database version to 1.3.4-hotfix1

# Deploy to new production instance (clean deployment)
half_orm dev deploy-to-prod --new-instance "1.3.4"
# → Use model/schema.sql directly (skip patch application)
# → Deploy clean schema at target version

# Only production and hotfix releases can be deployed
# Stage and RC releases are for testing only
```

#### `rollback`
```bash
# Rollback to previous version using backup
half_orm dev rollback --to-version="1.3.3"
# → Restore database from backups/1.3.3.sql
# → git reset --hard to version 1.3.3 for alignment
# → Verify rollback success

# Rollback from hotfix
half_orm dev rollback --to-version="1.3.4"
# → Restore database from backups/1.3.4.sql (pre-hotfix state)
# → Remove hotfix from production while preserving in ho-prod history
```

## Conflict Management and Prevention

### Developer Responsibility Model

#### No Automatic Conflict Detection
```bash
# System philosophy: Developers manage patch interactions
# → No automatic analysis of schema conflicts
# → No dependency tracking between patches
# → No prevention of conflicting modifications
# → Conflicts discovered during application or testing

# Example conflict scenarios (not prevented):
# Patch A: ALTER TABLE users ADD COLUMN email VARCHAR(255);
# Patch B: ALTER TABLE users ADD COLUMN email TEXT;
# → Both patches will be accepted into release
# → Conflict discovered when applying Patch B (SQL error)
# → Developer responsible for coordination and resolution
```

#### Error-Based Feedback System
```bash
# Conflicts discovered during patch application:
half_orm dev apply-patch
# → SQL error: column "email" already exists
# → System reports error and stops execution
# → No partial application, clean rollback to starting state
# → Developer must fix patch and retry

# Conflicts discovered during testing:
half_orm dev test
# → Business logic test failures
# → Integration test failures
# → Developer must coordinate with other patch authors
```

#### Manual Conflict Resolution
```bash
# Developer coordination strategies:
# 1. Communication: Team coordination to avoid conflicts
# 2. Stage testing: Discover conflicts early in stage releases
# 3. Patch modification: Edit patches to resolve conflicts
# 4. Release reordering: Change patch order in stage release file
# 5. Patch removal: Remove conflicting patches from release temporarily

# Example resolution in stage release:
vim releases/1.3.4-stage.txt
# Reorder patches to resolve dependencies:
# Before: patch-a, patch-b, patch-c
# After:  patch-b, patch-a, patch-c (patch-b creates table needed by patch-a)
git add releases/1.3.4-stage.txt
git commit -m "Reorder patches to resolve table dependency"
```

### Release Stage Conflict Management

```bash
# Stage releases are mutable - can resolve conflicts by reordering
vim releases/1.3.4-stage.txt
# Reorder patches to resolve dependencies
git add releases/1.3.4-stage.txt
git commit -m "Reorder patches to resolve dependencies"

# Or remove problematic patches temporarily
half_orm dev remove-from-release "problematic-patch"
# → Fix patch on preserved branch
# → Re-integrate when ready: add-to-release "problematic-patch"

# RC and production releases are immutable
# Conflicts require new RC with fixes
half_orm dev create-patch "999-dependency-fix"
half_orm dev add-to-release-rc "999-dependency-fix"
# → Creates new RC with fix included
```

### Resync Management for Active Patches

#### Commit-Based Notification System
```bash
# After any patch integration, notifications are sent via commit --allow-empty
# Developer sees notification on next git pull:

git checkout ho-patch/789-performance
git pull
# → New commit: "RESYNC REQUIRED: user-authentication integrated"

# Developer can check what needs resyncing
half_orm dev status --notifications
# → ho-patch/789-performance: ⚠️  Resync needed (user-authentication)  
# → ho-patch/234-reports: ✅ Up to date
# → ho-patch/567-bugfix: ⚠️  Resync needed (user-authentication)
```

#### Manual Resync Process
```bash
# Developer resyncs when ready (respects Git workflow)
git checkout ho-patch/789-performance
git merge ho-prod
# → Integrates all changes since last sync
# → Developer resolves conflicts manually if any
# → Natural Git merge workflow

half_orm dev apply-patch
# → Re-apply patch after resync
half_orm dev test
# → Re-validate after resync

# Clean up notification commits (optional)
half_orm dev mark-resync-complete
# → Removes notification commits from history
# → Updates branch state to indicate resync completed
```

### Natural Git Workflow
```bash
# Standard Git conflict resolution for release files
# If two developers modify releases/1.3.4-stage.txt simultaneously:

git pull
# Auto-merging releases/1.3.4-stage.txt
# CONFLICT (content): Merge conflict in releases/1.3.4-stage.txt

# Standard Git resolution:
vim releases/1.3.4-stage.txt  # Resolve conflict
git add releases/1.3.4-stage.txt
git commit -m "Resolve merge conflict in release 1.3.4-stage"

# Patch reservation conflicts (Git native):
git checkout -b ho-patch/456-user-auth
git push -u origin ho-patch/456-user-auth
# → Error: branch already exists on remote (natural Git behavior)
```

## Error Handling and Recovery

### Production Deployment Failure Recovery

#### Rollback Point Strategy
```bash
# Before any production deployment, create rollback point
half_orm dev deploy-to-prod "1.3.4"
# → Step 1: Create backups/1.3.3.sql (current production state)
# → Step 2: git tag rollback-point-1.3.3 (Git state before deployment)
# → Step 3: Begin patch application from releases/1.3.4.txt

# If deployment fails during patch application:
# → Automatic database restore from backups/1.3.3.sql
# → git reset --hard rollback-point-1.3.3
# → Production remains at version 1.3.3
# → Clear error reporting indicating which patch failed
# → No partial application, guaranteed clean state
```

### Common Error Scenarios and Recovery

#### 1. Failed Patch Application
```bash
# Scenario: Patch fails during apply-patch
half_orm dev apply-patch
# → Error: SQL syntax error in 02_add_indexes.sql line 3

# Automatic rollback:
# → Restore database to pre-application state (from model/schema.sql)
# → No partial changes committed  
# → Clear error message with failure point
# → Generated code reverted if any
# → Patch files remain for fixing
# → Branch preserved for continued development

# Recovery:
# → Fix patch files in Patches/456-user-authentication/
# → Re-run half_orm dev apply-patch
```

#### 2. Release Candidate Validation Failure
```bash
# Scenario: RC fails validation testing
half_orm dev apply-release "1.3.4-rc1"
# → Error: Integration test failure in user authentication

# Resolution:
# → Create fix patch: half_orm dev create-patch "999-rc1-auth-fix"
# → Develop and test fix: half_orm dev apply-patch + half_orm dev test
# → Add to new RC: half_orm dev add-to-release-rc "999-rc1-auth-fix"
# → Creates 1.3.4-rc2.txt with fix included
# → Re-validate: half_orm dev apply-release "1.3.4-rc2"
```

#### 3. Production Deployment Failure
```bash
# Scenario: Production deployment fails mid-release
half_orm dev deploy-to-prod "1.3.4"
# → Backup created: backups/1.3.3.sql
# → Rollback point: rollback-point-1.3.3
# → Error: Patch 789-security-fix failed during application

# Automatic recovery:
# → Database restored from backups/1.3.3.sql
# → git reset --hard rollback-point-1.3.3
# → Production remains at stable version 1.3.3
# → Clear indication of which patch failed

# Manual resolution:
# → Fix failing patch on new branch: half_orm dev create-patch "789-security-fix-v2"
# → Re-integrate with add-to-release
# → Create new RC: promote-to-rc
# → Re-test: apply-release "1.3.5-rc1"
# → Re-deploy when ready: deploy-to-prod "1.3.5"
```

#### 4. Invalid Promotion Attempts
```bash
# Scenario: Attempt to promote out-of-sequence release
half_orm dev promote-to-rc
# → Current prod: 1.3.3
# → Only 1.3.5-stage.txt exists (missing 1.3.4)
# → Error: Cannot promote 1.3.5-stage, missing sequential version 1.3.4

# Resolution:
# → Prepare missing version: half_orm dev prepare-release patch
# → Creates 1.3.4-stage.txt
# → Add patches to 1.3.4-stage or promote empty release
# → Then promote: half_orm dev promote-to-rc

# Scenario: Multiple RC attempt (violates single active rule)
half_orm dev promote-to-rc
# → Existing RC: 1.3.4-rc1.txt
# → Attempted promotion: 1.3.5-stage.txt
# → Error: Cannot promote 1.3.5-stage, 1.3.4-rc1 must be promoted to production first

# Resolution:
# → Complete current RC: half_orm dev promote-to-prod (1.3.4-rc1 → 1.3.4.txt)
# → Then promote next: half_orm dev promote-to-rc (1.3.5-stage → 1.3.5-rc1)
```

#### 5. Branch Cleanup Failure
```bash
# Scenario: Automatic branch cleanup fails during promote-to-rc
half_orm dev promote-to-rc
# → git mv successful: 1.3.4-stage.txt → 1.3.4-rc1.txt
# → Error: Cannot delete ho-patch/456-user-auth (has uncommitted changes)

# Manual resolution:
# → Check problematic branches: git branch --contains
# → Clean up manually: git checkout ho-patch/456-user-auth
# → Commit or stash changes: git stash
# → Delete branch: git branch -D ho-patch/456-user-auth
# → Push deletion: git push origin --delete ho-patch/456-user-auth
```

#### 6. Hotfix Integration Conflicts
```bash
# Scenario: Hotfix conflicts with ongoing development
half_orm dev add-to-hotfix "critical-fix"
# → Hotfix applied to production
# → Ongoing patches now have conflicts with ho-prod

# Automatic notification to active branches:
# → All ho-patch/* branches receive notification: "RESYNC REQUIRED: critical-fix integrated"
# → Developers handle resync when ready
# → Manual conflict resolution using standard Git workflow
```

## Validation and Testing Framework

### Comprehensive Validation Pipeline

#### Stage-Specific Validation Levels
```bash
# Development stage validation (fast feedback)
half_orm dev apply-patch
# → Basic SQL syntax validation
# → Schema consistency checks
# → Code generation validation
# → Isolated patch testing

# Release candidate validation (comprehensive)
half_orm dev apply-release "1.3.4-rc1"
# → Full patch sequence application
# → Integration testing between patches
# → Business logic validation
# → Performance impact assessment
# → Security scanning of schema changes

# Production deployment validation (critical)
half_orm dev deploy-to-prod "1.3.4"
# → Final pre-deployment validation
# → Backup verification
# → Rollback plan validation
# → Database migration dry-run
```

#### Validation Components
```bash
# Automatic validation during patch application:
# 1. SQL syntax validation - PostgreSQL parser validation
# 2. Schema consistency checks - Foreign key constraints, data types
# 3. halfORM metadata validation - Model generation compatibility
# 4. Code generation testing - Successful class generation
# 5. Business logic compilation - Python syntax and imports
# 6. Integration testing - Patch compatibility testing
# 7. Performance impact - Query plan analysis for new indexes
# 8. Security assessment - SQL injection prevention, permission changes
```

### Rollback on Validation Failure

#### Automatic Rollback Strategy
```bash
# Any validation failure triggers automatic rollback:
# → No release file modifications if validation fails
# → No database state changes if validation fails
# → No code generation artifacts if validation fails
# → No branch cleanup if validation fails
# → Clean error reporting with specific failure points
# → Stage-appropriate rollback strategies

# Example rollback during apply-patch:
half_orm dev apply-patch
# → Database restored from model/schema.sql
# → Patch 01_create_table.sql applied successfully
# → Patch 02_add_constraints.sql failed (foreign key constraint error)
# → ROLLBACK: Database restored to pre-patch state
# → ERROR: Foreign key constraint violation in 02_add_constraints.sql:15
# → All generated code changes reverted
# → Branch remains in development state for fixes
```

### Global State Testing

#### Multi-Level Testing Strategy
```bash
# Patch-level testing: half_orm dev apply-patch (on patch branch)
# → Isolated patch testing against clean database
# → Focus on patch-specific functionality
# → Fast feedback for patch development

# Global testing: half_orm dev test (standard halfORM command)
# → Complete test suite including new patch tests
# → Integration with existing functionality
# → Comprehensive business logic validation

# Stage testing: half_orm dev apply-release "X.Y.Z-stage"
# → All patches in release applied sequentially
# → Cross-patch interaction testing
# → Integration testing at release level

# RC testing: half_orm dev apply-release "X.Y.Z-rc1"
# → Production-like validation environment
# → Performance testing and optimization
# → Security and compliance validation

# Production deployment: half_orm dev deploy-to-prod "X.Y.Z"
# → Final validation before production application
# → Backup and rollback testing
# → Production environment compatibility
```

## Integration with halfORM

### Modular Architecture
- `ReleaseFileManager`: Manage releases/*.txt files with Git workflow and stage support
- `HGit`: Branch classification and patch management
- `CLI`: Adaptive Click interface based on branch context
- `PatchManager`: Patch application and validation
- `BackupManager`: Production backup management
- `ConflictAnalyzer`: Schema patch conflict detection (passive reporting only)
- `NotificationManager`: Resync notification system via commit --allow-empty
- `StageManager`: Multi-environment release stage management
- `VersionCalculator`: Intelligent version calculation across stages
- `BranchLifecycleManager`: Automatic branch cleanup and lifecycle management
- `HotfixManager`: Emergency hotfix workflow and integration
- `ModulesIntegration`: Integration with halfORM modules.py for code generation

### Seamless Integration
- CLI extension via `cli_extension.py`
- Reuse existing `HGit` infrastructure
- Compatible with existing halfORM workflows
- No impact on existing functionality
- Automatic code generation built into apply process using modules.py
- Stage-aware validation and testing
- Automatic branch lifecycle management
- Developer responsibility model for conflict management

## Release Stage Cleanup and Maintenance

### Automatic Cleanup Policies

```bash
# After successful production deployment
# Clean up intermediate stage files (configurable)
half_orm dev deploy-to-prod "1.3.4"
# → Deployment successful
# → Optional cleanup of 1.3.4-stage.txt and 1.3.4-rc*.txt
# → Keep for audit trail or remove to reduce clutter

# Manual cleanup command
half_orm dev cleanup-releases --version="1.3.4"
# → Remove stage and RC files for deployed version
# → Keep production release file (1.3.4.txt)
# → Archive to releases/archive/ if needed

# Automatic branch cleanup validation
half_orm dev status --branch-cleanup
# → Verify no orphaned branches exist
# → Check branch deletion consistency
# → Report any manual cleanup needed
```

### Release File Audit and History

```bash
# Show complete release history
half_orm dev status --release-history
# → Display all stages of each release
# → Show promotion timeline and validation results
# → Indicate current production version
# → Show branch cleanup status

# Example output:
# 1.3.4: stage (created: 2025-01-15) → rc1 (2025-01-16) → rc2 (2025-01-17) → prod (2025-01-18) [branches cleaned]
# 1.3.3: stage → rc1 → prod (deployed: 2025-01-14) [branches cleaned]
# 1.3.2: stage → rc1 → prod (deployed: 2025-01-10) [branches cleaned]

# Audit trail for specific release
half_orm dev audit-release "1.3.4"
# → git log --follow --oneline releases/1.3.4*
# → Show complete file evolution and branch cleanup events
# → Track all patches included and when
```

## Performance and Scalability Considerations

### Large Team Scenarios

```bash
# With 50+ active patch branches:
# - Notification system uses commit --allow-empty for resync signals
# - Branch cleanup reduces repository size
# - Status commands provide filtered views
# - Single active development rule prevents RC conflicts

# Notification optimization for large teams
half_orm dev configure-notifications --batch-size=10
# → Group notifications in batches to reduce commit frequency
# → Developers can configure personal notification preferences

# Branch lifecycle optimization
half_orm dev status --branch-metrics
# → Average branch lifetime
# → Cleanup efficiency statistics
# → Repository size impact of branch management
```

### Repository Size Management

```bash
# Regular maintenance commands
half_orm dev maintenance --prune-refs
# → Clean up remote branch references
# → Remove stale tracking branches
# → Optimize repository size

# Archive old releases
half_orm dev archive-releases --older-than="6months"
# → Move old stage/RC files to releases/archive/
# → Keep production releases for version history
# → Reduce releases/ directory clutter
```

## Integration Testing Strategy

### Multi-Patch Integration Testing

```bash
# Test combinations of patches before RC promotion
half_orm dev test-integration "1.3.4-stage"
# → Apply all patches in release sequentially
# → Test each combination: patch1, patch1+patch2, patch1+patch2+patch3
# → Identify integration issues early
# → Report which patch combinations cause problems

# Cross-patch dependency validation (passive analysis only)
half_orm dev validate-dependencies "1.3.4-stage"
# → Analyze patch order requirements
# → Suggest optimal ordering
# → Warn about potential conflicts
# → No automatic enforcement - developer responsibility
```

### Continuous Integration Hooks

```bash
# Git hooks for automated validation
# pre-commit: Validate patch file syntax
# pre-push: Run basic patch application tests
# post-receive: Trigger notification system

# CI/CD integration points:
# - Stage release creation → trigger staging deployment
# - RC promotion → trigger comprehensive test suite
# - Production promotion → trigger deployment pipeline
```

## Security and Compliance

### Audit Trail and Compliance

```bash
# Complete audit trail for compliance
half_orm dev audit-trail --from="2024-01-01" --to="2024-12-31"
# → List all patches applied to production
# → Show approval chain: stage → rc → production
# → Include deployment timestamps and responsible users
# → Export compliance reports

# Security patch tracking
half_orm dev security-report
# → Identify security patches in releases
# → Track emergency deployments (hotfixes)
# → Show time-to-deployment for critical fixes
```

### Access Control Integration

```bash
# Role-based command access (future enhancement)
# - Developers: create-patch, add-to-release
# - Release managers: promote-to-rc, promote-to-prod
# - Operations: deploy-to-prod, rollback

# Approval workflow integration
half_orm dev require-approval --for="promote-to-prod"
# → Require explicit approval before production promotion
# → Integration with pull request workflows
# → Audit approval chain
```

## Avoided Anti-Patterns and Eliminated Complexities

### ✅ Eliminated Intermediate Branches
- **Direct patch development** - No ho-dev/X.Y.x containers
- **Simplified architecture** - Only 2 branch types needed
- **Reduced synchronization** - No complex branch state management
- **Natural workflow** - Patch → Release → Production

### ✅ Unified Process for All Changes
- **Same workflow** for features, fixes, security, performance
- **Emergency support** - Hotfix mechanism for critical situations
- **Consistent tooling** - One set of commands for everything
- **Predictable process** - Always the same path to production

### ✅ Multi-Environment Support Without Branch Complexity
- **File-based stages** - stage/rc/prod differentiated by filename
- **Sequential promotion** - Clear progression through environments
- **Single branch** - All development on ho-prod with patch branches
- **Natural validation** - Each stage has appropriate validation level

### ✅ Respectful Developer Workflow
- **Notification-based sync** - Developers control when to integrate changes
- **No forced merges** - Respects ongoing work and timing
- **Standard Git workflow** - Uses familiar merge process
- **Clear communication** - Explicit notification of what needs syncing

### ✅ Automatic Branch Management
- **Intelligent cleanup** - Branches deleted at appropriate lifecycle stage
- **Preserve flexibility** - Branches kept during mutable stage development
- **Immutable releases** - No branches exist for RC and production (clean state)
- **Emergency workflow** - Immediate cleanup for hotfix deployment

### ✅ Developer Responsibility Model
- **No automatic conflict prevention** - Developers manage patch interactions
- **Error-based feedback** - Discover conflicts during application/testing
- **Team coordination** - Manual communication and planning
- **Flexible resolution** - Multiple strategies available

### ✅ Single Active Development Rule
- **One RC at a time** - Prevents parallel development chaos
- **Clear focus** - Teams concentrate on one release validation
- **Sequential progression** - Logical order from development to production
- **Reduced complexity** - No complex RC management needed

### ✅ Streamlined Version Management
- **No version skipping** - always sequential (except emergency hotfixes)
- **Database-driven calculation** - no ambiguity
- **File-based tracking** - no complex metadata
- **Single source of truth** per release stage

### ✅ Ultra-Simple Architecture
```bash
# BEFORE (complex):
ho-prod + ho-dev/X.Y.x + ho-patch/name + ho-sec/X.Y.Z  # 4 branch types
Multiple workflows for different change types
Automatic conflict detection and resolution
Parallel RC management

# AFTER (ultra-simple):
ho-prod + ho-patch/name                                 # 2 branch types
One unified workflow for all changes
Multi-environment via file suffixes (-stage, -rc1, .txt, -hotfix1)
Automatic branch lifecycle management
Emergency hotfix support
Developer responsibility for conflicts
Single active development rule
```

## Future Extensions

### Planned Enhancements
- **Analytics**: Schema evolution statistics and impact analysis
- **Advanced Testing**: Automated patch compatibility testing
- **Performance Monitoring**: Schema change performance impact tracking
- **CI/CD Integration**: Automated testing and deployment pipelines
- **Patch Templates**: Standard templates for common patch types
- **Release Automation**: Automated promotion based on validation results
- **Multi-Database Support**: Cross-database schema synchronization
- **Advanced Notifications**: Configurable notification preferences and grouping
- **Branch Analytics**: Statistics on branch lifecycle and cleanup efficiency

### Preserved Design Principles
- **Simplicity**: File-based, standard Git workflow
- **Reliability**: Direct development, global validation, automatic rollback
- **Collaboration**: Natural Git workflow, standard conflict resolution
- **Maintainability**: Lightweight backups, comprehensive testing, clean history
- **Flexibility**: Multi-environment support without architectural complexity
- **Efficiency**: Automatic branch management, optimized notifications
- **Developer Control**: Team responsibility for conflict management and coordination

## Glossary

- **patch_id**: Unique patch identifier (e.g., "456-user-authentication")
- **Patch branch**: `ho-patch/456-user-authentication` for complete patch development
- **Stage release**: `releases/X.Y.Z-stage.txt` for active development and patch integration
- **Release candidate**: `releases/X.Y.Z-rc1.txt` for validation and testing phase
- **Production release**: `releases/X.Y.Z.txt` for final deployment to production
- **Hotfix release**: `releases/X.Y.Z-hotfix1.txt` for emergency fixes bypassing normal sequence
- **Production branch**: `ho-prod` (main branch, always at latest production state)
- **Clean schema**: `model/schema.sql` (production-ready schema for new instances)
- **Production backup**: `backups/X.Y.Z.sql` (schema + metadata backup before upgrade)
- **Resync notification**: Automatic notification commits sent to active development branches when patches are integrated, using commit --allow-empty
- **Manual resync**: Developer-controlled integration of changes via standard Git merge workflow
- **Sequential promotion**: Only next version after production can be promoted through stages
- **Single active development**: Only one RC can exist at any time; must be promoted before next RC creation
- **Version 0.0.0**: Initial project version containing only half-orm-dev metadata
- **Unified workflow**: Same process for all types of changes (features, fixes, security, emergencies)
- **Release prioritization**: Managing urgency through release type selection (normal vs hotfix)
- **Stage mutability**: Only stage releases are mutable; RC and production are immutable via git mv
- **Version calculation**: Automatic determination of next version based on latest existing release across all stages
- **Git mv workflow**: Single file evolution preserves complete history while eliminating duplication
- **Branch lifecycle management**: Automatic deletion of branches at promote-to-rc to maintain clean repository state
- **Emergency hotfix**: Critical patches that bypass normal release sequence for immediate deployment
- **Apply-patch**: Command to apply current patch files to database and generate code using modules.py integration
- **Automatic integration**: Hotfix changes automatically included in future normal releases via ho-prod history
- **Developer responsibility**: Manual conflict management and patch coordination by development teams
- **Rollback point**: Git tag and database backup created before production deployment for guaranteed recovery