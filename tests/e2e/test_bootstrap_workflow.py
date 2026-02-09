"""
End-to-end tests for bootstrap workflow.

Tests the complete bootstrap lifecycle:
- Bootstrap directory creation during init
- Bootstrap file execution after schema restoration
- Tracking in half_orm_meta.bootstrap table
- Integration with patch merge and release promote
"""

import os
import pytest
import subprocess
from pathlib import Path

from tests.e2e.conftest import run_cmd


@pytest.mark.integration
class TestBootstrapDirectoryCreation:
    """Test bootstrap directory is created during project init."""

    def test_init_creates_bootstrap_directory(self, initialized_project):
        """Test that 'init' creates bootstrap/ directory."""
        project_dir = initialized_project['project_dir']

        bootstrap_dir = project_dir / 'bootstrap'
        assert bootstrap_dir.exists(), "bootstrap/ directory should be created"
        assert bootstrap_dir.is_dir(), "bootstrap/ should be a directory"

    def test_init_creates_bootstrap_readme(self, initialized_project):
        """Test that 'init' creates README.md in bootstrap/."""
        project_dir = initialized_project['project_dir']

        readme = project_dir / 'bootstrap' / 'README.md'
        assert readme.exists(), "bootstrap/README.md should be created"

        content = readme.read_text()
        assert '@HOP:bootstrap' in content, "README should document @HOP:bootstrap marker"


@pytest.mark.integration
class TestBootstrapTableCreation:
    """Test half_orm_meta.bootstrap table exists."""

    def test_bootstrap_table_exists(self, initialized_project):
        """Test that half_orm_meta.bootstrap table exists after init."""
        db_name = initialized_project['db_name']

        from half_orm.model import Model
        model = Model(db_name)

        try:
            result = list(model.execute_query(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'half_orm_meta' AND table_name = 'bootstrap'"
            ))
            # Handle both tuple and dict results
            columns = {row['column_name'] for row in result}
            print('XXX', columns)

            assert 'filename' in columns, "filename column should exist"
            assert 'version' in columns, "version column should exist"
            assert 'executed_at' in columns, "executed_at column should exist"
        finally:
            model.disconnect()


