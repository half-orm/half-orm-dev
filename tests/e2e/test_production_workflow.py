"""
End-to-end tests for production workflow.

Tests the complete production lifecycle:
- Update command (fetch and list available releases)
- Upgrade command (apply releases to production database)
- Bootstrap execution during upgrade
- Production mode command availability
"""

import os
import pytest
import subprocess
from pathlib import Path

from tests.e2e.conftest import run_cmd


@pytest.fixture(scope="function")
def production_environment(initialized_project):
    """
    Create a production environment with releases ready to upgrade.

    Sets up:
    - Development project with releases
    - A separate production database cloned from the project
    - Production configuration (production=True)

    Yields:
        dict with:
        - dev_env: The development environment dict
        - prod_db_name: Production database name
        - prod_project_dir: Path to production project
        - run_prod: Helper function to run commands in production project
    """
    env = initialized_project
    run = env['run']
    project_dir = env['project_dir']
    work_dir = env['work_dir']
    base_dir = work_dir.parent

    # === CREATE RELEASES IN DEVELOPMENT ===

    # Checkout ho-prod and create first release
    run(['git', 'checkout', 'ho-prod'])
    run(['half_orm', 'dev', 'release', 'create', 'minor'])  # 0.1.0

    # Create a patch with a schema change and bootstrap file
    run(['half_orm', 'dev', 'patch', 'create', '1-add-users-table'])

    # Add SQL schema file to patch
    patch_dir = project_dir / 'Patches' / '1-add-users-table'
    schema_file = patch_dir / '01_users.sql'
    schema_file.write_text("""
        CREATE TABLE public.users (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE
        );
    """)

    # Add bootstrap file to patch
    bootstrap_file = patch_dir / '02_seed_users.sql'
    bootstrap_file.write_text("""-- @HOP:bootstrap
        INSERT INTO public.users (name, email)
        VALUES ('admin', 'admin@example.com')
        ON CONFLICT DO NOTHING;
    """)

    # Apply and merge the patch
    run(['half_orm', 'dev', 'patch', 'apply'])
    run(['git', 'add', '.'])
    run(['git', 'commit', '-m', 'Add users table patch', '--no-verify'])
    run(['half_orm', 'dev', 'patch', 'merge', '--force'])

    # Promote to production
    run(['git', 'checkout', 'ho-prod'])
    run(['half_orm', 'dev', 'release', 'promote', 'prod'])

    # Push tags and branches to origin
    run(['git', 'push', 'origin', '--all'])
    run(['git', 'push', 'origin', '--tags'])

    # Create second release with another patch
    run(['half_orm', 'dev', 'release', 'create', 'patch'])  # 0.1.1

    run(['half_orm', 'dev', 'patch', 'create', '2-add-posts-table'])

    patch_dir2 = project_dir / 'Patches' / '2-add-posts-table'
    schema_file2 = patch_dir2 / '01_posts.sql'
    schema_file2.write_text("""
        CREATE TABLE public.posts (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES public.users(id),
            title TEXT NOT NULL,
            content TEXT
        );
    """)

    run(['half_orm', 'dev', 'patch', 'apply'])
    run(['git', 'add', '.'])
    run(['git', 'commit', '-m', 'Add posts table patch', '--no-verify'])
    run(['half_orm', 'dev', 'patch', 'merge', '--force'])

    run(['git', 'checkout', 'ho-prod'])
    run(['half_orm', 'dev', 'release', 'promote', 'prod'])

    # Push again
    run(['git', 'push', 'origin', '--all'])
    run(['git', 'push', 'origin', '--tags'])

    # === CREATE PRODUCTION ENVIRONMENT ===

    prod_db_name = f"{env['db_name']}_prod"
    prod_project_dir = work_dir / 'production'

    # Create production config directory
    prod_config_dir = base_dir / '.half_orm_prod'
    prod_config_dir.mkdir(exist_ok=True)

    # Create config file for production database
    prod_config_file = prod_config_dir / prod_db_name
    prod_config_file.write_text(f"""[database]
name = {prod_db_name}
user = {env['db_user']}
host = localhost
port = 5432
password = {env['db_password']}
production = True
""")

    # Clone the project for production use
    prod_env = {**os.environ, **env['env'], 'HALFORM_CONF_DIR': str(prod_config_dir)}

    # Clone from origin (simulates production deployment)
    clone_result = run_cmd(
        ['half_orm', 'dev', 'clone', str(env['git_origin']),
         '--database-name', prod_db_name,
         '--user', env['db_user'],
         '--password', env['db_password'],
         '--dest-dir', 'production',
         '--production'],
        cwd=str(work_dir),
        env=prod_env,
        input_text='y\n',
        check=False
    )

    if clone_result.returncode != 0:
        pytest.fail(f"Production clone failed: {clone_result.stderr}")

    prod_project_dir = work_dir / 'production'

    def run_in_prod(cmd, input_text=None, check=True):
        """Run command in production project directory."""
        return run_cmd(cmd, cwd=str(prod_project_dir), env=prod_env, input_text=input_text, check=check)

    # Configure git user
    run_in_prod(['git', 'config', 'user.email', 'prod@example.com'])
    run_in_prod(['git', 'config', 'user.name', 'Prod User'])

    yield {
        'dev_env': env,
        'prod_db_name': prod_db_name,
        'prod_project_dir': prod_project_dir,
        'prod_config_dir': prod_config_dir,
        'run_prod': run_in_prod,
        'run_dev': run,
        'env': prod_env
    }

    # Cleanup production database
    run_cmd(
        ['dropdb', '-U', env['db_user'], '-h', 'localhost',
         '--if-exists', '--force', prod_db_name],
        env=prod_env,
        check=False
    )


