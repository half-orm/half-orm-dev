"""
Tests pour l'application de patches.

Module de test focalisé sur apply_patch_files() et les méthodes
d'exécution SQL/Python utilisant les fixtures du conftest.py.
"""

import pytest
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch as mock_patch

from half_orm_dev.patch_manager import (
    PatchManager,
    PatchManagerError
)


class TestApplyPatchFiles:
    """Test patch files application functionality."""

    def test_apply_patch_files_sql_and_python(self, patch_manager, mock_database):
        """Test applying patch with SQL and Python files."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create patch with SQL and Python files
        patch_path = patches_dir / "456-mixed"
        patch_path.mkdir()
        (patch_path / "01_create_table.sql").write_text("CREATE TABLE users (id INTEGER);")
        (patch_path / "02_insert_data.sql").write_text("INSERT INTO users VALUES (1);")
        (patch_path / "03_script.py").write_text("print('Migration complete')")
        (patch_path / "04_final.sql").write_text("ANALYZE users;")

        applied_files = patch_mgr.apply_patch_files("456-mixed", mock_database)

        # Should return files in lexicographic order
        expected_files = ["01_create_table.sql", "02_insert_data.sql", "03_script.py", "04_final.sql"]
        assert applied_files == expected_files

        # Should have called database execute_query for SQL files (3 times)
        assert mock_database.execute_query.call_count == 3

    def test_apply_patch_files_sql_only(self, patch_manager, mock_database):
        """Test applying patch with only SQL files."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create patch with SQL files only
        patch_path = patches_dir / "456-sql-only"
        patch_path.mkdir()
        (patch_path / "create.sql").write_text("CREATE TABLE test (id INTEGER);")
        (patch_path / "insert.sql").write_text("INSERT INTO test VALUES (1);")

        applied_files = patch_mgr.apply_patch_files("456-sql-only", mock_database)

        # Should apply both SQL files
        assert applied_files == ["create.sql", "insert.sql"]
        assert mock_database.execute_query.call_count == 2

    def test_apply_patch_files_python_only(self, patch_manager, mock_database):
        """Test applying patch with only Python files."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create patch with Python files only  
        patch_path = patches_dir / "456-python-only"
        patch_path.mkdir()
        (patch_path / "migrate.py").write_text("print('Migration started')")
        (patch_path / "cleanup.py").write_text("print('Cleanup done')")

        applied_files = patch_mgr.apply_patch_files("456-python-only", mock_database)

        # Should apply both Python files
        assert applied_files == ["cleanup.py", "migrate.py"]  # lexicographic order
        # No SQL execution
        assert mock_database.execute_query.call_count == 0

    def test_apply_patch_files_empty_patch(self, patch_manager, mock_database):
        """Test applying empty patch."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create empty patch
        patch_path = patches_dir / "456-empty"
        patch_path.mkdir()

        applied_files = patch_mgr.apply_patch_files("456-empty", mock_database)

        # Should return empty list
        assert applied_files == []
        assert mock_database.execute_query.call_count == 0

    def test_apply_patch_files_mixed_file_types(self, patch_manager, mock_database):
        """Test applying patch with mixed file types (some ignored)."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create patch with various file types
        patch_path = patches_dir / "456-mixed-types"
        patch_path.mkdir()
        (patch_path / "README.md").write_text("# Documentation")
        (patch_path / "script.sql").write_text("SELECT 1;")
        (patch_path / "script.py").write_text("print('hello')")
        (patch_path / "data.json").write_text('{"key": "value"}')
        (patch_path / "config.txt").write_text("configuration")

        applied_files = patch_mgr.apply_patch_files("456-mixed-types", mock_database)

        # Should only apply SQL and Python files
        assert set(applied_files) == {"script.sql", "script.py"}
        assert mock_database.execute_query.call_count == 1  # Only one SQL file

    def test_apply_patch_files_nonexistent_patch(self, patch_manager, mock_database):
        """Test applying nonexistent patch."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        with pytest.raises(PatchManagerError, match="Cannot apply invalid patch"):
            patch_mgr.apply_patch_files("999-nonexistent", mock_database)

    def test_apply_patch_files_invalid_patch(self, patch_manager, mock_database):
        """Test applying invalid patch (file instead of directory)."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create file instead of directory
        patch_file = patches_dir / "456-invalid"
        patch_file.write_text("Not a directory")

        with pytest.raises(PatchManagerError, match="Cannot apply invalid patch"):
            patch_mgr.apply_patch_files("456-invalid", mock_database)

    def test_apply_patch_files_sql_execution_error(self, patch_manager, mock_database):
        """Test SQL execution error during patch application."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create patch with SQL file
        patch_path = patches_dir / "456-sql-error"
        patch_path.mkdir()
        (patch_path / "bad.sql").write_text("INVALID SQL SYNTAX;")

        # Mock database to raise error
        mock_database.execute_query.side_effect = Exception("SQL syntax error")

        with pytest.raises(PatchManagerError, match="SQL execution failed in bad.sql"):
            patch_mgr.apply_patch_files("456-sql-error", mock_database)

    def test_apply_patch_files_python_execution_error(self, patch_manager, mock_database):
        """Test Python execution error during patch application."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create patch with failing Python script
        patch_path = patches_dir / "456-python-error"
        patch_path.mkdir()
        (patch_path / "bad_script.py").write_text("raise ValueError('Python error')")

        with pytest.raises(PatchManagerError, match="Python execution failed in bad_script.py"):
            patch_mgr.apply_patch_files("456-python-error", mock_database)

    def test_apply_patch_files_empty_sql_file(self, patch_manager, mock_database):
        """Test applying patch with empty SQL file (should be skipped)."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create patch with empty SQL file
        patch_path = patches_dir / "456-empty-sql"
        patch_path.mkdir()
        (patch_path / "empty.sql").write_text("")
        (patch_path / "whitespace.sql").write_text("   \n  \t  ")
        (patch_path / "valid.sql").write_text("SELECT 1;")

        applied_files = patch_mgr.apply_patch_files("456-empty-sql", mock_database)

        # All files should be reported as applied
        assert applied_files == ["empty.sql", "valid.sql", "whitespace.sql"]
        # But only valid.sql should trigger database execution
        assert mock_database.execute_query.call_count == 1

    def test_apply_patch_files_lexicographic_order(self, patch_manager, mock_database):
        """Test that files are applied in lexicographic order."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create patch with files in non-lexicographic creation order
        patch_path = patches_dir / "456-order-test"
        patch_path.mkdir()
        (patch_path / "z_last.sql").write_text("-- Last")
        (patch_path / "a_first.py").write_text("print('first')")
        (patch_path / "m_middle.sql").write_text("-- Middle")

        applied_files = patch_mgr.apply_patch_files("456-order-test", mock_database)

        # Should be in lexicographic order
        assert applied_files == ["a_first.py", "m_middle.sql", "z_last.sql"]


class TestExecuteSqlFile:
    """Test internal _execute_sql_file method."""

    def test_execute_sql_file_success(self, patch_manager, mock_database):
        """Test successful SQL file execution."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create SQL file
        sql_file = Path(temp_dir) / "test.sql"
        sql_file.write_text("CREATE TABLE test (id INTEGER);")

        # Execute SQL file
        patch_mgr._execute_sql_file(sql_file, mock_database)

        # Should call database execute_query once
        assert mock_database.execute_query.call_count == 1
        mock_database.execute_query.assert_called_with("CREATE TABLE test (id INTEGER);")

    def test_execute_sql_file_utf8_content(self, patch_manager, mock_database):
        """Test SQL file execution with UTF-8 content."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create SQL file with UTF-8 content
        sql_file = Path(temp_dir) / "unicode.sql"
        sql_content = "-- Commentaire en français\n-- コメント\nSELECT 'café' as café;"
        sql_file.write_text(sql_content, encoding='utf-8')

        # Execute SQL file
        patch_mgr._execute_sql_file(sql_file, mock_database)

        # Should handle UTF-8 correctly
        assert mock_database.execute_query.call_count == 1
        mock_database.execute_query.assert_called_with(sql_content)

    def test_execute_sql_file_empty_file(self, patch_manager, mock_database):
        """Test SQL file execution with empty file (should be skipped)."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create empty SQL file
        sql_file = Path(temp_dir) / "empty.sql"
        sql_file.write_text("")

        # Execute SQL file
        patch_mgr._execute_sql_file(sql_file, mock_database)

        # Should skip execution for empty file
        assert mock_database.execute_query.call_count == 0

    def test_execute_sql_file_database_error(self, patch_manager, mock_database):
        """Test SQL file execution with database error."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create SQL file
        sql_file = Path(temp_dir) / "error.sql"
        sql_file.write_text("INVALID SQL;")

        # Mock database to raise error
        mock_database.execute_query.side_effect = Exception("Database connection error")

        # Should raise PatchManagerError
        with pytest.raises(PatchManagerError, match="SQL execution failed in error.sql"):
            patch_mgr._execute_sql_file(sql_file, mock_database)

    def test_execute_sql_file_read_error(self, patch_manager, mock_database):
        """Test SQL file execution with file read error."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Reference non-existent file
        sql_file = Path(temp_dir) / "nonexistent.sql"

        # Should raise PatchManagerError
        with pytest.raises(PatchManagerError, match="SQL execution failed in nonexistent.sql"):
            patch_mgr._execute_sql_file(sql_file, mock_database)