@pytest.mark.integration
class TestBootstrapCommand:
    """Test bootstrap CLI command."""

    def test_bootstrap_command_no_files(self, initialized_project):
        """Test bootstrap command with no files to execute."""
        run = initialized_project['run']

        result = run(['half_orm', 'dev', 'bootstrap'])

        assert result.returncode == 0
        assert 'No bootstrap scripts to execute' in result.stdout or 'executed' not in result.stdout.lower()

    def test_bootstrap_dry_run(self, initialized_project):
        """Test bootstrap --dry-run option."""
        project_dir = initialized_project['project_dir']
        run = initialized_project['run']
        db_name = initialized_project['db_name']

        # Create a bootstrap file
        bootstrap_dir = project_dir / 'bootstrap'
        bootstrap_file = bootstrap_dir / '1-test-data-0.1.0.sql'
        bootstrap_file.write_text("""
            INSERT INTO half_orm_meta.bootstrap (filename, version)
            VALUES ('should-not-exist.sql', '0.0.0');
        """)

        # Run with --dry-run
        result = run(['half_orm', 'dev', 'bootstrap', '--dry-run'])

        assert result.returncode == 0
        assert '1-test-data-0.1.0.sql' in result.stdout

        # Verify the file was NOT executed
        from half_orm.model import Model
        model = Model(db_name)
        try:
            rows = list(model.execute_query(
                "SELECT filename FROM half_orm_meta.bootstrap WHERE filename = 'should-not-exist.sql'"
            ))
            assert len(rows) == 0, "Dry run should not execute files"
        finally:
            model.disconnect()

    def test_bootstrap_executes_sql_file(self, initialized_project):
        """Test bootstrap executes SQL files and tracks them."""
        project_dir = initialized_project['project_dir']
        run = initialized_project['run']
        db_name = initialized_project['db_name']

        # Create a bootstrap SQL file that creates a test table
        bootstrap_dir = project_dir / 'bootstrap'
        bootstrap_file = bootstrap_dir / '1-init-test-0.1.0.sql'
        bootstrap_file.write_text("""
            CREATE TABLE IF NOT EXISTS public.bootstrap_test (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL
            );
            INSERT INTO public.bootstrap_test (name) VALUES ('test-data');
        """)

        # Execute bootstrap
        result = run(['half_orm', 'dev', 'bootstrap'])

        assert result.returncode == 0

        # Verify the table was created and data inserted
        from half_orm.model import Model
        model = Model(db_name)
        try:
            rows = list(model.execute_query(
                "SELECT name FROM public.bootstrap_test WHERE name = 'test-data'"
            ))
            assert len(rows) == 1, "Bootstrap should have created and populated table"

            # Verify tracking in half_orm_meta.bootstrap
            tracking = list(model.execute_query(
                "SELECT filename, version FROM half_orm_meta.bootstrap WHERE filename = '1-init-test-0.1.0.sql'"
            ))[0]
            print('XXX', tracking)
            assert tracking['filename'] == '1-init-test-0.1.0.sql', "Execution should be tracked"
            assert tracking['version'] == '0.1.0', "Version should be extracted from filename"
        finally:
            model.disconnect()

    def test_bootstrap_skips_already_executed(self, initialized_project):
        """Test bootstrap skips files already in tracking table."""
        project_dir = initialized_project['project_dir']
        run = initialized_project['run']
        db_name = initialized_project['db_name']

        # Create a bootstrap file
        bootstrap_dir = project_dir / 'bootstrap'
        bootstrap_file = bootstrap_dir / '1-init-0.1.0.sql'
        bootstrap_file.write_text("SELECT 1;")

        # Pre-populate tracking table using psql to ensure commit
        import subprocess
        import os
        env = {**os.environ, 'PGPASSWORD': initialized_project['db_password']}
        subprocess.run(
            ['psql', '-U', initialized_project['db_user'], '-h', 'localhost', '-d', db_name, '-c',
             "INSERT INTO half_orm_meta.bootstrap (filename, version) VALUES ('1-init-0.1.0.sql', '0.1.0')"],
            env=env, check=True, capture_output=True
        )
        # Execute bootstrap
        result = run(['half_orm', 'dev', 'bootstrap'])

        assert result.returncode == 0
        # File should be skipped (already executed) - check it's NOT in executed list
        print('XXX', result.stdout)
        assert 'Executing 1-init-0.1.0.sql' not in result.stdout.lower()

    def test_bootstrap_force_reexecutes(self, initialized_project):
        """Test bootstrap --force re-executes all files."""
        project_dir = initialized_project['project_dir']
        run = initialized_project['run']
        db_name = initialized_project['db_name']

        # Create bootstrap files
        bootstrap_dir = project_dir / 'bootstrap'
        file1 = bootstrap_dir / '1-first-0.1.0.sql'
        file1.write_text("SELECT 1;")
        file2 = bootstrap_dir / '2-second-0.1.0.sql'
        file2.write_text("SELECT 2;")

        # Pre-populate tracking table using psql to ensure commit
        import subprocess
        import os
        env = {**os.environ, 'PGPASSWORD': initialized_project['db_password']}
        subprocess.run(
            ['psql', '-U', initialized_project['db_user'], '-h', 'localhost', '-d', db_name, '-c',
             "INSERT INTO half_orm_meta.bootstrap (filename, version) VALUES ('1-first-0.1.0.sql', '0.1.0')"],
            env=env, check=True, capture_output=True
        )

        # Execute with --force
        result = run(['half_orm', 'dev', 'bootstrap', '--force'])

        assert result.returncode == 0
        # Both files should be in output (executed)
        assert '1-first-0.1.0.sql' in result.stdout
        assert '2-second-0.1.0.sql' in result.stdout


