"""
Regression tests for Repo._reset_database_schemas().

Bug scenario (observed in production on a real project):
  _reset_database_schemas() used to build its list of schemas to drop
  from self.model.desc(), which only lists *relations* (tables, views,
  materialized views, partitions). A schema holding no relation at all -
  either genuinely empty, or containing only functions/types/sequences -
  is therefore invisible to desc() and was never dropped.

  Such a schema survives the "reset", then collides with the
  CREATE SCHEMA emitted by the schema/release dump being restored:

      psql:.../schema-0.3.9.sql:64: ERROR: schema "si" already exists

  Before -v ON_ERROR_STOP=1 was added, psql swallowed that error, kept
  going and still exited 0 - so the reset silently left the database in
  a state that no longer matched the dump. With ON_ERROR_STOP the same
  latent defect turns into a hard, self-perpetuating failure of
  `patch apply` (an aborted load leaves more empty schemas behind, since
  pg_dump emits every CREATE SCHEMA up front).

  Fix: enumerate schemas from pg_catalog.pg_namespace instead, so that
  relation-less schemas are dropped too.
"""

import pytest
from unittest.mock import Mock

from half_orm_dev.repo import Repo


def _make_repo(catalog_schemas, relations=None):
    """Build a mock repo with the real _reset_database_schemas bound.

    Args:
        catalog_schemas: schema names pg_catalog.pg_namespace returns
        relations: optional model.desc() payload (defaults to none), used
            to prove the method no longer depends on it
    """
    repo = Mock()
    repo._reset_database_schemas = (
        Repo._reset_database_schemas.__get__(repo, Repo)
    )

    mock_model = Mock()
    mock_model.desc = Mock(return_value=relations or [])

    executed = []

    def execute_query(query, *args, **kwargs):
        executed.append(query)
        if query.lstrip().upper().startswith('SELECT'):
            # psycopg is configured with row_factory=dict_row in half_orm,
            # so rows are dicts, not tuples.
            return [{'nspname': name} for name in catalog_schemas]
        return Mock()

    mock_model.execute_query = Mock(side_effect=execute_query)
    repo.model = mock_model

    return repo, mock_model, executed


def _dropped_schemas(executed):
    """Extract schema names from the DROP SCHEMA statements issued."""
    dropped = []
    for query in executed:
        if query.startswith('DROP SCHEMA IF EXISTS '):
            dropped.append(query.split('"')[1])
    return dropped


class TestResetDatabaseSchemas:
    """Schemas are enumerated from the catalog, not from model.desc()."""

    def test_drops_schema_without_any_relation(self):
        """A relation-less schema ('si') must still be dropped.

        This is the exact production failure: 'si' held no table/view, so
        model.desc() never reported it and it survived every reset.
        """
        repo, _, executed = _make_repo(
            catalog_schemas=['public', 'api', 'si'],
            # desc() sees only the schemas that actually hold relations -
            # 'si' is absent, which is what used to hide it.
            relations=[
                ('r', ('test_database', 'api', 'route'), []),
                ('r', ('test_database', 'public', 'tag'), []),
            ],
        )

        repo._reset_database_schemas()

        dropped = _dropped_schemas(executed)
        assert 'si' in dropped, (
            "A schema holding no relation must be dropped; leaving it "
            "behind makes the next CREATE SCHEMA in the dump fail."
        )
        assert 'api' in dropped
        assert 'public' in dropped

    def test_queries_catalog_not_desc(self):
        """The schema list must come from pg_catalog, not model.desc()."""
        repo, mock_model, executed = _make_repo(
            catalog_schemas=['public', 'si'],
            relations=[('r', ('test_database', 'ghost', 't'), [])],
        )

        repo._reset_database_schemas()

        selects = [q for q in executed if q.lstrip().upper().startswith('SELECT')]
        assert len(selects) == 1, "Expected exactly one catalog lookup"
        assert 'pg_catalog.pg_namespace' in selects[0]

        mock_model.desc.assert_not_called()

        # 'ghost' only exists in desc() output, not in the catalog: it must
        # not be dropped, proving the catalog is the sole source of truth.
        assert 'ghost' not in _dropped_schemas(executed)

    def test_excludes_system_schemas(self):
        """pg_catalog / information_schema / pg_* are filtered by the query."""
        repo, _, executed = _make_repo(catalog_schemas=['public', 'si'])

        repo._reset_database_schemas()

        select = next(q for q in executed if q.lstrip().upper().startswith('SELECT'))
        assert "NOT IN ('pg_catalog', 'information_schema')" in select
        assert "NOT LIKE 'pg\\_%'" in select

    def test_always_includes_half_orm_meta(self):
        """half_orm_meta schemas are dropped even if absent from the catalog."""
        repo, _, executed = _make_repo(catalog_schemas=['public'])

        repo._reset_database_schemas()

        dropped = _dropped_schemas(executed)
        assert 'half_orm_meta' in dropped
        assert 'half_orm_meta.view' in dropped

    def test_recreates_public_schema(self):
        """public is dropped with the rest, then recreated empty."""
        repo, _, executed = _make_repo(catalog_schemas=['public', 'si'])

        repo._reset_database_schemas()

        assert 'public' in _dropped_schemas(executed)
        assert 'CREATE SCHEMA public' in executed
        assert 'GRANT ALL ON SCHEMA public TO public' in executed
        # Recreation must come after the drop.
        assert executed.index('CREATE SCHEMA public') > executed.index(
            'DROP SCHEMA IF EXISTS "public" CASCADE'
        )
