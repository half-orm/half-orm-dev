"""
Tests for ReleaseManager hotfix workflow.

Focused on testing:
- reopen_for_hotfix(): Reopening production versions
- promote_to_hotfix(): Promoting hotfix to production
- _determine_hotfix_number(): Calculating next hotfix number
- HOTFIX marker in candidates.txt
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, call

from half_orm_dev.release_manager import ReleaseManager, ReleaseManagerError


class TestReopenForHotfix:
    """Test reopen_for_hotfix() method."""

    @pytest.fixture
    def release_manager_with_tag(self, tmp_path):
        """Create ReleaseManager with mocked Git operations."""
        mock_repo = Mock()
        mock_repo.base_dir = str(tmp_path)
        mock_repo.model_dir = str(tmp_path / ".hop" / "model")

        # Create releases/ directory
        releases_dir = tmp_path / ".hop" / "releases"
        releases_dir.mkdir(parents=True, exist_ok=True)
        mock_repo.releases_dir = str(releases_dir)

        # Create model/schema-1.3.5.sql and symlink
        model_dir = tmp_path / "model"
        model_dir.mkdir(exist_ok=True)
        schema_versioned = model_dir / "schema-1.3.5.sql"
        schema_versioned.write_text("-- VERSION: 1.3.5\n")
        schema_file = model_dir / "schema.sql"
        schema_file.symlink_to("schema-1.3.5.sql")

        # Mock HGit
        mock_hgit = Mock()
        mock_hgit.tag_exists.return_value = True
        mock_hgit.branch_exists.return_value = False
        mock_hgit.list_tags.return_value = ["v1.3.5", "v1.3.4", "v1.3.3"]
        mock_repo.hgit = mock_hgit

        release_mgr = ReleaseManager(mock_repo)

        return release_mgr, releases_dir, mock_hgit

    def test_reopen_current_production_version(self, release_manager_with_tag):
        """Test reopening current production version (no version parameter)."""
        release_mgr, releases_dir, mock_hgit = release_manager_with_tag

        # Call without version parameter
        result = release_mgr.reopen_for_hotfix()

        # Verify correct version detected
        assert result['version'] == "1.3.5"
        assert result['branch'] == "ho-release/1.3.5"

        # Verify Git operations
        mock_hgit.tag_exists.assert_called_once_with("v1.3.5")
        mock_hgit.create_branch_from_tag.assert_called_once_with("ho-release/1.3.5", "v1.3.5")
        mock_hgit.push_branch.assert_called()
        mock_hgit.checkout.assert_called_with("ho-release/1.3.5")
        mock_hgit.commit.assert_called_once()

        # Verify files created
        candidates_file = releases_dir / "1.3.5-candidates.txt"
        stage_file = releases_dir / "1.3.5-stage.txt"

        assert candidates_file.exists()
        assert stage_file.exists()

        # Verify HOTFIX marker in candidates.txt
        candidates_content = candidates_file.read_text()
        assert candidates_content == "# HOTFIX\n"

        # Verify stage.txt is empty
        stage_content = stage_file.read_text()
        assert stage_content == ""

    def test_reopen_specific_version(self, release_manager_with_tag):
        """Test reopening specific version."""
        release_mgr, releases_dir, mock_hgit = release_manager_with_tag

        # Mock tag exists for 1.3.4
        mock_hgit.tag_exists.return_value = True

        result = release_mgr.reopen_for_hotfix()

        # Verify correct version used
        assert result['version'] == "1.3.5"
        assert result['branch'] == "ho-release/1.3.5"

        # Verify tag checked
        mock_hgit.tag_exists.assert_called_with("v1.3.5")

        # Verify files created with HOTFIX marker
        candidates_file = releases_dir / "1.3.5-candidates.txt"
        assert candidates_file.exists()
        assert candidates_file.read_text() == "# HOTFIX\n"

    def test_reopen_tag_does_not_exist(self, release_manager_with_tag):
        """Test error when production tag doesn't exist."""
        release_mgr, _, mock_hgit = release_manager_with_tag

        # Tag doesn't exist
        mock_hgit.tag_exists.return_value = False
        mock_hgit.list_tags.return_value = ["v1.3.4", "v1.3.3"]

        with pytest.raises(ReleaseManagerError, match="Production tag v1.3.5 does not exist"):
            release_mgr.reopen_for_hotfix()

    def test_reopen_deletes_existing_branch(self, release_manager_with_tag):
        """Test deletes existing ho-release/X.Y.Z branch if exists."""
        release_mgr, releases_dir, mock_hgit = release_manager_with_tag

        # Branch already exists
        mock_hgit.branch_exists.return_value = True

        result = release_mgr.reopen_for_hotfix()

        # Verify branch deletion
        mock_hgit.delete_branch.assert_called_once_with("ho-release/1.3.5", force=True)
        mock_hgit.delete_remote_branch.assert_called_once_with("ho-release/1.3.5")

        # Verify new branch created
        mock_hgit.create_branch_from_tag.assert_called_once_with("ho-release/1.3.5", "v1.3.5")

    def test_reopen_commit_message(self, release_manager_with_tag):
        """Test commit message format."""
        release_mgr, _, mock_hgit = release_manager_with_tag

        release_mgr.reopen_for_hotfix()

        # Verify commit message
        mock_hgit.commit.assert_called_once()
        commit_call = mock_hgit.commit.call_args
        assert commit_call[1]['message'] == "[release] Reopen %1.3.5 for hotfix development"

    def test_reopen_return_values(self, release_manager_with_tag):
        """Test return dictionary structure."""
        release_mgr, releases_dir, _ = release_manager_with_tag

        result = release_mgr.reopen_for_hotfix()

        # Verify all return keys present
        assert 'version' in result
        assert 'branch' in result
        assert 'candidates_file' in result
        assert 'stage_file' in result

        # Verify values
        assert result['version'] == "1.3.5"
        assert result['branch'] == "ho-release/1.3.5"
        assert "1.3.5-candidates.txt" in result['candidates_file']
        assert "1.3.5-stage.txt" in result['stage_file']