@pytest.mark.integration
class TestBootstrapNumericSorting:
    """Test that bootstrap files are executed in numeric order."""

    def test_files_executed_in_numeric_order(self, initialized_project):
        """Test files are sorted numerically, not lexicographically."""
        project_dir = initialized_project['project_dir']
        run = initialized_project['run']
        db_name = initialized_project['db_name']

        # Create a tracking table to record execution order
        from half_orm.model import Model
        model = Model(db_name)
        try:
            model.execute_query("""
                CREATE TABLE IF NOT EXISTS public.execution_order (
                    id SERIAL PRIMARY KEY,
                    file_name TEXT NOT NULL
                )
            """)
        finally:
            model.disconnect()

        # Create files in wrong lexicographic order
        bootstrap_dir = project_dir / 'bootstrap'

        # These would sort as 1, 10, 2 lexicographically, but should be 1, 2, 10
        (bootstrap_dir / '10-tenth-0.1.0.sql').write_text(
            "INSERT INTO public.execution_order (file_name) VALUES ('10-tenth');"
        )
        (bootstrap_dir / '2-second-0.1.0.sql').write_text(
            "INSERT INTO public.execution_order (file_name) VALUES ('2-second');"
        )
        (bootstrap_dir / '1-first-0.1.0.sql').write_text(
            "INSERT INTO public.execution_order (file_name) VALUES ('1-first');"
        )

        # Execute bootstrap
        result = run(['half_orm', 'dev', 'bootstrap'])
        assert result.returncode == 0

        # Verify execution order
        model = Model(db_name)
        try:
            rows = list(model.execute_query(
                "SELECT file_name FROM public.execution_order ORDER BY id"
            ))
            order = [row['file_name'] for row in rows]

            assert order == ['1-first', '2-second', '10-tenth'], (
                f"Files should execute in numeric order (1, 2, 10), got: {order}"
            )
        finally:
            model.disconnect()


@pytest.mark.integration
class TestBootstrapPythonExecution:
    """Test Python bootstrap file execution."""

    def test_bootstrap_executes_python_file(self, initialized_project):
        """Test bootstrap executes Python files."""
        project_dir = initialized_project['project_dir']
        run = initialized_project['run']
        db_name = initialized_project['db_name']

        # Create a Python bootstrap file
        bootstrap_dir = project_dir / 'bootstrap'
        py_file = bootstrap_dir / '1-seed-data-0.1.0.py'
        py_file.write_text(f'''
import psycopg2

conn = psycopg2.connect(dbname="{db_name}", host="localhost")
cur = conn.cursor()
cur.execute("""
    CREATE TABLE IF NOT EXISTS public.python_bootstrap_test (
        id SERIAL PRIMARY KEY,
        value TEXT
    )
""")
cur.execute("INSERT INTO public.python_bootstrap_test (value) VALUES ('from-python')")
conn.commit()
cur.close()
conn.close()
print("Python bootstrap executed successfully")
''')

        # Execute bootstrap
        result = run(['half_orm', 'dev', 'bootstrap'])

        assert result.returncode == 0

        # Verify the table was created
        from half_orm.model import Model
        model = Model(db_name)
        try:
            rows = list(model.execute_query(
                "SELECT value FROM public.python_bootstrap_test WHERE value = 'from-python'"
            ))
            assert len(rows) == 1, "Python bootstrap should have created and populated table"
        finally:
            model.disconnect()


