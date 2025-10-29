"""
Tests for Git tagging during promote-to RC and production.

Validates that promote_to() creates and pushes appropriate Git tags
for both RC and production releases.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, call
from half_orm_dev.release_manager import ReleaseManager, ReleaseManagerError


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def release_manager_for_tagging(tmp_path):
    """
    Setup ReleaseManager with mocked dependencies for tagging tests.

    Provides:
    - Temporary releases directory with stage file
    - Mocked HGit with complete tag operations
    - Mocked Repo with database
    - Pre-configured for successful promotion workflow
    """
    # Create releases directory structure
    releases_dir = tmp_path / "releases"
    releases_dir.mkdir()

    # Create model directory (needed for prod promotion schema generation)
    model_dir = tmp_path / "model"
    model_dir.mkdir()

    # Create stage file
    stage_file = releases_dir / "1.3.6-stage.txt"
    stage_file.write_text("456-user-auth\n789-security\n")

    # Mock Repo
    mock_repo = Mock()
    mock_repo.name = "test_repo"

    # Mock Database
    mock_database = Mock()
    mock_repo.database = mock_database

    # Mock HGit with all necessary methods
    mock_hgit = Mock()
    mock_hgit.branch = "ho-prod"
    mock_hgit.repos_is_clean.return_value = True
    mock_hgit.acquire_branch_lock.return_value = "lock-tag-123"
    mock_hgit.release_branch_lock.return_value = None
    mock_hgit.fetch.return_value = None
    mock_hgit.pull.return_value = None
    mock_hgit.is_branch_synced.return_value = (True, "synced")
    mock_hgit.add.return_value = None
    mock_hgit.commit.return_value = None
    mock_hgit.last_commit.return_value = "abc123de"  # Commit SHA
    mock_hgit.push.return_value = None

    # Tag operations (critical for these tests)
    mock_hgit.create_tag = Mock()
    mock_hgit.push_tag = Mock()

    mock_repo.hgit = mock_hgit
    mock_repo.restore_database_from_schema = Mock()
    mock_repo.base_dir = tmp_path  # ReleaseManager reads base_dir from repo

    # Create ReleaseManager (takes only repo argument)
    release_mgr = ReleaseManager(mock_repo)

    # Mock helper methods to focus on tagging logic
    release_mgr._get_production_version = Mock(return_value="1.3.5")
    release_mgr._detect_stage_to_promote = Mock(return_value=("1.3.6", "1.3.6-stage.txt"))
    release_mgr._validate_single_active_rc = Mock()
    release_mgr._determine_rc_number = Mock(return_value=1)
    release_mgr._merge_archived_patches_to_ho_prod = Mock(return_value=["456-user-auth", "789-security"])
    release_mgr._send_rebase_notifications = Mock(return_value=["ho-patch/999-reports"])
    release_mgr._cleanup_patch_branches = Mock(return_value=["ho-patch/456-user-auth"])
    release_mgr._restore_and_apply_all_patches = Mock(return_value=["456-user-auth", "789-security"])
    release_mgr._generate_schema_dumps = Mock(return_value={
        'schema_file': Path('model/schema-1.3.6.sql'),
        'metadata_file': Path('model/metadata-1.3.6.sql')
    })

    return release_mgr, releases_dir, mock_hgit


@pytest.fixture
def release_manager_for_hotfix_tagging(tmp_path):
    """
    Setup ReleaseManager for hotfix tagging tests.

    Similar to release_manager_for_tagging but configured for hotfix scenario.
    """
    # Create releases directory structure
    releases_dir = tmp_path / "releases"
    releases_dir.mkdir()

    # Create model directory (needed for prod promotion schema generation)
    model_dir = tmp_path / "model"
    model_dir.mkdir()

    # Create stage file for hotfix
    stage_file = releases_dir / "1.3.6-hotfix1-stage.txt"
    stage_file.write_text("999-critical-fix\n")

    # Mock Repo
    mock_repo = Mock()
    mock_repo.name = "test_repo"

    # Mock Database
    mock_database = Mock()
    mock_repo.database = mock_database

    # Mock HGit
    mock_hgit = Mock()
    mock_hgit.branch = "ho-prod"
    mock_hgit.repos_is_clean.return_value = True
    mock_hgit.acquire_branch_lock.return_value = "lock-tag-456"
    mock_hgit.release_branch_lock.return_value = None
    mock_hgit.fetch.return_value = None
    mock_hgit.pull.return_value = None
    mock_hgit.is_branch_synced.return_value = (True, "synced")
    mock_hgit.add.return_value = None
    mock_hgit.commit.return_value = None
    mock_hgit.last_commit.return_value = "def456gh"
    mock_hgit.push.return_value = None
    mock_hgit.create_tag = Mock()
    mock_hgit.push_tag = Mock()

    mock_repo.hgit = mock_hgit
    mock_repo.restore_database_from_schema = Mock()
    mock_repo.base_dir = tmp_path  # ReleaseManager reads base_dir from repo

    # Create ReleaseManager (takes only repo argument)
    release_mgr = ReleaseManager(mock_repo)

    # Mock helpers for hotfix
    release_mgr._get_production_version = Mock(return_value="1.3.6")
    release_mgr._detect_stage_to_promote = Mock(return_value=("1.3.6-hotfix1", "1.3.6-hotfix1-stage.txt"))
    release_mgr._validate_single_active_rc = Mock()
    release_mgr._determine_rc_number = Mock(return_value=1)
    release_mgr._merge_archived_patches_to_ho_prod = Mock(return_value=["999-critical-fix"])
    release_mgr._send_rebase_notifications = Mock(return_value=[])
    release_mgr._cleanup_patch_branches = Mock(return_value=[])
    release_mgr._restore_and_apply_all_patches = Mock(return_value=["999-critical-fix"])
    release_mgr._generate_schema_dumps = Mock(return_value={
        'schema_file': Path('model/schema-1.3.6-hotfix1.sql'),
        'metadata_file': Path('model/metadata-1.3.6-hotfix1.sql')
    })

    return release_mgr, releases_dir, mock_hgit


# ============================================================================
# TESTS - RC TAGGING
# ============================================================================

class TestPromoteToRCTagging:
    """Test Git tag creation during promote-to rc."""

    def test_rc_tag_created_and_pushed(self, release_manager_for_tagging):
        """Test that RC promotion creates and pushes git tag v{version}-rc{N}."""
        release_mgr, releases_dir, mock_hgit = release_manager_for_tagging

        # Execute promotion to RC
        result = release_mgr.promote_to('rc')

        # Verify tag was created with correct name and message
        expected_tag = "v1.3.6-rc1"
        expected_message = "Release 1.3.6-rc1"

        mock_hgit.create_tag.assert_called_once_with(expected_tag, expected_message)

        # Verify tag was pushed to origin
        mock_hgit.push_tag.assert_called_once_with(expected_tag)

    def test_rc_tag_name_in_result(self, release_manager_for_tagging):
        """Test that tag name is included in promotion result."""
        release_mgr, releases_dir, mock_hgit = release_manager_for_tagging

        # Execute promotion
        result = release_mgr.promote_to('rc')

        # Verify result contains tag name
        assert 'tag_name' in result
        assert result['tag_name'] == "v1.3.6-rc1"

    def test_rc_tag_created_after_commit(self, release_manager_for_tagging):
        """Test that tag is created after promotion commit, ensuring it points to correct commit."""
        release_mgr, releases_dir, mock_hgit = release_manager_for_tagging

        # Execute promotion
        result = release_mgr.promote_to('rc')

        # Verify order: There may be multiple commits (promotion + stage creation)
        # Tag should be created after at least one commit (the promotion commit)
        calls = mock_hgit.method_calls
        commit_indices = []
        create_tag_index = None

        for i, call_item in enumerate(calls):
            if call_item[0] == 'commit':
                commit_indices.append(i)
            elif call_item[0] == 'create_tag':
                create_tag_index = i

        assert len(commit_indices) > 0, "At least one commit() should have been called"
        assert create_tag_index is not None, "create_tag() should have been called"

        # Tag should be created after first commit (promotion commit)
        first_commit_index = commit_indices[0]
        assert first_commit_index < create_tag_index, "Tag should be created after promotion commit"

    def test_rc_tag_incremental_numbering(self, release_manager_for_tagging):
        """Test that RC2, RC3 get correct tag names."""
        release_mgr, releases_dir, mock_hgit = release_manager_for_tagging

        # Simulate RC2 promotion
        release_mgr._determine_rc_number.return_value = 2

        result = release_mgr.promote_to('rc')

        # Verify RC2 tag
        expected_tag = "v1.3.6-rc2"
        expected_message = "Release 1.3.6-rc2"

        mock_hgit.create_tag.assert_called_once_with(expected_tag, expected_message)
        assert result['tag_name'] == "v1.3.6-rc2"


# ============================================================================
# TESTS - PRODUCTION TAGGING
# ============================================================================

class TestPromoteToProdTagging:
    """Test Git tag creation during promote-to prod."""

    def test_prod_tag_created_and_pushed(self, release_manager_for_tagging):
        """Test that production promotion creates and pushes git tag v{version}."""
        release_mgr, releases_dir, mock_hgit = release_manager_for_tagging

        # Execute promotion to production
        result = release_mgr.promote_to('prod')

        # Verify tag was created with correct name and message
        expected_tag = "v1.3.6"
        expected_message = "Release 1.3.6"

        mock_hgit.create_tag.assert_called_once_with(expected_tag, expected_message)

        # Verify tag was pushed to origin
        mock_hgit.push_tag.assert_called_once_with(expected_tag)

    def test_prod_tag_name_in_result(self, release_manager_for_tagging):
        """Test that production tag name is included in result."""
        release_mgr, releases_dir, mock_hgit = release_manager_for_tagging

        # Execute promotion
        result = release_mgr.promote_to('prod')

        # Verify result contains tag name
        assert 'tag_name' in result
        assert result['tag_name'] == "v1.3.6"

    def test_prod_tag_created_after_commit(self, release_manager_for_tagging):
        """Test that production tag is created after promotion commit."""
        release_mgr, releases_dir, mock_hgit = release_manager_for_tagging

        # Execute promotion
        result = release_mgr.promote_to('prod')

        # Verify order: commit before create_tag
        calls = mock_hgit.method_calls
        commit_indices = []
        create_tag_index = None

        for i, call_item in enumerate(calls):
            if call_item[0] == 'commit':
                commit_indices.append(i)
            elif call_item[0] == 'create_tag':
                create_tag_index = i

        assert len(commit_indices) > 0, "At least one commit() should have been called"
        assert create_tag_index is not None, "create_tag() should have been called"

        # Tag should be created after first commit
        first_commit_index = commit_indices[0]
        assert first_commit_index < create_tag_index, "Tag should be created after promotion commit"

    @pytest.mark.skip
    def test_hotfix_tag_created_correctly(self, release_manager_for_hotfix_tagging):
        """Test that hotfix promotion creates tag with hotfix suffix."""
        release_mgr, releases_dir, mock_hgit = release_manager_for_hotfix_tagging

        # Execute promotion to production (hotfix)
        result = release_mgr.promote_to('prod')

        # Verify hotfix tag
        expected_tag = "v1.3.6-hotfix1"
        expected_message = "Release 1.3.6-hotfix1"

        mock_hgit.create_tag.assert_called_once_with(expected_tag, expected_message)
        mock_hgit.push_tag.assert_called_once_with(expected_tag)

        assert result['tag_name'] == "v1.3.6-hotfix1"


# ============================================================================
# TESTS - TAG OPERATION ORDER
# ============================================================================

class TestTaggingWorkflowOrder:
    """Test that tagging happens at correct point in workflow."""

    def test_tag_pushed_immediately_after_creation(self, release_manager_for_tagging):
        """Test that push_tag is called immediately after create_tag."""
        release_mgr, releases_dir, mock_hgit = release_manager_for_tagging

        # Execute promotion
        result = release_mgr.promote_to('rc')

        # Verify order: create_tag then push_tag
        calls = mock_hgit.method_calls
        create_tag_index = None
        push_tag_index = None

        for i, call_item in enumerate(calls):
            if call_item[0] == 'create_tag':
                create_tag_index = i
            elif call_item[0] == 'push_tag':
                push_tag_index = i

        assert create_tag_index is not None
        assert push_tag_index is not None
        assert push_tag_index == create_tag_index + 1, "push_tag should follow create_tag immediately"

    def test_tag_operations_happen_after_push(self, release_manager_for_tagging):
        """Test that tagging happens after main push (ho-prod push)."""
        release_mgr, releases_dir, mock_hgit = release_manager_for_tagging

        # Execute promotion
        result = release_mgr.promote_to('prod')

        # Find indices
        calls = mock_hgit.method_calls
        push_index = None
        create_tag_index = None

        for i, call_item in enumerate(calls):
            if call_item[0] == 'push' and push_index is None:
                # First push() call (main ho-prod push)
                push_index = i
            elif call_item[0] == 'create_tag':
                create_tag_index = i

        assert push_index is not None
        assert create_tag_index is not None
        assert create_tag_index > push_index, "Tag creation should happen after main push"
