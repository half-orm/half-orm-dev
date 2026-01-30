"""
End-to-end tests for clone workflow with multi-developer scenarios.

These tests validate:
1. Basic clone functionality
2. Clone with --database-name (different local DB name)
3. Clone with --dest-dir (custom directory)
4. Package name preservation after clone

Bug scenario: When cloning with --database-name, the Python package generation
incorrectly uses the database name instead of the original package name,
causing modules to be generated in the wrong directory.
"""

import os
import pytest
from pathlib import Path

from tests.e2e.conftest import run_cmd


pytestmark = pytest.mark.e2e


class TestCloneBasic:
    """Test basic clone workflow."""

    def test_clone_creates_project_structure(self, initialized_project):
        """Test that clone creates proper project structure from existing project."""
        env = initialized_project
        work_dir = env['work_dir']
        project_dir = env['project_dir']
        git_origin = env['git_origin']
        config_dir = env['config_dir']
        db_user = env['db_user']
        db_password = env['db_password']

        # First, push the initialized project to origin
        run = env['run']
        run(['git', 'push', '-u', 'origin', 'ho-prod'])

        # Create a second working directory for the clone
        clone_work_dir = work_dir.parent / 'clone_work'
        clone_work_dir.mkdir()

        # Generate unique database name for the clone
        import uuid
        clone_db_name = f"hop_clone_{str(uuid.uuid4())[:8]}"

        # Create half_orm config for clone database
        clone_config_file = config_dir / clone_db_name
        clone_config_content = f"""[database]
name = {clone_db_name}
user = {db_user}
host = localhost
port = 5432
"""
        if db_password:
            clone_config_content += f"password = {db_password}\n"
        clone_config_file.write_text(clone_config_content)

        # Clone the project
        cmd_env = env['env'].copy()
        cmd_env['HALFORM_CONF_DIR'] = str(config_dir)
        cmd_env['PGPASSWORD'] = db_password

        result = run_cmd(
            [
                'half_orm', 'dev', 'clone', str(git_origin),
                '--database-name', clone_db_name,
                '--user', db_user,
                '--password', db_password or ''
            ],
            cwd=clone_work_dir,
            env=cmd_env
        )

        # Verify clone succeeded
        # The clone directory is named after the git repo (origin.git -> origin)
        clone_dir = clone_work_dir / 'origin'

        assert clone_dir.exists(), f"Clone directory not created: {clone_dir}"
        assert (clone_dir / '.hop').is_dir()
        assert (clone_dir / '.hop' / 'config').is_file()
        assert (clone_dir / '.hop' / 'alt_config').is_file()  # Should have alt_config
        assert (clone_dir / '.git').is_dir()

        # Verify alt_config contains the custom database name
        alt_config = (clone_dir / '.hop' / 'alt_config').read_text().strip()
        assert alt_config == clone_db_name

        # Cleanup clone database
        run_cmd(
            ['dropdb', '-U', db_user, '-h', 'localhost', '--if-exists', '--force', clone_db_name],
            env=cmd_env,
            check=False
        )


