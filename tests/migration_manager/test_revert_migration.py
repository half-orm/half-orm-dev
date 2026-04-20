"""
Tests for MigrationManager.revert_migration() and related helpers.

Covers:
- _create_migration_tag(): annotated tag creation with correct annotation
- revert_migration(): happy path (lock acquired, commits reverted, tag deleted)
- revert_migration(): no tag → MigrationManagerError
- revert_migration(): malformed tag annotation → MigrationManagerError
- revert_migration(): LIFO order with multiple migration tags
"""
import pytest
from unittest.mock import Mock, call, patch
from packaging import version as pkg_version
from half_orm_dev.migration_manager import MigrationManager, MigrationManagerError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_tag(name: str, annotation: str):
    """Return a Mock that behaves like a GitPython Tag object."""
    tag = Mock()
    tag.name = name
    tag.tag = Mock()
    tag.tag.message = annotation
    return tag


def _make_mgr(extra_tags=None):
    """
    Build a MigrationManager wired to a minimal mock repo.

    extra_tags: list of Mock tag objects present in git_repo.tags
    """
    mock_repo = Mock()
    mock_repo.base_dir = '/fake/repo'

    # Config
    mock_config = Mock()
    mock_config.hop_version = '0.18.0'
    mock_repo._Repo__config = mock_config

    # hgit
    mock_git = Mock()
    mock_git_repo = Mock()
    mock_git_repo.git = mock_git
    mock_git_repo.tags = extra_tags or []
    mock_git_repo.head = Mock()
    mock_git_repo.head.commit = Mock()
    mock_git_repo.head.commit.hexsha = 'aabbcc001122'

    mock_hgit = Mock()
    mock_hgit._HGit__git_repo = mock_git_repo
    mock_hgit.acquire_branch_lock = Mock(return_value='lock-ho-prod-99999')
    mock_hgit.release_branch_lock = Mock()
    mock_repo.hgit = mock_hgit

    # sync_and_validate_ho_prod (called by decorator)
    mock_repo.sync_and_validate_ho_prod = Mock()
    # sync_hop_to_active_branches (called by decorator after success)
    mock_repo.sync_hop_to_active_branches = Mock(return_value={
        'synced_branches': [], 'skipped_branches': [], 'errors': [],
        'branch_commits': {},
    })

    def compare_versions(v1, v2):
        p1 = pkg_version.parse(v1)
        p2 = pkg_version.parse(v2)
        return 0 if p1 == p2 else (1 if p1 > p2 else -1)
    mock_repo.compare_versions = compare_versions

    mgr = MigrationManager(mock_repo)
    return mgr, mock_repo, mock_git_repo


# ---------------------------------------------------------------------------
# Tests for _create_migration_tag()
# ---------------------------------------------------------------------------

class TestCreateMigrationTag:

    def test_tag_created_with_correct_annotation(self):
        """Tag annotation encodes ho-prod SHA and branch→SHA pairs."""
        mgr, mock_repo, mock_git_repo = _make_mgr()
        mock_repo.hgit.tag_exists.return_value = False
        mock_git_repo.head.commit.hexsha = 'prod111'

        sync_result = {
            'sync_result': {
                'branch_commits': {
                    'ho-patch/3-foo': 'patch333',
                    'ho-release/0.18.0': 'rel444',
                }
            }
        }
        mgr._create_migration_tag('0.17.0', '0.18.0', sync_result)

        mock_repo.hgit.create_tag.assert_called_once()
        tag_name, = [c.args[0] for c in mock_repo.hgit.create_tag.call_args_list]
        assert tag_name == 'ho-migration/0.18.0'

        annotation = mock_repo.hgit.create_tag.call_args[1]['message']
        assert 'Migration from 0.17.0 to 0.18.0' in annotation
        assert 'ho-prod:prod111' in annotation
        assert 'ho-patch/3-foo:patch333' in annotation
        assert 'ho-release/0.18.0:rel444' in annotation

    def test_tag_pushed_to_remote(self):
        """Tag is pushed after creation."""
        mgr, mock_repo, _ = _make_mgr()
        mock_repo.hgit.tag_exists.return_value = False

        mgr._create_migration_tag('0.17.0', '0.18.0', {'sync_result': {'branch_commits': {}}})

        mock_repo.hgit.push_tag.assert_called_once_with('ho-migration/0.18.0')

    def test_stale_tag_deleted_before_creation(self):
        """If a stale tag exists, it is deleted before creating a fresh one."""
        mgr, mock_repo, _ = _make_mgr()
        mock_repo.hgit.tag_exists.return_value = True

        mgr._create_migration_tag('0.17.0', '0.18.0', {'sync_result': {'branch_commits': {}}})

        mock_repo.hgit.delete_local_tag.assert_called_once_with('ho-migration/0.18.0')
        mock_repo.hgit.create_tag.assert_called_once()


# ---------------------------------------------------------------------------
# Tests for revert_migration()
# ---------------------------------------------------------------------------

