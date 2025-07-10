#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unit tests for modules.py

Tests the enhanced test structure generation functionality.
"""

import os
import tempfile
import unittest
from unittest.mock import Mock, patch, mock_open
import shutil

# Import the module under test
# Assuming the module is in half_orm_dev.modules
try:
    from half_orm_dev.modules import (
        _create_tests_directory,
        _create_test_file,
        _create_pytest_config,
        _count_test_files_recursive,
        generate
    )
    # Import utils for BEGIN_CODE/END_CODE constants
    from half_orm import utils
except ImportError:
    # For testing outside the full package structure
    import sys
    sys.path.append('..')
    # Mock imports if not available
    utils = Mock()
    utils.BEGIN_CODE = "# BEGIN_CODE"
    utils.END_CODE = "# END_CODE"


class TestModulesTestStructure(unittest.TestCase):
    """Test the enhanced test structure functionality in modules.py"""

    def setUp(self):
        """Set up test environment with temporary directory"""
        self.test_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.test_dir)
        
        # Mock repository object
        self.mock_repo = Mock()
        self.mock_repo.name = 'test_db'
        self.mock_repo.base_dir = self.test_dir
        self.mock_repo.devel = True

    def test_create_tests_directory(self):
        """Test creation of standard tests/ directory structure"""
        tests_dir = _create_tests_directory(self.mock_repo)
        
        # Verify tests directory was created
        expected_tests_dir = os.path.join(self.test_dir, 'tests')
        self.assertEqual(tests_dir, expected_tests_dir)
        self.assertTrue(os.path.exists(tests_dir))
        
        # Verify __init__.py was created
        init_file = os.path.join(tests_dir, '__init__.py')
        self.assertTrue(os.path.exists(init_file))
        
        # Verify __init__.py content
        with open(init_file, 'r') as f:
            content = f.read()
            self.assertIn('Tests for the halfORM project', content)

    def test_create_tests_directory_idempotent(self):
        """Test that creating tests directory multiple times is safe"""
        # Create directory first time
        tests_dir1 = _create_tests_directory(self.mock_repo)
        
        # Create directory second time
        tests_dir2 = _create_tests_directory(self.mock_repo)
        
        # Should return same directory and not fail
        self.assertEqual(tests_dir1, tests_dir2)
        self.assertTrue(os.path.exists(tests_dir1))

    def test_create_test_file_basic(self):
        """Test creation of basic test file with hierarchical structure"""
        tests_dir = _create_tests_directory(self.mock_repo)
        
        # Create test file for public.users table
        test_file_path = _create_test_file(
            repo=self.mock_repo,
            module_name='users',
            class_name='Users',
            fqtn='public.users',
            tests_dir=tests_dir
        )
        
        # Verify hierarchical path structure
        expected_path = os.path.join(tests_dir, 'test_db', 'public', 'test_users.py')
        self.assertEqual(test_file_path, expected_path)
        self.assertTrue(os.path.exists(test_file_path))
        
        # Verify database directory and __init__.py
        db_dir = os.path.join(tests_dir, 'test_db')
        self.assertTrue(os.path.exists(db_dir))
        self.assertTrue(os.path.exists(os.path.join(db_dir, '__init__.py')))
        
        # Verify schema directory and __init__.py
        schema_dir = os.path.join(db_dir, 'public')
        self.assertTrue(os.path.exists(schema_dir))
        self.assertTrue(os.path.exists(os.path.join(schema_dir, '__init__.py')))

    def test_create_test_file_content(self):
        """Test the content of generated test files"""
        tests_dir = _create_tests_directory(self.mock_repo)
        
        test_file_path = _create_test_file(
            repo=self.mock_repo,
            module_name='orders',
            class_name='Orders',
            fqtn='public.orders',
            tests_dir=tests_dir
        )
        
        # Read and verify test file content
        with open(test_file_path, 'r') as f:
            content = f.read()
        
        # Check essential components
        self.assertIn('import pytest', content)
        self.assertIn('from test_db.public.orders import Orders', content)
        self.assertIn('class TestOrders:', content)
        self.assertIn('def test_instantiation(self):', content)
        self.assertIn('def test_fields_access(self):', content)
        self.assertIn('Auto-generated tests for test_db.public.orders', content)
        self.assertIn('These tests are regenerated', content)
        self.assertIn('Place custom tests outside the test_db/', content)

    def test_create_test_file_multiple_schemas(self):
        """Test creating test files for different schemas prevents conflicts"""
        tests_dir = _create_tests_directory(self.mock_repo)
        
        # Create test file for public.users
        public_test = _create_test_file(
            repo=self.mock_repo,
            module_name='users',
            class_name='Users',
            fqtn='public.users',
            tests_dir=tests_dir
        )
        
        # Create test file for billing.users (same table name, different schema)
        billing_test = _create_test_file(
            repo=self.mock_repo,
            module_name='users',
            class_name='Users',
            fqtn='billing.users',
            tests_dir=tests_dir
        )
        
        # Verify both files exist and are in different directories
        self.assertTrue(os.path.exists(public_test))
        self.assertTrue(os.path.exists(billing_test))
        self.assertNotEqual(public_test, billing_test)
        
        # Verify paths are correct
        self.assertIn('public', public_test)
        self.assertIn('billing', billing_test)

    def test_create_test_file_no_overwrite(self):
        """Test that existing test files are not overwritten"""
        tests_dir = _create_tests_directory(self.mock_repo)
        
        # Create initial test file
        test_file_path = _create_test_file(
            repo=self.mock_repo,
            module_name='products',
            class_name='Products',
            fqtn='public.products',
            tests_dir=tests_dir
        )
        
        # Modify the file
        custom_content = "# Custom test content"
        with open(test_file_path, 'w') as f:
            f.write(custom_content)
        
        # Try to create the same test file again
        test_file_path2 = _create_test_file(
            repo=self.mock_repo,
            module_name='products',
            class_name='Products',
            fqtn='public.products',
            tests_dir=tests_dir
        )
        
        # Verify file was not overwritten
        self.assertEqual(test_file_path, test_file_path2)
        with open(test_file_path, 'r') as f:
            content = f.read()
        self.assertEqual(content, custom_content)

    def test_create_pytest_config(self):
        """Test creation of pytest configuration file"""
        _create_pytest_config(self.mock_repo)
        
        # Verify pytest.ini was created
        pytest_ini_path = os.path.join(self.test_dir, 'pytest.ini')
        self.assertTrue(os.path.exists(pytest_ini_path))
        
        # Verify pytest.ini content
        with open(pytest_ini_path, 'r') as f:
            content = f.read()
        
        self.assertIn('[tool:pytest]', content)
        self.assertIn('testpaths = tests', content)
        self.assertIn('python_files = test_*.py', content)
        self.assertIn('python_classes = Test*', content)
        self.assertIn('python_functions = test_*', content)
        self.assertIn(f'tests/{self.mock_repo.name}/', content)

    def test_create_pytest_config_no_overwrite(self):
        """Test that existing pytest.ini is not overwritten"""
        pytest_ini_path = os.path.join(self.test_dir, 'pytest.ini')
        
        # Create custom pytest.ini
        custom_content = "[tool:pytest]\n# Custom configuration"
        with open(pytest_ini_path, 'w') as f:
            f.write(custom_content)
        
        # Try to create pytest config
        _create_pytest_config(self.mock_repo)
        
        # Verify file was not overwritten
        with open(pytest_ini_path, 'r') as f:
            content = f.read()
        self.assertEqual(content, custom_content)

    def test_count_test_files_recursive(self):
        """Test recursive counting of test files"""
        tests_dir = _create_tests_directory(self.mock_repo)
        
        # Create multiple test files in different directories
        _create_test_file(self.mock_repo, 'users', 'Users', 'public.users', tests_dir)
        _create_test_file(self.mock_repo, 'orders', 'Orders', 'public.orders', tests_dir)
        _create_test_file(self.mock_repo, 'invoices', 'Invoices', 'billing.invoices', tests_dir)
        
        # Create a custom test file in tests/ root
        custom_test_path = os.path.join(tests_dir, 'test_custom.py')
        with open(custom_test_path, 'w') as f:
            f.write('# Custom test')
        
        # Count test files
        count = _count_test_files_recursive(tests_dir)
        
        # Should count all test files: 3 auto-generated + 1 custom = 4
        self.assertEqual(count, 4)

    def test_count_test_files_empty_directory(self):
        """Test counting test files in empty directory"""
        tests_dir = _create_tests_directory(self.mock_repo)
        
        # Count should be 0 for empty tests directory
        count = _count_test_files_recursive(tests_dir)
        self.assertEqual(count, 0)

    def test_init_file_content_database_level(self):
        """Test content of database-level __init__.py file"""
        tests_dir = _create_tests_directory(self.mock_repo)
        
        _create_test_file(
            repo=self.mock_repo,
            module_name='users',
            class_name='Users',
            fqtn='public.users',
            tests_dir=tests_dir
        )
        
        # Check database __init__.py content
        db_init_path = os.path.join(tests_dir, 'test_db', '__init__.py')
        with open(db_init_path, 'r') as f:
            content = f.read()
        
        self.assertIn('Auto-generated tests for test_db database', content)

    def test_init_file_content_schema_level(self):
        """Test content of schema-level __init__.py file"""
        tests_dir = _create_tests_directory(self.mock_repo)
        
        _create_test_file(
            repo=self.mock_repo,
            module_name='products',
            class_name='Products',
            fqtn='inventory.products',
            tests_dir=tests_dir
        )
        
        # Check schema __init__.py content
        schema_init_path = os.path.join(tests_dir, 'test_db', 'inventory', '__init__.py')
        with open(schema_init_path, 'r') as f:
            content = f.read()
        
        self.assertIn('Auto-generated tests for test_db.inventory schema', content)

    def test_file_permissions(self):
        """Test that created files have appropriate permissions"""
        tests_dir = _create_tests_directory(self.mock_repo)
        
        test_file_path = _create_test_file(
            repo=self.mock_repo,
            module_name='categories',
            class_name='Categories',
            fqtn='public.categories',
            tests_dir=tests_dir
        )
        
        # Verify file is readable and writable
        self.assertTrue(os.access(test_file_path, os.R_OK))
        self.assertTrue(os.access(test_file_path, os.W_OK))

    @patch('half_orm_dev.modules.print')
    def test_logging_output(self, mock_print):
        """Test that appropriate logging messages are generated"""
        tests_dir = _create_tests_directory(self.mock_repo)
        
        _create_test_file(
            repo=self.mock_repo,
            module_name='logs',
            class_name='Logs',
            fqtn='public.logs',
            tests_dir=tests_dir
        )
        
        # Verify print statements were called for directory and file creation
        mock_print.assert_any_call(f"✅ Created tests directory: {tests_dir}")
        mock_print.assert_any_call("✅ Created tests/__init__.py")


class TestModulesIntegration(unittest.TestCase):
    """Integration tests for modules.py functionality"""

    def setUp(self):
        """Set up integration test environment"""
        self.test_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.test_dir)
        
        # Create more complete mock repository
        self.mock_repo = Mock()
        self.mock_repo.name = 'integration_test_db'
        self.mock_repo.base_dir = self.test_dir
        self.mock_repo.devel = True
        
        # Mock database and model
        self.mock_repo.database = Mock()
        self.mock_repo.database.model = Mock()

    def test_complete_test_structure_workflow(self):
        """Test the complete workflow of test structure creation"""
        # Simulate multiple tables across different schemas
        test_scenarios = [
            ('users', 'Users', 'public.users'),
            ('orders', 'Orders', 'public.orders'),
            ('products', 'Products', 'catalog.products'),
            ('categories', 'Categories', 'catalog.categories'),
            ('invoices', 'Invoices', 'billing.invoices'),
        ]
        
        tests_dir = _create_tests_directory(self.mock_repo)
        
        # Create test files for all scenarios
        created_files = []
        for module_name, class_name, fqtn in test_scenarios:
            test_file = _create_test_file(
                repo=self.mock_repo,
                module_name=module_name,
                class_name=class_name,
                fqtn=fqtn,
                tests_dir=tests_dir
            )
            created_files.append(test_file)
        
        # Create pytest configuration
        _create_pytest_config(self.mock_repo)
        
        # Verify complete structure
        expected_structure = {
            'tests/__init__.py',
            'tests/integration_test_db/__init__.py',
            'tests/integration_test_db/public/__init__.py',
            'tests/integration_test_db/public/test_users.py',
            'tests/integration_test_db/public/test_orders.py',
            'tests/integration_test_db/catalog/__init__.py',
            'tests/integration_test_db/catalog/test_products.py',
            'tests/integration_test_db/catalog/test_categories.py',
            'tests/integration_test_db/billing/__init__.py',
            'tests/integration_test_db/billing/test_invoices.py',
            'pytest.ini',
        }
        
        # Check all expected files exist
        for expected_file in expected_structure:
            full_path = os.path.join(self.test_dir, expected_file)
            self.assertTrue(os.path.exists(full_path), f"Missing file: {expected_file}")
        
        # Verify test file count
        test_count = _count_test_files_recursive(tests_dir)
        self.assertEqual(test_count, 5)  # 5 test files created

    def test_mixed_custom_and_generated_tests(self):
        """Test mixing custom tests with auto-generated tests"""
        tests_dir = _create_tests_directory(self.mock_repo)
        
        # Create auto-generated test
        _create_test_file(
            repo=self.mock_repo,
            module_name='users',
            class_name='Users',
            fqtn='public.users',
            tests_dir=tests_dir
        )
        
        # Create custom test files
        custom_tests = [
            'test_integration.py',
            'test_api.py',
            'test_performance.py',
        ]
        
        for custom_test in custom_tests:
            custom_path = os.path.join(tests_dir, custom_test)
            with open(custom_path, 'w') as f:
                f.write(f'"""Custom test: {custom_test}"""\n')
        
        # Create custom subdirectory with tests
        custom_dir = os.path.join(tests_dir, 'custom')
        os.makedirs(custom_dir)
        custom_subtest_path = os.path.join(custom_dir, 'test_custom_feature.py')
        with open(custom_subtest_path, 'w') as f:
            f.write('"""Custom feature test"""\n')
        
        # Count all test files
        total_count = _count_test_files_recursive(tests_dir)
        self.assertEqual(total_count, 5)  # 1 auto-generated + 4 custom
        
        # Verify structure allows both types
        auto_generated_path = os.path.join(tests_dir, 'integration_test_db', 'public', 'test_users.py')
        custom_path = os.path.join(tests_dir, 'test_integration.py')
        
        self.assertTrue(os.path.exists(auto_generated_path))
        self.assertTrue(os.path.exists(custom_path))


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