class TestCloneWithDatabaseName:
    """Test clone with --database-name option (multi-developer scenario)."""

    def test_clone_preserves_package_name(self, initialized_project):
        """
        Test that clone with --database-name preserves the original package name.

        Bug scenario:
        1. Developer A creates project 'test_pg' with database 'test_pg'
        2. Developer B clones with --database-name 'alt_test_pg'
        3. Python modules should still be generated in test_pg/ directory
           (not alt_test_pg/)

        This test verifies that package_name is correctly stored and used
        independently of database_name.
        """
        env = initialized_project
        work_dir = env['work_dir']
        project_dir = env['project_dir']
        git_origin = env['git_origin']
        config_dir = env['config_dir']
        db_user = env['db_user']
        db_password = env['db_password']
        original_project_name = env['db_name']

        # Push the initialized project to origin
        run = env['run']
        run(['git', 'push', '-u', 'origin', 'ho-prod'])

        # Create a release and add a patch with a table
        run(['git', 'checkout', 'ho-prod'])
        run(['half_orm', 'dev', 'release', 'create', 'minor'])

        run(['half_orm', 'dev', 'patch', 'create', '1-users'])
        run(['git', 'checkout', 'ho-patch/1-users'])

        patch_dir = project_dir / 'Patches' / '1-users'
        (patch_dir / '01_users.sql').write_text(
            'CREATE TABLE users (id SERIAL PRIMARY KEY, name TEXT NOT NULL);'
        )

        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Add users table'])
        run(['half_orm', 'dev', 'patch', 'merge'], input_text='y\n')

        # Promote to production
        run(['git', 'checkout', 'ho-release/0.1.0'])
        run(['half_orm', 'dev', 'release', 'promote', 'rc'])
        run(['half_orm', 'dev', 'release', 'promote', 'prod'])

        # Push everything to origin
        run(['git', 'push', '--all', 'origin'])
        run(['git', 'push', '--tags', 'origin'])

        # Verify original project has correct package structure
        original_package_dir = project_dir / original_project_name
        assert original_package_dir.exists(), \
            f"Original package dir should exist: {original_package_dir}"
        assert (original_package_dir / 'public').exists(), \
            "Original package should have public schema module"

        # Now clone with a different database name (Developer B scenario)
        clone_work_dir = work_dir.parent / 'dev_b_workspace'
        clone_work_dir.mkdir()

        import uuid
        alt_db_name = f"alt_db_{str(uuid.uuid4())[:8]}"

        # Create half_orm config for alternate database
        alt_config_file = config_dir / alt_db_name
        alt_config_content = f"""[database]
name = {alt_db_name}
user = {db_user}
host = localhost
port = 5432
"""
        if db_password:
            alt_config_content += f"password = {db_password}\n"
        alt_config_file.write_text(alt_config_content)

        cmd_env = env['env'].copy()
        cmd_env['HALFORM_CONF_DIR'] = str(config_dir)
        cmd_env['PGPASSWORD'] = db_password

        # Clone with custom database name
        result = run_cmd(
            [
                'half_orm', 'dev', 'clone', str(git_origin),
                '--database-name', alt_db_name,
                '--user', db_user,
                '--password', db_password or ''
            ],
            cwd=clone_work_dir,
            env=cmd_env
        )

        # The cloned project directory is named after the git repo (origin.git -> origin)
        clone_dir = clone_work_dir / 'origin'
        assert clone_dir.exists(), \
            f"Clone directory should exist: {clone_dir}"

        # The Python package directory should use the ORIGINAL package name
        # BUG: Currently it might incorrectly use alt_db_name
        cloned_package_dir = clone_dir / original_project_name
        wrong_package_dir = clone_dir / alt_db_name

        assert cloned_package_dir.exists(), \
            f"Package directory should be '{original_project_name}/', not '{alt_db_name}/'. " \
            f"Bug: package_name is being confused with database_name"
        assert not wrong_package_dir.exists(), \
            f"Package directory should NOT be '{alt_db_name}/'"

        # Verify the package has the correct modules
        assert (cloned_package_dir / 'public').exists(), \
            "Cloned package should have public schema module"
        assert (cloned_package_dir / 'public' / 'users.py').exists(), \
            "Cloned package should have users.py module"

        # Verify .hop/config stores the package_name
        config_path = clone_dir / '.hop' / 'config'
        config_content = config_path.read_text()
        # The config should have package_name that differs from database name
        assert 'package_name' in config_content or original_project_name in config_content, \
            "Config should store the original package name"

        # Cleanup
        run_cmd(
            ['dropdb', '-U', db_user, '-h', 'localhost', '--if-exists', '--force', alt_db_name],
            env=cmd_env,
            check=False
        )


