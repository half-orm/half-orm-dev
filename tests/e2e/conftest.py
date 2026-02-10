"""
End-to-end test fixtures using real PostgreSQL and CLI commands.

These fixtures provide real database and git repository setup for testing
the complete half-orm-dev workflow with actual CLI commands.
"""

import os
import pytest
import subprocess
import tempfile
import shutil
from pathlib import Path


def run_cmd(cmd, cwd=None, env=None, input_text=None, check=True):
    """
    Run a shell command and return the result.

    Args:
        cmd: Command string or list
        cwd: Working directory
        env: Environment variables (merged with os.environ)
        input_text: Text to send to stdin
        check: If True, raise on non-zero exit

    Returns:
        subprocess.CompletedProcess
    """
    if isinstance(cmd, str):
        cmd = cmd.split()

    run_env = os.environ.copy()
    if env:
        run_env.update(env)

    result = subprocess.run(
        cmd,
        cwd=cwd,
        env=run_env,
        capture_output=True,
        text=True,
        input=input_text
    )

    if check and result.returncode != 0:
        error_msg = (
            f"Command {cmd} failed with exit code {result.returncode}\n"
            f"STDOUT: {result.stdout}\n"
            f"STDERR: {result.stderr}"
        )
        # Create exception with detailed message
        exc = subprocess.CalledProcessError(
            result.returncode,
            cmd,
            result.stdout,
            result.stderr
        )
        exc.add_note(error_msg)
        raise exc

    return result


@pytest.fixture(scope="session")
def postgres_user():
    """
    Ensure a PostgreSQL user exists for testing.

    Always uses password authentication to avoid interactive prompts.
    Uses current OS user with a test password.
    """
    current_user = os.environ.get('USER', 'halftest')
    test_password = current_user  # Use username as password for simplicity

    # Check if we can connect with password auth
    env = {'PGPASSWORD': test_password}
    result = subprocess.run(
        ['psql', '-U', current_user, '-h', 'localhost', '-tAc', 'SELECT 1', 'postgres'],
        capture_output=True,
        text=True,
        env={**os.environ, **env}
    )

    if result.returncode == 0:
        return {'user': current_user, 'password': test_password, 'auth': 'password'}

    # Try to set password for current user or create user
    try:
        # Try to alter existing user to set password
        subprocess.run(
            ['sudo', '-u', 'postgres', 'psql', '-c',
             f"ALTER USER {current_user} WITH PASSWORD '{test_password}'"],
            check=True,
            capture_output=True
        )
        return {'user': current_user, 'password': test_password, 'auth': 'password'}
    except subprocess.CalledProcessError:
        pass

    # Fall back to halftest user
    check = subprocess.run(
        ['sudo', '-u', 'postgres', 'psql', '-tAc',
         "SELECT 1 FROM pg_roles WHERE rolname='halftest'"],
        capture_output=True,
        text=True
    )

    if check.returncode != 0 or '1' not in check.stdout:
        # Create halftest user
        subprocess.run(
            ['sudo', '-u', 'postgres', 'psql', '-c',
             "CREATE USER halftest WITH PASSWORD 'halftest' CREATEDB"],
            check=True,
            capture_output=True
        )

    return {'user': 'halftest', 'password': 'halftest', 'auth': 'password'}


