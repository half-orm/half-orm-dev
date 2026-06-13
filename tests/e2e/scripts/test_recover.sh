#!/usr/bin/env bash

# Test script for hop recover command
# Tests Phase 1 and Phase 2 crash recovery scenarios

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

PROJECT_NAME="hop_recover_test"
DB_NAME="hop_recover_test"
GIT_ORIGIN="/tmp/${PROJECT_NAME}.git"
VERSION="0.1.0"

echo "============================================================"
echo "  Testing hop recover command"
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
# STEP 1: Initialize project and create release
# ============================================================

init_hop_project "$PROJECT_NAME" "$GIT_ORIGIN"

# Create release
create_release "minor"

# Create and merge a patch to have a realistic state
echo "=== CREATE AND MERGE INITIAL PATCH ==="
create_patch_with_sql "1-initial-table" "
CREATE TABLE items (
    id SERIAL PRIMARY KEY,
    label TEXT NOT NULL
);
"

git add .
git commit -m "Add initial patch"
half_orm dev patch apply
git add .
git commit -m "Apply patch"

apply_and_merge_patch "1-initial-table"

# Return to release branch
git checkout ho-release/$VERSION

echo ""
echo "=== INITIAL STATE READY ==="
echo "Current branch: $(git branch --show-current)"

# ============================================================
# TEST 1: Phase 2 crash recovery (commit done, push not done)
# ============================================================

echo ""
echo "============================================================"
echo "  TEST 1: Phase 2 crash recovery"
echo "============================================================"

BRANCH="ho-release/$VERSION"
BEFORE_SHA=$(git rev-parse HEAD)

echo "=== SIMULATE PHASE 2 CRASH ==="
echo "Before SHA: $BEFORE_SHA"

# Create a sync commit (Phase 1 completed)
git commit --allow-empty -m "[HOP] Sync .hop/ — crash simulation (Phase 2 interrupted)"
SYNC_SHA=$(git rev-parse HEAD)
echo "Sync SHA: $SYNC_SHA"

# Create lock artifacts
LOCK_TAG="lock-ho-release-$(echo $VERSION | tr '.' '-')-$(date +%s)000"
echo "Lock tag: $LOCK_TAG"

git tag -a $LOCK_TAG -m "Crash test lock" $BEFORE_SHA
git push origin $LOCK_TAG

git update-ref refs/hop/sync/before/$BRANCH $BEFORE_SHA

echo "$LOCK_TAG" > .git/hop-sync-lock

# Verify lock is blocking commands
echo "=== VERIFY LOCK BLOCKS COMMANDS ==="
set +e
set -o pipefail
half_orm dev patch create blocked-patch 2>&1 | tee /tmp/blocked.log
BLOCKED_EXIT=$?
set +o pipefail
set -e

if [ $BLOCKED_EXIT -eq 0 ]; then
    error "Command should have been blocked by lock file"
fi

if ! grep -q "hop recover" /tmp/blocked.log; then
    error "Error message should mention 'hop recover'"
fi

echo "✓ Lock correctly blocks commands"

# Run recover
echo ""
echo "=== RUN HOP RECOVER ==="
half_orm dev recover

# Verify recovery
echo "=== VERIFY RECOVERY ==="

# Sync commit should be pushed
git fetch origin
ORIGIN_SHA=$(git rev-parse origin/$BRANCH)
if [ "$ORIGIN_SHA" != "$SYNC_SHA" ]; then
    error "Expected origin/$BRANCH=$SYNC_SHA, got $ORIGIN_SHA"
fi
echo "✓ Sync commit was pushed to origin"

# Lock tag should be removed
REMOTE_TAGS=$(git ls-remote --tags origin "lock-*")
if echo "$REMOTE_TAGS" | grep -q "$LOCK_TAG"; then
    error "Lock tag should have been removed from origin"
fi
echo "✓ Lock tag removed from origin"

