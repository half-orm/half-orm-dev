#!/usr/bin/env bash

# Test script for ho-prod-X.Y.Z branch handling during clone
# Verifies that production clone fetches versioned ho-prod branches

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

PROJECT_NAME="hop_clone_branches"
DB_NAME="hop_clone_branches"
DB_PROD="${DB_NAME}_prod"
GIT_ORIGIN="/tmp/${PROJECT_NAME}.git"

echo "============================================================"
echo "  Testing ho-prod-X.Y.Z branches during clone"
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
# DEVELOPMENT: Create multiple releases
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

# List all branches in dev
list_local_branches

# Push to origin
push_all

# List remote branches
list_remote_branches

# ============================================================
# PRODUCTION: Clone and verify branches
# ============================================================

cd $SCRIPT_DIR

clone_production "$GIT_ORIGIN" "$DB_PROD" "production"

echo ""
echo "=== CHECKING BRANCHES IN PRODUCTION CLONE ==="
list_local_branches
list_remote_branches

echo ""
echo "=== VERIFYING ho-prod-X.Y.Z BRANCHES ==="

# Check if ho-prod-X.Y.Z branches exist locally in production
echo ""
echo "Checking local branches:"
assert_branch_exists "ho-prod-0.1.0" "Production clone should fetch ho-prod-0.1.0 branch"
assert_branch_exists "ho-prod-0.1.1" "Production clone should fetch ho-prod-0.1.1 branch"
assert_branch_exists "ho-prod-0.2.0" "Production clone should fetch ho-prod-0.2.0 branch"

# Check if ho-prod-X.Y.Z branches are tracked from origin
echo ""
echo "Checking remote branches:"
assert_remote_branch_exists "ho-prod-0.1.0" "Production clone should track origin/ho-prod-0.1.0"
assert_remote_branch_exists "ho-prod-0.1.1" "Production clone should track origin/ho-prod-0.1.1"
assert_remote_branch_exists "ho-prod-0.2.0" "Production clone should track origin/ho-prod-0.2.0"

# Verify database state
assert_table_exists "$DB_PROD" "users"
assert_table_exists "$DB_PROD" "posts"
assert_table_exists "$DB_PROD" "comments"

# ============================================================
# SUMMARY
# ============================================================

echo ""
echo "============================================================"
echo "  SUMMARY: Clone and ho-prod-X.Y.Z Branches"
echo "============================================================"

echo ""
echo "Development created branches:"
echo "  - ho-prod-0.1.0"
echo "  - ho-prod-0.1.1"
echo "  - ho-prod-0.2.0"

echo ""
echo "Production clone fetched:"
git branch -r | grep "ho-prod-" || echo "  (none found - THIS IS THE BUG)"

echo ""
echo "Expected behavior:"
echo "  ✓ Production servers should have access to ho-prod-X.Y.Z branches"
echo "  ✓ These branches allow rollback to specific versions"

# Cleanup
echo ""
echo "=== CLEANUP ==="
cleanup_all $DB_NAME $PROJECT_NAME production
rm -rf "$GIT_ORIGIN"

echo ""
echo "=== TEST COMPLETED ==="
cd $CUR_DIR
