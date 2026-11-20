"""
Tests for HGit.file_is_committed.

The predicate answers one question: can git give this file back after it
is deleted? modules.py uses it to decide whether an obsolete generated
module may be removed or must be rescued (see
half_orm_dev.modules._discard_obsolete_module).
"""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import git
import pytest

from half_orm_dev.hgit import HGit


@pytest.fixture
def hgit_with_repo():
    """HGit wired to a real git repository holding one committed file."""
    temp_dir = tempfile.mkdtemp()
    try:
        git_repo = git.Repo.init(temp_dir)
        git_repo.git.config('user.email', 'test@example.com')
        git_repo.git.config('user.name', 'Test User')
        (Path(temp_dir) / 'committed.py').write_text("print('hello')\n")
        git_repo.git.add('committed.py')
        git_repo.git.commit('-m', 'initial')

        mock_repo = Mock()
        mock_repo.git_origin = ""
        mock_repo.base_dir = temp_dir
        with patch.object(HGit, '_HGit__post_init'):
            hgit = HGit(mock_repo)
            hgit._HGit__git_repo = git_repo

        yield hgit, Path(temp_dir)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_tracked_and_unmodified_is_committed(hgit_with_repo):
    hgit, _ = hgit_with_repo
    assert hgit.file_is_committed('committed.py') is True


def test_untracked_is_not_committed(hgit_with_repo):
    hgit, base_dir = hgit_with_repo
    (base_dir / 'brand_new.py').write_text("print('new')\n")
    assert hgit.file_is_committed('brand_new.py') is False


def test_modified_is_not_committed(hgit_with_repo):
    """The file is tracked, but its current content is not in git."""
    hgit, base_dir = hgit_with_repo
    (base_dir / 'committed.py').write_text("print('edited')\n")
    assert hgit.file_is_committed('committed.py') is False


def test_staged_is_not_committed(hgit_with_repo):
    hgit, base_dir = hgit_with_repo
    (base_dir / 'committed.py').write_text("print('edited')\n")
    hgit._HGit__git_repo.git.add('committed.py')
    assert hgit.file_is_committed('committed.py') is False


def test_missing_file_is_not_committed(hgit_with_repo):
    hgit, _ = hgit_with_repo
    assert hgit.file_is_committed('never_existed.py') is False
