#!/usr/bin/env bash

# Test script for release ordering constraint during patch merge
# Verifies that patches cannot be merged in higher releases while lower releases
# have unmerged patches (candidate or staged status)

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

PROJECT_NAME="hop_release_ordering"
DB_NAME="hop_release_ordering"
GIT_ORIGIN="/tmp/${PROJECT_NAME}.git"

echo "============================================================"
echo "  Testing release ordering constraint during merge"
echo "============================================================"

# Setup test user
setup_test_db_user

# Cleanup
echo "=== CLEANUP ==="
cleanup_all $DB_NAME $PROJECT_NAME
rm -rf "$GIT_ORIGIN"

# Create bare git repo
create_bare_git "$GIT_ORIGIN"

# ============================================================
# STEP 1: Initialize project and create first release 0.0.1
# ============================================================

init_hop_project "$PROJECT_NAME" "$GIT_ORIGIN"

# Create release 0.0.1 (patch level)
create_release "patch"

echo "=== CREATE PATCH 1-add-users IN 0.0.1 ==="
create_patch_with_sql "1-add-users" "
CREATE TABLE public.users (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE
);
"

# Add bootstrap data
echo "=== ADD BOOTSTRAP DATA ==="
cat > bootstrap/01-seed-admin.sql << 'EOF'
INSERT INTO public.users (name, email)
VALUES ('admin', 'admin@example.com');
EOF

echo "=== MERGE PATCH IN 0.0.1 ==="
apply_and_merge_patch "1-add-users"

pause_for_inspection "After merging patch 1-add-users in release 0.0.1"

echo "=== PROMOTE 0.0.1 TO PRODUCTION ==="
promote_to_prod

pause_for_inspection "After promoting 0.0.1 to production"

push_all

# ============================================================
# STEP 2: Create release 0.1.0 (minor) and a patch
# ============================================================

echo "=== CREATE RELEASE 0.1.0 (MINOR) ==="
create_release "minor"

echo "=== CREATE PATCH 2-add-posts IN 0.1.0 ==="
create_patch_with_sql "2-add-posts" "
CREATE TABLE public.posts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES public.users(id),
    title TEXT NOT NULL
);
"

# Commit the patch files first
git add .
git commit -m "Add patch 2-add-posts"

# Apply the patch to database (generates Python code)
half_orm dev patch apply

# Commit generated code
git add .
git commit -m "Generated code for patch 2-add-posts"

pause_for_inspection "After creating patch 2-add-posts in 0.1.0 (NOT merged yet)"

# ============================================================
# STEP 3: Create release 0.0.2 (patch) and a patch
# ============================================================

# Return to ho-prod to create next release
git checkout ho-prod

echo "=== CREATE RELEASE 0.0.2 (PATCH) ==="
create_release "patch"

echo "=== CREATE PATCH 3-add-role IN 0.0.2 ==="
create_patch_with_sql "3-add-role" "
ALTER TABLE public.users ADD COLUMN role TEXT DEFAULT 'user';
"

# Commit the patch files first
git add .
git commit -m "Add patch 3-add-role"

# Apply the patch to database (generates Python code)
half_orm dev patch apply

# Commit generated code
git add .
git commit -m "Generated code for patch 3-add-role"

pause_for_inspection "After creating patch 3-add-role in 0.0.2 (NOT merged yet)"

# ============================================================
# STEP 4: Try to merge patch in 0.1.0 → should FAIL
# ============================================================

echo ""
echo "=== ATTEMPTING TO MERGE PATCH IN 0.1.0 (should FAIL) ==="
echo "Reason: Release 0.0.2 (lower) has unmerged patches"

git checkout ho-patch/2-add-posts

# Enable pipefail to get exit code from first command in pipeline, not tee
set +e
set -o pipefail
half_orm dev patch merge --force 2>&1 | tee /tmp/merge_error.log
MERGE_EXIT_CODE=$?
set +o pipefail
set -e

if [ $MERGE_EXIT_CODE -eq 0 ]; then
    error "Merge should have FAILED but succeeded! Lower release 0.0.2 has unmerged patches"