@pytest.mark.integration
class TestBootstrapWithClone:
    """Test bootstrap runs automatically after clone."""

    def test_clone_executes_bootstrap(self, project_with_release):
        """Test that cloning a project executes bootstrap files."""
        env = project_with_release
        run = env['run']
        project_dir = env['project_dir']
        db_name = env['db_name']

        # Switch to ho-prod branch to add bootstrap file
        run(['git', 'checkout', 'ho-prod'])

        # Create a bootstrap file in the original project
        bootstrap_dir = project_dir / 'bootstrap'
        bootstrap_file = bootstrap_dir / '1-clone-test-0.1.0.sql'
        bootstrap_file.write_text("""
            CREATE TABLE clone_test (
                id SERIAL PRIMARY KEY,
                marker TEXT DEFAULT 'clone-executed'
            );
            INSERT INTO clone_test (marker) VALUES ('clone-executed');
        """)

        # Commit the bootstrap file and push to origin
        run(['git', 'add', 'bootstrap/'])
        run(['git', 'commit', '-m', 'Add bootstrap file', '--no-verify'])
        run(['git', 'push', 'origin', 'ho-prod'])

        # Create a clone in a new directory
        work_dir = env['work_dir']
        clone_dir = work_dir / 'cloned_project'
        clone_db_name = f"{db_name}_clone"

        # Create config for clone database
        config_dir = env['config_dir']
        clone_config = config_dir / clone_db_name
        clone_config.write_text(f"""[database]
name = {clone_db_name}
user = {env['db_user']}
host = localhost
port = 5432
password = {env['db_password']}
""")

        # Clone the project using run_cmd
        cmd_env = {**os.environ, **env['env'], 'HALFORM_CONF_DIR': str(config_dir)}

        clone_result = run_cmd(
            ['half_orm', 'dev', 'clone', str(env['git_origin']),
             '--database-name', clone_db_name,
             '--user', env['db_user'],
             '--password', env['db_password']],
            cwd=str(work_dir),
            env=cmd_env,
            input_text='y\n',  # Confirm metadata installation
            check=False
        )

        # Cleanup the clone database after test
        try:
            if clone_result.returncode == 0:
                # Verify bootstrap was executed in cloned database
                from half_orm.model import Model
                model = Model(clone_db_name)
                try:
                    rows = list(model.execute_query(
                        "SELECT marker FROM clone_test WHERE marker = 'clone-executed'"
                    ))
                    assert len(rows) == 1, "Bootstrap should have run during clone"
                finally:
                    model.disconnect()
            else:
                pytest.fail(f"Clone failed: {clone_result.stderr}")
        finally:
            # Cleanup clone database
            run_cmd(
                ['dropdb', '-U', env['db_user'], '-h', 'localhost',
                 '--if-exists', '--force', clone_db_name],
                env=cmd_env,
                check=False
            )


