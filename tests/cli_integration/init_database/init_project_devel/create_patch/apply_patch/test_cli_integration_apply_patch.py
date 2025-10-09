"""
Integration tests for 'half_orm dev apply-patch' CLI command (nominal case).

Tests end-to-end patch application via subprocess with real database.
Uses autonomous standalone_applied_patch fixture for complete isolation.
"""

import pytest
import sys
from pathlib import Path


@pytest.mark.integration
class TestApplyPatchSqlExecution:
    """Test SQL file execution from patch."""

    def test_apply_patch_applies_sql_files(self, standalone_applied_patch):
        """Test that SQL files in patch are executed and table is created."""
        project_dir, db_name, patch_id = standalone_applied_patch

        # Verify table test_users was created in database
        from half_orm.model import Model

        try:
            model = Model(db_name)

            # Check if test_users table exists
            TestUsers = model.get_relation_class('public.test_users')

            # TestUsers shoud be instantiable
            test_users = TestUsers()

            assert hasattr(test_users, 'id'), "Column 'id' should exist"
            assert hasattr(test_users, 'name'), "Column 'name' should exist"

            model.disconnect()
        except Exception as e:
            pytest.fail(f"SQL execution verification failed: {e}")


@pytest.mark.integration
class TestApplyPatchCodeGeneration:
    """Test Python code generation from database schema."""

    def test_apply_patch_generates_python_code(self, standalone_applied_patch):
        """Test that Python code is generated and is functional for test_users table."""
        project_dir, db_name, patch_id = standalone_applied_patch

        # Add project to sys.path for imports
        sys.path.insert(0, str(project_dir))

        try:
            # Verify Python package structure exists
            package_dir = project_dir / db_name / "public"
            assert package_dir.exists(), f"Package directory {package_dir} should exist"

            # Verify test_users.py was generated
            test_users_file = package_dir / "test_users.py"
            assert test_users_file.exists(), "test_users.py should be generated"

            # Import the generated module
            import importlib
            module_name = f"{db_name}.public.test_users"
            module = importlib.import_module(module_name)

            # Verify class exists
            assert hasattr(module, 'TestUsers'), "TestUsers class should exist in module"

            # Verify we can instantiate the class
            TestUsers = getattr(module, 'TestUsers')
            instance = TestUsers()
            assert instance is not None, "Should be able to instantiate TestUsers"

            # Verify the instance has expected attributes from table schema
            assert hasattr(instance, 'id'), "Instance should have 'id' attribute"
            assert hasattr(instance, 'name'), "Instance should have 'name' attribute"

        except ImportError as e:
            pytest.fail(f"Failed to import generated module: {e}")
        except Exception as e:
            pytest.fail(f"Code generation verification failed: {e}")
        finally:
            # Cleanup sys.path
            if str(project_dir) in sys.path:
                sys.path.remove(str(project_dir))


@pytest.mark.integration
class TestApplyPatchExitCode:
    """Test successful command exit code."""

    def test_apply_patch_success_exit_code(self, standalone_applied_patch):
        """Test that apply-patch completes successfully."""
        project_dir, db_name, patch_id = standalone_applied_patch

        # The fixture already verified exit code 0 during setup
        # This test documents the expected behavior explicitly

        # Verify we're still on the patch branch after apply-patch
        import subprocess
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )

        assert result.returncode == 0
        assert result.stdout.strip() == f"ho-patch/{patch_id}", (
            f"Should still be on ho-patch/{patch_id} after apply-patch"
        )