"""
Tests pour les méthodes utilitaires de la classe HGit.

Module de test focalisé uniquement sur TestHGitUtilities :
- Tests des méthodes utilitaires conservées (repos_is_clean, last_commit, branch)
- Tests des propriétés (current_release, is_hop_patch_branch)
- Tests d'intégration Git basiques avec nouvelle architecture ho-prod/ho-patch
"""

import pytest
import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import git
from git.exc import GitCommandError

from half_orm_dev.hgit import HGit


class TestHGitUtilities:
    """Test active utility methods that are still functional."""

    @pytest.fixture
    def temp_git_repo(self):
        """Create a temporary git repository for testing."""
        temp_dir = tempfile.mkdtemp()

        try:
            # Initialize git repo
            git.Repo.init(temp_dir)
            repo = git.Repo(temp_dir)

            # Create initial commit
            test_file = Path(temp_dir) / "test.txt"
            test_file.write_text("Initial content")
            repo.git.add("test.txt")
            repo.git.commit("-m", "Initial commit")

            # Create ho-prod branch (nouvelle architecture)
            repo.git.checkout("-b", "ho-prod")

            yield temp_dir, repo

        finally:
            # Cleanup
            shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def hgit_with_real_repo(self, temp_git_repo):
        """Create HGit instance with real git repository."""
        temp_dir, git_repo = temp_git_repo

        mock_repo = Mock()
        mock_repo.git_origin = ""
        mock_repo.base_dir = temp_dir

        # Patch __post_init to avoid complex initialization
        with patch.object(HGit, '_HGit__post_init'):
            hgit = HGit(mock_repo)
            # Manually set git repo
            hgit._HGit__git_repo = git_repo

        return hgit, git_repo

    @pytest.fixture
    def hgit_mock_only(self):
        """Create HGit instance with only mock git repository."""
        mock_git_repo = Mock()
        hgit = HGit()
        hgit._HGit__git_repo = mock_git_repo
        return hgit, mock_git_repo

    def test_branch_property(self, hgit_with_real_repo):
        """Test branch property returns current branch."""
        hgit, git_repo = hgit_with_real_repo

        branch_name = hgit.branch

        # Should return string representation of active branch
        assert isinstance(branch_name, str)
        assert branch_name == str(git_repo.active_branch)

    def test_branch_property_with_different_branches(self, hgit_with_real_repo):
        """Test branch property with different branch names."""
        hgit, git_repo = hgit_with_real_repo

        # Test avec la branche ho-prod existante (déjà créée dans fixture)
        current_branch = str(git_repo.active_branch)  # Should be ho-prod
        result = hgit.branch
        assert result == current_branch

        # Test with nouvelles branches patch
        test_branches = ["ho-patch/456-user-auth", "ho-patch/789-security-fix"]

        for branch_name in test_branches:
            git_repo.git.checkout("-b", branch_name)

            result = hgit.branch
            assert result == branch_name

    def test_current_release_property_ho_prefix_removal(self, hgit_with_real_repo):
        """Test current_release property removes 'hop_' prefix (legacy compatibility)."""
        hgit, git_repo = hgit_with_real_repo

        # Test with legacy hop_main branch (if it exists)
        git_repo.git.checkout("-b", "hop_main")

        current_release = hgit.current_release

        # Should remove 'hop_' prefix for legacy compatibility
        assert current_release == "main"

    def test_current_release_property_no_prefix_new_architecture(self, hgit_with_real_repo):
        """Test current_release property with new architecture (no hop_ prefix)."""
        hgit, git_repo = hgit_with_real_repo

        # Test with branche ho-prod existante
        current_branch = str(git_repo.active_branch)  # Should be ho-prod
        current_release = hgit.current_release
        # Should return branch name as-is (no hop_ prefix to remove)
        assert current_release == current_branch

        # Test with nouvelle branche patch
        patch_branch = "ho-patch/456-user-auth"
        git_repo.git.checkout("-b", patch_branch)

        current_release = hgit.current_release
        # Should return branch name as-is (no hop_ prefix to remove)
        assert current_release == patch_branch

    def test_is_hop_patch_branch_legacy_valid_version(self, hgit_with_real_repo):
        """Test is_hop_patch_branch with legacy valid version format."""
        hgit, git_repo = hgit_with_real_repo

        # Test legacy hop_X.Y.Z format (should still work for compatibility)
        valid_versions = ["hop_1.2.3", "hop_0.0.1", "hop_10.20.30"]

        for version_branch in valid_versions:
            git_repo.git.checkout("-b", version_branch)

            result = hgit.is_hop_patch_branch
            assert result is True, f"Failed for legacy branch: {version_branch}"

    def test_is_hop_patch_branch_new_architecture_invalid(self, hgit_with_real_repo):
        """Test is_hop_patch_branch with new architecture (should be False)."""
        hgit, git_repo = hgit_with_real_repo

        # Test avec branche ho-prod existante
        current_branch = str(git_repo.active_branch)  # Should be ho-prod
        result = hgit.is_hop_patch_branch
        assert result is False, f"New architecture branch {current_branch} should not be hop patch"

        # Test avec nouvelles branches patch
        new_arch_branches = ["ho-patch/456-user-auth", "ho-patch/789-security-fix"]

        for branch_name in new_arch_branches:
            git_repo.git.checkout("-b", branch_name)

            result = hgit.is_hop_patch_branch
            assert result is False, f"New architecture branch {branch_name} should not be hop patch"

    def test_is_hop_patch_branch_invalid_format(self, hgit_with_real_repo):
        """Test is_hop_patch_branch with invalid version format."""
        hgit, git_repo = hgit_with_real_repo

        # Test avec branche courante (ho-prod)
        current_branch = str(git_repo.active_branch)
        result = hgit.is_hop_patch_branch
        assert result is False, f"Should be False for branch: {current_branch}"

        # Test avec nouvelles branches invalides (éviter main qui peut déjà exister)
        invalid_branches = ["feature", "hop_main", "hop_1.2", "hop_1.2.3.4"]

        for branch_name in invalid_branches:
            git_repo.git.checkout("-b", branch_name)

            result = hgit.is_hop_patch_branch
            assert result is False, f"Should be False for branch: {branch_name}"

    def test_repos_is_clean_with_clean_repo(self, hgit_with_real_repo):
        """Test repos_is_clean with clean repository."""
        hgit, git_repo = hgit_with_real_repo

        result = hgit.repos_is_clean()

        # Clean repo should return True
        assert result is True

    def test_repos_is_clean_with_dirty_repo(self, hgit_with_real_repo):
        """Test repos_is_clean with dirty repository."""
        hgit, git_repo = hgit_with_real_repo
        temp_dir = git_repo.working_dir

        # Make repo dirty by modifying file
        test_file = Path(temp_dir) / "test.txt"
        test_file.write_text("Modified content")

        result = hgit.repos_is_clean()

        # Dirty repo should return False
        assert result is False

    def test_repos_is_clean_with_untracked_files(self, hgit_with_real_repo):
        """Test repos_is_clean with untracked files."""
        hgit, git_repo = hgit_with_real_repo
        temp_dir = git_repo.working_dir

        # Add untracked file
        untracked_file = Path(temp_dir) / "untracked.txt"
        untracked_file.write_text("Untracked content")

        result = hgit.repos_is_clean()

        # Repo with untracked files should return False (untracked_files=True)
        assert result is False

    def test_repos_is_clean_with_staged_changes(self, hgit_with_real_repo):
        """Test repos_is_clean with staged changes."""
        hgit, git_repo = hgit_with_real_repo
        temp_dir = git_repo.working_dir

        # Add new file and stage it
        new_file = Path(temp_dir) / "staged.txt"
        new_file.write_text("Staged content")
        git_repo.git.add("staged.txt")

        result = hgit.repos_is_clean()

        # Repo with staged changes should return False
        assert result is False

    def test_last_commit(self, hgit_with_real_repo):
        """Test last_commit returns commit hash."""
        hgit, git_repo = hgit_with_real_repo

        result = hgit.last_commit()

        # Should return 8-character commit hash
        assert isinstance(result, str)
        assert len(result) == 8

        # Should match the actual last commit
        actual_commit = git_repo.head.commit.hexsha[:8]
        assert result == actual_commit

    def test_last_commit_with_multiple_commits(self, hgit_with_real_repo):
        """Test last_commit returns latest commit after multiple commits."""
        hgit, git_repo = hgit_with_real_repo
        temp_dir = git_repo.working_dir

        # Create additional commits
        for i in range(3):
            test_file = Path(temp_dir) / f"file_{i}.txt"
            test_file.write_text(f"Content {i}")
            git_repo.git.add(f"file_{i}.txt")
            git_repo.git.commit("-m", f"Commit {i}")

        result = hgit.last_commit()

        # Should return the latest commit (last one created)
        latest_commit = git_repo.head.commit.hexsha[:8]
        assert result == latest_commit

    def test_last_commit_assertion_validation(self, hgit_with_real_repo):
        """Test last_commit internal assertion validation."""
        hgit, git_repo = hgit_with_real_repo

        # This test ensures the assertion in last_commit() works correctly
        result = hgit.last_commit()

        # The method should complete without assertion error
        assert result is not None
        assert len(result) == 8

        # Verify the assertion condition manually
        iter_commit = str(list(git_repo.iter_commits(hgit.branch, max_count=1))[0])[:8]
        head_commit = git_repo.head.commit.hexsha[:8]
        assert iter_commit == head_commit
        assert result == head_commit

    def test_branch_exists_method(self, hgit_with_real_repo):
        """Test branch_exists method."""
        hgit, git_repo = hgit_with_real_repo

        # Test existing branch
        current_branch = str(git_repo.active_branch)
        assert hgit.branch_exists(current_branch) is True

        # Create new branch and test
        git_repo.git.checkout("-b", "test_branch")
        assert hgit.branch_exists("test_branch") is True

        # Test non-existent branch
        assert hgit.branch_exists("nonexistent_branch") is False

    def test_git_proxy_methods_add(self, hgit_mock_only):
        """Test git proxy method: add."""
        hgit, mock_git_repo = hgit_mock_only

        # Test add method proxy
        hgit.add("file1.txt", "file2.txt")

        # Should call git.add with same arguments
        mock_git_repo.git.add.assert_called_once_with("file1.txt", "file2.txt")

    def test_git_proxy_methods_commit(self, hgit_mock_only):
        """Test git proxy method: commit."""
        hgit, mock_git_repo = hgit_mock_only

        # Test commit method proxy
        hgit.commit("-m", "Test commit")

        # Should call git.commit with same arguments
        mock_git_repo.git.commit.assert_called_once_with("-m", "Test commit")

    def test_git_proxy_methods_rebase(self, hgit_mock_only):
        """Test git proxy method: rebase."""
        hgit, mock_git_repo = hgit_mock_only

        # Test rebase method proxy
        hgit.rebase("ho-prod")

        # Should call git.rebase with same arguments
        mock_git_repo.git.rebase.assert_called_once_with("ho-prod")

    def test_checkout_to_hop_main_legacy_compatibility(self, hgit_mock_only):
        """Test checkout_to_hop_main method (legacy compatibility)."""
        hgit, mock_git_repo = hgit_mock_only

        hgit.checkout_to_hop_main()

        # Should still call git.checkout with hop_main for legacy compatibility
        mock_git_repo.git.checkout.assert_called_once_with('hop_main')

    def test_git_proxy_methods_with_kwargs(self, hgit_mock_only):
        """Test git proxy methods support kwargs."""
        hgit, mock_git_repo = hgit_mock_only

        # Test with keyword arguments
        hgit.add("file.txt", force=True)
        mock_git_repo.git.add.assert_called_once_with("file.txt", force=True)

        hgit.commit("-m", "message", amend=True)
        mock_git_repo.git.commit.assert_called_once_with("-m", "message", amend=True)

    def test_utility_methods_error_handling(self, hgit_mock_only):
        """Test utility methods handle git errors gracefully."""
        hgit, mock_git_repo = hgit_mock_only

        # Test repos_is_clean with git error
        mock_git_repo.is_dirty.side_effect = GitCommandError("git error", 1)

        with pytest.raises(GitCommandError):
            hgit.repos_is_clean()

        # Test last_commit with git error
        mock_git_repo.iter_commits.side_effect = GitCommandError("git error", 1)

        with pytest.raises(GitCommandError):
            hgit.last_commit()

    def test_new_architecture_branches_integration(self, hgit_with_real_repo):
        """Test integration with nouvelle architecture branches."""
        hgit, git_repo = hgit_with_real_repo

        # Test nouvelle architecture patch branch
        patch_branch = "ho-patch/456-user-authentication"
        git_repo.git.checkout("-b", patch_branch)

        # Branch property should work correctly
        assert hgit.branch == patch_branch

        # current_release should return branch as-is (no hop_ prefix to remove)
        assert hgit.current_release == patch_branch

        # is_hop_patch_branch should be False (nouvelle architecture)
        assert hgit.is_hop_patch_branch is False

        # Utility methods should work normally
        assert hgit.repos_is_clean() is True
        assert len(hgit.last_commit()) == 8
        assert hgit.branch_exists(patch_branch) is True