class TestCloneWithDestDir:
    """Test clone with --dest-dir option."""

    def test_clone_to_custom_directory(self, initialized_project):
        """Test that clone with --dest-dir uses specified directory."""
        env = initialized_project
        work_dir = env['work_dir']
        project_dir = env['project_dir']
        git_origin = env['git_origin']
        config_dir = env['config_dir']
        db_user = env['db_user']
        db_password = env['db_password']

        # Push the initialized project to origin
        run = env['run']
        run(['git', 'push', '-u', 'origin', 'ho-prod'])

        # Clone to a custom directory
        clone_work_dir = work_dir.parent / 'custom_dir_work'
        clone_work_dir.mkdir()

        import uuid
        clone_db_name = f"hop_custom_{str(uuid.uuid4())[:8]}"
        custom_dest = 'my_custom_project'

        # Create half_orm config for clone database
        clone_config_file = config_dir / clone_db_name
        clone_config_content = f"""[database]
name = {clone_db_name}
user = {db_user}
host = localhost
port = 5432
"""
        if db_password:
            clone_config_content += f"password = {db_password}\n"
        clone_config_file.write_text(clone_config_content)

        cmd_env = env['env'].copy()
        cmd_env['HALFORM_CONF_DIR'] = str(config_dir)
        cmd_env['PGPASSWORD'] = db_password

        result = run_cmd(
            [
                'half_orm', 'dev', 'clone', str(git_origin),
                '--database-name', clone_db_name,
                '--dest-dir', custom_dest,
                '--user', db_user,
                '--password', db_password or ''
            ],
            cwd=clone_work_dir,
            env=cmd_env
        )

        # Verify the project was cloned to the custom directory
        clone_dir = clone_work_dir / custom_dest
        assert clone_dir.exists(), f"Project should be cloned to {custom_dest}/"
        assert (clone_dir / '.hop').is_dir()
        assert (clone_dir / '.git').is_dir()

        # Cleanup
        run_cmd(
            ['dropdb', '-U', db_user, '-h', 'localhost', '--if-exists', '--force', clone_db_name],
            env=cmd_env,
            check=False
        )


