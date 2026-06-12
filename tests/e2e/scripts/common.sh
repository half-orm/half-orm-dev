#!/usr/bin/env bash

# Common functions for e2e test scripts
# Usage: source ./common.sh

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Error function - prints message and exits
error() {
    local message="$1"
    echo -e "${RED}✗ ERROR: ${message}${NC}" >&2
    exit 1
}

# Configure git user if in CI
setup_git_user() {
    if [ -n "$GITHUB_ENV" ]; then
        git config --global user.email "half_orm_ci@collorg.org"
        git config --global user.name "HalfORM CI"
    fi
}

# Setup test database user
setup_test_db_user() {
    echo -e "${GREEN}=== SETTING UP TEST DB USER ===${NC}"
    set +e
    # Check if user exists
    psql -U postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='halftest'" | grep -q 1
    if [ $? -ne 0 ]; then
        # Create user if it doesn't exist
        psql -U postgres -c "CREATE USER halftest WITH PASSWORD 'halftest' CREATEDB;"
        echo -e "${GREEN}✓ Created user halftest${NC}"
    else
        echo -e "${GREEN}✓ User halftest already exists${NC}"
    fi
    set -e

    # Configure .pgpass with wildcard entry for all databases
    setup_pgpass "*"
}

# Test DB credentials
TEST_DB_USER="halftest"
TEST_DB_PASSWORD="halftest"

# Setup .pgpass for passwordless authentication
setup_pgpass() {
    local db_name="${1:-*}"  # Default to wildcard if no db specified

    echo -e "${GREEN}=== CONFIGURING .pgpass ===${NC}"

    local pgpass_file="$HOME/.pgpass"
    local pgpass_entry="*:*:${db_name}:${TEST_DB_USER}:${TEST_DB_PASSWORD}"

    # Create .pgpass if it doesn't exist
    touch "$pgpass_file"

    # Add entry if not already present
    if ! grep -qF "$pgpass_entry" "$pgpass_file" 2>/dev/null; then
        echo "$pgpass_entry" >> "$pgpass_file"
        echo -e "${GREEN}✓ Added entry to .pgpass for database: ${db_name}${NC}"
    else
        echo -e "${GREEN}✓ .pgpass already configured for database: ${db_name}${NC}"
    fi

    # Set correct permissions (PostgreSQL requires 0600)
    chmod 0600 "$pgpass_file"
    echo -e "${GREEN}✓ Set .pgpass permissions to 0600${NC}"
}

# Clean up databases
cleanup_databases() {
    local db_prefix="$1"
    set +e
    dropdb -h localhost -U "$TEST_DB_USER" "${db_prefix}" 2>/dev/null
    dropdb -h localhost -U "$TEST_DB_USER" "${db_prefix}_prod" 2>/dev/null
    set -e
}

# Clean up project directory
cleanup_project() {
    local project_name="$1"
    rm -rf "$project_name" 2>/dev/null || true
}

# Complete cleanup (databases + directories + config)
cleanup_all() {
    local db_prefix="$1"
    shift  # Get remaining arguments as directory names
    local dirs="$@"

    cd "$SCRIPT_DIR"

    # Clean directories
    rm -rf $dirs .config 2>/dev/null || true

    # Clean databases
    set +e
    dropdb -h localhost -U "$TEST_DB_USER" "${db_prefix}" 2>/dev/null
    dropdb -h localhost -U "$TEST_DB_USER" "${db_prefix}_prod" 2>/dev/null
    set -e
}

# Create bare git repository
create_bare_git() {
    local git_path="$1"
    rm -rf "$git_path"
    git init --bare "$git_path"
}

# Initialize a new hop project
init_hop_project() {
    local project_name="$1"
    local git_origin="$2"

    echo -e "${GREEN}=== INITIALIZING PROJECT ${project_name} ===${NC}"

    # Drop database if it exists (in case of previous test failure)
    set +e
    dropdb -h localhost -U "$TEST_DB_USER" "$project_name" 2>/dev/null
    set -e

    half_orm dev init "$project_name" \
        --git-origin "$git_origin" \
        --user "$TEST_DB_USER" \
        --password "$TEST_DB_PASSWORD"

    cd "$project_name"

    echo -e "${GREEN}✓ Project initialized${NC}"
}

# Create a release
create_release() {
    local level="$1"  # patch, minor, major

    echo -e "${GREEN}=== CREATING RELEASE ($level) ===${NC}"
    git checkout ho-prod
    half_orm dev release create "$level"
    echo -e "${GREEN}✓ Release created${NC}"
}

