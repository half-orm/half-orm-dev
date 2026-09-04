"""
Tests for file_executor module.

Tests the shared file execution utilities used by both
PatchManager and BootstrapManager.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from half_orm_dev.file_executor import (
    execute_sql_file,
    execute_sql_file_psql,
    execute_python_file,
    execute_python_bootstrap,
    execute_bootstrap_files,
    _has_run_entrypoint,
    FileExecutionError
)


class TestExecuteSqlFile:
    """Test execute_sql_file function."""

    def test_executes_sql_content(self, tmp_path):
        """Test that SQL content is executed via model."""
        sql_file = tmp_path / 'test.sql'
        sql_file.write_text('SELECT 1;')

        mock_model = Mock()
        execute_sql_file(sql_file, mock_model)

        mock_model.execute_query.assert_called_once_with('SELECT 1;')

    def test_skips_empty_file(self, tmp_path):
        """Test that empty files are skipped."""
        sql_file = tmp_path / 'empty.sql'
        sql_file.write_text('   \n   ')

        mock_model = Mock()
        execute_sql_file(sql_file, mock_model)

        mock_model.execute_query.assert_not_called()

    def test_raises_on_execution_error(self, tmp_path):
        """Test that execution errors are wrapped."""
        sql_file = tmp_path / 'bad.sql'
        sql_file.write_text('INVALID SQL;')

        mock_model = Mock()
        mock_model.execute_query.side_effect = Exception("syntax error")

        with pytest.raises(FileExecutionError, match="SQL execution failed"):
            execute_sql_file(sql_file, mock_model)

    def test_multiline_sql(self, tmp_path):
        """Test execution of multi-line SQL."""
        sql_file = tmp_path / 'multi.sql'
        sql_content = """
        CREATE TABLE test (id INT);
        INSERT INTO test VALUES (1);
        """
        sql_file.write_text(sql_content)

        mock_model = Mock()
        execute_sql_file(sql_file, mock_model)

        mock_model.execute_query.assert_called_once_with(sql_content)


class TestExecuteSqlFilePsql:
    """Test execute_sql_file_psql function."""

    def test_calls_psql_command(self, tmp_path):
        """Test that psql is called with correct arguments."""
        sql_file = tmp_path / 'test.sql'
        sql_file.write_text('SELECT 1;')

        mock_database = Mock()
        execute_sql_file_psql(sql_file, mock_database, 'mydb')

        mock_database.execute_pg_command.assert_called_once_with(
            'psql', '-v', 'ON_ERROR_STOP=1', '-d', 'mydb', '-f', str(sql_file)
        )

    def test_raises_on_psql_error(self, tmp_path):
        """Test that psql errors are wrapped."""
        sql_file = tmp_path / 'test.sql'
        sql_file.write_text('SELECT 1;')

        mock_database = Mock()
        mock_database.execute_pg_command.side_effect = Exception("psql failed")

        with pytest.raises(FileExecutionError, match="psql execution failed"):
            execute_sql_file_psql(sql_file, mock_database, 'mydb')


class TestExecutePythonFile:
    """Test execute_python_file function."""

    def test_executes_python_script(self, tmp_path):
        """Test that Python script is executed and returns output."""
        py_file = tmp_path / 'script.py'
        py_file.write_text('print("Hello, World!")')

        output = execute_python_file(py_file)

        assert output == "Hello, World!"

    def test_returns_empty_for_no_output(self, tmp_path):
        """Test script with no output."""
        py_file = tmp_path / 'silent.py'
        py_file.write_text('x = 1 + 1')

        output = execute_python_file(py_file)

        assert output == ""

    def test_uses_custom_cwd(self, tmp_path):
        """Test that custom working directory is used."""
        subdir = tmp_path / 'subdir'
        subdir.mkdir()

        py_file = tmp_path / 'script.py'
        py_file.write_text('import os; print(os.getcwd())')

        output = execute_python_file(py_file, cwd=subdir)

        assert str(subdir) in output

    def test_raises_on_script_error(self, tmp_path):
        """Test that script errors are wrapped."""
        py_file = tmp_path / 'bad.py'
        py_file.write_text('raise ValueError("intentional error")')

        with pytest.raises(FileExecutionError, match="Python execution failed"):
            execute_python_file(py_file)

    def test_raises_on_syntax_error(self, tmp_path):
        """Test that syntax errors are wrapped."""
        py_file = tmp_path / 'syntax.py'
        py_file.write_text('def broken(')

        with pytest.raises(FileExecutionError, match="Python execution failed"):
            execute_python_file(py_file)

    def test_uses_current_python(self, tmp_path):
        """Test that current Python interpreter is used."""
        py_file = tmp_path / 'version.py'
        py_file.write_text('import sys; print(sys.executable)')

        output = execute_python_file(py_file)

        assert sys.executable in output

    def test_default_cwd_is_file_parent(self, tmp_path):
        """Test that default cwd is file's parent directory."""
        subdir = tmp_path / 'subdir'
        subdir.mkdir()
        py_file = subdir / 'script.py'
        py_file.write_text('import os; print(os.getcwd())')

        output = execute_python_file(py_file)

        assert str(subdir) in output


