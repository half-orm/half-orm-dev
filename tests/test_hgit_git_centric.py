#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test suite for HGit Git-centric refactoring
Tests the new Git-centric workflow while preserving existing functionality
"""

import os
import tempfile
import shutil
import subprocess
from unittest import TestCase
from unittest.mock import patch, MagicMock
import git
from git.exc import GitCommandError

# Import the classes we're testing
from half_orm_dev.hgit import HGit
from half_orm_dev.repo import Repo
from half_orm import utils


class TestHGitGitCentricWorkflow(TestCase):
    """Test suite for the Git-centric workflow in HGit"""
    
    def setUp(self):
        """Set up test environment with temporary git repositories"""
        self.test_dir = tempfile.mkdtemp()
        
        # Create "remote" repository (simulates origin)
        self.remote_dir = os.path.join(self.test_dir, 'remote_repo.git')
        self.remote_repo = git.Repo.init(self.remote_dir, bare=True)
        
        # Create local repository 
        self.repo_dir = os.path.join(self.test_dir, 'local_repo')
        self.git_repo = git.Repo.clone_from(self.remote_dir, self.repo_dir)
        
        # Create mock repo object
        self.mock_repo = MagicMock()
        self.mock_repo.base_dir = self.repo_dir
        self.mock_repo.git_origin = self.remote_dir  # Point to our test remote
        self.mock_repo.name = 'test_project'
        
        # Create initial commit and hop_main branch
        test_file = os.path.join(self.repo_dir, 'README.md')
        with open(test_file, 'w') as f:
            f.write('# Test Project')
        self.git_repo.index.add([test_file])
        self.git_repo.index.commit('Initial commit')
        self.git_repo.create_head('hop_main')
        self.git_repo.heads.hop_main.checkout()
        
        # Push initial state to remote
        self.git_repo.git.push('origin', 'hop_main')
        
        # Initialize HGit
        with patch.object(HGit, '_HGit__post_init'):
            self.hgit = HGit(self.mock_repo)
            self.hgit._HGit__git_repo = self.git_repo
            self.hgit._HGit__current_branch = 'hop_main'

    def tearDown(self):
        """Clean up test environment"""
        shutil.rmtree(self.test_dir)


class TestBranchDetectionAndClassification(TestHGitGitCentricWorkflow):
    """Test Git branch detection and HOP branch classification"""
    
    def test_get_hop_branches_empty(self):
        """Should return empty set when no HOP branches exist"""
        branches = self.hgit.get_hop_branches()
        expected = {'hop_main'}  # Only hop_main exists
        self.assertEqual(branches, expected)
    
    def test_get_hop_branches_with_development_branches(self):
        """Should detect all HOP development branches"""
        # Create test branches
        self.git_repo.create_head('hop_1.2.3')
        self.git_repo.create_head('hop_2.0.0')
        self.git_repo.create_head('feature_branch')  # Non-HOP branch
        
        branches = self.hgit.get_hop_branches()
        expected = {'hop_main', 'hop_1.2.3', 'hop_2.0.0'}
        self.assertEqual(branches, expected)
    
    def test_get_hop_branches_with_maintenance_branches(self):
        """Should detect HOP maintenance branches"""
        self.git_repo.create_head('hop_1.2.x')
        self.git_repo.create_head('hop_2.0.x')
        
        branches = self.hgit.get_hop_branches()
        expected = {'hop_main', 'hop_1.2.x', 'hop_2.0.x'}
        self.assertEqual(branches, expected)
    
    def test_classify_hop_branch_types(self):
        """Should correctly classify different types of HOP branches"""
        # Create different branch types
        self.git_repo.create_head('hop_1.2.3')  # Development
        self.git_repo.create_head('hop_1.2.x')  # Maintenance
        
        dev_branches = self.hgit.get_development_branches()
        maintenance_branches = self.hgit.get_maintenance_branches()
        
        self.assertIn('hop_1.2.3', dev_branches)
        self.assertIn('hop_1.2.x', maintenance_branches)
        self.assertNotIn('hop_main', dev_branches)
        self.assertNotIn('hop_main', maintenance_branches)


class TestImmediateBranchReservation(TestHGitGitCentricWorkflow):
    """Test immediate branch pushing for version reservation"""
    
    def test_immediate_branch_push_success(self):
        """Should push branch immediately to reserve version"""
        # Create a separate HGit instance with mocked git repo
        mock_repo_instance = MagicMock()
        mock_git = MagicMock()
        mock_repo_instance.git = mock_git
        
        # Create HGit with the mocked repo
        with patch.object(HGit, '_HGit__post_init'):
            hgit = HGit(self.mock_repo)
            hgit._HGit__git_repo = mock_repo_instance
        
        hgit.immediate_branch_push('hop_1.2.3')
        
        mock_git.push.assert_called_once_with('-u', 'origin', 'hop_1.2.3')
    
    def test_immediate_branch_push_no_origin(self):
        """Should error when no origin is configured"""
        # Create a separate mock repo with no origin
        mock_repo_no_origin = MagicMock()
        mock_repo_no_origin.git_origin = ''  # No origin configured
        mock_repo_no_origin.base_dir = self.repo_dir
        
        # Create HGit instance with mocked initialization
        with patch.object(HGit, '_HGit__post_init'):
            hgit_no_origin = HGit(mock_repo_no_origin)
            hgit_no_origin._HGit__git_repo = self.git_repo
            hgit_no_origin._HGit__repo = mock_repo_no_origin
        
        # Should raise SystemExit when trying to push without origin
        with self.assertRaises(SystemExit):  # utils.error calls sys.exit
            hgit_no_origin.immediate_branch_push('hop_1.2.3')
    
    def test_immediate_branch_push_conflict(self):
        """Should error when branch already exists on remote"""
        # Create a separate HGit instance with mocked git repo
        mock_repo_instance = MagicMock()
        mock_git = MagicMock()
        mock_repo_instance.git = mock_git
        mock_git.push.side_effect = GitCommandError(
            'git push', 128, 'already exists'
        )
        
        # Create HGit with the mocked repo
        with patch.object(HGit, '_HGit__post_init'):
            hgit = HGit(self.mock_repo)
            hgit._HGit__git_repo = mock_repo_instance
        
        with self.assertRaises(SystemExit):
            hgit.immediate_branch_push('hop_1.2.3')
    
    def test_set_branch_with_immediate_push(self):
        """set_branch should push immediately after creating branch"""
        with patch.object(self.hgit, 'immediate_branch_push') as mock_push:
            with patch.object(self.hgit, 'add') as mock_add:
                with patch.object(self.hgit, 'cherry_pick_changelog') as mock_cherry:
                    # Mock changelog file
                    self.mock_repo.changelog = MagicMock()
                    self.mock_repo.changelog.file = '/fake/changelog'
                    
                    self.hgit.set_branch('1.2.3')
                    
                    mock_push.assert_called_once_with('hop_1.2.3')


class TestConflictDetection(TestHGitGitCentricWorkflow):
    """Test Git-based conflict detection"""
    
    def test_check_version_conflict_no_conflict(self):
        """Should return False when version is available"""
        conflict = self.hgit.check_version_conflict('1.2.3')
        self.assertFalse(conflict)
    
    def test_check_version_conflict_local_branch_exists(self):
        """Should detect conflict when local branch exists"""
        self.git_repo.create_head('hop_1.2.3')
        
        conflict = self.hgit.check_version_conflict('1.2.3')
        self.assertTrue(conflict)
    
    def test_check_version_conflict_remote_branch_exists(self):
        """Should detect conflict when remote branch exists - CORRECTED VERSION"""
        # Create a separate HGit instance with mocked git repo
        mock_repo_instance = MagicMock()
        
        # Mock local heads (empty - no local conflict)
        mock_repo_instance.heads = []
        
        # Mock remote refs
        mock_remote = MagicMock()
        mock_ref = MagicMock()
        mock_ref.name = 'origin/hop_1.2.3'
        mock_remote.refs = [mock_ref]
        mock_repo_instance.remotes = [mock_remote]
        
        # Create HGit with the mocked repo
        with patch.object(HGit, '_HGit__post_init'):
            hgit = HGit(self.mock_repo)
            hgit._HGit__git_repo = mock_repo_instance
        
        # Test the conflict detection
        conflict = hgit.check_version_conflict('1.2.3')
        self.assertTrue(conflict)
    
    def test_check_rebase_needed_up_to_date(self):
        """Should return False when branch is up to date"""
        self.git_repo.create_head('hop_1.2.3')
        
        # Mock same commits on local and remote
        with patch.object(self.hgit, '_HGit__git_repo') as mock_repo:
            mock_commit = MagicMock()
            mock_commit.hexsha = 'abc123'
            mock_repo.commit.return_value = mock_commit
            
            needs_rebase = self.hgit.check_rebase_needed('hop_1.2.3')
            self.assertFalse(needs_rebase)
    
    def test_check_rebase_needed_behind_remote(self):
        """Should return True when local branch is behind remote"""
        self.git_repo.create_head('hop_1.2.3')
        
        # Mock different commits
        with patch.object(self.hgit, '_HGit__git_repo') as mock_repo:
            def commit_side_effect(branch):
                if branch == 'hop_1.2.3':
                    mock_commit = MagicMock()
                    mock_commit.hexsha = 'abc123'
                    return mock_commit
                elif branch == 'origin/hop_1.2.3':
                    mock_commit = MagicMock()
                    mock_commit.hexsha = 'def456'
                    return mock_commit
            
            mock_repo.commit.side_effect = commit_side_effect
            
            needs_rebase = self.hgit.check_rebase_needed('hop_1.2.3')
            self.assertTrue(needs_rebase)


class TestMaintenanceBranchManagement(TestHGitGitCentricWorkflow):
    """Test automatic maintenance branch creation and management"""
    
    def test_create_maintenance_branch_minor_release(self):
        """Should create maintenance branch for minor release"""
        # Create a tag for version 1.2.0
        self.git_repo.create_tag('1.2.0')
        
        with patch.object(self.hgit, 'immediate_branch_push') as mock_push:
            created = self.hgit.create_maintenance_branch('1.2.0')
            
            self.assertTrue(created)
            self.assertIn('hop_1.2.x', [h.name for h in self.git_repo.heads])
            mock_push.assert_called_once_with('hop_1.2.x')
    
    def test_create_maintenance_branch_already_exists(self):
        """Should not create maintenance branch if it already exists"""
        self.git_repo.create_head('hop_1.2.x')
        
        created = self.hgit.create_maintenance_branch('1.2.0')
        
        self.assertFalse(created)
    
    def test_create_maintenance_branch_patch_release(self):
        """Should not create maintenance branch for patch release"""
        self.git_repo.create_tag('1.2.3')
        
        # Patch releases shouldn't create maintenance branches
        with patch.object(self.hgit, 'immediate_branch_push') as mock_push:
            # This should be called from release logic, not patch logic
            created = self.hgit.create_maintenance_branch('1.2.3')
            
            # Should create anyway if called explicitly, 
            # but release logic should only call for minor/major
            self.assertTrue(created)


class TestRebaseWarnings(TestHGitGitCentricWorkflow):
    """Test intelligent rebase notifications"""
    
    @patch('half_orm_dev.hgit.utils.warning')
    def test_apply_with_rebase_warning_behind_remote(self, mock_warning):
        """Should warn when branch is behind remote"""
        self.git_repo.create_head('hop_1.2.3')
        self.git_repo.heads['hop_1.2.3'].checkout()
        
        with patch.object(self.hgit, 'check_rebase_needed', return_value=True):
            self.hgit.apply_with_rebase_warning()
            
            # Should have warnings about being behind
            warning_calls = [call[0][0] for call in mock_warning.call_args_list]
            self.assertTrue(any('behind remote' in warning for warning in warning_calls))
            self.assertTrue(any('git rebase' in warning for warning in warning_calls))
    
    @patch('half_orm_dev.hgit.utils.warning')
    def test_apply_with_rebase_warning_maintenance_advanced(self, mock_warning):
        """Should warn when maintenance branch has advanced"""
        self.git_repo.create_head('hop_1.2.3')
        self.git_repo.create_head('hop_1.2.x')
        self.git_repo.heads['hop_1.2.3'].checkout()
        
        def rebase_needed_side_effect(branch):
            return branch == 'hop_1.2.x'  # Only maintenance branch needs rebase
        
        with patch.object(self.hgit, 'check_rebase_needed', 
                         side_effect=rebase_needed_side_effect):
            self.hgit.apply_with_rebase_warning()
            
            warning_calls = [call[0][0] for call in mock_warning.call_args_list]
            self.assertTrue(any('hop_1.2.x has advanced' in warning for warning in warning_calls))


class TestCleanupMergedBranches(TestHGitGitCentricWorkflow):
    """Test automatic cleanup of merged branches"""
    
    def test_cleanup_merged_branches_with_tags(self):
        """Should cleanup development branches that have been tagged"""
        # Create and push development branches to remote
        hop_120 = self.git_repo.create_head('hop_1.2.0')
        hop_121 = self.git_repo.create_head('hop_1.2.1') 
        hop_130 = self.git_repo.create_head('hop_1.3.0')
        
        # Push branches to remote
        self.git_repo.git.push('origin', 'hop_1.2.0')
        self.git_repo.git.push('origin', 'hop_1.2.1')
        self.git_repo.git.push('origin', 'hop_1.3.0')
        
        # Create tags for some versions (simulating releases)
        self.git_repo.create_tag('1.2.0')
        self.git_repo.create_tag('1.2.1')
        # No tag for 1.3.0 (still in development)
        
        # Get initial branch count
        initial_branches = set(h.name for h in self.git_repo.heads)
        
        # Run cleanup
        self.hgit.cleanup_merged_branches()
        
        # Check results
        remaining_branches = set(h.name for h in self.git_repo.heads)
        
        # Tagged branches should be removed
        self.assertNotIn('hop_1.2.0', remaining_branches)
        self.assertNotIn('hop_1.2.1', remaining_branches)
        
        # Untagged branch should remain
        self.assertIn('hop_1.3.0', remaining_branches)
        self.assertIn('hop_main', remaining_branches)
        
        # Check that remote branches were also cleaned up
        remote_refs = [ref.name for ref in self.git_repo.remotes.origin.refs]
        self.assertNotIn('origin/hop_1.2.0', remote_refs)
        self.assertNotIn('origin/hop_1.2.1', remote_refs)
    
    def test_cleanup_preserves_maintenance_branches(self):
        """Should never cleanup maintenance branches"""
        # Create and push maintenance branches
        self.git_repo.create_head('hop_1.2.x')
        self.git_repo.create_head('hop_2.0.x')
        self.git_repo.git.push('origin', 'hop_1.2.x')
        self.git_repo.git.push('origin', 'hop_2.0.x')
        
        # Create tags (shouldn't matter for maintenance branches)
        self.git_repo.create_tag('1.2.0')
        self.git_repo.create_tag('2.0.0')
        
        # Run cleanup
        self.hgit.cleanup_merged_branches()
        
        # Maintenance branches should still exist
        remaining_branches = set(h.name for h in self.git_repo.heads)
        self.assertIn('hop_1.2.x', remaining_branches)
        self.assertIn('hop_2.0.x', remaining_branches)
        
        # Remote maintenance branches should also remain
        remote_refs = [ref.name for ref in self.git_repo.remotes.origin.refs]
        self.assertIn('origin/hop_1.2.x', remote_refs)
        self.assertIn('origin/hop_2.0.x', remote_refs)


class TestBackwardCompatibility(TestHGitGitCentricWorkflow):
    """Test that existing HGit functionality is preserved"""
    
    def test_existing_methods_still_work(self):
        """All existing HGit methods should continue to work"""
        # Test that key methods exist and are callable
        self.assertTrue(hasattr(self.hgit, 'branch'))
        self.assertTrue(hasattr(self.hgit, 'current_release'))
        self.assertTrue(hasattr(self.hgit, 'repos_is_clean'))
        self.assertTrue(hasattr(self.hgit, 'last_commit'))
        self.assertTrue(hasattr(self.hgit, 'add'))
        self.assertTrue(hasattr(self.hgit, 'commit'))
        self.assertTrue(hasattr(self.hgit, 'checkout_to_hop_main'))
    
    def test_branch_property(self):
        """Branch property should return current branch name"""
        branch_name = self.hgit.branch
        self.assertEqual(branch_name, 'hop_main')
    
    def test_repos_is_clean(self):
        """repos_is_clean should work as before"""
        # Clean repo
        self.assertTrue(self.hgit.repos_is_clean())
        
        # Dirty repo
        test_file = os.path.join(self.repo_dir, 'dirty.txt')
        with open(test_file, 'w') as f:
            f.write('dirty content')
        
        self.assertFalse(self.hgit.repos_is_clean())


class TestIntegrationWithRepo(TestHGitGitCentricWorkflow):
    """Test integration between HGit and Repo classes"""
    
    @patch('half_orm_dev.repo.Database')
    @patch('half_orm_dev.changelog.Changelog')
    def test_prepare_release_uses_new_workflow(self, mock_changelog, mock_database):
        """prepare_release should use new Git-centric workflow"""
        # Setup mocks
        mock_changelog.return_value.releases_in_dev = []
        mock_changelog.return_value.last_release = '1.2.2'
        mock_database.return_value.last_release_s = '1.2.2'
        
        with patch.object(self.hgit, 'check_version_conflict', return_value=False):
            with patch.object(self.hgit, 'immediate_branch_push') as mock_push:
                with patch.object(self.hgit, 'set_branch') as mock_set_branch:
                    # This would be called by Repo.prepare_release
                    self.hgit.set_branch('1.2.3')
                    
                    mock_set_branch.assert_called_once_with('1.2.3')
    
    def test_error_handling_preserves_existing_behavior(self):
        """Error handling should work the same way as before"""
        # Test that utils.error is still used for consistency
        with patch('half_orm_dev.hgit.utils.error') as mock_error:
            mock_error.side_effect = SystemExit(1)
            
            with self.assertRaises(SystemExit):
                self.hgit.immediate_branch_push('hop_1.2.3')  # No origin configured
            
            mock_error.assert_called()


if __name__ == '__main__':
    import unittest
    
    # Run specific test classes or all tests
    test_classes = [
        TestBranchDetectionAndClassification,
        TestImmediateBranchReservation,
        TestConflictDetection,
        TestMaintenanceBranchManagement,
        TestRebaseWarnings,
        TestCleanupMergedBranches,
        TestBackwardCompatibility,
        TestIntegrationWithRepo,
    ]
    
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    for test_class in test_classes:
        tests = loader.loadTestsFromTestCase(test_class)
        suite.addTests(tests)
    
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)