"""
Tests for ReleaseManager._run_validation_tests() method.

Focused on testing:
- Successful pytest execution (exit code 0)
- Failed pytest execution (exit code non-zero)
- Error message includes pytest output
- Correct pytest command execution
- Working directory set correctly
- Capture stdout and stderr
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from half_orm_dev.release_manager import ReleaseManager, ReleaseManagerError


class TestRunValidationTests:
    """Test _run_validation_tests() method."""

    @pytest.fixture
    def release_manager_basic(self, tmp_path):
        """Create basic ReleaseManager."""
        mock_repo = Mock()
        mock_repo.base_dir = str(tmp_path)

        # Create releases/ and tests/ directories
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir(exist_ok=True)
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        release_mgr = ReleaseManager(mock_repo)

        return release_mgr, tmp_path

    @patch('subprocess.run')
    def test_tests_pass_no_error(self, mock_run, release_manager_basic):
        """Test successful test execution (exit code 0)."""
        release_mgr, base_dir = release_manager_basic

        # Mock successful pytest run
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "===== 25 passed in 2.5s ====="
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        # Should not raise
        release_mgr._run_validation_tests()

        # Verify pytest was called correctly
        mock_run.assert_called_once()
        call_args = mock_run.call_args

        # Check command
        assert call_args[0][0] == ["pytest", "tests/"]

        # Check working directory
        assert call_args[1]['cwd'] == str(base_dir)

        # Check output capture
        assert call_args[1]['capture_output'] is True
        assert call_args[1]['text'] is True

    @patch('subprocess.run')
    def test_tests_fail_raises_error(self, mock_run, release_manager_basic):
        """Test failed test execution raises error."""
        release_mgr, base_dir = release_manager_basic

        # Mock failed pytest run
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = "===== 2 failed, 23 passed in 3.1s ====="
        mock_result.stderr = "FAILED tests/test_user.py::test_authentication"
        mock_run.return_value = mock_result

        # Should raise error with output
        with pytest.raises(ReleaseManagerError) as exc_info:
            release_mgr._run_validation_tests()

        error_msg = str(exc_info.value)
        assert "Tests failed" in error_msg or "test" in error_msg.lower()
        # Error should include pytest output for debugging
        assert "failed" in error_msg.lower() or mock_result.stdout in error_msg

    @patch('subprocess.run')
    def test_pytest_command_format(self, mock_run, release_manager_basic):
        """Test pytest command has correct format."""
        release_mgr, base_dir = release_manager_basic

        # Mock successful run
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        release_mgr._run_validation_tests()

        # Verify command is ["pytest", "tests/"]
        call_args = mock_run.call_args
        command = call_args[0][0]

        assert command[0] == "pytest"
        assert command[1] == "tests/"

    @patch('subprocess.run')
    def test_working_directory_set(self, mock_run, release_manager_basic):
        """Test working directory set to repository base."""
        release_mgr, base_dir = release_manager_basic

        # Mock successful run
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        release_mgr._run_validation_tests()

        # Verify cwd is set to base_dir
        call_args = mock_run.call_args
        assert call_args[1]['cwd'] == str(base_dir)

    @patch('subprocess.run')
    def test_captures_stdout_and_stderr(self, mock_run, release_manager_basic):
        """Test stdout and stderr are captured."""
        release_mgr, base_dir = release_manager_basic

        # Mock successful run
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "test output"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        release_mgr._run_validation_tests()

        # Verify capture_output and text flags
        call_args = mock_run.call_args
        assert call_args[1]['capture_output'] is True
        assert call_args[1]['text'] is True

    @patch('subprocess.run')
    def test_error_includes_stdout(self, mock_run, release_manager_basic):
        """Test error message includes pytest stdout."""
        release_mgr, base_dir = release_manager_basic

        # Mock failed run with detailed output
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = "FAILED tests/test_critical.py::test_security - AssertionError: Expected 200, got 500"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        with pytest.raises(ReleaseManagerError) as exc_info:
            release_mgr._run_validation_tests()

        # Error should include stdout for debugging
        error_msg = str(exc_info.value)
        assert "FAILED" in error_msg or "test_security" in error_msg or "AssertionError" in error_msg

    @patch('subprocess.run')
    def test_error_includes_stderr(self, mock_run, release_manager_basic):
        """Test error message includes pytest stderr."""
        release_mgr, base_dir = release_manager_basic

        # Mock failed run with stderr
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "ERROR: ImportError: cannot import name 'UserAuth'"
        mock_run.return_value = mock_result

        with pytest.raises(ReleaseManagerError) as exc_info:
            release_mgr._run_validation_tests()

        # Error should include stderr for debugging
        error_msg = str(exc_info.value)
        assert "ImportError" in error_msg or "cannot import" in error_msg

    @patch('subprocess.run')
    def test_subprocess_exception_handled(self, mock_run, release_manager_basic):
        """Test subprocess exception is handled properly."""
        release_mgr, base_dir = release_manager_basic

        # Mock subprocess exception
        mock_run.side_effect = FileNotFoundError("pytest not found")

        # Should raise ReleaseManagerError
        with pytest.raises(ReleaseManagerError) as exc_info:
            release_mgr._run_validation_tests()

        error_msg = str(exc_info.value)
        assert "pytest" in error_msg.lower() or "test" in error_msg.lower()

    @patch('subprocess.run')
    def test_timeout_handled(self, mock_run, release_manager_basic):
        """Test timeout is handled if tests hang."""
        release_mgr, base_dir = release_manager_basic

        # Mock timeout
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired("pytest", 300)

        # Should raise ReleaseManagerError
        with pytest.raises(ReleaseManagerError) as exc_info:
            release_mgr._run_validation_tests()

        error_msg = str(exc_info.value)
        assert "timeout" in error_msg.lower() or "test" in error_msg.lower()

    @patch('subprocess.run')
    def test_multiple_test_failures_in_output(self, mock_run, release_manager_basic):
        """Test error message with multiple test failures."""
        release_mgr, base_dir = release_manager_basic

        # Mock run with multiple failures
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = """
===== FAILURES =====
_____ test_user_auth _____
AssertionError: Invalid credentials

_____ test_admin_access _____
PermissionError: Admin access denied

===== 2 failed, 23 passed in 5.2s =====
"""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        with pytest.raises(ReleaseManagerError) as exc_info:
            release_mgr._run_validation_tests()

        error_msg = str(exc_info.value)
        # Should include failure info
        assert "failed" in error_msg.lower()