class TestPromoteToHotfix:
    """Test promote_to_hotfix() method."""

    @pytest.fixture
    def release_manager_hotfix_ready(self, tmp_path):
        """Create ReleaseManager ready for hotfix promotion."""
        mock_repo = Mock()
        mock_repo.base_dir = str(tmp_path)
        mock_repo.model_dir = str(tmp_path / ".hop" / "model")

        # Create releases/ directory
        releases_dir = tmp_path / ".hop" / "releases"
        releases_dir.mkdir(parents=True, exist_ok=True)
        mock_repo.releases_dir = str(releases_dir)

        # Create empty candidates.txt with HOTFIX marker
        candidates_file = releases_dir / "1.3.5-candidates.txt"
        candidates_file.write_text("# HOTFIX\n")

        # Mock HGit
        mock_hgit = Mock()
        mock_hgit.branch = "ho-release/1.3.5"
        mock_hgit.list_tags.return_value = ["v1.3.5", "v1.3.4"]  # No hotfix tags yet
        mock_repo.hgit = mock_hgit

        release_mgr = ReleaseManager(mock_repo)

        # Mock _apply_release_patches
        release_mgr._apply_release_patches = Mock()

        return release_mgr, releases_dir, mock_hgit

    def test_promote_first_hotfix(self, release_manager_hotfix_ready):
        """Test promoting first hotfix for a version."""
        release_mgr, _, mock_hgit = release_manager_hotfix_ready

        result = release_mgr.promote_to_hotfix()

        # Verify hotfix number is 1
        assert result['version'] == "1.3.5"
        assert result['hotfix_tag'] == "v1.3.5-hotfix1"
        assert result['branch'] == "ho-release/1.3.5"

        # Verify Git operations
        mock_hgit.checkout.assert_any_call("ho-prod")
        mock_hgit.merge.assert_called_once_with(
            "ho-release/1.3.5",
            message="[release] Merge hotfix %1.3.5-hotfix1"
        )
        mock_hgit.create_tag.assert_called_once_with(
            "v1.3.5-hotfix1",
            "Hotfix release %1.3.5-hotfix1"
        )
        mock_hgit.push_tag.assert_called_once_with("v1.3.5-hotfix1")
        mock_hgit.push_branch.assert_called_once_with("ho-prod")

        # Verify returned to ho-release branch
        mock_hgit.checkout.assert_called_with("ho-prod")

    def test_promote_second_hotfix(self, release_manager_hotfix_ready):
        """Test promoting second hotfix for same version."""
        release_mgr, _, mock_hgit = release_manager_hotfix_ready

        # First hotfix already exists
        mock_hgit.list_tags.return_value = ["v1.3.5", "v1.3.5-hotfix1"]

        result = release_mgr.promote_to_hotfix()

        # Verify hotfix number is 2
        assert result['hotfix_tag'] == "v1.3.5-hotfix2"

        mock_hgit.create_tag.assert_called_once_with(
            "v1.3.5-hotfix2",
            "Hotfix release %1.3.5-hotfix2"
        )

    def test_promote_error_not_on_release_branch(self, release_manager_hotfix_ready):
        """Test error when not on ho-release/* branch."""
        release_mgr, _, mock_hgit = release_manager_hotfix_ready

        # On wrong branch
        mock_hgit.branch = "main"

        with pytest.raises(ReleaseManagerError, match="Must be on ho-release/"):
            release_mgr.promote_to_hotfix()

    def test_promote_error_candidates_not_empty(self, release_manager_hotfix_ready):
        """Test error when candidates.txt has uncommitted patches."""
        release_mgr, releases_dir, _ = release_manager_hotfix_ready

        # Add patches to candidates.txt
        candidates_file = releases_dir / "1.3.5-candidates.txt"
        candidates_file.write_text("# HOTFIX\npatch-001\npatch-002\n")

        with pytest.raises(ReleaseManagerError, match="Cannot promote hotfix: 2 candidate patch"):
            release_mgr.promote_to_hotfix()

    def test_promote_applies_release_patches(self, release_manager_hotfix_ready):
        """Test calls _apply_release_patches with correct version."""
        release_mgr, _, _ = release_manager_hotfix_ready

        release_mgr.promote_to_hotfix()

        # Verify patches applied
        release_mgr._apply_release_patches.assert_called_once_with("1.3.5", True)


