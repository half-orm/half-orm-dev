"""Shared fixtures for the ReleaseManager tests."""
import pytest

from half_orm_dev.release_manager import ReleaseManager
from half_orm_dev.utils import hop_version


@pytest.fixture(autouse=True)
def releases_made_with_the_installed_half_orm_dev(monkeypatch):
    """Every release reads as made with the installed half_orm_dev.

    upgrade_production() refuses a release made with another version, which
    it reads from the release's ho-prod-X.Y.Z branch. The tests here mock
    git, and are about something else; test_release_manager_upgrade_tool_version
    covers that check, overriding this fixture.
    """
    monkeypatch.setattr(
        ReleaseManager, '_release_hop_version', lambda self, version: hop_version())
