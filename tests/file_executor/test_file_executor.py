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
    _has_run_entrypoint,
    is_bootstrap_file,
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
            'psql', '-d', 'mydb', '-f', str(sql_file)
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


class TestIsBootstrapFile:
    """Test is_bootstrap_file function."""

    def test_sql_with_bootstrap_marker(self, tmp_path):
        """Test SQL file with @HOP:bootstrap marker."""
        sql_file = tmp_path / 'test.sql'
        sql_file.write_text('-- @HOP:bootstrap\nSELECT 1;')

        assert is_bootstrap_file(sql_file) is True

    def test_sql_with_data_marker(self, tmp_path):
        """Test SQL file with @HOP:data marker (alias)."""
        sql_file = tmp_path / 'test.sql'
        sql_file.write_text('-- @HOP:data\nSELECT 1;')

        assert is_bootstrap_file(sql_file) is True

    def test_python_with_bootstrap_marker(self, tmp_path):
        """Test Python file with @HOP:bootstrap marker."""
        py_file = tmp_path / 'test.py'
        py_file.write_text('# @HOP:bootstrap\nprint("data")')

        assert is_bootstrap_file(py_file) is True

    def test_python_with_data_marker(self, tmp_path):
        """Test Python file with @HOP:data marker (alias)."""
        py_file = tmp_path / 'test.py'
        py_file.write_text('# @HOP:data\nprint("data")')

        assert is_bootstrap_file(py_file) is True

    def test_no_marker(self, tmp_path):
        """Test file without marker."""
        sql_file = tmp_path / 'test.sql'
        sql_file.write_text('SELECT 1;')

        assert is_bootstrap_file(sql_file) is False

    def test_marker_not_on_first_line(self, tmp_path):
        """Test that marker must be on first line."""
        sql_file = tmp_path / 'test.sql'
        sql_file.write_text('SELECT 1;\n-- @HOP:bootstrap')

        assert is_bootstrap_file(sql_file) is False

    def test_case_insensitive(self, tmp_path):
        """Test that marker matching is case insensitive."""
        sql_file = tmp_path / 'test.sql'
        sql_file.write_text('-- @HOP:BOOTSTRAP\nSELECT 1;')

        assert is_bootstrap_file(sql_file) is True

    def test_marker_with_extra_spaces(self, tmp_path):
        """Test marker with extra spaces."""
        sql_file = tmp_path / 'test.sql'
        sql_file.write_text('--   @HOP:bootstrap\nSELECT 1;')

        assert is_bootstrap_file(sql_file) is True

    def test_nonexistent_file(self, tmp_path):
        """Test that nonexistent file returns False."""
        fake_file = tmp_path / 'nonexistent.sql'

        assert is_bootstrap_file(fake_file) is False

    def test_empty_file(self, tmp_path):
        """Test that empty file returns False."""
        empty_file = tmp_path / 'empty.sql'
        empty_file.write_text('')

        assert is_bootstrap_file(empty_file) is False

    def test_binary_file(self, tmp_path):
        """Test that binary file returns False gracefully."""
        binary_file = tmp_path / 'binary.bin'
        binary_file.write_bytes(b'\x00\x01\x02\x03')

        # Should return False, not raise
        assert is_bootstrap_file(binary_file) is False


class TestFileExecutionError:
    """Test FileExecutionError exception."""

    def test_exception_message(self):
        """Test exception can be raised with message."""
        with pytest.raises(FileExecutionError, match="test error"):
            raise FileExecutionError("test error")

    def test_exception_inheritance(self):
        """Test exception inherits from Exception."""
        assert issubclass(FileExecutionError, Exception)