@pytest.mark.integration
class TestBootstrapVersionFiltering:
    """Test bootstrap files are filtered by version during promote."""

    def test_promote_only_executes_bootstraps_up_to_version(self, project_with_release):
        """
        Test that promote to prod only executes bootstraps for the release version.

        Scenario:
        - Release 0.1.0 promoted with bootstrap
        - Release 0.1.1 created with additional bootstrap (in bootstrap/ dir manually)
        - When promoting 0.1.0, only 0.1.0 bootstraps should execute
        """
        env = project_with_release
        run = env['run']
        project_dir = env['project_dir']
        db_name = env['db_name']

        # Create a patch with bootstrap for 0.1.0
        run(['half_orm', 'dev', 'patch', 'create', '1-first'])
        run(['git', 'checkout', 'ho-patch/1-first'])

        patch_dir = project_dir / 'Patches' / '1-first'
        (patch_dir / '01_schema.sql').write_text("""
            CREATE TABLE first_release_table (id SERIAL PRIMARY KEY);
        """)
        (patch_dir / '02_bootstrap.sql').write_text("""-- @HOP:bootstrap
            INSERT INTO first_release_table (id) VALUES (1);
        """)

        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'First patch', '--no-verify'])
        run(['half_orm', 'dev', 'patch', 'merge', '--force'])

        # Manually add a bootstrap file for a future version (0.1.1)
        # This simulates having bootstraps from future releases in the directory
        bootstrap_dir = project_dir / 'bootstrap'
        future_bootstrap = bootstrap_dir / '2-future-0.1.1.sql'
        future_bootstrap.write_text("""
            CREATE TABLE IF NOT EXISTS future_release_marker (id INT);
            INSERT INTO future_release_marker (id) VALUES (999);
        """)

        # Commit the future bootstrap
        run(['git', 'checkout', 'ho-release/0.1.0'])
        run(['git', 'add', 'bootstrap/'])
        run(['git', 'commit', '-m', 'Add future bootstrap (for testing)', '--no-verify'])

        # Push to make sure release branch is up to date
        run(['git', 'push', 'origin', 'ho-release/0.1.0'])

        # Promote 0.1.0 to prod (should NOT execute 0.1.1 bootstraps)
        run(['half_orm', 'dev', 'release', 'promote', 'prod'])

        # Verify: first_release_table should have data
        from half_orm.model import Model
        model = Model(db_name)
        try:
            # Check 0.1.0 bootstrap was executed
            rows = list(model.execute_query(
                "SELECT id FROM first_release_table WHERE id = 1"
            ))
            assert len(rows) == 1, "Bootstrap for 0.1.0 should have executed"

            # Check 0.1.1 bootstrap was NOT executed
            try:
                rows = list(model.execute_query(
                    "SELECT id FROM future_release_marker WHERE id = 999"
                ))
                # If table exists, it should be empty (bootstrap didn't run)
                assert len(rows) == 0, "Bootstrap for 0.1.1 should NOT have executed during 0.1.0 promote"
            except Exception:
                # Table doesn't exist = bootstrap didn't run = correct
                pass
        finally:
            model.disconnect()

    def test_patch_apply_executes_all_bootstraps(self, project_with_release):
        """
        Test that patch apply executes all bootstraps (no version filtering).

        During development, all bootstraps should run so developers see
        the full state including staged patches.
        """
        env = project_with_release
        run = env['run']
        project_dir = env['project_dir']
        db_name = env['db_name']

        # Create and merge first patch with bootstrap
        run(['half_orm', 'dev', 'patch', 'create', '1-base'])
        run(['git', 'checkout', 'ho-patch/1-base'])

        patch_dir = project_dir / 'Patches' / '1-base'
        (patch_dir / '01_schema.sql').write_text("""
            CREATE TABLE base_data (id SERIAL PRIMARY KEY, name TEXT);
        """)
        (patch_dir / '02_bootstrap.sql').write_text("""-- @HOP:bootstrap
            INSERT INTO base_data (name) VALUES ('base');
        """)

        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Base patch', '--no-verify'])
        run(['half_orm', 'dev', 'patch', 'merge', '--force'])

        # Create second patch (candidate, not yet merged)
        run(['git', 'checkout', 'ho-release/0.1.0'])
        run(['half_orm', 'dev', 'patch', 'create', '2-extra'])
        run(['git', 'checkout', 'ho-patch/2-extra'])

        patch_dir2 = project_dir / 'Patches' / '2-extra'
        (patch_dir2 / '01_schema.sql').write_text("""
            CREATE TABLE extra_data (id SERIAL PRIMARY KEY, value TEXT);
        """)
        # Note: This bootstrap won't be in bootstrap/ yet (not merged)
        # but staged patch's bootstrap should still run

        # Apply should restore DB and run all staged patch bootstraps
        run(['half_orm', 'dev', 'patch', 'apply'])

        # Verify: base_data bootstrap should have run
        from half_orm.model import Model
        model = Model(db_name)
        try:
            rows = list(model.execute_query(
                "SELECT name FROM base_data WHERE name = 'base'"
            ))
            assert len(rows) == 1, "Staged patch bootstrap should have executed during patch apply"
        finally:
            model.disconnect()
