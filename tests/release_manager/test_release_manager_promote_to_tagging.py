"""
Tests for Git tagging during promote-to RC and production in the new workflow.

Tests the new release integration workflow where:
- promote_to_rc creates tags on release branches (ho-release/{version})
- promote_to_prod creates production tags on ho-prod
- RC numbering is automatic (rc1, rc2, etc.)
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, call
from half_orm_dev.release_manager import ReleaseManager, ReleaseManagerError


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def release_manager_for_rc_tagging(tmp_path):
    """
    Setup ReleaseManager for RC tagging tests.

    Creates:
    - Stage file for version 1.3.6
    - Mocked Repo and HGit with complete tag operations
    """
    # Create releases directory
    releases_dir = tmp_path / "releases"
    releases_dir.mkdir()

    # Create stage file
    stage_file = releases_dir / "1.3.6-stage.txt"
    stage_file.write_text("456-user-auth\n789-security\n")

    # Mock Repo
    mock_repo = Mock()
    mock_repo.base_dir = str(tmp_path)

    # Mock HGit
    mock_hgit = Mock()
    mock_hgit.branch = "ho-prod"
    mock_hgit.checkout = Mock()
    mock_hgit.list_tags = Mock(return_value=[])  # No existing tags
    mock_hgit.create_tag = Mock()
    mock_hgit.push_tag = Mock()

    mock_repo.hgit = mock_hgit

    # Create ReleaseManager
    release_mgr = ReleaseManager(mock_repo)

    return release_mgr, releases_dir, mock_hgit


@pytest.fixture
def release_manager_for_prod_tagging(tmp_path):
    """
    Setup ReleaseManager for production tagging tests.

    Creates:
    - RC file for version 1.3.6
    - Stage file (created after RC promotion)
    - Mocked Repo and HGit with complete tag operations
    """
    # Create releases directory
    releases_dir = tmp_path / "releases"
    releases_dir.mkdir()

    # Create RC file (needed for promote to prod)
    rc_file = releases_dir / "1.3.6-rc1.txt"
    rc_file.write_text("456-user-auth\n789-security\n")

    # Create stage file (automatically created after promote_to_rc)
    stage_file = releases_dir / "1.3.6-stage.txt"
    stage_file.write_text("456-user-auth\n789-security\n")

    # Mock Repo
    mock_repo = Mock()
    mock_repo.base_dir = str(tmp_path)

    # Mock HGit
    mock_hgit = Mock()
    mock_hgit.branch = "ho-prod"
    mock_hgit.checkout = Mock()
    mock_hgit.merge = Mock()
    mock_hgit.create_tag = Mock()
    mock_hgit.push_tag = Mock()
    mock_hgit.push_branch = Mock()
    mock_hgit.delete_branch = Mock()
    mock_hgit.delete_remote_branch = Mock()

    mock_repo.hgit = mock_hgit

    # Create ReleaseManager
    release_mgr = ReleaseManager(mock_repo)

    return release_mgr, releases_dir, mock_hgit


# ============================================================================
# TESTS - RC TAGGING
# ============================================================================

class TestPromoteToRCTagging:
    """Test that promote_to_rc creates correct tags."""

    def test_rc_tag_created_and_pushed(self, release_manager_for_rc_tagging):
        """Test that RC promotion creates and pushes tag with correct format."""
        release_mgr, releases_dir, mock_hgit = release_manager_for_rc_tagging

        # Execute promotion to RC
        result = release_mgr.promote_to_rc("1.3.6")

        # Verify tag was created with correct name and message
        expected_tag = "v1.3.6-rc1"
        expected_message = "Release Candidate 1.3.6"

        mock_hgit.create_tag.assert_called_once_with(expected_tag, expected_message)

        # Verify tag was pushed to origin
        mock_hgit.push_tag.assert_called_once_with(expected_tag)

    def test_rc_tag_in_result(self, release_manager_for_rc_tagging):
        """Test that tag is included in promotion result."""
        release_mgr, releases_dir, mock_hgit = release_manager_for_rc_tagging

        # Execute promotion
        result = release_mgr.promote_to_rc("1.3.6")

        # Verify result contains tag
        assert 'tag' in result
        assert result['tag'] == "v1.3.6-rc1"
        assert result['version'] == "1.3.6"
        assert result['branch'] == "ho-release/1.3.6"

    def test_rc_tag_incremental_numbering(self, release_manager_for_rc_tagging):
        """Test that RC2, RC3 get correct tag names."""
        release_mgr, releases_dir, mock_hgit = release_manager_for_rc_tagging

        # Simulate existing RC1 tag
        mock_hgit.list_tags.return_value = ["v1.3.6-rc1"]

        # Create RC1 file to simulate first promotion
        rc1_file = releases_dir / "1.3.6-rc1.txt"
        rc1_file.write_text("456-user-auth\n")

        result = release_mgr.promote_to_rc("1.3.6")

        # Verify RC2 tag with correct message format
        expected_tag = "v1.3.6-rc2"
        expected_message = "Release Candidate 1.3.6"

        mock_hgit.create_tag.assert_called_once_with(expected_tag, expected_message)
        assert result['tag'] == "v1.3.6-rc2"

    def test_rc_tags_pushed_immediately_after_creation(self, release_manager_for_rc_tagging):
        """Test that push_tag is called immediately after create_tag."""
        release_mgr, releases_dir, mock_hgit = release_manager_for_rc_tagging

        # Execute promotion
        result = release_mgr.promote_to_rc("1.3.6")

        # Verify order: create_tag then push_tag
        calls = mock_hgit.method_calls
        create_tag_index = None
        push_tag_index = None

        for i, call_item in enumerate(calls):
            if call_item[0] == 'create_tag':
                create_tag_index = i
            elif call_item[0] == 'push_tag':
                push_tag_index = i

        assert create_tag_index is not None, "create_tag should be called"
        assert push_tag_index is not None, "push_tag should be called"
        assert push_tag_index > create_tag_index, "push_tag should follow create_tag"

    def test_rc_checkout_release_branch_before_tagging(self, release_manager_for_rc_tagging):
        """Test that release branch is checked out before creating tag."""
        release_mgr, releases_dir, mock_hgit = release_manager_for_rc_tagging

        result = release_mgr.promote_to_rc("1.3.6")

        # Verify checkout was called with release branch
        checkout_calls = [c for c in mock_hgit.checkout.call_args_list
                         if c == call("ho-release/1.3.6")]
        assert len(checkout_calls) > 0, "Should checkout release branch before tagging"


# ============================================================================
# TESTS - PRODUCTION TAGGING
# ============================================================================

class TestPromoteToProdTagging:
    """Test that promote_to_prod creates correct production tags."""

    def test_prod_tag_created_and_pushed(self, release_manager_for_prod_tagging):
        """Test that production promotion creates and pushes tag."""
        release_mgr, releases_dir, mock_hgit = release_manager_for_prod_tagging

        # Execute promotion to production
        result = release_mgr.promote_to_prod("1.3.6")

        # Verify production tag was created
        expected_tag = "v1.3.6"
        expected_message = "Production release 1.3.6"

        mock_hgit.create_tag.assert_called_once_with(expected_tag, expected_message)

        # Verify tag was pushed
        mock_hgit.push_tag.assert_called_once_with(expected_tag)

    def test_prod_tag_in_result(self, release_manager_for_prod_tagging):
        """Test that production tag is included in result."""
        release_mgr, releases_dir, mock_hgit = release_manager_for_prod_tagging

        result = release_mgr.promote_to_prod("1.3.6")

        # Verify result contains tag
        assert 'tag' in result
        assert result['tag'] == "v1.3.6"
        assert result['version'] == "1.3.6"

    def test_prod_tag_on_ho_prod_branch(self, release_manager_for_prod_tagging):
        """Test that production tag is created on ho-prod after merge."""
        release_mgr, releases_dir, mock_hgit = release_manager_for_prod_tagging

        result = release_mgr.promote_to_prod("1.3.6")

        # Verify ho-prod was checked out before tagging
        checkout_calls = mock_hgit.checkout.call_args_list

        # Find the checkout to ho-prod
        ho_prod_checkouts = [c for c in checkout_calls if c == call("ho-prod")]
        assert len(ho_prod_checkouts) > 0, "Should checkout ho-prod before tagging"

    def test_prod_tag_after_merge(self, release_manager_for_prod_tagging):
        """Test that tag is created after merging release branch."""
        release_mgr, releases_dir, mock_hgit = release_manager_for_prod_tagging

        result = release_mgr.promote_to_prod("1.3.6")

        # Verify merge was called before create_tag
        calls = mock_hgit.method_calls
        merge_index = None
        create_tag_index = None

        for i, call_item in enumerate(calls):
            if call_item[0] == 'merge':
                merge_index = i
            elif call_item[0] == 'create_tag':
                create_tag_index = i

        assert merge_index is not None, "merge should be called"
        assert create_tag_index is not None, "create_tag should be called"
        assert create_tag_index > merge_index, "Tag should be created after merge"


# ============================================================================
# TESTS - TAG FORMAT AND CONSISTENCY
# ============================================================================

class TestTagFormatConsistency:
    """Test that tag format is consistent across RC and production."""

    def test_rc_tag_uses_v_prefix(self, release_manager_for_rc_tagging):
        """Test that RC tags use 'v' prefix."""
        release_mgr, releases_dir, mock_hgit = release_manager_for_rc_tagging

        result = release_mgr.promote_to_rc("1.3.6")

        # Verify tag starts with 'v'
        tag = result['tag']
        assert tag.startswith('v'), "RC tag should start with 'v'"
        assert tag == "v1.3.6-rc1"

    def test_prod_tag_uses_v_prefix(self, release_manager_for_prod_tagging):
        """Test that production tags use 'v' prefix."""
        release_mgr, releases_dir, mock_hgit = release_manager_for_prod_tagging

        result = release_mgr.promote_to_prod("1.3.6")

        # Verify tag starts with 'v'
        tag = result['tag']
        assert tag.startswith('v'), "Production tag should start with 'v'"
        assert tag == "v1.3.6"

    def test_tag_message_format_rc(self, release_manager_for_rc_tagging):
        """Test RC tag message format."""
        release_mgr, releases_dir, mock_hgit = release_manager_for_rc_tagging

        release_mgr.promote_to_rc("1.3.6")

        # Get the actual call arguments
        call_args = mock_hgit.create_tag.call_args
        tag_name = call_args[0][0]
        tag_message = call_args[0][1]

        # Verify message format
        assert tag_message == "Release Candidate 1.3.6"
        assert "Release Candidate" in tag_message
        assert "1.3.6" in tag_message

    def test_tag_message_format_prod(self, release_manager_for_prod_tagging):
        """Test production tag message format."""
        release_mgr, releases_dir, mock_hgit = release_manager_for_prod_tagging

        release_mgr.promote_to_prod("1.3.6")

        # Get the actual call arguments
        call_args = mock_hgit.create_tag.call_args
        tag_name = call_args[0][0]
        tag_message = call_args[0][1]

        # Verify message format
        assert tag_message == "Production release 1.3.6"
        assert "Production release" in tag_message
        assert "1.3.6" in tag_message
