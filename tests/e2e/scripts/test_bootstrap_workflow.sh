#!/usr/bin/env bash

# Test script for bootstrap workflow with new API
# Tests that bootstrap files are created manually and executed correctly

set -vex

CUR_DIR=$PWD
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
echo $SCRIPT_DIR

if [ -n "$GITHUB_ENV" ]
then
   git config --global user.email "half_orm_ci@collorg.org"
   git config --global user.name "HalfORM CI"
fi

cd $SCRIPT_DIR
export HALFORM_CONF_DIR=$SCRIPT_DIR/.config

clean_db() {
    cd $SCRIPT_DIR
    rm -rf hop_bootstrap_test hop_bootstrap_test_prod production .config
    set +e
    dropdb hop_bootstrap_test
    dropdb hop_bootstrap_test_prod
    set -e
}

echo "=== CLEANUP ==="
clean_db

# Create git repo
rm -rf /tmp/hop_bootstrap_test.git
git init --bare /tmp/hop_bootstrap_test.git

# Initialize project
half_orm dev init hop_bootstrap_test \
    --git-origin /tmp/hop_bootstrap_test.git

cd hop_bootstrap_test

echo "=== CREATE FIRST RELEASE (0.1.0) ==="
git checkout ho-prod
half_orm dev release create minor  # Creates ho-release/0.1.0

echo "=== CREATE PATCH WITH TABLE USERS ==="
half_orm dev patch create 1-add-users-table

# Add SQL file to create users table
cat > Patches/1-add-users-table/01_users.sql << 'EOF'
CREATE TABLE public.users (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE
);
EOF

echo "=== CREATE BOOTSTRAP FILE MANUALLY ==="
# Bootstrap file created manually by developer
# This file will be used during clone (production)
cat > bootstrap/01-seed-users.sql << 'EOF'
INSERT INTO public.users (name, email)
VALUES ('admin', 'admin@example.com');
EOF

echo "=== PATCH APPLY (Bootstrap should NOT execute) ==="
# At this point:
# - schema.sql = production schema (no users table yet)
# - Patch adds users table
# - Bootstrap wants to insert in users table
# - But bootstrap should NOT execute during patch apply
half_orm dev patch apply

echo "=== VERIFY TABLE EXISTS AFTER APPLY ==="
psql hop_bootstrap_test -c '\dt public.users'

echo "=== VERIFY BOOTSTRAP DID NOT EXECUTE ==="
# Bootstrap should NOT have executed, so no data should be present
set +e
COUNT=$(psql hop_bootstrap_test -t -c "SELECT COUNT(*) FROM public.users WHERE email = 'admin@example.com'")
if [ "$COUNT" -ne 0 ]; then
    echo "ERROR: Bootstrap executed during patch apply! Count=$COUNT"
    exit 1
fi
set -e
echo "OK: Bootstrap did not execute during patch apply"

echo "=== COMMIT PATCH ==="
git add .
git commit -m "Add users table and bootstrap" --no-verify

echo "=== MERGE PATCH ==="
git checkout ho-patch/1-add-users-table
half_orm dev patch merge --force

echo "=== PROMOTE TO PRODUCTION ==="
git checkout ho-prod
half_orm dev release promote prod

echo "=== PUSH TO ORIGIN ==="
git push origin --all
git push origin --tags

echo "=== CLONE IN PRODUCTION MODE ==="
cd ..
mkdir production
cd production

# Clone in production mode
half_orm dev clone /tmp/hop_bootstrap_test.git \
    --database-name hop_bootstrap_test_prod \
    --production

cd hop_bootstrap_test

echo "=== VERIFY BOOTSTRAP EXECUTED DURING CLONE ==="
# Bootstrap should have executed during clone
COUNT=$(psql hop_bootstrap_test_prod -t -c "SELECT COUNT(*) FROM public.users WHERE email = 'admin@example.com'")
if [ "$COUNT" -ne 1 ]; then
    echo "ERROR: Bootstrap did not execute during clone! Count=$COUNT"
    exit 1
fi
echo "OK: Bootstrap executed during clone. Count=$COUNT"

echo "=== VERIFY TABLE EXISTS IN PRODUCTION ==="
psql hop_bootstrap_test_prod -c '\dt public.users'
psql hop_bootstrap_test_prod -c 'SELECT * FROM public.users'

echo "=== CLEANUP ==="
clean_db

echo "=== ALL TESTS PASSED ==="
cd $CUR_DIR