class TestHasRunEntrypoint:
    """Test _has_run_entrypoint function."""

    def test_detects_run_function(self, tmp_path):
        f = tmp_path / 's.py'
        f.write_text('def run(model):\n    pass\n')
        assert _has_run_entrypoint(f) is True

    def test_no_run_function(self, tmp_path):
        f = tmp_path / 's.py'
        f.write_text('def other(model):\n    pass\n')
        assert _has_run_entrypoint(f) is False

    def test_nested_run_not_detected(self, tmp_path):
        """run() inside a class or function must not match."""
        f = tmp_path / 's.py'
        f.write_text('class Foo:\n    def run(self, model):\n        pass\n')
        assert _has_run_entrypoint(f) is False

    def test_syntax_error_returns_false(self, tmp_path):
        f = tmp_path / 's.py'
        f.write_text('def broken(')
        assert _has_run_entrypoint(f) is False

    def test_nonexistent_file_returns_false(self, tmp_path):
        assert _has_run_entrypoint(tmp_path / 'nope.py') is False


class TestExecutePythonBootstrap:
    """Test execute_python_bootstrap function."""

    def test_calls_run_with_model(self, tmp_path):
        """Script defining run(model) is called in-process with the model."""
        f = tmp_path / '1-seed-0.1.0.py'
        f.write_text(
            '# @hop:bootstrap\n'
            'def run(model):\n'
            '    model.called = True\n'
        )
        mock_model = Mock()
        mock_model.called = False
        execute_python_bootstrap(f, mock_model)
        assert mock_model.called is True

    def test_returns_run_return_value(self, tmp_path):
        f = tmp_path / '1-seed-0.1.0.py'
        f.write_text('def run(model):\n    return "42 rows inserted"\n')
        result = execute_python_bootstrap(f, Mock())
        assert result == '42 rows inserted'

    def test_returns_empty_when_run_returns_none(self, tmp_path):
        f = tmp_path / '1-seed-0.1.0.py'
        f.write_text('def run(model):\n    pass\n')
        assert execute_python_bootstrap(f, Mock()) == ''

    def test_fallback_to_subprocess_without_run(self, tmp_path):
        """Script without run(model) uses subprocess (backwards compat)."""
        f = tmp_path / '1-seed-0.1.0.py'
        f.write_text('print("legacy output")')
        result = execute_python_bootstrap(f, Mock())
        assert result == 'legacy output'

    def test_run_exception_wrapped_in_file_execution_error(self, tmp_path):
        f = tmp_path / '1-seed-0.1.0.py'
        f.write_text('def run(model):\n    raise ValueError("bad data")\n')
        with pytest.raises(FileExecutionError, match="bad data"):
            execute_python_bootstrap(f, Mock())

    def test_sys_path_restored_after_execution(self, tmp_path):
        f = tmp_path / '1-seed-0.1.0.py'
        f.write_text('def run(model):\n    pass\n')
        path_before = list(sys.path)
        execute_python_bootstrap(f, Mock(), cwd=tmp_path)
        assert sys.path == path_before

    def test_module_not_left_in_sys_modules(self, tmp_path):
        f = tmp_path / '1-seed-0.1.0.py'
        f.write_text('def run(model):\n    pass\n')
        execute_python_bootstrap(f, Mock())
        assert not any('_hop_bootstrap_' in k for k in sys.modules)

    def test_project_root_makes_generated_package_importable(self, tmp_path):
        """
        Regression: a bootstrap script under project/bootstrap/ doing
        `from myproject.api.role import Role` must find myproject/ at the
        project root, not just siblings inside bootstrap/.
        """
        project_root = tmp_path / 'myproject'
        bootstrap_dir = project_root / 'bootstrap'
        bootstrap_dir.mkdir(parents=True)
        pkg_dir = project_root / 'myproject'
        pkg_dir.mkdir()
        (pkg_dir / '__init__.py').write_text('GREETING = "hi from package"')

        f = bootstrap_dir / '01-roles.py'
        f.write_text(
            'from myproject import GREETING\n'
            'def run(model):\n'
            '    return GREETING\n'
        )

        result = execute_python_bootstrap(f, Mock(), cwd=bootstrap_dir, project_root=project_root)

        assert result == 'hi from package'

    def test_project_root_removed_from_sys_path_after_execution(self, tmp_path):
        project_root = tmp_path / 'myproject'
        bootstrap_dir = project_root / 'bootstrap'
        bootstrap_dir.mkdir(parents=True)
        f = bootstrap_dir / '01-seed.py'
        f.write_text('def run(model):\n    pass\n')

        path_before = list(sys.path)
        execute_python_bootstrap(f, Mock(), cwd=bootstrap_dir, project_root=project_root)
        assert sys.path == path_before

    def test_no_run_entrypoint_still_finds_project_package(self, tmp_path):
        """Subprocess fallback (no run(model)) also needs PYTHONPATH set."""
        project_root = tmp_path / 'myproject'
        bootstrap_dir = project_root / 'bootstrap'
        bootstrap_dir.mkdir(parents=True)
        pkg_dir = project_root / 'myproject'
        pkg_dir.mkdir()
        (pkg_dir / '__init__.py').write_text('GREETING = "hi from subprocess"')

        f = bootstrap_dir / '01-legacy.py'
        f.write_text('from myproject import GREETING\nprint(GREETING)')

        result = execute_python_bootstrap(f, Mock(), cwd=bootstrap_dir, project_root=project_root)

        assert result == 'hi from subprocess'


