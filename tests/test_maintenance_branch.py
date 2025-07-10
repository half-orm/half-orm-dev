#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test Maintenance Branch Management
Tests creation, lifecycle and long-term support workflows for maintenance branches

Usage:
    pytest test_maintenance_branches.py -v
    pytest test_maintenance_branches.py::test_maintenance_branch_lifecycle -v -s
"""

import os
from unittest.mock import patch
from integration_setup import IntegrationTestBase


class TestMaintenanceBranches(IntegrationTestBase):
    """Test maintenance branch creation and lifecycle management"""
    
    def test_maintenance_branch_lifecycle(self):
        """Test complete maintenance branch lifecycle from creation to patches"""
        print("\n=== Testing Maintenance Branch Lifecycle ===")
        
        # Step 1: Create maintenance branch for major release 2.0.0
        print("Step 1: Creating maintenance branch for 2.0.0...")
        
        # Use actual remote operations since we have proper setup
        created = self.hgit.create_maintenance_branch('2.0.0')
        
        self.assertTrue(created)
        self.assertIn('hop_2.0.x', [h.name for h in self.git_repo.heads])
        
        # Verify branch exists on remote
        self.git_repo.remotes.origin.fetch()
        remote_branches = [ref.name.split('/')[-1] for ref in self.git_repo.remotes.origin.refs]
        self.assertIn('hop_2.0.x', remote_branches)
        
        print("✅ Maintenance branch hop_2.0.x created and pushed")
        
        # Step 2: Switch to maintenance branch and verify state
        print("Step 2: Switching to maintenance branch...")
        
        self.git_repo.heads['hop_2.0.x'].checkout()
        self.assertEqual(str(self.git_repo.active_branch), 'hop_2.0.x')
        
        # Verify maintenance branch classification
        maint_branches = self.hgit.get_maintenance_branches()
        self.assertIn('hop_2.0.x', maint_branches)
        
        print("✅ Successfully on maintenance branch")
        
        # Step 3: Create patch release 2.0.1
        print("Step 3: Creating patch release 2.0.1...")
        
        with patch.object(self.hgit, 'check_version_conflict', return_value=False):
            with patch.object(self.hgit, 'cherry_pick_changelog'):
                self.hgit.set_branch('2.0.1')
        
        self.assertEqual(self.hgit.branch, 'hop_2.0.1')
        print("✅ Patch branch hop_2.0.1 created")
        
        # Step 4: Add critical bug fix
        print("Step 4: Adding critical bug fix...")
        
        self.add_file_and_commit(
            'security_fix.py',
            'def fix_security_vulnerability():\n    """Critical security fix for 2.0.1"""\n    return "vulnerability_patched"\n',
            'SECURITY: Fix critical vulnerability'
        )
        
        # Update changelog for patch
        changelog_path = self.git_repo.working_dir + '/CHANGELOG.md'
        with open(changelog_path, 'a') as f:
            f.write('\n## [2.0.1] - 2024-01-20\n- SECURITY: Fix critical vulnerability\n- Patch release for 2.0.x series\n')
        
        self.git_repo.index.add(['CHANGELOG.md'])
        self.git_repo.index.commit('Update changelog for 2.0.1 security patch')
        
        print("✅ Security fix applied and documented")
        
        # Step 5: Test rebase warnings against maintenance branch
        print("Step 5: Testing rebase warnings against maintenance...")
        
        # Advance maintenance branch (simulate another patch)
        self.git_repo.heads['hop_2.0.x'].checkout()
        self.add_file_and_commit(
            'another_fix.py',
            'def another_maintenance_fix():\n    """Another maintenance fix"""\n    return "fixed"\n',
            'Another maintenance fix directly on 2.0.x'
        )
        
        # Go back to patch branch
        self.git_repo.heads['hop_2.0.1'].checkout()
        
        # Should warn about maintenance branch advancement
        with patch('half_orm_dev.hgit.utils.warning') as mock_warning:
            self.hgit.apply_with_rebase_warning()
            
            warning_calls = [call[0][0] for call in mock_warning.call_args_list]
            maintenance_warning = any('hop_2.0.x has advanced' in warning for warning in warning_calls)
            self.assertTrue(maintenance_warning)
        
        print("✅ Maintenance rebase warnings working correctly")
        
        # Step 6: Create another patch release 2.0.2
        print("Step 6: Creating second patch release 2.0.2...")
        
        self.git_repo.heads['hop_2.0.x'].checkout()
        
        with patch.object(self.hgit, 'check_version_conflict', return_value=False):
            with patch.object(self.hgit, 'cherry_pick_changelog'):
                self.hgit.set_branch('2.0.2')
        
        self.assertEqual(self.hgit.branch, 'hop_2.0.2')
        print("✅ Second patch release hop_2.0.2 created")
        
        # Verify branch structure
        branches = [h.name for h in self.git_repo.heads]
        expected_branches = ['hop_main', 'hop_2.0.x', 'hop_2.0.1', 'hop_2.0.2']
        for branch in expected_branches:
            self.assertIn(branch, branches)
        
        print("✅ Maintenance branch lifecycle complete!")
        print(f"   Branches created: {expected_branches}")

    def test_multiple_maintenance_lines(self):
        """Test managing multiple maintenance lines simultaneously"""
        print("\n=== Testing Multiple Maintenance Lines ===")
        
        # Create maintenance branches for different major.minor versions
        versions = ['3.0.0', '3.1.0', '4.0.0']
        
        print("Creating multiple maintenance lines...")
        for version in versions:
            created = self.hgit.create_maintenance_branch(version)
            self.assertTrue(created)
        
        # Verify all maintenance branches exist
        maint_branches = self.hgit.get_maintenance_branches()
        expected_maint = {'hop_3.0.x', 'hop_3.1.x', 'hop_4.0.x'}
        
        for branch in expected_maint:
            self.assertIn(branch, maint_branches)
        
        print(f"✅ Created maintenance lines: {expected_maint}")
        
        # Test working on patches for different maintenance lines
        print("Creating patches for different maintenance lines...")
        
        # Patch for 3.0.x line
        self.git_repo.heads['hop_3.0.x'].checkout()
        with patch.object(self.hgit, 'check_version_conflict', return_value=False):
            with patch.object(self.hgit, 'cherry_pick_changelog'):
                self.hgit.set_branch('3.0.1')
        
        self.add_file_and_commit('fix_3_0_1.py', '# Fix for 3.0.1\n', 'Fix for 3.0.1')
        
        # Patch for 4.0.x line
        self.git_repo.heads['hop_4.0.x'].checkout()
        with patch.object(self.hgit, 'check_version_conflict', return_value=False):
            with patch.object(self.hgit, 'cherry_pick_changelog'):
                self.hgit.set_branch('4.0.1')
        
        self.add_file_and_commit('fix_4_0_1.py', '# Fix for 4.0.1\n', 'Fix for 4.0.1')
        
        # Verify independent development
        self.git_repo.heads['hop_3.0.1'].checkout()
        files_3_0_1 = os.listdir(self.git_repo.working_dir)
        
        self.git_repo.heads['hop_4.0.1'].checkout() 
        files_4_0_1 = os.listdir(self.git_repo.working_dir)
        
        self.assertIn('fix_3_0_1.py', files_3_0_1)
        self.assertNotIn('fix_4_0_1.py', files_3_0_1)
        
        self.assertIn('fix_4_0_1.py', files_4_0_1)
        
        print("✅ Multiple maintenance lines working independently")

    def test_maintenance_branch_creation_edge_cases(self):
        """Test edge cases in maintenance branch creation"""
        print("\n=== Testing Maintenance Branch Creation Edge Cases ===")
        
        # Test 1: Already exists
        print("Test 1: Attempting to create existing maintenance branch...")
        
        # Create first time
        created1 = self.hgit.create_maintenance_branch('5.0.0')
        self.assertTrue(created1)
        
        # Try to create again
        created2 = self.hgit.create_maintenance_branch('5.0.0')
        self.assertFalse(created2)
        
        print("✅ Duplicate creation prevented")
        
        # Test 2: Invalid version formats
        print("Test 2: Testing invalid version formats...")
        
        invalid_versions = ['', 'invalid', '1', '1.2', '1.2.3.4']
        
        for version in invalid_versions:
            created = self.hgit.create_maintenance_branch(version)
            # Should handle gracefully (return False)
            self.assertFalse(created)
        
        print("✅ Invalid versions handled gracefully")
        
        # Test 3: Patch versions (should still create maintenance branch)
        print("Test 3: Creating maintenance from patch version...")
        
        created = self.hgit.create_maintenance_branch('5.1.3')  # Patch version
        self.assertTrue(created)  # Should create hop_5.1.x
        
        maint_branches = self.hgit.get_maintenance_branches()
        self.assertIn('hop_5.1.x', maint_branches)
        
        print("✅ Maintenance branch created from patch version")

    def test_maintenance_branch_rebase_scenarios(self):
        """Test rebase scenarios specific to maintenance branches"""
        print("\n=== Testing Maintenance Branch Rebase Scenarios ===")
        
        # Setup: Create maintenance branch and patch
        self.hgit.create_maintenance_branch('6.0.0')
        
        self.git_repo.heads['hop_6.0.x'].checkout()
        
        with patch.object(self.hgit, 'check_version_conflict', return_value=False):
            with patch.object(self.hgit, 'cherry_pick_changelog'):
                self.hgit.set_branch('6.0.1')
        
        # Scenario 1: Maintenance branch advances, patch needs rebase
        print("Scenario 1: Maintenance branch advances...")
        
        # Advance maintenance branch
        self.git_repo.heads['hop_6.0.x'].checkout()
        self.add_file_and_commit('maint_advance.py', '# Maintenance advance\n', 'Advance maintenance')
        
        # Check from patch branch perspective
        self.git_repo.heads['hop_6.0.1'].checkout()
        
        with patch('half_orm_dev.hgit.utils.warning') as mock_warning:
            self.hgit.apply_with_rebase_warning()
            
            # Should warn about maintenance advancement
            warnings = [call[0][0] for call in mock_warning.call_args_list]
            maint_warning = any('hop_6.0.x has advanced' in w for w in warnings)
            self.assertTrue(maint_warning)
        
        print("✅ Maintenance advancement warning triggered")
        
        # Scenario 2: Multiple patches on same maintenance line
        print("Scenario 2: Multiple patches on same maintenance...")
        
        # Create second patch
        self.git_repo.heads['hop_6.0.x'].checkout()
        
        with patch.object(self.hgit, 'check_version_conflict', return_value=False):
            with patch.object(self.hgit, 'cherry_pick_changelog'):
                self.hgit.set_branch('6.0.2')
        
        # Both patches should be independent
        branches = self.hgit.get_development_branches()
        self.assertIn('hop_6.0.1', branches)
        self.assertIn('hop_6.0.2', branches)
        
        print("✅ Multiple patches on same maintenance line working")

    def test_maintenance_branch_cleanup_preservation(self):
        """Test that maintenance branches are preserved during cleanup"""
        print("\n=== Testing Maintenance Branch Cleanup Preservation ===")
        
        # Create maintenance branches and development branches
        self.hgit.create_maintenance_branch('7.0.0')
        self.hgit.create_maintenance_branch('7.1.0')
        
        # Create development branches with real push
        dev_versions = ['7.0.1', '7.0.2', '7.1.1']
        for version in dev_versions:
            self.create_and_push_branch(version, push=True)
            self.switch_to_main()
        
        # Create tags for some development branches (simulate releases)
        self.git_repo.create_tag('7.0.1', message='Release 7.0.1')
        self.git_repo.create_tag('7.0.2', message='Release 7.0.2')
        # No tag for 7.1.1 (still in development)
        
        print("Running cleanup with maintenance branches present...")
        
        initial_branches = set(h.name for h in self.git_repo.heads)
        self.hgit.cleanup_merged_branches()
        final_branches = set(h.name for h in self.git_repo.heads)
        
        # Verify maintenance branches preserved
        self.assertIn('hop_7.0.x', final_branches)
        self.assertIn('hop_7.1.x', final_branches)
        
        # Verify tagged development branches removed
        self.assertNotIn('hop_7.0.1', final_branches)
        self.assertNotIn('hop_7.0.2', final_branches)
        
        # Verify untagged development branch preserved
        self.assertIn('hop_7.1.1', final_branches)
        
        print("✅ Maintenance branches preserved during cleanup")
        print(f"   Preserved: hop_7.0.x, hop_7.1.x, hop_7.1.1")
        print(f"   Cleaned: hop_7.0.1, hop_7.0.2")


if __name__ == '__main__':
    import pytest
    import sys
    
    # Run with pytest if called directly
    sys.exit(pytest.main([__file__, '-v', '-s']))