class TestRevertMigration:

    def _annotation(self, from_v, to_v, branch_shas: dict) -> str:
        lines = [f"Migration from {from_v} to {to_v}", f"ho-prod:prodSHA"]
        for branch, sha in branch_shas.items():
            lines.append(f"{branch}:{sha}")
        return '\n'.join(lines)

    def test_revert_calls_git_revert_on_each_branch(self):
        """git revert is called for each branch listed in the tag annotation."""
        ann = self._annotation('0.17.0', '0.18.0', {
            'ho-patch/3-foo': 'patchSHA',
            'ho-release/0.18.0': 'relSHA',
        })
        tag = _make_mock_tag('ho-migration/0.18.0', ann)
        mgr, mock_repo, mock_git_repo = _make_mgr(extra_tags=[tag])

        mgr.revert_migration()

        revert_calls = mock_git_repo.git.revert.call_args_list
        reverted_shas = [c.args[0] for c in revert_calls]
        assert 'patchSHA' in reverted_shas
        assert 'relSHA' in reverted_shas
        assert 'prodSHA' in reverted_shas

    def test_ho_prod_reverted_last(self):
        """ho-prod commit is reverted after the active-branch sync commits."""
        ann = self._annotation('0.17.0', '0.18.0', {'ho-patch/3-foo': 'patchSHA'})
        tag = _make_mock_tag('ho-migration/0.18.0', ann)
        mgr, mock_repo, mock_git_repo = _make_mgr(extra_tags=[tag])

        mgr.revert_migration()

        revert_calls = mock_git_repo.git.revert.call_args_list
        shas_in_order = [c.args[0] for c in revert_calls]
        # ho-prod revert must be last
        assert shas_in_order[-1] == 'prodSHA'
        assert shas_in_order[0] == 'patchSHA'

    def test_tag_deleted_after_revert(self):
        """Migration tag is deleted (local + remote) after successful revert."""
        ann = self._annotation('0.17.0', '0.18.0', {})
        tag = _make_mock_tag('ho-migration/0.18.0', ann)
        mgr, mock_repo, mock_git_repo = _make_mgr(extra_tags=[tag])

        mgr.revert_migration()

        mock_repo.hgit.delete_local_tag.assert_called_once_with('ho-migration/0.18.0')
        mock_repo.hgit.delete_remote_tag.assert_called_once_with('ho-migration/0.18.0')

    def test_branches_pushed_after_revert(self):
        """All affected branches are pushed after reverting."""
        ann = self._annotation('0.17.0', '0.18.0', {'ho-patch/3-foo': 'patchSHA'})
        tag = _make_mock_tag('ho-migration/0.18.0', ann)
        mgr, mock_repo, mock_git_repo = _make_mgr(extra_tags=[tag])

        mgr.revert_migration()

        pushed = [c.args[0] for c in mock_repo.hgit.push_branch.call_args_list]
        assert 'ho-patch/3-foo' in pushed
        assert 'ho-prod' in pushed

    def test_no_tag_raises_error(self):
        """MigrationManagerError raised when no ho-migration/* tag exists."""
        mgr, mock_repo, _ = _make_mgr(extra_tags=[])

        with pytest.raises(MigrationManagerError, match="No migration tag found"):
            mgr.revert_migration()

    def test_malformed_tag_missing_ho_prod_raises_error(self):
        """MigrationManagerError raised when annotation is missing ho-prod SHA."""
        # Annotation without ho-prod line
        ann = "Migration from 0.17.0 to 0.18.0\nho-patch/3-foo:patchSHA"
        tag = _make_mock_tag('ho-migration/0.18.0', ann)
        mgr, mock_repo, _ = _make_mgr(extra_tags=[tag])

        with pytest.raises(MigrationManagerError, match="malformed"):
            mgr.revert_migration()

    def test_lifo_highest_version_reverted_first(self):
        """With multiple migration tags, the highest version is reverted."""
        ann_018 = self._annotation('0.17.0', '0.18.0', {})
        ann_100 = self._annotation('0.18.0', '1.0.0', {})
        tag_018 = _make_mock_tag('ho-migration/0.18.0', ann_018)
        tag_100 = _make_mock_tag('ho-migration/1.0.0', ann_100)
        # Provide in reverse insertion order to ensure sorting works
        mgr, mock_repo, mock_git_repo = _make_mgr(extra_tags=[tag_018, tag_100])

        mgr.revert_migration()

        # Only the 1.0.0 tag should be deleted (highest version)
        deleted = [c.args[0] for c in mock_repo.hgit.delete_local_tag.call_args_list]
        assert 'ho-migration/1.0.0' in deleted
        assert 'ho-migration/0.18.0' not in deleted

    def test_lock_acquired_on_ho_prod(self):
        """Branch lock on ho-prod is acquired (and released) by the decorator."""
        ann = self._annotation('0.17.0', '0.18.0', {})
        tag = _make_mock_tag('ho-migration/0.18.0', ann)
        mgr, mock_repo, _ = _make_mgr(extra_tags=[tag])

        mgr.revert_migration()

        mock_repo.hgit.acquire_branch_lock.assert_called_once_with(
            'ho-prod', timeout_minutes=30
        )
        mock_repo.hgit.release_branch_lock.assert_called_once()