# Local artifacts should be cleaned
if [ -f .git/hop-sync-lock ]; then
    error "Lock file should be deleted"
fi
echo "✓ Lock file deleted"

RECOVERY_REFS=$(git for-each-ref refs/hop/sync/)
if [ -n "$RECOVERY_REFS" ]; then
    error "Recovery refs should be deleted: $RECOVERY_REFS"
fi
echo "✓ Recovery refs deleted"

# Subsequent command should work
echo "=== VERIFY SUBSEQUENT COMMANDS WORK ==="
half_orm dev patch create 2-post-recovery
if ! git branch -l "ho-patch/*" | grep -q "ho-patch/2-post-recovery"; then
    error "Patch branch should have been created"
fi
echo "✓ Subsequent commands work"

# Cleanup patch branch
git checkout ho-release/$VERSION
git branch -D ho-patch/2-post-recovery 2>/dev/null || true

echo ""
echo "✓ TEST 1 PASSED: Phase 2 crash recovery works"

# ============================================================
# TEST 2: Phase 1 crash recovery (staged changes, no commit)
# ============================================================

echo ""
echo "============================================================"
echo "  TEST 2: Phase 1 crash recovery"
echo "============================================================"

git checkout ho-release/$VERSION
BEFORE_SHA=$(git rev-parse HEAD)

echo "=== SIMULATE PHASE 1 CRASH ==="
echo "Before SHA: $BEFORE_SHA"

# Stage changes without committing
echo "# crash marker" >> .hop/config
git add .hop/config

# Create lock artifacts
LOCK_TAG="lock-ho-release-$(echo $VERSION | tr '.' '-')-$(date +%s)000"
echo "Lock tag: $LOCK_TAG"

git tag -a $LOCK_TAG -m "Crash test lock (phase 1)" $BEFORE_SHA
git push origin $LOCK_TAG

git update-ref refs/hop/sync/before/$BRANCH $BEFORE_SHA

echo "$LOCK_TAG" > .git/hop-sync-lock

# Verify staged changes exist
if ! git diff --cached --quiet; then
    echo "✓ Staged changes present (simulating crash)"
else
    error "Expected staged changes to be present"
fi

# Run recover
echo ""
echo "=== RUN HOP RECOVER ==="
half_orm dev recover

# Verify recovery
echo "=== VERIFY RECOVERY ==="

# Staged changes should be cleaned
if ! git diff --cached --quiet; then
    error "Staged changes should have been cleaned"
fi
echo "✓ Staged changes cleaned"

# Working directory should be clean
if ! git diff --quiet; then
    error "Working directory should be clean"
fi
echo "✓ Working directory clean"

# HEAD should still be at before_sha
CURRENT_SHA=$(git rev-parse HEAD)
if [ "$CURRENT_SHA" != "$BEFORE_SHA" ]; then
    error "HEAD should still be at $BEFORE_SHA, got $CURRENT_SHA"
fi
echo "✓ HEAD unchanged"

# Lock artifacts should be cleaned
if [ -f .git/hop-sync-lock ]; then
    error "Lock file should be deleted"
fi
echo "✓ Lock file deleted"

RECOVERY_REFS=$(git for-each-ref refs/hop/sync/)
if [ -n "$RECOVERY_REFS" ]; then
    error "Recovery refs should be deleted"
fi
echo "✓ Recovery refs deleted"

echo ""
echo "✓ TEST 2 PASSED: Phase 1 crash recovery works"

# ============================================================
# SUMMARY
# ============================================================

echo ""
echo "============================================================"
echo "  SUMMARY: hop recover tests"
echo "============================================================"
echo ""
echo "✓ Phase 2 crash recovery (push not done)"
echo "✓ Phase 1 crash recovery (commit not done)"
echo ""
echo "All recover tests passed!"

# Cleanup
cd /tmp
rm -rf "$SCRIPT_DIR/$PROJECT_NAME"

echo ""
echo "=== TEST COMPLETED ==="
cd "$CUR_DIR"
