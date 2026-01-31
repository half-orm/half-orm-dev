"""
Shared utilities for executing SQL and Python files.

This module provides common file execution functionality used by both
PatchManager and BootstrapManager.
"""

import re
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


def is_bootstrap_file(file_path: Path) -> bool:
    """
    Check if file has @HOP:bootstrap or @HOP:data marker on first line.

    The marker must be on the first line of the file:
    - SQL files: -- @HOP:bootstrap or -- @HOP:data
    - Python files: # @HOP:bootstrap or # @HOP:data

    Note: @HOP:data is supported as an alias for backwards compatibility.

    Args:
        file_path: Path to file to check

    Returns:
        True if file has bootstrap marker, False otherwise
    """
    try:
        with file_path.open('r', encoding='utf-8') as f:
            first_line = f.readline().strip().lower()
            # Match both @HOP:bootstrap and @HOP:data (alias for backwards compat)
            return (
                re.match(r"(--|#)\s*@hop:bootstrap", first_line) is not None or
                re.match(r"(--|#)\s*@hop:data", first_line) is not None
            )
    except Exception:
        return False
