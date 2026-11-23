"""
Test candidate patches at promote_to_prod: they are detached, once the user
agrees, before the release goes to production with its staged patches only.

The detachment itself is PatchManager.detach_patch (tested with the patch
manager); the end-to-end behaviour is in
tests/e2e/test_promote_prod_detaches_candidates.py.
"""

import pytest
from unittest.mock import Mock, call, patch

from half_orm_dev.release_manager import ReleaseManager, ReleaseManagerError
from half_orm_dev.release_file import ReleaseFile


@pytest.fixture
def release_manager(tmp_path):
    """ReleaseManager on a mocked Repo, release 0.17.1 with one staged patch."""
    releases_dir = tmp_path / ".hop" / "releases"
    releases_dir.mkdir(parents=True)
    (tmp_path / ".hop" / "model").mkdir(parents=True)

    repo = Mock()
    repo.base_dir = str(tmp_path)
    repo.releases_dir = str(releases_dir)
    repo.model_dir = str(tmp_path / ".hop" / "model")

    hgit = Mock()
    hgit.get_remote_branches = Mock(return_value=[])
    hgit._HGit__git_repo.tags = []
    repo.hgit = hgit
    repo.patch_manager = Mock()
    repo.patch_manager._collect_data_files_from_patches = Mock(return_value=[])
    repo.database = Mock()
    repo.restore_database_from_schema = Mock()
    repo.model = Mock()

    release_file = ReleaseFile("0.17.1", releases_dir)
    release_file.create_empty()
    release_file.add_patch("42-feature")
    release_file.move_to_staged("42-feature", "commit42")

    return ReleaseManager(repo), repo, release_file


def _add_candidates(release_file, *patch_ids):
    for patch_id in patch_ids:
        release_file.add_patch(patch_id)


@patch('builtins.print')
def test_declined_detach_cancels_the_promotion(mock_print, release_manager):
    rel_mgr, repo, release_file = release_manager
    _add_candidates(release_file, "43-bugfix")

    with patch('builtins.input', return_value='n'):
        with pytest.raises(ReleaseManagerError, match="Promotion cancelled"):
            rel_mgr.promote_to_prod()

    repo.patch_manager._detach_patch.assert_not_called()
    repo.hgit.merge.assert_not_called()


@patch('builtins.print')
def test_accepted_detach_detaches_each_candidate_from_its_branch(mock_print, release_manager):
    rel_mgr, repo, release_file = release_manager
    _add_candidates(release_file, "43-bugfix", "44-other")
    events = Mock()
    events.attach_mock(repo.hgit.checkout, 'checkout')
    events.attach_mock(repo.patch_manager._detach_patch, '_detach_patch')

    with patch('builtins.input', return_value='y'):
        result = rel_mgr.promote_to_prod()

    assert events.mock_calls[:5] == [
        call.checkout("ho-patch/43-bugfix"),
        call._detach_patch("43-bugfix"),
        call.checkout("ho-patch/44-other"),
        call._detach_patch("44-other"),
        call.checkout("ho-release/0.17.1"),
    ]
    assert result['detached_patches'] == ["43-bugfix", "44-other"]


@patch('builtins.print')
def test_candidates_are_neither_rebased_nor_moved_to_a_new_release(mock_print, release_manager):
    rel_mgr, repo, release_file = release_manager
    _add_candidates(release_file, "43-bugfix")

    with patch('builtins.input', return_value='y'):
        rel_mgr.promote_to_prod()

    repo.hgit.rebase.assert_not_called()
    assert call("-b", "ho-release/0.17.2") not in repo.hgit.checkout.call_args_list


@patch('builtins.print')
def test_without_candidates_nothing_is_asked(mock_print, release_manager):
    rel_mgr, repo, release_file = release_manager

    with patch('builtins.input') as mock_input:
        result = rel_mgr.promote_to_prod()

    mock_input.assert_not_called()
    repo.patch_manager._detach_patch.assert_not_called()
    assert result['version'] == "0.17.1"
    assert result['detached_patches'] == []