class TestExecutePythonBootstrapWithVenv:
    """venv_python forces every script through half_orm_dev._bootstrap_runner."""

    @patch('half_orm_dev.file_executor.subprocess.run')
    def test_run_entrypoint_script_forced_to_subprocess(self, mock_run, tmp_path):
        """
        Regression: even a script defining run(model) must NOT take the
        in-process fast path when venv_python is given - it must go
        through the venv's interpreter instead, to avoid mixing the
        project's dependencies into half_orm_dev's own process.
        """
        f = tmp_path / '01-seed.py'
        f.write_text('def run(model):\n    pass\n')
        mock_run.return_value = Mock(returncode=0, stdout='ok\n')
        venv_python = Path('/proj/.venv/bin/python')

        result = execute_python_bootstrap(
            f, Mock(), cwd=tmp_path, venv_python=venv_python, database_name='my_db'
        )

        mock_run.assert_called_once()
        cmd = mock_run.call_args.args[0]
        assert cmd == [str(venv_python), '-m', 'half_orm_dev._bootstrap_runner', str(f), 'my_db']
        assert result == 'ok'

    @patch('half_orm_dev.file_executor.subprocess.run')
    def test_legacy_script_also_forced_to_subprocess(self, mock_run, tmp_path):
        f = tmp_path / '01-legacy.py'
        f.write_text('print("hi")')
        mock_run.return_value = Mock(returncode=0, stdout='hi\n')
        venv_python = Path('/proj/.venv/bin/python')

        execute_python_bootstrap(
            f, Mock(), cwd=tmp_path, venv_python=venv_python, database_name='my_db'
        )

        cmd = mock_run.call_args.args[0]
        assert cmd[0] == str(venv_python)
        assert cmd[1:3] == ['-m', 'half_orm_dev._bootstrap_runner']

    @patch('half_orm_dev.file_executor.subprocess.run')
    def test_project_root_added_to_pythonpath(self, mock_run, tmp_path):
        f = tmp_path / '01-seed.py'
        f.write_text('def run(model):\n    pass\n')
        mock_run.return_value = Mock(returncode=0, stdout='')
        project_root = tmp_path.parent

        execute_python_bootstrap(
            f, Mock(), cwd=tmp_path, project_root=project_root,
            venv_python=Path('/proj/.venv/bin/python'), database_name='my_db',
        )

        env = mock_run.call_args.kwargs['env']
        assert str(project_root) in env['PYTHONPATH']

    @patch('half_orm_dev.file_executor.subprocess.run')
    def test_subprocess_failure_raises_file_execution_error(self, mock_run, tmp_path):
        import subprocess
        f = tmp_path / '01-bad.py'
        f.write_text('def run(model):\n    pass\n')
        mock_run.side_effect = subprocess.CalledProcessError(1, ['python'], stderr='boom')

        with pytest.raises(FileExecutionError, match="boom"):
            execute_python_bootstrap(
                f, Mock(), cwd=tmp_path,
                venv_python=Path('/proj/.venv/bin/python'), database_name='my_db',
            )


