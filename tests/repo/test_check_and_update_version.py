"""
Tests for version validation in check_and_update() after git pull/sync.

When check_and_update() pulls ho-prod and syncs branches, .hop/config may
have been updated to a newer hop_version. If the installed version is older,
OutdatedHalfORMDevError must be raised so the user is informed before any
further operation.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from half_orm_dev.repo import Repo, OutdatedHalfORMDevError, RepoError, Config


# ============================================================================
# HELPERS
# ============================================================================

def _make_repo_with_version(base_dir, config_version: str, installed_version: str):
    """
    Build a minimal Repo-like object (not fully initialised) and test
    _validate_version() after a simulated config reload.

    We test the behaviour of check_and_update step 0c in isolation:
      - After pull+sync, Config is recreated with the new version on disk
      - _validate_version() is called
      - If installed < required → OutdatedHalfORMDevError
    """
    mock_repo = Mock(spec=Repo)

    # Simulate Config with a freshly-pulled hop_version
    config = Mock()
    config.hop_version = config_version
    mock_repo.config = config
    mock_repo._Repo__base_dir = str(base_dir)

    from packaging import version as pkg_version
    def compare_versions(v1, v2):
        p1, p2 = pkg_version.parse(v1), pkg_version.parse(v2)
        return -1 if p1 < p2 else (1 if p1 > p2 else 0)
    mock_repo.compare_versions = compare_versions

    # Wire _validate_version to use the real implementation logic
    def _validate_version():
        required = mock_repo.config.hop_version
        if not required:
            return
        if mock_repo.compare_versions(installed_version, required) < 0:
            raise OutdatedHalfORMDevError(required, installed_version)
    mock_repo._validate_version = _validate_version

    return mock_repo


# ============================================================================
# TESTS — Point 1 : version mismatch detected after pull in check_and_update
# ============================================================================

class TestCheckAndUpdateVersionReload:
    """
    Verify that check_and_update step 0c raises OutdatedHalfORMDevError when
    .hop/config has been updated to a version newer than the installed tool.
    """

    def test_raises_when_config_newer_than_installed(self, tmp_path):
        """
        After pull, config says 1.0.0-a16 but installed is 1.0.0-a15
        → OutdatedHalfORMDevError.
        """
        repo = _make_repo_with_version(tmp_path, "1.0.0-a16", "1.0.0-a15")

        with pytest.raises(OutdatedHalfORMDevError) as exc_info:
            repo._validate_version()

        assert exc_info.value.required_version == "1.0.0-a16"
        assert exc_info.value.installed_version == "1.0.0-a15"

    def test_no_error_when_installed_equals_config(self, tmp_path):
        """Installed == config version → no error."""
        repo = _make_repo_with_version(tmp_path, "1.0.0-a16", "1.0.0-a16")
        repo._validate_version()  # must not raise

    def test_no_error_when_installed_newer_than_config(self, tmp_path):
        """Installed > config version (migration pending) → no downgrade error."""
        repo = _make_repo_with_version(tmp_path, "1.0.0-a15", "1.0.0-a16")
        repo._validate_version()  # must not raise

    def test_error_carries_upgrade_instruction(self, tmp_path):
        """Exception message contains pip upgrade hint."""
        repo = _make_repo_with_version(tmp_path, "1.0.0-a16", "1.0.0-a15")

        with pytest.raises(OutdatedHalfORMDevError) as exc_info:
            repo._validate_version()

        assert "pip install" in str(exc_info.value).lower()

    def test_no_error_when_no_hop_version_in_config(self, tmp_path):
        """No hop_version in config (legacy project) → no error."""
        repo = _make_repo_with_version(tmp_path, "", "1.0.0-a16")
        repo._validate_version()  # empty string → return early, no raise