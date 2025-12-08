"""
Tests for PatchManager._validate_patch_before_merge() - Validation before merge.

Focused on testing:
- Temporary branch creation and cleanup
- Merge validation in temp branch
- Patch apply idempotency check
- Error handling when apply modifies files
- Cleanup after validation failures
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call

from half_orm_dev.patch_manager import PatchManager, PatchManagerError


class TestValidatePatchBeforeMerge:
    """Test _validate_patch_before_merge() method."""

    @pytest.fixture(autouse=True)
    def mock_modules_generate(self):
        """Mock modules.generate to avoid filesystem issues in tests."""
        with patch('half_orm_dev.patch_manager.modules.generate'):
            yield

    @pytest.fixture(autouse=True)
    def mock_click_echo(self):
        """Mock click.echo to suppress output in tests."""
        with patch('click.echo'):
            yield

    @pytest.fixture
    def patch_manager_basic(self, tmp_path):
        """Create basic PatchManager with mocked dependencies."""
        mock_repo = Mock()
        mock_repo.base_dir = tmp_path
        mock_repo.model_dir = str(tmp_path / ".hop" / "model")
        mock_repo.model = Mock()

        # Create releases/ directory
        releases_dir = tmp_path / ".hop" / "releases"
        releases_dir.mkdir(parents=True, exist_ok=True)
        mock_repo.releases_dir = str(releases_dir)

        # Create empty TOML patches file
        from half_orm_dev.release_file import ReleaseFile
        release_file = ReleaseFile("0.17.0", releases_dir)
        release_file.create_empty()

        # Create Patches directory
        patches_dir = tmp_path / "Patches"
        patches_dir.mkdir(exist_ok=True)

        # Mock HGit
        mock_hgit = Mock()
        mock_hgit.branch = "ho-release/0.17.0"
        mock_hgit.repos_is_clean.return_value = True
        mock_hgit.branch_exists.return_value = True
        mock_repo.hgit = mock_hgit

        # Mock database
        mock_database = Mock()
        mock_repo.database = mock_database

        patch_mgr = PatchManager(mock_repo)

        # Mock apply_patch_files
        patch_mgr.apply_patch_files = Mock()

        return patch_mgr, mock_hgit, mock_database, tmp_path

    def test_validation_creates_temp_branch(self, patch_manager_basic):
        """Test creates temporary validation branch."""
        patch_mgr, mock_hgit, mock_database, tmp_path = patch_manager_basic

        patch_mgr._validate_patch_before_merge(
            "42-feature",
            "0.17.0",
            "ho-release/0.17.0",
            "ho-patch/42-feature"
        )

        # Verify temp branch was created
        checkout_calls = [call[0] for call in mock_hgit.checkout.call_args_list]
        assert any('ho-validate/42-feature' in str(c) for c in checkout_calls)

    def test_validation_merges_patch_in_temp_branch(self, patch_manager_basic):
        """Test merges patch into temp branch."""
        patch_mgr, mock_hgit, mock_database, tmp_path = patch_manager_basic

        with patch('click.echo'):
            patch_mgr._validate_patch_before_merge(
                "42-feature",
                "0.17.0",
                "ho-release/0.17.0",
                "ho-patch/42-feature"
            )

        # Verify merge was called
        mock_hgit.merge.assert_called()
        merge_call_args = str(mock_hgit.merge.call_args_list)
        assert "ho-patch/42-feature" in merge_call_args

    def test_validation_runs_database_restore(self, patch_manager_basic):
        """Test runs database restore."""
        patch_mgr, mock_hgit, mock_database, tmp_path = patch_manager_basic

        with patch('click.echo'):
            patch_mgr._validate_patch_before_merge(
                "42-feature",
                "0.17.0",
                "ho-release/0.17.0",
                "ho-patch/42-feature"
            )

        # Verify database restore was called
        patch_mgr._repo.restore_database_from_schema.assert_called_once()

    def test_validation_applies_patch_files(self, patch_manager_basic):
        """Test applies patch files."""
        patch_mgr, mock_hgit, mock_database, tmp_path = patch_manager_basic

        # Create patch directory
        patch_dir = tmp_path / "Patches" / "42-feature"
        patch_dir.mkdir(parents=True)

        with patch('click.echo'):
            patch_mgr._validate_patch_before_merge(
                "42-feature",
                "0.17.0",
                "ho-release/0.17.0",
                "ho-patch/42-feature"
            )

        # Verify patch was applied
        patch_mgr.apply_patch_files.assert_called_once_with(
            "42-feature",
            patch_mgr._repo.model
        )

    def test_validation_checks_repo_clean_after_apply(self, patch_manager_basic):
        """Test verifies repository is clean after apply."""
        patch_mgr, mock_hgit, mock_database, tmp_path = patch_manager_basic

        # Create patch directory
        patch_dir = tmp_path / "Patches" / "42-feature"
        patch_dir.mkdir(parents=True)

        with patch('click.echo'):
            patch_mgr._validate_patch_before_merge(
                "42-feature",
                "0.17.0",
                "ho-release/0.17.0",
                "ho-patch/42-feature"
            )

        # Verify repos_is_clean was called after apply
        assert mock_hgit.repos_is_clean.called

    def test_validation_fails_when_apply_modifies_files(self, patch_manager_basic):
        """Test fails when patch apply modifies files."""
        patch_mgr, mock_hgit, mock_database, tmp_path = patch_manager_basic

        # Mock repo not clean after apply
        mock_hgit.repos_is_clean.return_value = False
        mock_hgit.get_modified_files.return_value = ['model/schema.sql', 'mydb/public/user.py']

        # Create patch directory
        patch_dir = tmp_path / "Patches" / "42-feature"
        patch_dir.mkdir(parents=True)

        with patch('click.echo'):
            with pytest.raises(PatchManagerError, match="Patch validation failed: patch apply modified files"):
                patch_mgr._validate_patch_before_merge(
                    "42-feature",
                    "0.17.0",
                    "ho-release/0.17.0",
                    "ho-patch/42-feature"
                )

    def test_validation_cleans_up_temp_branch_on_success(self, patch_manager_basic):
        """Test cleans up temp branch after successful validation."""
        patch_mgr, mock_hgit, mock_database, tmp_path = patch_manager_basic

        with patch('click.echo'):
            patch_mgr._validate_patch_before_merge(
                "42-feature",
                "0.17.0",
                "ho-release/0.17.0",
                "ho-patch/42-feature"
            )

        # Verify temp branch was deleted
        mock_hgit.delete_branch.assert_called()
        delete_call_args = str(mock_hgit.delete_branch.call_args_list)
        assert "ho-validate/42-feature" in delete_call_args

    def test_validation_cleans_up_temp_branch_on_failure(self, patch_manager_basic):
        """Test cleans up temp branch even after validation failure."""
        patch_mgr, mock_hgit, mock_database, tmp_path = patch_manager_basic

        # Mock repo not clean after apply
        mock_hgit.repos_is_clean.return_value = False
        mock_hgit.get_modified_files.return_value = ['model/schema.sql']

        # Create patch directory
        patch_dir = tmp_path / "Patches" / "42-feature"
        patch_dir.mkdir(parents=True)

        with patch('click.echo'):
            with pytest.raises(PatchManagerError):
                patch_mgr._validate_patch_before_merge(
                    "42-feature",
                    "0.17.0",
                    "ho-release/0.17.0",
                    "ho-patch/42-feature"
                )

        # Verify temp branch was deleted even after failure
        mock_hgit.delete_branch.assert_called()

    def test_validation_returns_to_original_branch(self, patch_manager_basic):
        """Test returns to original branch after validation."""
        patch_mgr, mock_hgit, mock_database, tmp_path = patch_manager_basic

        # Set original branch
        mock_hgit.branch = "ho-patch/42-feature"

        with patch('click.echo'):
            patch_mgr._validate_patch_before_merge(
                "42-feature",
                "0.17.0",
                "ho-release/0.17.0",
                "ho-patch/42-feature"
            )

        # Verify returned to original branch
        checkout_calls = [str(c) for c in mock_hgit.checkout.call_args_list]
        # Should checkout to original branch at some point
        assert len(checkout_calls) > 1

    def test_validation_applies_staged_patches_before_current(self, patch_manager_basic):
        """Test applies already staged patches before current patch."""
        patch_mgr, mock_hgit, mock_database, tmp_path = patch_manager_basic

        # Create TOML patches file with existing patches
        from half_orm_dev.release_file import ReleaseFile
        releases_dir = tmp_path / ".hop" / "releases"
        release_file = ReleaseFile("0.17.0", releases_dir)
        release_file.create_empty()
        release_file.add_patch("38-auth")
        release_file.move_to_staged("38-auth")
        release_file.add_patch("39-api")
        release_file.move_to_staged("39-api")

        # Create patch directories
        for pid in ["38-auth", "39-api", "42-feature"]:
            patch_dir = tmp_path / "Patches" / pid
            patch_dir.mkdir(parents=True)

        with patch('click.echo'):
            patch_mgr._validate_patch_before_merge(
                "42-feature",
                "0.17.0",
                "ho-release/0.17.0",
                "ho-patch/42-feature"
            )

        # Verify all patches were applied in order
        apply_calls = patch_mgr.apply_patch_files.call_args_list
        assert len(apply_calls) == 3
        assert apply_calls[0][0][0] == "38-auth"
        assert apply_calls[1][0][0] == "39-api"
        assert apply_calls[2][0][0] == "42-feature"

    def test_validation_ignores_comments_in_stage_file(self, patch_manager_basic):
        """Test handles patches in TOML file correctly."""
        patch_mgr, mock_hgit, mock_database, tmp_path = patch_manager_basic

        # Create TOML patches file with patches (TOML doesn't have inline comments like TXT)
        from half_orm_dev.release_file import ReleaseFile
        releases_dir = tmp_path / ".hop" / "releases"
        release_file = ReleaseFile("0.17.0", releases_dir)
        release_file.create_empty()
        release_file.add_patch("38-auth")
        release_file.move_to_staged("38-auth")
        release_file.add_patch("39-api")
        release_file.move_to_staged("39-api")

        # Create patch directories
        for pid in ["38-auth", "39-api", "42-feature"]:
            patch_dir = tmp_path / "Patches" / pid
            patch_dir.mkdir(parents=True)

        with patch('click.echo'):
            patch_mgr._validate_patch_before_merge(
                "42-feature",
                "0.17.0",
                "ho-release/0.17.0",
                "ho-patch/42-feature"
            )

        # Verify all patches were applied
        apply_calls = patch_mgr.apply_patch_files.call_args_list
        assert len(apply_calls) == 3
        patch_ids = [call[0][0] for call in apply_calls]
        assert "38-auth" in patch_ids
        assert "39-api" in patch_ids
        assert "42-feature" in patch_ids

    def test_validation_handles_merge_conflicts(self, patch_manager_basic):
        """Test handles merge conflicts during validation."""
        patch_mgr, mock_hgit, mock_database, tmp_path = patch_manager_basic

        # Mock merge failure
        mock_hgit.merge.side_effect = Exception("Merge conflict")

        with patch('click.echo'):
            with pytest.raises(PatchManagerError, match="Failed to merge.*during validation"):
                patch_mgr._validate_patch_before_merge(
                    "42-feature",
                    "0.17.0",
                    "ho-release/0.17.0",
                    "ho-patch/42-feature"
                )

        # Verify temp branch cleanup still happened
        mock_hgit.delete_branch.assert_called()

    def test_validation_with_empty_stage_file(self, patch_manager_basic):
        """Test validation with no staged patches."""
        patch_mgr, mock_hgit, mock_database, tmp_path = patch_manager_basic

        # Stage file is empty (created in fixture)

        # Create patch directory for current patch only
        patch_dir = tmp_path / "Patches" / "42-feature"
        patch_dir.mkdir(parents=True)

        with patch('click.echo'):
            patch_mgr._validate_patch_before_merge(
                "42-feature",
                "0.17.0",
                "ho-release/0.17.0",
                "ho-patch/42-feature"
            )

        # Verify only current patch was applied
        apply_calls = patch_mgr.apply_patch_files.call_args_list
        assert len(apply_calls) == 1
        assert apply_calls[0][0][0] == "42-feature"

    def test_validation_error_message_includes_modified_files(self, patch_manager_basic):
        """Test error message includes list of modified files."""
        patch_mgr, mock_hgit, mock_database, tmp_path = patch_manager_basic

        # Mock repo not clean with specific modified files
        mock_hgit.repos_is_clean.return_value = False
        mock_hgit.get_modified_files.return_value = [
            'model/schema.sql',
            'mydb/public/user.py',
            'mydb/public/session.py'
        ]

        # Create patch directory
        patch_dir = tmp_path / "Patches" / "42-feature"
        patch_dir.mkdir(parents=True)

        with patch('click.echo'):
            try:
                patch_mgr._validate_patch_before_merge(
                    "42-feature",
                    "0.17.0",
                    "ho-release/0.17.0",
                    "ho-patch/42-feature"
                )
                assert False, "Should have raised PatchManagerError"
            except PatchManagerError as e:
                error_msg = str(e)
                # Verify all modified files are in error message
                assert "model/schema.sql" in error_msg
                assert "mydb/public/user.py" in error_msg
                assert "mydb/public/session.py" in error_msg
                # Verify helpful guidance is present
                assert "idempotent" in error_msg.lower()
                assert "patch apply" in error_msg.lower()