class TestExecuteBootstrapFiles:
    """Test execute_bootstrap_files - the bootstrap/ directory orchestrator."""

    def test_missing_directory_is_a_noop(self, tmp_path):
        execute_bootstrap_files(tmp_path / "does-not-exist", Mock())  # no raise

    def test_empty_directory_is_a_noop(self, tmp_path):
        model = Mock()
        execute_bootstrap_files(tmp_path, model)
        model.execute_query.assert_not_called()

    def test_ignores_non_sql_py_files(self, tmp_path):
        (tmp_path / "README.md").write_text("not executable")
        (tmp_path / "notes.txt").write_text("not executable")
        model = Mock()
        execute_bootstrap_files(tmp_path, model)
        model.execute_query.assert_not_called()

    def test_executes_sql_file_via_model(self, tmp_path):
        (tmp_path / "01-seed.sql").write_text("INSERT INTO t VALUES (1);")
        model = Mock()
        execute_bootstrap_files(tmp_path, model)
        model.execute_query.assert_called_once_with("INSERT INTO t VALUES (1);")

    @patch('half_orm_dev.file_executor.subprocess.run')
    def test_venv_python_and_database_name_threaded_through(self, mock_run, tmp_path):
        (tmp_path / "01-seed.py").write_text('def run(model):\n    pass\n')
        mock_run.return_value = Mock(returncode=0, stdout='')
        venv_python = Path('/proj/.venv/bin/python')

        execute_bootstrap_files(tmp_path, Mock(), venv_python=venv_python, database_name='my_db')

        cmd = mock_run.call_args.args[0]
        assert cmd[0] == str(venv_python)
        assert cmd[-1] == 'my_db'

    def test_executes_python_file_with_model(self, tmp_path):
        (tmp_path / "01-seed.py").write_text(
            'def run(model):\n    model.seeded = True\n'
        )
        model = Mock()
        model.seeded = False
        execute_bootstrap_files(tmp_path, model)
        assert model.seeded is True

    def test_python_file_can_import_generated_project_package(self, tmp_path):
        """
        Regression: execute_bootstrap_files(project/bootstrap, model) must
        make project/ importable, not just project/bootstrap/ - real
        bootstrap scripts import the ORM-generated project package
        (e.g. `from myproject.api.role import Role`).

        Uses a package name distinct from other tests in this module: a
        plain `import` (unlike the bootstrap wrapper module) is never
        popped from sys.modules, so a shared name would leak between tests.
        """
        project_root = tmp_path / 'orchestrator_project'
        bootstrap_dir = project_root / 'bootstrap'
        bootstrap_dir.mkdir(parents=True)
        pkg_dir = project_root / 'orchestrator_project'
        pkg_dir.mkdir()
        (pkg_dir / '__init__.py').write_text('GREETING = "hi"')
        (bootstrap_dir / '01-roles.py').write_text(
            'from orchestrator_project import GREETING\n'
            'def run(model):\n'
            '    model.greeting = GREETING\n'
        )
        model = Mock()

        execute_bootstrap_files(bootstrap_dir, model)

        assert model.greeting == 'hi'

    def test_alphabetic_order_across_sql_and_py(self, tmp_path):
        (tmp_path / "02-second.sql").write_text("-- second")
        (tmp_path / "01-first.py").write_text(
            'def run(model):\n    model.log("first")\n'
        )
        (tmp_path / "03-third.sql").write_text("-- third")
        model = Mock()
        order = []
        model.log = lambda name: order.append(name)
        model.execute_query = lambda sql: order.append(sql)

        execute_bootstrap_files(tmp_path, model)

        assert order == ["first", "-- second", "-- third"]

    def test_sql_error_wrapped_and_stops_remaining_files(self, tmp_path):
        (tmp_path / "01-bad.sql").write_text("INVALID SQL;")
        (tmp_path / "02-after.sql").write_text("-- should not run")
        model = Mock()
        model.execute_query = Mock(side_effect=Exception("syntax error"))

        with pytest.raises(FileExecutionError, match="01-bad.sql"):
            execute_bootstrap_files(tmp_path, model)

        model.execute_query.assert_called_once()

    def test_python_error_propagates_as_file_execution_error(self, tmp_path):
        (tmp_path / "01-bad.py").write_text(
            'def run(model):\n    raise ValueError("boom")\n'
        )
        with pytest.raises(FileExecutionError, match="boom"):
            execute_bootstrap_files(tmp_path, Mock())


class TestFileExecutionError:
    """Test FileExecutionError exception."""

    def test_exception_message(self):
        """Test exception can be raised with message."""
        with pytest.raises(FileExecutionError, match="test error"):
            raise FileExecutionError("test error")

    def test_exception_inheritance(self):
        """Test exception inherits from Exception."""
        assert issubclass(FileExecutionError, Exception)