class TestExecutePythonFile:
    """Test internal _execute_python_file method."""

    def test_execute_python_file_success(self, patch_manager):
        """Test successful Python file execution."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create Python file
        py_file = Path(temp_dir) / "test.py"
        py_file.write_text("print('Hello from Python')")

        # Mock subprocess.run to simulate success
        with mock_patch('subprocess.run') as mock_run:
            mock_run.return_value.stdout = "Hello from Python\n"
            mock_run.return_value.stderr = ""

            # Execute Python file
            patch_mgr._execute_python_file(py_file)

            # Should call subprocess.run
            assert mock_run.call_count == 1

    def test_execute_python_file_with_output(self, patch_manager, capsys):
        """Test Python file execution with output capture."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create Python file
        py_file = Path(temp_dir) / "output.py"
        py_file.write_text("print('Migration output')")

        # Mock subprocess to return output
        with mock_patch('subprocess.run') as mock_run:
            mock_run.return_value.stdout = "Migration output\n"
            mock_run.return_value.stderr = ""

            # Execute Python file
            patch_mgr._execute_python_file(py_file)

            # Should print output
            captured = capsys.readouterr()
            assert "Migration output" in captured.out

    def test_execute_python_file_error(self, patch_manager):
        """Test Python file execution with script error."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create Python file that will fail
        py_file = Path(temp_dir) / "error.py"
        py_file.write_text("raise ValueError('Script error')")

        # Mock subprocess to raise CalledProcessError
        with mock_patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                1, 'python', stderr="ValueError: Script error"
            )

            # Should raise PatchManagerError
            with pytest.raises(PatchManagerError, match="Python execution failed in error.py"):
                patch_mgr._execute_python_file(py_file)

    def test_execute_python_file_subprocess_error(self, patch_manager):
        """Test Python file execution with subprocess error."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create Python file
        py_file = Path(temp_dir) / "subprocess_error.py"
        py_file.write_text("print('test')")

        # Mock subprocess to raise generic error
        with mock_patch('subprocess.run') as mock_run:
            mock_run.side_effect = OSError("Subprocess failed")

            # Should raise PatchManagerError
            with pytest.raises(PatchManagerError, match="Failed to execute Python file"):
                patch_mgr._execute_python_file(py_file)

    def test_execute_python_file_working_directory(self, patch_manager):
        """Test Python file execution uses correct working directory."""
        patch_mgr, repo, temp_dir, patches_dir = patch_manager

        # Create Python file in patch directory
        patch_path = patches_dir / "456-working-dir"
        patch_path.mkdir()
        py_file = patch_path / "script.py"
        py_file.write_text("print('test')")

        # Mock subprocess.run
        with mock_patch('subprocess.run') as mock_run:
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = ""

            # Execute Python file
            patch_mgr._execute_python_file(py_file)

            # Should use patch directory as cwd
            mock_run.assert_called_once()
            call_args = mock_run.call_args
            assert call_args[1]['cwd'] == patch_path