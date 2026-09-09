"""
End-to-end test fixtures using real PostgreSQL and CLI commands.

These fixtures provide real database and git repository setup for testing
the complete half-orm-dev workflow with actual CLI commands.
"""

import os
import sys
import pytest
import subprocess
import tempfile
import shutil
from pathlib import Path

from packaging.version import Version
from half_orm_dev.utils import hop_version as installed_hop_version


def pg_port() -> int:
    """
    PostgreSQL port to target in e2e tests.

    Respects the PGPORT environment variable (e.g. a dedicated non-default
    cluster), falling back to 5432. Used where a test writes a
    ~/.half_orm/<db> config file directly (half_orm_dev's own --host/--port
    CLI options already resolve PGHOST/PGPORT on their own and don't need
    this).
    """
    return int(os.environ.get('PGPORT', 5432))


def _one_pre_release_below(installed: str) -> str:
    """Return a version string one pre-release step below *installed*.

    The returned version shares the same release tuple (major.minor.micro) so
    that no real migration scripts exist between the two versions — meaning
    ``get_pending_migrations`` will detect a version mismatch (triggering a
    sync commit) without trying to run any interactive migration script.

    Examples::

        '0.18.0-a2' → '0.18.0-a1'
        '0.18.0-a1' → '0.18.0-a0'
        '1.0.0'     → '1.0.0-a0'   (stable release → invent a pre-release)
    """
    v = Version(installed)
    if v.pre and v.pre[1] > 0:
        kind, num = v.pre
        return f"{v.major}.{v.minor}.{v.micro}-{kind}{num - 1}"
    return f"{v.major}.{v.minor}.{v.micro}-a0"


@pytest.fixture(scope="session")
def old_hop_version():
    """Version one pre-release step below the installed hop version.

    Use this fixture in any e2e test that needs to simulate a project whose
    .hop/config was written by a slightly older version of hop, so that
    ``half_orm dev migrate`` (or any command that checks the version) sees a
    mismatch and triggers the sync logic — without running real migration
    scripts.
    """
    return _one_pre_release_below(installed_hop_version())


def _console_script_interpreter(script_path):
    """Python running a console script, read from its shebang.

    The e2e tests exercise the `half_orm` on PATH, which may well come
    from a different environment than the one running pytest - that is
    exactly what this is here to detect, so the interpreter cannot be
    assumed to be sys.executable.
    """
    try:
        with open(script_path, 'rb') as f:
            first_line = f.readline()
    except OSError:
        return None

    if not first_line.startswith(b'#!'):
        return None  # binary launcher: no way to tell, let the tests run

    try:
        tokens = first_line[2:].strip().decode().split()
    except UnicodeDecodeError:
        return None

    if not tokens:
        return None
    if Path(tokens[0]).name == 'env' and len(tokens) > 1:
        return shutil.which(tokens[1])
    return tokens[0]


@pytest.fixture(scope="session", autouse=True)
def _cli_is_the_working_tree():
    """
    Stop the session when `half_orm` on PATH is not this working tree.

    Every e2e test drives the CLI as a subprocess, so a stale install
    silently tests released code instead of the code under review - and
    fails on assertions about behaviour that working tree has and the
    installed version does not, which reads as a broken feature rather
    than a broken environment. That cost a full debugging round already.
    """
    repo_root = Path(__file__).resolve().parents[2]
    package_dir = repo_root / 'half_orm_dev'

    script = shutil.which('half_orm')
    if script is None:
        pytest.exit(
            "`half_orm` is not on PATH.\n"
            f"Install this working tree: pip install -e {repo_root}",
            returncode=1,
        )

    interpreter = _console_script_interpreter(script)
    if interpreter is None:
        return  # cannot introspect it; let the tests speak for themselves

    # Run from outside the repository: `python -c` puts the current
    # directory first on sys.path, so probing from the repo root would
    # import the working tree whatever the CLI actually uses - the guard
    # would then never catch the very situation it exists for.
    probe = subprocess.run(
        [
            interpreter, '-c',
            'import half_orm_dev, pathlib;'
            'from half_orm_dev.utils import hop_version;'
            'print(hop_version());'
            'print(pathlib.Path(half_orm_dev.__file__).resolve().parent)'
        ],
        capture_output=True, text=True, cwd=tempfile.gettempdir()
    )

    if probe.returncode != 0:
        pytest.exit(
            f"`half_orm` ({script}) cannot import half_orm_dev:\n"
            f"{probe.stderr.strip()}\n"
            f"Install this working tree: pip install -e {repo_root}",
            returncode=1,
        )

    cli_version, cli_package_dir = (probe.stdout.strip().splitlines() + ['', ''])[:2]

    if Path(cli_package_dir) != package_dir.resolve():
        expected_version = (package_dir / 'version.txt').read_text().strip()
        pytest.exit(
            f"`half_orm` on PATH runs another half_orm_dev than this working tree.\n"
            f"  script:       {script}\n"
            f"  it runs:      {cli_package_dir} ({cli_version})\n"
            f"  expected:     {package_dir} ({expected_version})\n"
            f"The e2e tests drive that CLI, so they would be testing the "
            f"installed version, not your changes.\n"
            f"Fix it with: pip install -e {repo_root}",
            returncode=1,
        )


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
        raise subprocess.CalledProcessError(
            result.returncode,
            cmd,
            f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}",
            result.stderr
        )

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


