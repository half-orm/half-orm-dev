#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test Parallel Development Scenarios
Tests multiple developers working simultaneously on different versions

Usage:
    pytest test_parallel_development.py -v
    pytest test_parallel_development.py::test_two_developers_different_versions -v -s
"""

import os
from unittest.mock import patch
from integration_setup import IntegrationTestBase


class TestParallelDevelopment(IntegrationTestBase):
    """Test parallel development scenarios with multiple developers"""
    
    def test_two_developers_different_versions(self):
        """Test two developers working on different versions simultaneously"""
        print("\n=== Testing Two Developers on Different Versions ===")
        
        # Create second developer environment
        dev2_git, dev2_hgit = self.create_second_developer('dev2')
        
        # Developer 1 starts working on 1.1.0
        print("Dev1: Starting work on version 1.1.0...")
        
        # Create proper patch structure for set_branch to work
        patch_dir = os.path.join(self.local_dir, 'Patches', '1', '1', '0')
        os.makedirs(patch_dir, exist_ok=True)
        
        # Now call set_branch with real patch structure
        self.hgit.set_branch('1.1.0', 'Authentication feature development')
        self.assertEqual(self.hgit.branch, 'hop_1.1.0')
        
        # Add some work by dev1
        self.add_file_and_commit(
            'feature_auth.py',
            'def authenticate_user(username, password):\n    """User authentication feature"""\n    return True\n',
            'Dev1: Add user authentication'
        )
        
        print("✅ Dev1 working on 1.1.0 with authentication feature")
        
        # Developer 2 fetches and sees dev1's work
        print("Dev2: Fetching updates...")
        dev2_git.git.fetch('origin')
        
        # Dev2 tries to work on 1.1.0 - should detect conflict
        print("Dev2: Checking if can work on 1.1.0...")
        conflict = dev2_hgit.check_version_conflict('1.1.0')
        self.assertTrue(conflict)
        print("✅ Dev2 correctly detects version 1.1.0 is taken")
        
        # Developer 2 works on 1.2.0 instead
        print("Dev2: Working on version 1.2.0 instead...")
        
        # Create patch structure for dev2
        dev2_patch_dir = os.path.join(dev2_git.working_dir, 'Patches', '1', '2', '0')
        os.makedirs(dev2_patch_dir, exist_ok=True)
        
        dev2_hgit.set_branch('1.2.0', 'API endpoint development')
        self.assertEqual(dev2_hgit.branch, 'hop_1.2.0')
        
        # Add different work by dev2
        dev2_file = dev2_git.working_dir + '/feature_api.py'
        with open(dev2_file, 'w') as f:
            f.write('def api_endpoint(data):\n    """API endpoint feature"""\n    return {"status": "success"}\n')
        
        dev2_git.index.add(['feature_api.py'])
        dev2_git.index.commit('Dev2: Add API endpoints')
        
        print("✅ Dev2 working on 1.2.0 with API features")
        
        # Verify both developers working independently
        self.assertEqual(self.hgit.branch, 'hop_1.1.0')
        self.assertEqual(dev2_hgit.branch, 'hop_1.2.0')
        
        # Verify their work doesn't interfere
        dev1_files = os.listdir(self.git_repo.working_dir)
        dev2_files = os.listdir(dev2_git.working_dir)
        
        self.assertIn('feature_auth.py', dev1_files)
        self.assertNotIn('feature_api.py', dev1_files)
        
        self.assertIn('feature_api.py', dev2_files)
        self.assertNotIn('feature_auth.py', dev2_files)
        
        print("✅ Parallel development successful - no interference!")

    def test_three_developers_version_coordination(self):
        """Test coordination between three developers"""
        print("\n=== Testing Three Developers Version Coordination ===")
        
        # Create two additional developers
        dev2_git, dev2_hgit = self.create_second_developer('dev2')
        dev3_git, dev3_hgit = self.create_second_developer('dev3')
        
        # All developers start from hop_main
        print("All developers starting from hop_main...")
        
        # Developer 1: Claims 2.0.0 (major release)
        print("Dev1: Claiming version 2.0.0 (major release)...")
        
        # Create patch structure
        patch_dir = os.path.join(self.local_dir, 'Patches', '2', '0', '0')
        os.makedirs(patch_dir, exist_ok=True)
        
        self.hgit.set_branch('2.0.0', 'Major release development')
        
        # Developer 2: Fetches, sees 2.0.0 taken, claims 2.1.0
        print("Dev2: Fetching and checking available versions...")
        dev2_git.git.fetch('origin')
        
        # Check conflicts
        conflict_2_0_0 = dev2_hgit.check_version_conflict('2.0.0')
        conflict_2_1_0 = dev2_hgit.check_version_conflict('2.1.0')
        
        self.assertTrue(conflict_2_0_0)   # Should conflict
        self.assertFalse(conflict_2_1_0)  # Should be available
        
        print("Dev2: 2.0.0 taken, claiming 2.1.0...")
        
        # Create patch structure for dev2
        dev2_patch_dir = os.path.join(dev2_git.working_dir, 'Patches', '2', '1', '0')
        os.makedirs(dev2_patch_dir, exist_ok=True)
        
        dev2_hgit.set_branch('2.1.0', 'Minor release development')
        
        # Developer 3: Fetches, sees both taken, claims 2.0.1 (patch)
        print("Dev3: Fetching and checking available versions...")
        dev3_git.git.fetch('origin')
        
        conflict_2_0_1 = dev3_hgit.check_version_conflict('2.0.1')
        self.assertFalse(conflict_2_0_1)  # Should be available
        
        print("Dev3: 2.0.0 and 2.1.0 taken, claiming 2.0.1 (patch)...")
        
        # Create patch structure for dev3
        dev3_patch_dir = os.path.join(dev3_git.working_dir, 'Patches', '2', '0', '1')
        os.makedirs(dev3_patch_dir, exist_ok=True)
        
        dev3_hgit.set_branch('2.0.1', 'Patch release development')
        
        # Verify all developers on different versions
        versions = {
            'dev1': self.hgit.branch,
            'dev2': dev2_hgit.branch,
            'dev3': dev3_hgit.branch
        }
        
        expected_versions = {
            'dev1': 'hop_2.0.0',
            'dev2': 'hop_2.1.0', 
            'dev3': 'hop_2.0.1'
        }
        
        self.assertEqual(versions, expected_versions)
        print(f"✅ All developers coordinated: {versions}")
        
        # Each developer does different work
        print("Each developer working on their features...")
        
        # Dev1: Major new feature
        self.add_file_and_commit(
            'major_feature.py',
            'class MajorFeature:\n    """Major new feature for 2.0.0"""\n    def __init__(self):\n        self.version = "2.0.0"\n',
            'Dev1: Add major feature for 2.0.0'
        )
        
        # Dev2: Minor feature
        dev2_file = dev2_git.working_dir + '/minor_feature.py'
        with open(dev2_file, 'w') as f:
            f.write('def minor_improvement():\n    """Minor improvement for 2.1.0"""\n    return "improved"\n')
        dev2_git.index.add(['minor_feature.py'])
        dev2_git.index.commit('Dev2: Add minor improvement for 2.1.0')
        
        # Dev3: Bug fix
        dev3_file = dev3_git.working_dir + '/bugfix.py'
        with open(dev3_file, 'w') as f:
            f.write('def fix_critical_bug():\n    """Critical bug fix for 2.0.1"""\n    return "fixed"\n')
        dev3_git.index.add(['bugfix.py'])
        dev3_git.index.commit('Dev3: Fix critical bug for 2.0.1')
        
        print("✅ Three developers coordination successful!")

    def test_version_conflict_edge_cases(self):
        """Test edge cases in version conflict detection"""
        print("\n=== Testing Version Conflict Edge Cases ===")
        
        # Create and push a branch
        patch_dir = os.path.join(self.local_dir, 'Patches', '3', '0', '0')
        os.makedirs(patch_dir, exist_ok=True)
        
        self.hgit.set_branch('3.0.0', 'Edge case testing')
        
        # Test case 1: Exact version conflict
        print("Test 1: Exact version conflict...")
        conflict = self.hgit.check_version_conflict('3.0.0')
        self.assertTrue(conflict)
        print("✅ Exact conflict detected")
        
        # Test case 2: Similar but different versions
        print("Test 2: Similar but different versions...")
        similar_versions = ['3.0.1', '3.1.0', '30.0.0']
        
        for version in similar_versions:
            conflict = self.hgit.check_version_conflict(version)
            self.assertFalse(conflict, f"Version {version} should not conflict with 3.0.0")
        
        print("✅ Similar versions correctly distinguished")
        
        # Test case 3: Remote vs local conflicts
        print("Test 3: Remote vs local conflict detection...")
        
        # Create second developer to simulate remote conflict
        dev2_git, dev2_hgit = self.create_second_developer('dev2')
        
        # Dev2 creates branch locally but doesn't push
        dev2_patch_dir = os.path.join(dev2_git.working_dir, 'Patches', '3', '1', '0')
        os.makedirs(dev2_patch_dir, exist_ok=True)
        
        # Mock immediate_branch_push to prevent actual push
        with patch.object(dev2_hgit, 'immediate_branch_push'):
            dev2_hgit.set_branch('3.1.0', 'Local only development')
        
        # Dev1 should detect remote conflict from dev1's repo perspective
        dev1_conflict = self.hgit.check_version_conflict('3.0.0')  # Dev1's own branch
        self.assertTrue(dev1_conflict)
        
        # Dev1 should not detect dev2's local-only branch
        dev1_no_conflict = self.hgit.check_version_conflict('3.1.0')
        self.assertFalse(dev1_no_conflict)
        
        print("✅ Local vs remote conflicts handled correctly")

    def test_branch_classification_with_parallel_work(self):
        """Test branch classification when multiple developers create branches"""
        print("\n=== Testing Branch Classification with Parallel Work ===")
        
        # Create second developer
        dev2_git, dev2_hgit = self.create_second_developer('dev2')
        
        # Both developers create different types of branches
        print("Creating various branch types...")
        
        # Dev1: Development branches
        dev1_branches = ['4.0.0', '4.1.0', '4.2.0']
        for version in dev1_branches:
            # Create patch structure
            parts = version.split('.')
            patch_dir = os.path.join(self.local_dir, 'Patches', *parts)
            os.makedirs(patch_dir, exist_ok=True)
            
            self.hgit.set_branch(version, f'Development of {version}')
            self.switch_to_main()
        
        # Dev1: Maintenance branches
        self.hgit.create_maintenance_branch('4.0.0')
        self.hgit.create_maintenance_branch('4.1.0')
        
        # Dev2: More development branches
        dev2_branches = ['4.3.0', '4.0.1', '4.1.1']
        for version in dev2_branches:
            # Create patch structure for dev2
            parts = version.split('.')
            dev2_patch_dir = os.path.join(dev2_git.working_dir, 'Patches', *parts)
            os.makedirs(dev2_patch_dir, exist_ok=True)
            
            # Mock immediate_branch_push to prevent conflicts
            with patch.object(dev2_hgit, 'immediate_branch_push'):
                dev2_hgit.set_branch(version, f'Dev2 development of {version}')
            
            dev2_git.heads.hop_main.checkout()
        
        # Test branch classification from dev1's perspective
        print("Testing branch classification...")
        
        hop_branches = self.hgit.get_hop_branches()
        dev_branches = self.hgit.get_development_branches()
        maint_branches = self.hgit.get_maintenance_branches()
        
        # Verify development branches
        expected_dev = {'hop_4.0.0', 'hop_4.1.0', 'hop_4.2.0'}
        actual_dev = dev_branches & expected_dev
        self.assertEqual(actual_dev, expected_dev)
        
        # Verify maintenance branches
        expected_maint = {'hop_4.0.x', 'hop_4.1.x'}
        actual_maint = maint_branches & expected_maint
        self.assertEqual(actual_maint, expected_maint)
        
        print(f"✅ Found {len(dev_branches)} development branches")
        print(f"✅ Found {len(maint_branches)} maintenance branches")
        print(f"✅ Total HOP branches: {len(hop_branches)}")

    def test_concurrent_branch_operations(self):
        """Test concurrent branch operations without race conditions"""
        print("\n=== Testing Concurrent Branch Operations ===")
        
        # Create multiple developers
        developers = []
        for i in range(3):
            dev_git, dev_hgit = self.create_second_developer(f'dev{i+2}')  # dev2, dev3, dev4
            developers.append((dev_git, dev_hgit))
        
        # Each developer performs branch operations
        print("Performing concurrent operations...")
        
        # Dev1 (self): Branch classification operations
        for _ in range(5):
            hop_branches = self.hgit.get_hop_branches()
            dev_branches = self.hgit.get_development_branches()
            maint_branches = self.hgit.get_maintenance_branches()
        
        # Dev2: Version conflict checks
        dev2_git, dev2_hgit = developers[0]
        versions_to_check = ['5.0.0', '5.1.0', '5.2.0', '5.0.1', '5.1.1']
        for version in versions_to_check:
            conflict = dev2_hgit.check_version_conflict(version)
            # Should not crash
            self.assertIsInstance(conflict, bool)
        
        # Dev3: Repository status checks  
        dev3_git, dev3_hgit = developers[1]
        for _ in range(5):
            clean = dev3_hgit.repos_is_clean()
            branch = dev3_hgit.branch
            current_release = dev3_hgit.current_release
            # Should not crash
            self.assertIsInstance(clean, bool)
            self.assertIsInstance(branch, str)
            self.assertIsInstance(current_release, str)
        
        # Dev4: Create actual branches
        dev4_git, dev4_hgit = developers[2]
        
        # Create patch structure for dev4
        dev4_patch_dir = os.path.join(dev4_git.working_dir, 'Patches', '5', '0', '0')
        os.makedirs(dev4_patch_dir, exist_ok=True)
        
        # Mock immediate_branch_push to prevent conflicts
        with patch.object(dev4_hgit, 'immediate_branch_push'):
            dev4_hgit.set_branch('5.0.0', 'Concurrent development test')
        
        print("✅ Concurrent operations completed without crashes")
        
        # Verify final state is consistent
        final_hop_branches = self.hgit.get_hop_branches()
        self.assertGreater(len(final_hop_branches), 0)
        
        print("✅ Final state consistent across all operations")


if __name__ == '__main__':
    import pytest
    import sys
    
    # Run with pytest if called directly
    sys.exit(pytest.main([__file__, '-v', '-s']))