class TestDetermineHotfixNumber:
    """Test _determine_hotfix_number() method."""

    @pytest.fixture
    def release_manager_basic(self, tmp_path):
        """Create basic ReleaseManager."""
        mock_repo = Mock()
        mock_repo.base_dir = str(tmp_path)
        mock_repo.model_dir = str(tmp_path / ".hop" / "model")

        # Create releases/ directory
        releases_dir = tmp_path / ".hop" / "releases"
        releases_dir.mkdir(parents=True, exist_ok=True)
        mock_repo.releases_dir = str(releases_dir)

        # Mock HGit
        mock_hgit = Mock()
        mock_repo.hgit = mock_hgit

        release_mgr = ReleaseManager(mock_repo)

        return release_mgr, mock_hgit

    def test_no_existing_hotfix_returns_one(self, release_manager_basic):
        """Test returns 1 when no hotfix exists for version."""
        release_mgr, mock_hgit = release_manager_basic

        # No hotfix tags
        mock_hgit.list_tags.return_value = ["v1.3.5", "v1.3.4"]

        hotfix_num = release_mgr._determine_hotfix_number("1.3.5")

        assert hotfix_num == 1

    def test_hotfix1_exists_returns_two(self, release_manager_basic):
        """Test returns 2 when hotfix1 exists."""
        release_mgr, mock_hgit = release_manager_basic

        mock_hgit.list_tags.return_value = ["v1.3.5", "v1.3.5-hotfix1"]

        hotfix_num = release_mgr._determine_hotfix_number("1.3.5")

        assert hotfix_num == 2

    def test_multiple_hotfixes_returns_max_plus_one(self, release_manager_basic):
        """Test returns max hotfix number + 1."""
        release_mgr, mock_hgit = release_manager_basic

        mock_hgit.list_tags.return_value = [
            "v1.3.5",
            "v1.3.5-hotfix1",
            "v1.3.5-hotfix2",
            "v1.3.5-hotfix3"
        ]

        hotfix_num = release_mgr._determine_hotfix_number("1.3.5")

        assert hotfix_num == 4

    def test_ignores_different_version_hotfixes(self, release_manager_basic):
        """Test ignores hotfix tags of different versions."""
        release_mgr, mock_hgit = release_manager_basic

        mock_hgit.list_tags.return_value = [
            "v1.3.4-hotfix1",
            "v1.3.4-hotfix2",
            "v1.4.0-hotfix1",
            "v1.3.5"
        ]

        hotfix_num = release_mgr._determine_hotfix_number("1.3.5")

        # Should return 1 (other versions ignored)
        assert hotfix_num == 1

    def test_handles_double_digit_hotfix_numbers(self, release_manager_basic):
        """Test handles hotfix numbers >= 10."""
        release_mgr, mock_hgit = release_manager_basic

        # Create many hotfixes
        tags = ["v1.3.5"] + [f"v1.3.5-hotfix{i}" for i in range(1, 15)]
        mock_hgit.list_tags.return_value = tags

        hotfix_num = release_mgr._determine_hotfix_number("1.3.5")

        assert hotfix_num == 15

    def test_out_of_order_hotfix_tags(self, release_manager_basic):
        """Test handles hotfix tags in non-sequential order."""
        release_mgr, mock_hgit = release_manager_basic

        mock_hgit.list_tags.return_value = [
            "v1.3.5-hotfix3",
            "v1.3.5-hotfix1",
            "v1.3.5-hotfix5",
            "v1.3.5-hotfix2"
        ]

        hotfix_num = release_mgr._determine_hotfix_number("1.3.5")

        # Should return 6 (max=5, +1)
        assert hotfix_num == 6

    def test_gap_in_hotfix_numbering(self, release_manager_basic):
        """Test handles gaps in hotfix numbering."""
        release_mgr, mock_hgit = release_manager_basic

        mock_hgit.list_tags.return_value = [
            "v1.3.5-hotfix1",
            "v1.3.5-hotfix3",
            "v1.3.5-hotfix5"
        ]

        hotfix_num = release_mgr._determine_hotfix_number("1.3.5")

        # Should return 6 (max=5, +1, doesn't fill gaps)
        assert hotfix_num == 6

    def test_ignores_non_hotfix_tags(self, release_manager_basic):
        """Test ignores RC and other tags."""
        release_mgr, mock_hgit = release_manager_basic

        mock_hgit.list_tags.return_value = [
            "v1.3.5",
            "v1.3.5-rc1",
            "v1.3.5-rc2",
            "v1.3.4"
        ]

        hotfix_num = release_mgr._determine_hotfix_number("1.3.5")

        # Should return 1 (no hotfixes found)
        assert hotfix_num == 1

    def test_different_versions_independent(self, release_manager_basic):
        """Test hotfix numbering is independent per version."""
        release_mgr, mock_hgit = release_manager_basic

        # Version 1.3.5 has hotfix1, hotfix2
        # Version 1.4.0 has hotfix1
        mock_hgit.list_tags.return_value = [
            "v1.3.5-hotfix1",
            "v1.3.5-hotfix2",
            "v1.4.0-hotfix1"
        ]

        # Check 1.3.5 → should be 3
        assert release_mgr._determine_hotfix_number("1.3.5") == 3

        # Mock different tag list for 1.4.0
        mock_hgit.list_tags.return_value = [
            "v1.3.5-hotfix1",
            "v1.3.5-hotfix2",
            "v1.4.0-hotfix1"
        ]

        # Check 1.4.0 → should be 2
        assert release_mgr._determine_hotfix_number("1.4.0") == 2

        # Check new version → should be 1
        assert release_mgr._determine_hotfix_number("1.5.0") == 1