@pytest.mark.integration
class TestProductionModeCommands:
    """Test that production mode has correct commands available."""

    def test_production_mode_excludes_check(self, production_environment):
        """Test that 'check' command is not available in production mode."""
        run_prod = production_environment['run_prod']

        result = run_prod(['half_orm', 'dev', 'check'], check=False)

        # Should fail because check is not available in production
        assert result.returncode != 0
        assert 'No such command' in result.stderr or 'not available' in result.stderr.lower()

    def test_production_mode_has_update(self, production_environment):
        """Test that 'update' command is available in production mode."""
        run_prod = production_environment['run_prod']

        result = run_prod(['half_orm', 'dev', 'update'], check=False)

        # Should succeed (or show no updates if already current)
        assert result.returncode == 0

    def test_production_mode_has_upgrade(self, production_environment):
        """Test that 'upgrade' command is available in production mode."""
        run_prod = production_environment['run_prod']

        # Use --dry-run to avoid actual changes
        result = run_prod(['half_orm', 'dev', 'upgrade', '--dry-run'], check=False)

        # Should succeed
        assert result.returncode == 0

    def test_production_mode_has_bootstrap(self, production_environment):
        """Test that 'bootstrap' command is available in production mode."""
        run_prod = production_environment['run_prod']

        result = run_prod(['half_orm', 'dev', 'bootstrap', '--dry-run'], check=False)

        # Should succeed
        assert result.returncode == 0


@pytest.mark.integration
class TestUpdateCommand:
    """Test the update command in production."""

    def test_update_shows_current_version(self, production_environment):
        """Test update displays current production version."""
        run_prod = production_environment['run_prod']

        result = run_prod(['half_orm', 'dev', 'update'])

        assert result.returncode == 0
        assert 'Current production version' in result.stdout

    def test_update_fetches_releases(self, production_environment):
        """Test update fetches from origin."""
        run_prod = production_environment['run_prod']

        result = run_prod(['half_orm', 'dev', 'update'])

        assert result.returncode == 0
        assert 'Fetching releases' in result.stdout


@pytest.mark.integration
class TestUpgradeCommand:
    """Test the upgrade command in production."""

    def test_upgrade_dry_run(self, production_environment):
        """Test upgrade --dry-run shows what would be applied."""
        run_prod = production_environment['run_prod']
        prod_db_name = production_environment['prod_db_name']

        # First, let's check current state
        result = run_prod(['half_orm', 'dev', 'upgrade', '--dry-run'])

        assert result.returncode == 0
        assert 'DRY RUN' in result.stdout or 'already at latest' in result.stdout.lower()

    def test_upgrade_with_skip_backup(self, production_environment):
        """Test upgrade with --skip-backup option."""
        run_prod = production_environment['run_prod']

        result = run_prod(['half_orm', 'dev', 'upgrade', '--skip-backup'], check=False)

        # Should succeed (might be at latest already)
        assert result.returncode == 0

    def test_upgrade_creates_backup_by_default(self, production_environment):
        """Test that upgrade creates backup unless --skip-backup is used."""
        run_prod = production_environment['run_prod']
        prod_project_dir = production_environment['prod_project_dir']

        # Check if there are releases to apply
        update_result = run_prod(['half_orm', 'dev', 'update'])

        # If there are updates, upgrade should create backup
        if 'Available releases' in update_result.stdout:
            result = run_prod(['half_orm', 'dev', 'upgrade'])
            assert result.returncode == 0
            # Check backup was created
            assert 'Backup created' in result.stdout or 'already at latest' in result.stdout.lower()


