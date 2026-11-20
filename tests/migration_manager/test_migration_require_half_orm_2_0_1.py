"""
Tests for migration 2.0.0a2: half-orm 2.0.1 required.

Covers half_orm_dev/migrations/2/0/0/a2/00_require_half_orm_2_0_1.py, which
changes nothing in the repository but tells the developer why half-orm was
upgraded, and warns when the half-orm actually imported is still affected.
"""

import importlib.util
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "half_orm_dev" / "migrations" / "2" / "0" / "0" / "a2"
    / "00_require_half_orm_2_0_1.py"
)


@pytest.fixture
def migration():
    spec = importlib.util.spec_from_file_location("require_half_orm_2_0_1", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_it_explains_the_upgrade_and_changes_nothing(migration, capsys):
    with patch("half_orm.__version__", "2.0.1"):
        result = migration.migrate(Mock())

    out = capsys.readouterr().out
    assert result == {}
    assert "data-loss" in out
    assert "ho_delete()" in out
    assert "❌" not in out


def test_it_warns_when_the_affected_half_orm_is_still_imported(migration, capsys):
    with patch("half_orm.__version__", "2.0.0"):
        migration.migrate(Mock())

    out = capsys.readouterr().out
    assert "half-orm 2.0.0 is installed" in out
    assert "pip install --upgrade 'half-orm>=2.0.1,<3'" in out


def test_it_runs_on_the_way_from_2_0_0a1_to_2_0_0a2():
    """The runner maps migrations/2/0/0/a2/ to 2.0.0a2."""
    from half_orm_dev.migration_manager import MigrationManager

    manager = MigrationManager.__new__(MigrationManager)
    manager._migrations_root = MIGRATION_PATH.parents[4]  # migrations/

    pending = manager.get_pending_migrations("2.0.0-a1", "2.0.0-a2")

    assert [(v, d) for v, d in pending] == [("2.0.0a2", MIGRATION_PATH.parent)]
    assert manager.get_pending_migrations("2.0.0-a2", "2.0.0-a2") == []