def drop_database(db_name, db_user, db_password=None):
    """
    Drop a test database, ignoring the case where it doesn't exist.

    Passes the full environment through (so PGPORT and friends survive)
    and names the port explicitly: a bare env= would hand dropdb an
    environment without PGPORT, silently sending it to the default
    cluster - which is how e2e databases used to pile up on non-default
    clusters, run after run.

    Returns:
        subprocess.CompletedProcess of the dropdb call
    """
    drop_env = os.environ.copy()
    if db_password:
        drop_env['PGPASSWORD'] = db_password

    return subprocess.run(
        [
            'dropdb', '-U', db_user, '-h', 'localhost',
            '-p', str(pg_port()), '--if-exists', '--force', db_name
        ],
        env=drop_env,
        capture_output=True,
        text=True,
    )


@pytest.fixture(scope="session")
def e2e_databases():
    """
    Names of every database created by this test session.

    Tests that create databases of their own (a second actor, a clone
    with --database-name) register them here so they get dropped at the
    end of the session: the per-test teardown only knows about the
    database of its own e2e_environment.
    """
    created = []
    yield created


@pytest.fixture(scope="session", autouse=True)
def _drop_session_databases(postgres_user, e2e_databases):
    """Drop every database this session created, whatever happened to it.

    postgres_user is a declared dependency rather than a late
    getfixturevalue() lookup: a fixture is only torn down once its
    dependents are, so this keeps the credentials alive long enough to
    run dropdb.
    """
    yield

    if not e2e_databases:
        return

    credentials = postgres_user
    leftovers = []
    for db_name in e2e_databases:
        result = drop_database(db_name, credentials['user'], credentials['password'])
        if result.returncode != 0:
            leftovers.append(f"{db_name}: {result.stderr.strip()}")

    if leftovers:
        # Never fail the session on cleanup, but do not stay silent
        # either: a swallowed dropdb failure is what let these
        # databases accumulate unnoticed in the first place.
        print(
            "\nWarning: could not drop test database(s):\n  "
            + "\n  ".join(leftovers)
            + "\n  Run scripts/drop-stale-e2e-databases.py to clean up.",
            file=sys.stderr,
        )


@pytest.fixture(scope="function")
def e2e_environment(postgres_user, tmp_path_factory, e2e_databases):
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

    # Registered before creation: an interrupted test still gets its
    # database dropped at the end of the session.
    e2e_databases.append(db_name)

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
    drop_database(db_name, db_user, db_password)


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
port = {pg_port()}
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


@pytest.fixture(scope="function")
def project_with_fk_patch(project_with_release):
    """
    Create a project with a patch introducing two FK-related tables.

    Creates:
      - public.author(id SERIAL PK, name TEXT)
      - public.post(id SERIAL PK, title TEXT, author_id INT → author.id)

    Yields:
        dict with all project_with_release keys plus:
        - patch_id: The applied patch identifier
    """
    env = project_with_release
    run = env['run']
    project_dir = env['project_dir']

    patch_id = '1-author-post'
    run(['half_orm', 'dev', 'patch', 'create', patch_id])

    patch_dir = project_dir / 'Patches' / patch_id
    (patch_dir / '01_create_tables.sql').write_text(
        "CREATE TABLE author (\n"
        "    id   SERIAL PRIMARY KEY,\n"
        "    name TEXT NOT NULL\n"
        ");\n"
        "CREATE TABLE post (\n"
        "    id        SERIAL PRIMARY KEY,\n"
        "    title     TEXT NOT NULL,\n"
        "    author_id INT REFERENCES author(id),\n"
        "    metadata  jsonb\n"
        ");\n"
        "COMMENT ON COLUMN post.metadata IS 'Post metadata.\n"
        "@json\n"
        "```yaml\n"
        "lang:  text\n"
        "views: integer\n"
        "tags:  [text]\n"
        "items:\n"
        "  - id:    integer\n"
        "    title: text\n"
        "```\n"
        "';\n"
    )

    run(['half_orm', 'dev', 'patch', 'apply'])

    env['patch_id'] = patch_id
    yield env