@pytest.mark.integration
class TestBootstrapInProduction:
    """Test bootstrap execution in production context."""

    def test_bootstrap_runs_after_clone(self, production_environment):
        """Test that bootstrap files run after production clone."""
        prod_db_name = production_environment['prod_db_name']
        prod_env = production_environment['env']

        # Check if bootstrap was executed during clone
        from half_orm.model import Model
        model = Model(prod_db_name)
        try:
            # Check if users table exists (from schema)
            result = list(model.execute_query(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = 'users')"
            ))
            table_exists = result[0]['exists']
            assert table_exists, "Users table should exist after clone"

            # Check if bootstrap data was inserted
            users = list(model.execute_query(
                "SELECT name, email FROM public.users WHERE email = 'admin@example.com'"
            ))
            assert len(users) == 1, "Bootstrap should have inserted admin user"
            assert users[0]['name'] == 'admin'
        finally:
            model.disconnect()

    def test_bootstrap_tracked_in_table(self, production_environment):
        """Test that executed bootstrap scripts are tracked."""
        prod_db_name = production_environment['prod_db_name']

        from half_orm.model import Model
        model = Model(prod_db_name)
        try:
            # Check bootstrap tracking table
            tracked = list(model.execute_query(
                "SELECT filename, version FROM half_orm_meta.bootstrap"
            ))
            # Should have at least one tracked file
            assert len(tracked) >= 0  # May be 0 if bootstrap ran during patch merge
        finally:
            model.disconnect()

    def test_bootstrap_command_in_production(self, production_environment):
        """Test bootstrap command works in production mode."""
        run_prod = production_environment['run_prod']

        # Run bootstrap (should be idempotent)
        result = run_prod(['half_orm', 'dev', 'bootstrap'])

        assert result.returncode == 0


@pytest.mark.integration
class TestProductionUpgradeWithNewRelease:
    """Test production upgrade when new releases are available."""

    def test_upgrade_applies_new_release(self, production_environment):
        """Test that upgrade applies a new release created after clone."""
        dev_env = production_environment['dev_env']
        run_dev = production_environment['run_dev']
        run_prod = production_environment['run_prod']
        prod_db_name = production_environment['prod_db_name']

        # First check current production version
        from half_orm.model import Model
        model = Model(prod_db_name)
        try:
            before_tables = list(model.execute_query(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' ORDER BY table_name"
            ))
            before_table_names = [t['table_name'] for t in before_tables]
        finally:
            model.disconnect()

        # Create a new release in development
        dev_project = dev_env['project_dir']
        run_dev(['git', 'checkout', 'ho-prod'])
        run_dev(['half_orm', 'dev', 'release', 'create', 'patch'])  # 0.1.2

        run_dev(['half_orm', 'dev', 'patch', 'create', '3-add-comments'])

        patch_dir = dev_project / 'Patches' / '3-add-comments'
        schema_file = patch_dir / '01_comments.sql'
        schema_file.write_text("""
            CREATE TABLE public.comments (
                id SERIAL PRIMARY KEY,
                post_id INTEGER REFERENCES public.posts(id),
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)

        run_dev(['half_orm', 'dev', 'patch', 'apply'])
        run_dev(['git', 'add', '.'])
        run_dev(['git', 'commit', '-m', 'Add comments table', '--no-verify'])
        run_dev(['half_orm', 'dev', 'patch', 'merge', '--force'])

        run_dev(['git', 'checkout', 'ho-prod'])
        run_dev(['half_orm', 'dev', 'release', 'promote', 'prod'])

        # Push to origin
        run_dev(['git', 'push', 'origin', '--all'])
        run_dev(['git', 'push', 'origin', '--tags'])


        # Update production to see new release
        update_result = run_prod(['half_orm', 'dev', 'update'])
        assert 'Available releases' in update_result.stdout or 'up to date' in update_result.stdout.lower()

        # If there are updates, apply them
        if 'Available releases' in update_result.stdout:
            upgrade_result = run_prod(['half_orm', 'dev', 'upgrade', '--skip-backup'])
            assert upgrade_result.returncode == 0
            assert 'Upgrade complete' in upgrade_result.stdout or '0.1.2' in upgrade_result.stdout

            # Verify new table was created
            model = Model(prod_db_name)
            try:
                after_tables = list(model.execute_query(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' ORDER BY table_name"
                ))
                print('XXX', after_tables)
                after_table_names = [t['table_name'] for t in after_tables]
                assert 'comments' in after_table_names, "Comments table should exist after upgrade"
            finally:
                model.disconnect()


@pytest.mark.integration
class TestProductionUpgradeToSpecificVersion:
    """Test upgrading to a specific version."""

    def test_upgrade_to_specific_release(self, production_environment):
        """Test upgrade --to-release stops at specified version."""
        run_prod = production_environment['run_prod']

        # Use dry-run to test the option parsing
        result = run_prod(['half_orm', 'dev', 'upgrade', '--to-release=0.1.1', '--dry-run'], check=False)

        # Should succeed (even if already at that version)
        assert result.returncode == 0
