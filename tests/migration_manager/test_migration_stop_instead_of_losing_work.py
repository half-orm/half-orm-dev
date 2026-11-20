"""
Tests for migration 2.0.0a3: `patch apply` and `patch merge` stop instead of
losing work.

Covers half_orm_dev/migrations/2/0/0/a3/00_stop_instead_of_losing_work.py,
which changes nothing in the repository but announces the two behaviours.
"""

import importlib.util
from pathlib import Path
from unittest.mock import Mock

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "half_orm_dev" / "migrations" / "2" / "0" / "0" / "a3"
    / "00_stop_instead_of_losing_work.py"
)


def _migration():
    spec = importlib.util.spec_from_file_location("stop_instead_of_losing_work", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_it_announces_both_behaviours_and_changes_nothing(capsys):
    result = _migration().migrate(Mock())

    out = capsys.readouterr().out
    assert result == {}
    assert "`patch apply`" in out and "`patch merge`" in out
    assert "git merge ho-release/X.Y.Z" in out


def test_it_runs_on_the_way_from_2_0_0a2_to_2_0_0a3():
    from half_orm_dev.migration_manager import MigrationManager

    manager = MigrationManager.__new__(MigrationManager)
    manager._migrations_root = MIGRATION_PATH.parents[4]  # migrations/

    pending = manager.get_pending_migrations("2.0.0-a2", "2.0.0-a3")

    assert [(v, d) for v, d in pending] == [("2.0.0a3", MIGRATION_PATH.parent)]
    # From a1, both a2 and a3 run, in order
    assert [v for v, _ in manager.get_pending_migrations("2.0.0-a1", "2.0.0-a3")] == [
        "2.0.0a2", "2.0.0a3"]
