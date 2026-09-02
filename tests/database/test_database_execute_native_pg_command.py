"""
Tests for Database._execute_native_pg_command() classmethod.

Focused on testing:
- PG* environment variable construction from connection_params
- Falsy/None values (unset user/host/port) are omitted, not crashing
- The base os.environ is preserved (PATH, etc.), not replaced
- subprocess.run invocation (command_args, capture_output, text, check)
"""

import subprocess
import pytest
from unittest.mock import patch

from half_orm_dev.database import Database


class TestExecuteNativePgCommand:
    """Test Database._execute_native_pg_command() classmethod."""

    @patch('half_orm_dev.database.subprocess.run')
    def test_full_connection_params_sets_all_env_vars(self, mock_run):
        """All PG* env vars are set when connection_params provides them."""
        connection_params = {
            'user': 'dev', 'host': 'localhost', 'port': 5432, 'password': 'secret'
        }

        Database._execute_native_pg_command(
            'my_db', connection_params, 'psql', '-c', 'SELECT 1'
        )

        _, kwargs = mock_run.call_args
        env = kwargs['env']
        assert env['PGUSER'] == 'dev'
        assert env['PGHOST'] == 'localhost'
        assert env['PGPORT'] == '5432'
        assert env['PGPASSWORD'] == 'secret'

    @patch('half_orm_dev.database.subprocess.run')
    def test_port_is_stringified(self, mock_run):
        """PGPORT must be a str (subprocess env values cannot be int)."""
        connection_params = {'user': 'dev', 'host': 'localhost', 'port': 5432, 'password': None}

        Database._execute_native_pg_command('my_db', connection_params, 'psql')

        env = mock_run.call_args.kwargs['env']
        assert isinstance(env['PGPORT'], str)

    @patch('half_orm_dev.database.subprocess.run')
    def test_no_password_does_not_set_pgpassword(self, mock_run):
        """PGPASSWORD is omitted when password is None/empty (trust/peer auth)."""
        connection_params = {'user': 'dev', 'host': 'localhost', 'port': 5432, 'password': None}

        Database._execute_native_pg_command('my_db', connection_params, 'psql')

        env = mock_run.call_args.kwargs['env']
        assert 'PGPASSWORD' not in env

    @patch('half_orm_dev.database.subprocess.run')
    @patch.dict('half_orm_dev.database.os.environ', {'PATH': '/usr/bin:/bin'}, clear=True)
    def test_none_user_host_port_do_not_crash_and_are_omitted(self, mock_run):
        """
        None values for user/host/port (peer authentication - no config file,
        cf. half_orm.model.Model._dbinfo) must not raise and must not be
        forwarded to the subprocess environment.

        os.environ is cleared here: this asserts PGUSER/PGHOST/PGPORT/
        PGPASSWORD are omitted when connection_params doesn't provide them
        - it must not depend on whether the machine running the test
        happens to have those variables set ambiently (e.g. PGPORT/PGUSER
        pointing at a dedicated dev cluster).
        """
        connection_params = {'user': None, 'host': None, 'port': None, 'password': None}

        Database._execute_native_pg_command('my_db', connection_params, 'psql')

        env = mock_run.call_args.kwargs['env']
        assert 'PGUSER' not in env
        assert 'PGHOST' not in env
        assert 'PGPORT' not in env
        assert 'PGPASSWORD' not in env

    @patch('half_orm_dev.database.subprocess.run')
    @patch.dict('half_orm_dev.database.os.environ',
        {
            'PATH': '/usr/bin:/bin',
            'PGUSER': 'devenv'
        }, clear=True)
    def test_empty_connection_params_does_not_crash(self, mock_run):
        """
        An empty connection_params dict (no keys at all, not just falsy
        values) must not raise (no direct dict-key access), and the
        subprocess env must fall back to a plain copy of os.environ,
        and preserves the PG variables already present in the ambient
        environment (they are inherited, not stripped, since
        connection_params provides no override for them).
        """
        Database._execute_native_pg_command('my_db', {}, 'psql')

        env = mock_run.call_args.kwargs['env']
        assert env['PGUSER'] == 'devenv'
        assert 'PGHOST' not in env
        assert 'PGPORT' not in env
        assert 'PGPASSWORD' not in env
        assert env['PATH'] == '/usr/bin:/bin'

    @patch('half_orm_dev.database.subprocess.run')
    @patch.dict('half_orm_dev.database.os.environ', {'PATH': '/usr/bin:/bin'}, clear=True)
    def test_empty_string_host_and_port_are_omitted(self, mock_run):
        """
        Empty-string host/port (local socket convention) are also falsy and
        omitted - independent of whatever PGHOST/PGPORT the machine running
        the test happens to have set ambiently.
        """
        connection_params = {'user': 'dev', 'host': '', 'port': '', 'password': None}

        Database._execute_native_pg_command('my_db', connection_params, 'psql')

        env = mock_run.call_args.kwargs['env']
        assert env['PGUSER'] == 'dev'
        assert 'PGHOST' not in env
        assert 'PGPORT' not in env

    @patch('half_orm_dev.database.subprocess.run')
    @patch.dict('half_orm_dev.database.os.environ', {'PATH': '/usr/bin:/bin'}, clear=True)
    def test_preserves_base_os_environ(self, mock_run):
        """The subprocess env is os.environ + PG* overrides, not a fresh dict (PATH must survive)."""
        connection_params = {'user': 'dev', 'host': 'localhost', 'port': 5432, 'password': None}

        Database._execute_native_pg_command('my_db', connection_params, 'psql')

        env = mock_run.call_args.kwargs['env']
        assert env['PATH'] == '/usr/bin:/bin'

    @patch('half_orm_dev.database.subprocess.run')
    def test_command_args_passed_through(self, mock_run):
        """command_args are forwarded to subprocess.run unchanged, as positional args."""
        connection_params = {'user': 'dev', 'host': 'localhost', 'port': 5432, 'password': None}

        Database._execute_native_pg_command(
            'my_db', connection_params, 'createdb', '-T', 'template0', 'my_db'
        )

        args, _ = mock_run.call_args
        assert args[0] == ('createdb', '-T', 'template0', 'my_db')

    @patch('half_orm_dev.database.subprocess.run')
    def test_subprocess_run_called_with_capture_and_check(self, mock_run):
        """subprocess.run is called with capture_output=True, text=True, check=True."""
        connection_params = {'user': 'dev', 'host': 'localhost', 'port': 5432, 'password': None}

        Database._execute_native_pg_command('my_db', connection_params, 'psql')

        kwargs = mock_run.call_args.kwargs
        assert kwargs['capture_output'] is True
        assert kwargs['text'] is True
        assert kwargs['check'] is True

    @patch('half_orm_dev.database.subprocess.run')
    def test_returns_subprocess_result(self, mock_run):
        """The CompletedProcess returned by subprocess.run is returned as-is."""
        connection_params = {'user': 'dev', 'host': 'localhost', 'port': 5432, 'password': None}
        mock_run.return_value = subprocess.CompletedProcess(
            args=['psql'], returncode=0, stdout='ok', stderr=''
        )

        result = Database._execute_native_pg_command('my_db', connection_params, 'psql')

        assert result.stdout == 'ok'

    @patch('half_orm_dev.database.subprocess.run')
    def test_called_process_error_propagates(self, mock_run):
        """A failing PostgreSQL command (check=True) propagates CalledProcessError."""
        connection_params = {'user': 'dev', 'host': 'localhost', 'port': 5432, 'password': None}
        mock_run.side_effect = subprocess.CalledProcessError(1, 'psql')

        with pytest.raises(subprocess.CalledProcessError):
            Database._execute_native_pg_command('my_db', connection_params, 'psql')