@pytest.fixture(scope="function")
def e2e_environment(postgres_user, tmp_path_factory):
    """
    Create a complete end-to-end test environment.

    Sets up:
    - Temporary working directory
    - Bare git repository (simulates remote origin)
    - PostgreSQL database
    - Environment variables

    Yields:
        dict with:
        - work_dir: Path to working directory
        - git_origin: Path to bare git repo
        - db_name: Database name
        - db_user: Database user
        - db_password: Database password (or None for peer auth)
        - run: Helper function to run commands in work_dir
    """
    # Create unique names based on test
    import uuid
    test_id = str(uuid.uuid4())[:8]

    # Create temporary directories
    base_dir = tmp_path_factory.mktemp(f"e2e_{test_id}")
    work_dir = base_dir / "work"
    work_dir.mkdir()

    git_origin = base_dir / "origin.git"

    # Create bare git repo
    run_cmd(['git', 'init', '--bare', str(git_origin)])

    # Database name (will be created by 'half_orm dev init')
    db_name = f"hop_e2e_{test_id}"
    db_user = postgres_user['user']
    db_password = postgres_user['password']

    env = {
        'PGPASSWORD': db_password,
        # Disable GPG signing for commits in tests
        'GIT_CONFIG_COUNT': '1',
        'GIT_CONFIG_KEY_0': 'commit.gpgsign',
        'GIT_CONFIG_VALUE_0': 'false',
    }

    def run_in_workdir(cmd, cwd=None, input_text=None, check=True):
        """Run command in working directory."""
        target_cwd = cwd or work_dir
        cmd_env = env.copy()
        return run_cmd(cmd, cwd=target_cwd, env=cmd_env, input_text=input_text, check=check)

    yield {
        'work_dir': work_dir,
        'git_origin': git_origin,
        'db_name': db_name,
        'db_user': db_user,
        'db_password': db_password,
        'run': run_in_workdir,
        'env': env
    }

    # Cleanup
    drop_env = env.copy()
    subprocess.run(
        ['dropdb', '-U', db_user, '-h', 'localhost', '--if-exists', '--force', db_name],
        env=drop_env,
        capture_output=True
    )


@pytest.fixture(scope="function")
def initialized_project(e2e_environment):
    """
    Create an initialized half-orm project ready for development.

    Sets up:
    - Database with half-orm metadata
    - Git repository connected to origin
    - Project initialized with 'half_orm dev init'

    Yields:
        dict with all e2e_environment keys plus:
        - project_dir: Path to the project directory
    """
    env = e2e_environment
    work_dir = env['work_dir']
    base_dir = work_dir.parent

    # Create half_orm config directory for this test
    config_dir = base_dir / '.half_orm'
    config_dir.mkdir(exist_ok=True)

    # Create config file for the database
    config_file = config_dir / env['db_name']
    config_content = f"""[database]
name = {env['db_name']}
user = {env['db_user']}
host = localhost
port = 5432
"""
    if env['db_password']:
        config_content += f"password = {env['db_password']}\n"

    config_file.write_text(config_content)

    # Set environment variable to use our config directory
    cmd_env = env['env'].copy()
    cmd_env['HALFORM_CONF_DIR'] = str(config_dir)

    # Project directory (will be created by init)
    project_dir = work_dir / env['db_name']

    # Set PYTHONPATH so tests can find the project module
    cmd_env['PYTHONPATH'] = str(project_dir)

    # Build init command
    # Always pass --password to avoid interactive prompt
    cmd = [
        'half_orm', 'dev', 'init', env['db_name'],
        '--git-origin', str(env['git_origin']),
        '--user', env['db_user'],
        '--password', env['db_password'] or ''
    ]

    # Initialize project - send 'y' for metadata installation prompt
    run_cmd(cmd, cwd=work_dir, env=cmd_env, input_text='y\n')

    project_dir = work_dir / env['db_name']

    # Configure git user for commits
    run_cmd(['git', 'config', 'user.email', 'test@example.com'], cwd=project_dir)
    run_cmd(['git', 'config', 'user.name', 'Test User'], cwd=project_dir)

    def run_in_project(cmd, input_text=None, check=True):
        """Run command in project directory."""
        return run_cmd(cmd, cwd=project_dir, env=cmd_env, input_text=input_text, check=check)

    env['project_dir'] = project_dir
    env['run'] = run_in_project
    env['config_dir'] = config_dir

    yield env


@pytest.fixture(scope="function")
def project_with_release(initialized_project):
    """
    Create a project with a release ready for patches.

    Sets up:
    - Initialized project
    - Minor release created (0.1.0)

    Yields:
        dict with all initialized_project keys plus:
        - release_version: The created release version
    """
    env = initialized_project
    run = env['run']

    # Checkout ho-prod and create a release
    run(['git', 'checkout', 'ho-prod'])
    run(['half_orm', 'dev', 'release', 'create', 'minor'])

    env['release_version'] = '0.1.0'

    yield env
