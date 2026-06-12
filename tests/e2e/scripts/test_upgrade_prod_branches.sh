#!/usr/bin/env bash

# Test script for ho-prod-X.Y.Z branch handling during upgrade
# Verifies that production upgrade fetches new versioned ho-prod branches

set -vex

CUR_DIR=$PWD
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

if [ -n "$GITHUB_ENV" ]
then
   git config --global user.email "half_orm_ci@collorg.org"
   git config --global user.name "HalfORM CI"
fi

cd $SCRIPT_DIR
export HALFORM_CONF_DIR=$SCRIPT_DIR/.config

set +v
source ./common.sh
set -v

PROJECT_NAME="hop_upgrade_branches"
DB_NAME="hop_upgrade_branches"
DB_PROD="${DB_NAME}_prod"
GIT_ORIGIN="/tmp/${PROJECT_NAME}.git"

echo "============================================================"
echo "  Testing ho-prod-X.Y.Z branches during upgrade"
echo "============================================================"

# Setup test user
setup_test_db_user

# Cleanup
echo "=== CLEANUP ==="
cleanup_all $DB_NAME $PROJECT_NAME production
rm -rf "$GIT_ORIGIN"

# Create bare git repo
create_bare_git "$GIT_ORIGIN"

# ============================================================
# DEVELOPMENT: Create initial release
# ============================================================

init_hop_project "$PROJECT_NAME" "$GIT_ORIGIN"

# Release 0.1.0
create_release "minor"

create_patch_with_sql "1-add-users" "
CREATE TABLE public.users (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE
);
"

apply_and_merge_patch "1-add-users"
promote_to_prod

echo "=== VERIFYING ho-prod-0.1.0 CREATED ==="
assert_branch_exists "ho-prod-0.1.0"

push_all

# ============================================================
# PRODUCTION: Initial clone at version 0.1.0
# ============================================================

cd $SCRIPT_DIR

clone_production "$GIT_ORIGIN" "$DB_PROD" "production"

echo ""
echo "=== INITIAL PRODUCTION STATE (0.1.0) ==="
list_local_branches
list_remote_branches

# Verify initial branch
assert_branch_exists "ho-prod-0.1.0" "Initial clone should fetch ho-prod-0.1.0 branch"

# ============================================================
# DEVELOPMENT: Create new releases
# ============================================================

cd "$SCRIPT_DIR/$PROJECT_NAME"

# Release 0.1.1
create_release "patch"

create_patch_with_sql "2-add-posts" "
CREATE TABLE public.posts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES public.users(id),
    title TEXT NOT NULL
);
"

apply_and_merge_patch "2-add-posts"
promote_to_prod

echo "=== VERIFYING ho-prod-0.1.1 CREATED ==="
assert_branch_exists "ho-prod-0.1.1"

# Release 0.2.0
create_release "minor"

create_patch_with_sql "3-add-comments" "
CREATE TABLE public.comments (
    id SERIAL PRIMARY KEY,
    post_id INTEGER REFERENCES public.posts(id),
    content TEXT NOT NULL
);
"

apply_and_merge_patch "3-add-comments"
promote_to_prod

echo "=== VERIFYING ho-prod-0.2.0 CREATED ==="
assert_branch_exists "ho-prod-0.2.0"

# Release 0.2.1
create_release "patch"

create_patch_with_sql "4-add-tags" "
CREATE TABLE public.tags (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);
"

apply_and_merge_patch "4-add-tags"
promote_to_prod

echo "=== VERIFYING ho-prod-0.2.1 CREATED ==="
assert_branch_exists "ho-prod-0.2.1"

# Push new releases
push_all

echo ""
echo "=== DEVELOPMENT BRANCHES AFTER NEW RELEASES ==="
list_local_branches

# ============================================================
# PRODUCTION: Upgrade and verify new branches
# ============================================================

cd "$SCRIPT_DIR/production"

echo ""
echo "=== PRODUCTION STATE BEFORE UPGRADE ==="
list_local_branches
list_remote_branches

echo ""
echo "=== RUNNING UPGRADE ==="
half_orm dev upgrade --skip-backup --yes

echo ""
echo "=== PRODUCTION STATE AFTER UPGRADE ==="
list_local_branches
list_remote_branches

echo ""
echo "=== VERIFYING NEW ho-prod-X.Y.Z BRANCHES ==="

# Check if new ho-prod-X.Y.Z branches exist locally
echo ""
echo "Checking local branches after upgrade:"
assert_branch_exists "ho-prod-0.1.1" "Upgrade should fetch ho-prod-0.1.1 branch"
assert_branch_exists "ho-prod-0.2.0" "Upgrade should fetch ho-prod-0.2.0 branch"
assert_branch_exists "ho-prod-0.2.1" "Upgrade should fetch ho-prod-0.2.1 branch"

# Check remote branches
echo ""
echo "Checking remote branches after upgrade:"
assert_remote_branch_exists "ho-prod-0.1.1" "Upgrade should track origin/ho-prod-0.1.1"
assert_remote_branch_exists "ho-prod-0.2.0" "Upgrade should track origin/ho-prod-0.2.0"
assert_remote_branch_exists "ho-prod-0.2.1" "Upgrade should track origin/ho-prod-0.2.1"

# Verify database state after upgrade
assert_table_exists "$DB_PROD" "users"
assert_table_exists "$DB_PROD" "posts"
assert_table_exists "$DB_PROD" "comments"
assert_table_exists "$DB_PROD" "tags"

# ============================================================
# SUMMARY
# ============================================================

echo ""
echo "============================================================"
echo "  SUMMARY: Upgrade and ho-prod-X.Y.Z Branches"
echo "============================================================"

echo ""
echo "Initial production state:"
echo "  - Clone at 0.1.0 (ho-prod-0.1.0 should be fetched)"

echo ""
echo "Development created new releases:"
echo "  - ho-prod-0.1.1"
echo "  - ho-prod-0.2.0"
echo "  - ho-prod-0.2.1"

echo ""
echo "Production after upgrade should have:"
git branch -r | grep "ho-prod-" || echo "  (none found - THIS IS THE BUG)"

echo ""
echo "Expected behavior:"
echo "  ✓ Upgrade should fetch new ho-prod-X.Y.Z branches from origin"
echo "  ✓ These branches allow rollback to specific versions"
echo "  ✓ Production servers track version history via branches"

# Cleanup
echo ""
echo "=== CLEANUP ==="
cleanup_all $DB_NAME $PROJECT_NAME production
rm -rf "$GIT_ORIGIN"

echo ""
echo "=== TEST COMPLETED ==="
cd $CUR_DIR
