"""
Tests for Database._get_connection_params().

A port left empty in the configuration must stay empty, so that psql,
pg_dump... resolve it like half_orm's own connection does (libpq reads
PGPORT, then defaults to 5432) instead of being sent to 5432.
"""

import pytest
from unittest.mock import Mock, patch

from half_orm_dev.database import Database


def _database(dbinfo):
    """A Database on a model whose configuration is `dbinfo`."""
    database = object.__new__(Database)
    database._Database__repo = Mock(name='repo')
    database._Database__repo.name = 'my_db'
    database._Database__model = Mock(_dbinfo=dbinfo, _production_mode=False)
    database._Database__connection_params_cache = None
    return database


class TestGetConnectionParamsPort:

    @pytest.mark.parametrize('port', ['', None])
    def test_empty_port_is_left_to_libpq(self, port):
        params = _database({'user': 'dev', 'host': '', 'port': port})._get_connection_params()
        assert params['port'] is None

    def test_missing_port_is_left_to_libpq(self):
        params = _database({'user': 'dev', 'host': ''})._get_connection_params()
        assert params['port'] is None

    def test_configured_port_is_kept(self):
        params = _database({'user': 'dev', 'host': '', 'port': '5435'})._get_connection_params()
        assert params['port'] == 5435

    @patch('half_orm_dev.database.subprocess.run')
    @patch.dict('half_orm_dev.database.os.environ', {'PGPORT': '5435'}, clear=True)
    def test_empty_port_keeps_pgport_for_pg_commands(self, mock_run):
        database = _database({'user': 'dev', 'host': '', 'port': ''})
        database._Database__name = 'my_db'

        database.execute_pg_command('psql', '-c', 'select 1')

        assert mock_run.call_args.kwargs['env']['PGPORT'] == '5435'
