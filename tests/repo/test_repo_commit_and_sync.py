"""
Tests for Repo.commit_and_sync_to_active_branches() method.

Tests the unified commit + push + sync operation.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from half_orm_dev.repo import Repo


class TestRepoCommitAndSync:
    """Test Repo.commit_and_sync_to_active_branches() method."""

    @pytest.fixture
    def mock_repo(self, tmp_path):
        """Create a mock Repo with necessary structure."""
        # Create .hop directory
        hop_dir = tmp_path / '.hop'
        hop_dir.mkdir()
        (hop_dir / 'config').write_text('[halfORM]\nhop_version = "0.17.0"\n')

        # Mock Repo instance
        repo = Mock(spec=Repo)
        repo.base_dir = str(tmp_path)
        repo._Repo__config = Mock()
        repo._Repo__config.hop_version = "0.17.0"

        # Mock HGit
        repo.hgit = Mock()
        repo.hgit.branch = 'ho-release/0.17.0'
        repo.hgit.add = Mock()
        repo.hgit.commit = Mock(return_value='abc123')
        repo.hgit.push_branch = Mock()

        # Mock sync method
        repo.sync_hop_to_active_branches = Mock(return_value={
            'synced_branches': ['ho-prod', 'ho-patch/123-test'],
            'skipped_branches': [],
            'errors': []
        })

        # Bind the real method to the mock
        repo.commit_and_sync_to_active_branches = Repo.commit_and_sync_to_active_branches.__get__(repo, Repo)

        return repo, tmp_path

    def test_commit_and_sync_basic(self, mock_repo):
        """Test basic commit and sync with .hop/ only."""
        repo, tmp_path = mock_repo

        result = repo.commit_and_sync_to_active_branches(
            message="[HOP] Test commit"
        )

        # Verify .hop/ was added
        repo.hgit.add.assert_called_once_with('.hop/')

        # Verify commit was created
        repo.hgit.commit.assert_called_once_with("-m", "[HOP] Test commit")
        assert result['commit_hash'] == 'abc123'

        # Verify push
        repo.hgit.push_branch.assert_called_once_with('ho-release/0.17.0')
        assert result['pushed_branch'] == 'ho-release/0.17.0'

        # Verify sync was called with extracted reason
        repo.sync_hop_to_active_branches.assert_called_once()
        call_kwargs = repo.sync_hop_to_active_branches.call_args[1]
        assert 'reason' in call_kwargs
        assert call_kwargs['reason'] == 'Test commit'

        # Verify sync result
        assert result['sync_result']['synced_branches'] == ['ho-prod', 'ho-patch/123-test']

    def test_commit_and_sync_with_additional_files(self, mock_repo):
        """Test commit and sync with additional files beyond .hop/."""
        repo, tmp_path = mock_repo

        result = repo.commit_and_sync_to_active_branches(
            message="[HOP] Create release branch",
            files=['Patches/0.17.0-candidates.txt', 'README.md']
        )

        # Verify all files were added (.hop/ + additional files)
        assert repo.hgit.add.call_count == 3
        repo.hgit.add.assert_any_call('.hop/')
        repo.hgit.add.assert_any_call('Patches/0.17.0-candidates.txt')
        repo.hgit.add.assert_any_call('README.md')

        # Verify commit
        repo.hgit.commit.assert_called_once_with("-m", "[HOP] Create release branch")
        assert result['commit_hash'] == 'abc123'

        # Verify sync
        assert result['sync_result'] is not None

    def test_commit_and_sync_with_explicit_reason(self, mock_repo):
        """Test commit and sync with explicit reason parameter."""
        repo, tmp_path = mock_repo

        result = repo.commit_and_sync_to_active_branches(
            message="[HOP] Update configuration for migration 0.17.0 → 0.17.1",
            reason="migration 0.17.0 → 0.17.1"
        )

        # Verify sync was called with explicit reason
        repo.sync_hop_to_active_branches.assert_called_once_with(
            reason="migration 0.17.0 → 0.17.1"
        )

    def test_commit_and_sync_reason_extraction_with_period(self, mock_repo):
        """Test reason extraction from message with period."""
        repo, tmp_path = mock_repo

        result = repo.commit_and_sync_to_active_branches(
            message="[HOP] Create release branch. Additional details here."
        )

        # Verify sync was called with extracted reason (first sentence)
        call_kwargs = repo.sync_hop_to_active_branches.call_args[1]
        assert call_kwargs['reason'] == 'Create release branch'

    def test_commit_and_sync_reason_extraction_long_message(self, mock_repo):
        """Test reason extraction from long message without period."""
        repo, tmp_path = mock_repo

        long_message = "[HOP] " + "A" * 100  # Very long message

        result = repo.commit_and_sync_to_active_branches(
            message=long_message
        )

        # Verify sync was called with truncated reason (50 chars)
        call_kwargs = repo.sync_hop_to_active_branches.call_args[1]
        assert len(call_kwargs['reason']) == 50
        assert call_kwargs['reason'] == "A" * 50

    def test_commit_and_sync_from_patch_branch(self, mock_repo):
        """Test commit and sync from patch branch."""
        repo, tmp_path = mock_repo
        repo.hgit.branch = 'ho-patch/123-test'

        result = repo.commit_and_sync_to_active_branches(
            message="[HOP] Update patch configuration"
        )

        # Verify push on patch branch
        repo.hgit.push_branch.assert_called_once_with('ho-patch/123-test')
        assert result['pushed_branch'] == 'ho-patch/123-test'

    def test_commit_and_sync_from_ho_prod(self, mock_repo):
        """Test commit and sync from ho-prod branch."""
        repo, tmp_path = mock_repo
        repo.hgit.branch = 'ho-prod'

        result = repo.commit_and_sync_to_active_branches(
            message="[HOP] Update production configuration"
        )

        # Verify push on ho-prod
        repo.hgit.push_branch.assert_called_once_with('ho-prod')
        assert result['pushed_branch'] == 'ho-prod'

    def test_commit_and_sync_empty_files_list(self, mock_repo):
        """Test commit and sync with empty files list (should still include .hop/)."""
        repo, tmp_path = mock_repo

        result = repo.commit_and_sync_to_active_branches(
            message="[HOP] Test",
            files=[]
        )

        # Verify only .hop/ was added (empty list doesn't prevent it)
        repo.hgit.add.assert_called_once_with('.hop/')

    def test_commit_and_sync_none_files_list(self, mock_repo):
        """Test commit and sync with None files list (should still include .hop/)."""
        repo, tmp_path = mock_repo

        result = repo.commit_and_sync_to_active_branches(
            message="[HOP] Test",
            files=None
        )

        # Verify only .hop/ was added
        repo.hgit.add.assert_called_once_with('.hop/')

    def test_commit_and_sync_preserves_sync_errors(self, mock_repo):
        """Test that sync errors are preserved in result."""
        repo, tmp_path = mock_repo

        # Mock sync to return errors
        repo.sync_hop_to_active_branches.return_value = {
            'synced_branches': ['ho-prod'],
            'skipped_branches': [],
            'errors': ['Failed to sync to ho-patch/456-test: checkout failed']
        }

        result = repo.commit_and_sync_to_active_branches(
            message="[HOP] Test"
        )

        # Verify errors are in sync_result
        assert len(result['sync_result']['errors']) == 1
        assert 'Failed to sync to ho-patch/456-test' in result['sync_result']['errors'][0]

    def test_commit_and_sync_return_structure(self, mock_repo):
        """Test that return structure is complete and correct."""
        repo, tmp_path = mock_repo

        result = repo.commit_and_sync_to_active_branches(
            message="[HOP] Test commit"
        )

        # Verify return structure
        assert 'commit_hash' in result
        assert 'pushed_branch' in result
        assert 'sync_result' in result

        assert result['commit_hash'] == 'abc123'
        assert result['pushed_branch'] == 'ho-release/0.17.0'
        assert isinstance(result['sync_result'], dict)
        assert 'synced_branches' in result['sync_result']