class TestHotfixMarker:
    """Test HOTFIX marker in candidates.txt distinguishes hotfix releases."""

    @pytest.fixture
    def release_manager_with_tag(self, tmp_path):
        """Create ReleaseManager for testing marker."""
        mock_repo = Mock()
        mock_repo.base_dir = str(tmp_path)
        mock_repo.model_dir = str(tmp_path / ".hop" / "model")

        # Create releases/ directory
        releases_dir = tmp_path / ".hop" / "releases"
        releases_dir.mkdir(parents=True, exist_ok=True)
        mock_repo.releases_dir = str(releases_dir)

        # Create model/schema-1.3.5.sql and symlink
        model_dir = tmp_path / "model"
        model_dir.mkdir(exist_ok=True)
        schema_versioned = model_dir / "schema-1.3.5.sql"
        schema_versioned.write_text("-- VERSION: 1.3.5\n")
        schema_file = model_dir / "schema.sql"
        schema_file.symlink_to("schema-1.3.5.sql")

        # Mock HGit
        mock_hgit = Mock()
        mock_hgit.tag_exists.return_value = True
        mock_hgit.branch_exists.return_value = False
        mock_repo.hgit = mock_hgit

        release_mgr = ReleaseManager(mock_repo)

        return release_mgr, releases_dir

    def test_hotfix_marker_present_in_candidates(self, release_manager_with_tag):
        """Test # HOTFIX marker is present in candidates.txt."""
        release_mgr, releases_dir = release_manager_with_tag

        release_mgr.reopen_for_hotfix()

        candidates_file = releases_dir / "1.3.5-candidates.txt"
        content = candidates_file.read_text()

        # Verify marker present
        assert "# HOTFIX" in content
        assert content.startswith("# HOTFIX")

    def test_hotfix_marker_format(self, release_manager_with_tag):
        """Test HOTFIX marker format is exactly '# HOTFIX\\n'."""
        release_mgr, releases_dir = release_manager_with_tag

        release_mgr.reopen_for_hotfix()

        candidates_file = releases_dir / "1.3.5-candidates.txt"
        content = candidates_file.read_text()

        # Verify exact format
        assert content == "# HOTFIX\n"

    def test_stage_file_no_marker(self, release_manager_with_tag):
        """Test stage.txt does not have HOTFIX marker."""
        release_mgr, releases_dir = release_manager_with_tag

        release_mgr.reopen_for_hotfix()

        stage_file = releases_dir / "1.3.5-stage.txt"
        content = stage_file.read_text()

        # Verify stage is empty (no marker)
        assert content == ""
        assert "# HOTFIX" not in content