fi

echo "✓ Merge correctly blocked (exit code: $MERGE_EXIT_CODE)"

# Verify error message mentions lower release
if ! grep -q "0.0.2" /tmp/merge_error.log && ! grep -q "lower release" /tmp/merge_error.log; then
    error "Error message should mention lower release blocking the merge"
fi

echo "✓ Error message correctly explains the constraint"

pause_for_inspection "After blocked merge attempt in 0.1.0"

# ============================================================
# STEP 5: Merge and promote 0.0.2
# ============================================================

echo ""
echo "=== MERGE PATCH IN 0.0.2 ==="
apply_and_merge_patch "3-add-role"

pause_for_inspection "After merging patch 3-add-role in 0.0.2"

echo "=== PROMOTE 0.0.2 TO PRODUCTION ==="
promote_to_prod

pause_for_inspection "After promoting 0.0.2 to production"

push_all

# ============================================================
# STEP 6: Now merge in 0.1.0 should SUCCEED
# ============================================================

echo ""
echo "=== ATTEMPTING TO MERGE PATCH IN 0.1.0 (should SUCCEED now) ==="
echo "Reason: No lower releases with unmerged patches"

git checkout ho-patch/2-add-posts
half_orm dev patch merge --force

echo "✓ Merge succeeded after lower release was promoted"

pause_for_inspection "After merging patch 2-add-posts in 0.1.0 (CRITICAL: check propagation)"

# ============================================================
# STEP 7: Promote 0.1.0 and verify schema consistency
# ============================================================

echo ""
echo "=== PROMOTE 0.1.0 TO PRODUCTION ==="
promote_to_prod

pause_for_inspection "After promoting 0.1.0 to production (final state)"

echo ""
echo "=== VERIFY SCHEMA CONSISTENCY ==="
echo "Checking that 0.1.0 includes changes from both releases..."

# Verify table from 0.0.1 (baseline)
assert_table_exists "$DB_NAME" "users"
echo "✓ Table users exists (from 0.0.1)"

# Verify table from 0.1.0 (higher release)
assert_table_exists "$DB_NAME" "posts"
echo "✓ Table posts exists (from 0.1.0)"

# CRITICAL: Verify users.role column exists (from lower release 0.0.2)
echo "=== VERIFY CHANGES FROM LOWER RELEASE 0.0.2 ARE PRESENT ==="
COLUMN_EXISTS=$(psql -h localhost -U $TEST_DB_USER $DB_NAME -t -c "SELECT column_name FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'role'" | tr -d ' ')
if [ -z "$COLUMN_EXISTS" ]; then
    error "Column users.role should exist (added in 0.0.2). Lower release changes not propagated!"
fi
echo "✓ Column users.role exists (from 0.0.2)"
echo "✓ Schema consistency verified: lower release changes propagated to higher release"

# ============================================================
# SUMMARY
# ============================================================

echo ""
echo "============================================================"
echo "  SUMMARY: Release Ordering Constraint"
echo "============================================================"

echo ""
echo "Test verified:"
echo "  ✓ Patch merge blocked in 0.1.0 when 0.0.2 has unmerged patches"
echo "  ✓ Error message clearly explains the constraint"
echo "  ✓ Patch merge succeeds after 0.0.2 is promoted"
echo "  ✓ Sequential promotion maintains schema consistency"
echo "  ✓ Changes from lower releases propagate to higher releases"

# Cleanup project directory (but keep DB and git for post-mortem debugging if needed)
echo ""
echo "=== CLEANUP PROJECT DIRECTORY ==="
# Make sure we're outside the project directory before removing it
cd /tmp
rm -rf "$SCRIPT_DIR/$PROJECT_NAME"
echo "✓ Removed $PROJECT_NAME directory"

# Note: Database and git origin kept for debugging
# To cleanup manually:
#   dropdb -h localhost -U halftest $DB_NAME
#   rm -rf "$GIT_ORIGIN"

echo ""
echo "=== TEST COMPLETED ==="
cd "$CUR_DIR"
