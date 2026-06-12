"""
Shared utilities for executing SQL and Python files.

This module provides common file execution functionality for patch application
and bootstrap initialization.
"""

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Optional


class FileExecutionError(Exception):
    """Raised when file execution fails."""
    pass


def execute_sql_file(file_path: Path, database_model) -> None:
    """
    Execute SQL file against database using halfORM Model.

    Args:
        file_path: Path to SQL file
        database_model: halfORM Model instance

    Raises:
        FileExecutionError: If SQL execution fails
    """
    try:
        sql_content = file_path.read_text(encoding='utf-8')

        # Skip empty files
        if not sql_content.strip():
            return

        database_model.execute_query(sql_content)

    except Exception as e:
        raise FileExecutionError(f"SQL execution failed in {file_path.name}: {e}") from e


def execute_sql_file_psql(file_path: Path, database, database_name: str) -> None:
    """
    Execute SQL file using psql command.

    Uses psql directly instead of halfORM Model, useful for files that
    may contain transaction control or other psql-specific features.

    Args:
        file_path: Path to SQL file
        database: Database instance with execute_pg_command method
        database_name: Name of the database to connect to

    Raises:
        FileExecutionError: If psql execution fails
    """
    try:
        database.execute_pg_command('psql', '-d', database_name, '-f', str(file_path))
    except Exception as e:
        raise FileExecutionError(f"psql execution failed for {file_path.name}: {e}") from e


def execute_python_file(file_path: Path, cwd: Optional[Path] = None) -> str:
    """
    Execute Python script as subprocess.

    Args:
        file_path: Path to Python file
        cwd: Working directory for execution (default: file's parent directory)

    Returns:
        stdout from the script execution

    Raises:
        FileExecutionError: If Python execution fails
    """
    if cwd is None:
        cwd = file_path.parent

    try:
        result = subprocess.run(
            [sys.executable, str(file_path)],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()

    except subprocess.CalledProcessError as e:
        error_msg = f"Python execution failed in {file_path.name}"
        if e.stderr:
            error_msg += f": {e.stderr.strip()}"
        raise FileExecutionError(error_msg) from e
    except Exception as e:
        raise FileExecutionError(f"Failed to execute Python file {file_path.name}: {e}") from e


def _has_run_entrypoint(file_path: Path) -> bool:
    """Return True if the file defines a top-level run() function."""
    try:
        tree = ast.parse(file_path.read_text(encoding='utf-8'))
    except (OSError, SyntaxError):
        return False
    return any(
        isinstance(node, ast.FunctionDef) and node.name == 'run'
        for node in tree.body
    )


def execute_python_bootstrap(file_path: Path, model, cwd: Optional[Path] = None) -> str:
    """
    Execute a Python bootstrap script.

    Fast path — if the script defines a top-level run(model) function it is
    loaded in-process via importlib and called with the live database model,
    sharing the existing connection.

    Slow path — scripts without run(model) are executed as a subprocess
    (backwards-compatible with pre-API scripts).

    Args:
        file_path: Path to Python bootstrap script
        model: halfORM Model instance (shared database connection)
        cwd: Working directory for execution (default: file's parent)

    Returns:
        Return value of run() converted to str, or subprocess stdout.
        Empty string if run() returns None.

    Raises:
        FileExecutionError: If execution fails
    """
    if cwd is None:
        cwd = file_path.parent

    if not _has_run_entrypoint(file_path):
        return execute_python_file(file_path, cwd)

    module_name = f"_hop_bootstrap_{file_path.stem.replace('-', '_').replace('.', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)

    cwd_str = str(cwd)
    inserted = cwd_str not in sys.path
    if inserted:
        sys.path.insert(0, cwd_str)

    try:
        spec.loader.exec_module(module)
        result = module.run(model)
        return str(result) if result is not None else ''
    except FileExecutionError:
        raise
    except Exception as e:
        raise FileExecutionError(
            f"Python execution failed in {file_path.name}: {e}"
        ) from e
    finally:
        if inserted and cwd_str in sys.path:
            sys.path.remove(cwd_str)
        sys.modules.pop(module_name, None)


def execute_bootstrap_files(bootstrap_dir: Path, model) -> None:
    """
    Execute all bootstrap files in alphabetic order.

    Bootstrap files are SQL and Python files in the bootstrap/ directory that
    initialize application data on empty databases. They are executed in
    alphabetic order (no numeric parsing needed).

    Args:
        bootstrap_dir: Path to bootstrap directory
        model: halfORM Model instance (shared database connection)

    Raises:
        FileExecutionError: If any file execution fails

    Example:
        bootstrap_dir = Path('/path/to/project/bootstrap')
        execute_bootstrap_files(bootstrap_dir, model)

        # Executes files in order:
        # - 01-init-users.sql
        # - 02-seed-config.py
        # - 03-reference-data.sql
    """
    if not bootstrap_dir.exists():
        return

    # Collect all SQL and Python files
    files = []
    for file_path in bootstrap_dir.iterdir():
        if file_path.is_file() and file_path.suffix in ('.sql', '.py'):
            files.append(file_path)

    if not files:
        return

    # Sort alphabetically by filename
    files.sort(key=lambda f: f.name)

    # Execute each file
    for file_path in files:
        try:
            if file_path.suffix == '.sql':
                execute_sql_file(file_path, model)
            elif file_path.suffix == '.py':
                execute_python_bootstrap(file_path, model, cwd=bootstrap_dir)
        except FileExecutionError:
            # Re-raise FileExecutionError as-is (already has good error message)
            raise
        except Exception as e:
            # Wrap unexpected errors
            raise FileExecutionError(
                f"Failed to execute bootstrap file {file_path.name}: {e}"
            ) from e
