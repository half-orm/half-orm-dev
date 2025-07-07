#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Ordered test execution plan for HGit Git-centric refactoring
Tests are organized by implementation dependency levels
"""

import unittest
from test_hgit_git_centric import *


class OrderedTestExecution:
    """Manages test execution in dependency order"""
    
    # Level 1: Basic Git foundations (no dependencies)
    LEVEL_1_TESTS = [
        # Basic branch detection - foundational method
        'TestBranchDetectionAndClassification.test_get_hop_branches_empty',
        'TestBranchDetectionAndClassification.test_get_hop_branches_with_development_branches',
        'TestBranchDetectionAndClassification.test_get_hop_branches_with_maintenance_branches',
        
        # Backward compatibility - ensure existing methods work
        'TestBackwardCompatibility.test_existing_methods_still_work',
        'TestBackwardCompatibility.test_branch_property',
        'TestBackwardCompatibility.test_repos_is_clean',
    ]
    
    # Level 2: Branch classification (depends on get_hop_branches)
    LEVEL_2_TESTS = [
        'TestBranchDetectionAndClassification.test_classify_hop_branch_types',
    ]
    
    # Level 3: Conflict detection (depends on get_hop_branches)
    LEVEL_3_TESTS = [
        'TestConflictDetection.test_check_version_conflict_no_conflict',
        'TestConflictDetection.test_check_version_conflict_local_branch_exists',
        'TestConflictDetection.test_check_version_conflict_remote_branch_exists',
        'TestConflictDetection.test_check_rebase_needed_up_to_date',
        'TestConflictDetection.test_check_rebase_needed_behind_remote',
    ]
    
    # Level 4: Git actions (depends on conflict detection)
    LEVEL_4_TESTS = [
        'TestImmediateBranchReservation.test_immediate_branch_push_success',
        'TestImmediateBranchReservation.test_immediate_branch_push_no_origin',
        'TestImmediateBranchReservation.test_immediate_branch_push_conflict',
        
        'TestRebaseWarnings.test_apply_with_rebase_warning_behind_remote',
        'TestRebaseWarnings.test_apply_with_rebase_warning_maintenance_advanced',
    ]
    
    # Level 5: Advanced business logic (depends on actions)
    LEVEL_5_TESTS = [
        'TestMaintenanceBranchManagement.test_create_maintenance_branch_minor_release',
        'TestMaintenanceBranchManagement.test_create_maintenance_branch_already_exists',
        'TestMaintenanceBranchManagement.test_create_maintenance_branch_patch_release',
        
        'TestCleanupMergedBranches.test_cleanup_merged_branches_with_tags',
        'TestCleanupMergedBranches.test_cleanup_preserves_maintenance_branches',
    ]
    
    # Level 6: Workflow integration (depends on everything)
    LEVEL_6_TESTS = [
        'TestImmediateBranchReservation.test_set_branch_with_immediate_push',
        'TestIntegrationWithRepo.test_prepare_release_uses_new_workflow',
        'TestIntegrationWithRepo.test_error_handling_preserves_existing_behavior',
    ]
    
    @staticmethod
    def run_level(level_number, test_names):
        """Run tests for a specific level"""
        print(f"\n{'='*60}")
        print(f"LEVEL {level_number} TESTS")
        print(f"{'='*60}")
        
        loader = unittest.TestLoader()
        suite = unittest.TestSuite()
        
        for test_name in test_names:
            try:
                # Parse test name: TestClass.test_method
                class_name, method_name = test_name.split('.')
                test_class = globals()[class_name]
                suite.addTest(test_class(method_name))
            except (ValueError, KeyError) as e:
                print(f"Warning: Could not load test {test_name}: {e}")
        
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        
        print(f"\nLevel {level_number} Results:")
        print(f"  Tests run: {result.testsRun}")
        print(f"  Failures: {len(result.failures)}")
        print(f"  Errors: {len(result.errors)}")
        
        if result.failures:
            print("\nFailures:")
            for test, traceback in result.failures:
                print(f"  - {test}: {traceback.split('AssertionError:')[-1].strip()}")
        
        if result.errors:
            print("\nErrors:")
            for test, traceback in result.errors:
                print(f"  - {test}: {traceback.split('AttributeError:')[-1].strip()}")
        
        return len(result.failures) == 0 and len(result.errors) == 0
    
    @classmethod
    def run_all_levels(cls):
        """Run all test levels in order"""
        levels = [
            (1, cls.LEVEL_1_TESTS),
            (2, cls.LEVEL_2_TESTS),
            (3, cls.LEVEL_3_TESTS),
            (4, cls.LEVEL_4_TESTS),
            (5, cls.LEVEL_5_TESTS),
            (6, cls.LEVEL_6_TESTS),
        ]
        
        print("HGit Git-Centric Refactoring - Ordered Test Execution")
        print("=" * 60)
        
        for level_num, tests in levels:
            success = cls.run_level(level_num, tests)
            
            if not success:
                print(f"\n❌ Level {level_num} FAILED - Stopping execution")
                print("💡 Implement the failing methods before proceeding to next level")
                return False
            else:
                print(f"\n✅ Level {level_num} PASSED")
        
        print(f"\n🎉 ALL LEVELS PASSED! Git-centric refactoring complete!")
        return True


# Implementation tracking - what needs to be implemented for each level
IMPLEMENTATION_REQUIREMENTS = {
    1: [
        "get_hop_branches() - Basic branch detection",
        "Ensure existing methods (branch, repos_is_clean) still work"
    ],
    2: [
        "get_development_branches() - Filter development branches",
        "get_maintenance_branches() - Filter maintenance branches"
    ],
    3: [
        "check_version_conflict(version) - Local and remote conflict detection",
        "check_rebase_needed(branch) - Compare local vs remote commits"
    ],
    4: [
        "immediate_branch_push(branch_name) - Push with error handling",
        "apply_with_rebase_warning() - Intelligent rebase notifications"
    ],
    5: [
        "create_maintenance_branch(version) - Auto maintenance branch creation",
        "cleanup_merged_branches() - Clean tagged development branches"
    ],
    6: [
        "Modify set_branch() - Add immediate push after creation",
        "Modify rebase_to_hop_main() - Add maintenance branch creation"
    ]
}


def print_implementation_guide():
    """Print what needs to be implemented for each level"""
    print("\nIMPLEMENTATION GUIDE")
    print("=" * 40)
    
    for level, requirements in IMPLEMENTATION_REQUIREMENTS.items():
        print(f"\nLevel {level}:")
        for req in requirements:
            print(f"  • {req}")


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        # Run specific level
        try:
            level = int(sys.argv[1])
            if level in IMPLEMENTATION_REQUIREMENTS:
                test_levels = {
                    1: OrderedTestExecution.LEVEL_1_TESTS,
                    2: OrderedTestExecution.LEVEL_2_TESTS,
                    3: OrderedTestExecution.LEVEL_3_TESTS,
                    4: OrderedTestExecution.LEVEL_4_TESTS,
                    5: OrderedTestExecution.LEVEL_5_TESTS,
                    6: OrderedTestExecution.LEVEL_6_TESTS,
                }
                OrderedTestExecution.run_level(level, test_levels[level])
            else:
                print(f"Invalid level: {level}. Choose 1-6.")
        except ValueError:
            print("Usage: python test_execution_order.py [level_number]")
    else:
        # Run all levels in order
        print_implementation_guide()
        print("\n" + "="*60)
        OrderedTestExecution.run_all_levels()