class TestClonePatchApply:
    """Test patch apply after clone with different database name."""

    def test_patch_apply_uses_correct_package_name(self, initialized_project):
        """
        Test that patch apply after clone generates modules with the original package name.

        This is the core bug scenario:
        1. Original project has package 'test_pg' with database 'test_pg'
        2. Clone with --database-name 'alt_db'
        3. Create a release and patch, run patch apply
        4. Modules should be generated in test_pg/, not alt_db/
        """
        env = initialized_project
        work_dir = env['work_dir']
        project_dir = env['project_dir']
        git_origin = env['git_origin']
        config_dir = env['config_dir']
        db_user = env['db_user']
        db_password = env['db_password']
        original_project_name = env['db_name']

        # Push the initialized project
        run = env['run']
        run(['git', 'push', '-u', 'origin', 'ho-prod'])

        # Clone with different database name
        clone_work_dir = work_dir.parent / 'patch_apply_workspace'
        clone_work_dir.mkdir()

        import uuid
        alt_db_name = f"patch_alt_{str(uuid.uuid4())[:8]}"

        alt_config_file = config_dir / alt_db_name
        alt_config_content = f"""[database]
name = {alt_db_name}
user = {db_user}
host = localhost
port = 5432
"""
        if db_password:
            alt_config_content += f"password = {db_password}\n"
        alt_config_file.write_text(alt_config_content)

        cmd_env = env['env'].copy()
        cmd_env['HALFORM_CONF_DIR'] = str(config_dir)
        cmd_env['PGPASSWORD'] = db_password

        run_cmd(
            [
                'half_orm', 'dev', 'clone', str(git_origin),
                '--database-name', alt_db_name,
                '--user', db_user,
                '--password', db_password or ''
            ],
            cwd=clone_work_dir,
            env=cmd_env
        )
        # Clone directory is named after git repo (origin.git -> origin)


        clone_dir = clone_work_dir / 'origin'
        assert clone_dir.exists(), f"Clone directory should exist: {clone_dir}"

        # Debug: verify .hop/alt_config exists and contains the right value
        alt_config_path = clone_dir / '.hop' / 'alt_config'
        assert alt_config_path.exists(), f".hop/alt_config should exist after clone"
        alt_config_content = alt_config_path.read_text().strip()
        assert alt_config_content == alt_db_name, \
            f".hop/alt_config should contain '{alt_db_name}', got '{alt_config_content}'"

        # Debug: verify half_orm config file exists and has correct content
        half_orm_config = config_dir / alt_db_name
        assert half_orm_config.exists(), \
            f"half_orm config file should exist at {half_orm_config}"
        half_orm_config_content = half_orm_config.read_text()

        # Configure git user for commits in cloned project
        run_cmd(['git', 'config', 'user.email', 'test@example.com'], cwd=clone_dir)
        run_cmd(['git', 'config', 'user.name', 'Test User'], cwd=clone_dir)

        # Create a release and patch in the cloned project
        run_cmd(['git', 'checkout', 'ho-prod'], cwd=clone_dir, env=cmd_env)
        run_cmd(['half_orm', 'dev', 'release', 'create', 'minor'], cwd=clone_dir, env=cmd_env)

        run_cmd(['half_orm', 'dev', 'patch', 'create', '1-test'], cwd=clone_dir, env=cmd_env)
        print(run_cmd(['git', 'branch']).stdout)
        run_cmd(['git', 'checkout', 'ho-patch/1-test'], cwd=clone_dir, env=cmd_env)

        # Create a SQL file in the patch
        patch_dir = clone_dir / 'Patches' / '1-test'
        (patch_dir / '01_test.sql').write_text(
            'CREATE TABLE test_table (id SERIAL PRIMARY KEY, name TEXT);'
        )

        # Run patch apply - this should generate modules in the correct package directory
        result = run_cmd(['half_orm', 'dev', 'patch', 'apply'], cwd=clone_dir, env=cmd_env)
        print(run_cmd(['tree', str(clone_dir), '--gitignore']).stdout)

        # Debug: check if table was created in the database
        table_check = run_cmd(
            ['psql', '-U', db_user, '-h', 'localhost', '-d', alt_db_name, '-tAc',
             "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name='test_table'"],
            env=cmd_env,
            check=False
        )
        table_exists = 'test_table' in table_check.stdout

        # Verify modules are generated in the correct package directory
        correct_package_dir = clone_dir / original_project_name
        wrong_package_dir = clone_dir / alt_db_name

        # Debug: list what directories exist
        import os
        clone_contents = list(clone_dir.iterdir())

        # Check if modules were incorrectly generated in wrong_package_dir
        wrong_has_public = wrong_package_dir.exists() and (wrong_package_dir / 'public').exists()

        # Debug: check what's in the correct package dir
        correct_pkg_contents = []
        if correct_package_dir.exists():
            correct_pkg_contents = [p.name for p in correct_package_dir.iterdir()]
            print(correct_package_dir)
        print(run_cmd(['tree', str(correct_package_dir), '--gitignore']).stdout)
        assert correct_package_dir.exists(), \
            f"patch apply should generate modules in '{original_project_name}/' directory. " \
            f"Clone contains: {[p.name for p in clone_contents]}"
        assert (correct_package_dir / 'public').exists(), \
            f"Package should have public schema module in '{original_project_name}/public/'. " \
            f"Wrong dir '{alt_db_name}/public' exists: {wrong_has_public}. " \
            f"Table 'test_table' exists in DB '{alt_db_name}': {table_exists}. " \
            f".hop/config: {hop_config[:200]}. " \
            f"half_orm config ({alt_db_name}): {half_orm_config_content[:200]}. " \
            f"patch apply output: {result.stdout[:500]}. " \
            f"Package dir contains: {correct_pkg_contents}"
        assert not wrong_has_public, \
            f"patch apply should NOT generate modules in '{alt_db_name}/' directory"

        # Cleanup
        run_cmd(
            ['dropdb', '-U', db_user, '-h', 'localhost', '--if-exists', '--force', alt_db_name],
            env=cmd_env,
            check=False
        )