# Create a patch with SQL file
create_patch_with_sql() {
    local patch_id="$1"
    local sql_content="$2"

    echo -e "${GREEN}=== CREATING PATCH ${patch_id} ===${NC}"
    half_orm dev patch create "$patch_id"

    echo "$sql_content" > "Patches/${patch_id}/01_patch.sql"

    echo -e "${GREEN}✓ Patch created${NC}"
}

# Apply and merge a patch
apply_and_merge_patch() {
    local patch_id="$1"

    echo -e "${GREEN}=== APPLYING AND MERGING PATCH ${patch_id} ===${NC}"

    half_orm dev patch apply

    git add .
    git commit -m "Add patch ${patch_id}" --no-verify

    git checkout "ho-patch/${patch_id}"
    half_orm dev patch merge --force

    echo -e "${GREEN}✓ Patch merged${NC}"
}

# Promote release to production
promote_to_prod() {
    echo -e "${GREEN}=== PROMOTING TO PRODUCTION ===${NC}"
    git checkout ho-prod
    half_orm dev release promote prod
    echo -e "${GREEN}✓ Promoted to production${NC}"
}

# Push all branches and tags
push_all() {
    echo -e "${GREEN}=== PUSHING TO ORIGIN ===${NC}"
    git push origin --all
    git push origin --tags
    echo -e "${GREEN}✓ Pushed${NC}"
}

# Clone in production mode
clone_production() {
    local git_origin="$1"
    local db_name="$2"
    local dest_dir="$3"

    echo -e "${GREEN}=== CLONING IN PRODUCTION MODE ===${NC}"

    # Drop database if it exists (in case of previous test failure)
    set +e
    dropdb -h localhost -U "$TEST_DB_USER" "$db_name" 2>/dev/null
    set -e

    half_orm dev clone "$git_origin" \
        --database-name "$db_name" \
        --dest-dir "$dest_dir" \
        --user "$TEST_DB_USER" \
        --password "$TEST_DB_PASSWORD" \
        --production

    cd "$dest_dir"
    echo -e "${GREEN}✓ Cloned in production${NC}"
}

# Verify a branch exists locally
assert_branch_exists() {
    local branch_name="$1"
    local error_msg="${2:-Branch $branch_name should exist}"

    if ! git show-ref --verify --quiet "refs/heads/$branch_name"; then
        echo -e "${RED}✗ ASSERTION FAILED: $error_msg${NC}"
        echo -e "${RED}  Branch '$branch_name' does not exist locally${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Branch $branch_name exists${NC}"
}

# Verify a branch does NOT exist locally
assert_branch_not_exists() {
    local branch_name="$1"
    local error_msg="${2:-Branch $branch_name should NOT exist}"

    if git show-ref --verify --quiet "refs/heads/$branch_name"; then
        echo -e "${RED}✗ ASSERTION FAILED: $error_msg${NC}"
        echo -e "${RED}  Branch '$branch_name' exists but should not${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Branch $branch_name does not exist (expected)${NC}"
}

# Verify a remote branch exists
assert_remote_branch_exists() {
    local branch_name="$1"
    local error_msg="${2:-Remote branch $branch_name should exist}"

    if ! git show-ref --verify --quiet "refs/remotes/origin/$branch_name"; then
        echo -e "${RED}✗ ASSERTION FAILED: $error_msg${NC}"
        echo -e "${RED}  Remote branch 'origin/$branch_name' does not exist${NC}"
        git branch -r  # Show all remote branches for debugging
        exit 1
    fi
    echo -e "${GREEN}✓ Remote branch origin/$branch_name exists${NC}"
}

# List all local branches
list_local_branches() {
    echo -e "${YELLOW}=== LOCAL BRANCHES ===${NC}"
    git branch
}

# List all remote branches
list_remote_branches() {
    echo -e "${YELLOW}=== REMOTE BRANCHES ===${NC}"
    git branch -r
}

# Verify database table exists
assert_table_exists() {
    local db_name="$1"
    local table_name="$2"

    local exists=$(psql -h localhost -U "$TEST_DB_USER" "$db_name" -t -c "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = '$table_name')")

    if [[ "$exists" =~ "f" ]]; then
        echo -e "${RED}✗ ASSERTION FAILED: Table $table_name should exist${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Table $table_name exists${NC}"
}

# Verify row count in table
assert_row_count() {
    local db_name="$1"
    local table_name="$2"
    local expected_count="$3"
    local where_clause="${4:-}"

    local query="SELECT COUNT(*) FROM public.$table_name"
    if [ -n "$where_clause" ]; then
        query="$query WHERE $where_clause"
    fi

    local count=$(psql -h localhost -U "$TEST_DB_USER" "$db_name" -t -c "$query" | tr -d ' ')

    if [ "$count" != "$expected_count" ]; then
        echo -e "${RED}✗ ASSERTION FAILED: Expected $expected_count rows, got $count${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Row count matches: $count${NC}"
}
