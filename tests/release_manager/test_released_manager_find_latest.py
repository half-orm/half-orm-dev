"""
Tests for ReleaseManager.find_latest_version() method.

find_latest_version() returns a packaging.version.Version (or None).
PEP 440 ordering applies: post-releases (hotfixes) > production > rc > dev.
Files with invalid PEP 440 version strings are silently ignored.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock

from half_orm_dev.release_manager import ReleaseManager, ReleaseFileError


@pytest.fixture
def rm(tmp_path):
    """ReleaseManager with an empty releases/ directory."""
    mock_repo = Mock()
    mock_repo.base_dir = str(tmp_path)
    mock_repo.model_dir = str(tmp_path / ".hop" / "model")
    releases_dir = tmp_path / ".hop" / "releases"
    releases_dir.mkdir(parents=True, exist_ok=True)
    mock_repo.releases_dir = str(releases_dir)
    mgr = ReleaseManager(mock_repo)
    return mgr, releases_dir


class TestReleaseManagerFindLatest:

    def test_empty_directory_returns_none(self, rm):
        mgr, _ = rm
        assert mgr.find_latest_version() is None

    def test_single_production_release(self, rm):
        mgr, d = rm
        (d / "1.3.5.txt").touch()
        assert str(mgr.find_latest_version()) == "1.3.5"

    def test_multiple_production_releases(self, rm):
        mgr, d = rm
        for v in ("1.3.3", "1.3.5", "1.3.4"):
            (d / f"{v}.txt").touch()
        assert str(mgr.find_latest_version()) == "1.3.5"

    def test_major_takes_precedence(self, rm):
        mgr, d = rm
        for v in ("1.9.9", "2.0.0", "1.10.10"):
            (d / f"{v}.txt").touch()
        assert str(mgr.find_latest_version()) == "2.0.0"

    def test_minor_takes_precedence_over_patch(self, rm):
        mgr, d = rm
        for v in ("1.3.99", "1.4.0", "1.3.100"):
            (d / f"{v}.txt").touch()
        assert str(mgr.find_latest_version()) == "1.4.0"

    def test_production_greater_than_rc_same_version(self, rm):
        """1.3.5 > 1.3.5rc2 in PEP 440."""
        mgr, d = rm
        (d / "1.3.5-rc2.txt").touch()
        (d / "1.3.5.txt").touch()
        assert str(mgr.find_latest_version()) == "1.3.5"

    def test_rc_greater_than_rc_lower_number(self, rm):
        mgr, d = rm
        for rc in ("rc1", "rc3", "rc2"):
            (d / f"1.3.5-{rc}.txt").touch()
        result = mgr.find_latest_version()
        assert result.pre == ("rc", 3)

    def test_post_release_greater_than_production(self, rm):
        """Hotfix (post-release) is newer than the base production release."""
        mgr, d = rm
        (d / "1.3.4.txt").touch()
        (d / "1.3.4.post1.txt").touch()
        (d / "1.3.4.post2.txt").touch()
        result = mgr.find_latest_version()
        assert result.post == 2
        assert str(result) == "1.3.4.post2"

    def test_post_release_higher_base_version_wins(self, rm):
        mgr, d = rm
        (d / "1.3.4.txt").touch()
        (d / "1.3.4.post1.txt").touch()
        (d / "1.3.5.txt").touch()
        assert str(mgr.find_latest_version()) == "1.3.5"

    def test_ignores_non_txt_files(self, rm):
        mgr, d = rm
        (d / "1.3.5.txt").touch()
        (d / "1.3.6.sql").touch()
        (d / "1.3.7.md").touch()
        assert str(mgr.find_latest_version()) == "1.3.5"

    def test_ignores_invalid_pep440_filenames(self, rm):
        mgr, d = rm
        (d / "1.3.5.txt").touch()
        (d / "README.txt").touch()
        (d / "1.2.txt").touch()
        (d / "1.3.5-invalid.txt").touch()
        assert str(mgr.find_latest_version()) == "1.3.5"

    def test_only_invalid_files_returns_none(self, rm):
        mgr, d = rm
        (d / "README.txt").touch()
        (d / "1.3.5-stage.txt").touch()   # not valid PEP 440
        assert mgr.find_latest_version() is None

    def test_releases_directory_missing_raises(self, tmp_path):
        mock_repo = Mock()
        mock_repo.base_dir = str(tmp_path)
        mock_repo.releases_dir = str(tmp_path / ".hop" / "releases")
        mock_repo.model_dir = str(tmp_path / ".hop" / "model")
        mgr = ReleaseManager(mock_repo)
        with pytest.raises(ReleaseFileError):
            mgr.find_latest_version()
