#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Common Setup for HGit Integration Tests
Provides reusable test environment setup for all integration tests

Usage:
    from integration_setup import IntegrationTestBase
    
    class TestMyFeature(IntegrationTestBase):
        def test_something(self):
            # Use self.hgit, self.git_repo, etc.
"""

import os
import tempfile
import shutil
from unittest import TestCase
from unittest.mock import patch, MagicMock
import git

# Import the classes we're testing
from half_orm_dev.hgit import HGit
from half_orm import utils


class IntegrationTestBase(TestCase):
    """Base class for all HGit integration tests"""
    
    def setUp(self):
        """Create a clean test environment for each test"""
        self.test_dir = tempfile.mkdtemp()
        
        # Create remote repo (simulates origin/GitHub)
        self.remote_dir = os.path.join(self.test_dir, 'origin.git')
        self.remote_repo = git.Repo.init(self.remote_dir, bare=True)
        
        # Create local repo
        self.local_dir = os.path.join(self.test_dir, 'local_repo')
        self.git_repo = git.Repo.clone_from(self.remote_dir, self.local_dir)
        
        # Setup basic project structure
        self._setup_project()
        
        # Create HGit instance
        self.mock_repo = self._create_mock_repo()
        self.hgit = self._create_hgit_instance()

    def _setup_project(self):
        """Create realistic project structure following HOP conventions"""
        # Create project files
        files = {
            'README.md': '# Test Project\nIntegration test project for HGit\n',
            'CHANGELOG.md': '# Changelog\n\n## [0.0.1] - 2024-01-01\n- Initial project\n',
            'setup.py': 'from setuptools import setup\nsetup(name="test-project")\n',
            'requirements.txt': 'half_orm>=3.0.0\n',
        }
        
        # Create directories following HOP structure
        os.makedirs(os.path.join(self.local_dir, 'src'), exist_ok=True)
        os.makedirs(os.path.join(self.local_dir, '.hop'), exist_ok=True)
        os.makedirs(os.path.join(self.local_dir, 'Patches'), exist_ok=True)
        
        # Create HOP config
        files['.hop/config'] = '[project]\nname = test_project\n'
        
        # Create empty Patches structure (needed by set_branch)
        patches_readme = os.path.join(self.local_dir, 'Patches', 'README.md')
        with open(patches_readme, 'w') as f:
            f.write('# Patches Directory\nDatabase migration patches are stored here.\n')
        files['Patches/README.md'] = None  # Will be created above
        
        # Write all files
        for file_path, content in files.items():
            if content is not None:  # Skip already created files
                full_path = os.path.join(self.local_dir, file_path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, 'w') as f:
                    f.write(content)
        
        # Initial commit on master/main
        self.git_repo.index.add(['README.md', 'CHANGELOG.md', 'setup.py', 'requirements.txt', '.hop/config', 'Patches/README.md'])
        self.git_repo.index.commit('Initial project setup')
        
        # Create hop_main branch from current commit and switch to it
        hop_main_branch = self.git_repo.create_head('hop_main')
        hop_main_branch.checkout()
        
        # Push hop_main to remote so clones will have content
        self.git_repo.git.push('origin', 'hop_main')
        
        print(f"✅ Project setup complete with initial commit")

    def _create_mock_repo(self):
        """Create mock Repo object with realistic configuration"""
        mock_repo = MagicMock()
        mock_repo.base_dir = self.local_dir
        mock_repo.git_origin = self.remote_dir
        mock_repo.name = 'test_project'
        
        # Mock changelog
        mock_changelog = MagicMock()
        mock_changelog.file = os.path.join(self.local_dir, 'CHANGELOG.md')
        mock_changelog.releases_in_dev = []
        mock_changelog.last_release = '0.0.1'
        mock_repo.changelog = mock_changelog
        
        # Mock database
        mock_database = MagicMock()
        mock_database.last_release_s = '0.0.1'
        mock_repo.database = mock_database
        
        return mock_repo

    def _create_hgit_instance(self):
        """Create HGit instance with real git repo"""
        with patch.object(HGit, '_HGit__post_init'):
            hgit = HGit(self.mock_repo)
            hgit._HGit__git_repo = self.git_repo
            hgit._HGit__repo = self.mock_repo
            hgit._HGit__current_branch = 'hop_main'
            hgit._HGit__origin = self.remote_dir
        return hgit

    def tearDown(self):
        """Clean up test environment"""
        shutil.rmtree(self.test_dir)

    # Utility methods for tests
    
    def create_second_developer(self, name='dev2'):
        """Create a second developer environment for parallel testing"""
        dev_dir = os.path.join(self.test_dir, f'{name}_repo')
        
        # Clone from remote (which now has initial commits)
        try:
            dev_git = git.Repo.clone_from(self.remote_dir, dev_dir)
            print(f"✅ Cloned repository for {name}")
        except Exception as e:
            print(f"❌ Failed to clone for {name}: {e}")
            raise
        
        # Ensure we're on hop_main
        try:
            if 'hop_main' in [h.name for h in dev_git.heads]:
                dev_git.heads.hop_main.checkout()
                print(f"✅ {name} checked out hop_main")
            else:
                # If hop_main doesn't exist locally, fetch it
                dev_git.git.fetch('origin', 'hop_main:hop_main')
                dev_git.heads.hop_main.checkout()
                print(f"✅ {name} fetched and checked out hop_main")
                
            # Verify we have commits
            last_commit = dev_git.head.commit
            print(f"✅ {name} repository ready, HEAD at: {last_commit.hexsha[:8]}")
            
        except Exception as e:
            print(f"❌ {name} setup failed: {e}")
            print(f"   Available heads: {[h.name for h in dev_git.heads] if dev_git.heads else 'None'}")
            raise
        
        # Create mock repo for second dev
        mock_repo2 = MagicMock()
        mock_repo2.base_dir = dev_dir
        mock_repo2.git_origin = self.remote_dir
        mock_repo2.name = 'test_project'
        
        # Mock changelog for second dev
        mock_changelog2 = MagicMock()
        mock_changelog2.file = os.path.join(dev_dir, 'CHANGELOG.md')
        mock_changelog2.releases_in_dev = []
        mock_changelog2.last_release = '0.0.1'
        mock_repo2.changelog = mock_changelog2
        
        # Create HGit instance for second dev
        with patch.object(HGit, '_HGit__post_init'):
            hgit2 = HGit(mock_repo2)
            hgit2._HGit__git_repo = dev_git
            hgit2._HGit__repo = mock_repo2
            hgit2._HGit__current_branch = 'hop_main'
            hgit2._HGit__origin = self.remote_dir
        
        return dev_git, hgit2

    def add_file_and_commit(self, filename, content, commit_msg=None):
        """Utility to add a file and commit (common test operation)"""
        if commit_msg is None:
            commit_msg = f'Add {filename}'
        
        file_path = os.path.join(self.local_dir, filename)
        with open(file_path, 'w') as f:
            f.write(content)
        
        self.git_repo.index.add([filename])
        self.git_repo.index.commit(commit_msg)
        
        return file_path

    def create_and_push_branch(self, version, push=True):
        """
        Utility to create a version branch using the real HOP workflow.
        
        This method creates the proper patch structure and uses set_branch
        to create branches in a realistic way.
        """
        # Create patch directory structure that set_branch expects
        version_parts = version.split('.')
        if len(version_parts) == 3:
            major, minor, patch = version_parts
            patch_dir = os.path.join(self.local_dir, 'Patches', major, minor, patch)
            os.makedirs(patch_dir, exist_ok=True)
            
        # Use the real set_branch method
        self.hgit.set_branch(version, f'Development of version {version}')
        
        if push:
            # The branch is already pushed by set_branch's immediate_branch_push
            print(f"✅ Branch hop_{version} created and pushed")
        
        return version

    def switch_to_main(self):
        """Utility to switch back to hop_main"""
        self.git_repo.heads.hop_main.checkout()
        return self.hgit.branch

    def create_realistic_patch_structure(self, version, message="Patch development"):
        """
        Create a realistic patch structure for a given version.
        
        This mimics what a developer would do after 'hop prepare'.
        """
        version_parts = version.split('.')
        if len(version_parts) != 3:
            raise ValueError(f"Version must be in X.Y.Z format, got: {version}")
        
        major, minor, patch = version_parts
        patch_dir = os.path.join(self.local_dir, 'Patches', major, minor, patch)
        os.makedirs(patch_dir, exist_ok=True)
        
        # Create realistic SQL patch files
        sql_files = [
            ('01_create_table.sql', f'CREATE TABLE example_{version.replace(".", "_")} (id SERIAL PRIMARY KEY, name TEXT);'),
            ('02_add_index.sql', f'CREATE INDEX idx_example_{version.replace(".", "_")}_name ON example_{version.replace(".", "_")} (name);')
        ]
        
        for filename, content in sql_files:
            sql_file = os.path.join(patch_dir, filename)
            with open(sql_file, 'w') as f:
                f.write(content)
        
        print(f"✅ Created realistic patch structure for {version}")
        return patch_dir