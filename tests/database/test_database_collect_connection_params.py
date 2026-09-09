"""
Tests for Database._collect_connection_params() host/port resolution.

Host and port are never prompted for: like psql, pg_dump and every other
PostgreSQL client, they come from the explicit option, then PGHOST/PGPORT,
then localhost/5432.

Regression: an empty password (peer/trust auth) used to force host='' and
port='', which both discarded an explicit --port and short-circuited the
PGPORT fallback. `half_orm dev clone` then wrote a configuration naming no
cluster, so the cloned project only worked in a shell that happened to
export PGPORT - on a machine running several clusters it silently targeted
the wrong one.
"""

import os
import pytest
from unittest.mock import patch

from half_orm_dev.database import Database


@pytest.fixture(autouse=True)
def clean_pg_env(monkeypatch):
    """Start each test from an environment with no PG* leaking in."""
    for var in ('PGHOST', 'PGPORT'):
        monkeypatch.delenv(var, raising=False)


def _collect(**options):
    """Collect params with an empty password (peer/trust authentication)."""
    connection_options = {
        'host': None, 'port': None, 'user': 'dev',
        'password': None, 'production': False
    }
    connection_options.update(options)

    with patch('getpass.getpass', return_value=''), \
         patch('builtins.input', return_value=''), \
         patch('builtins.print'):
        return Database._collect_connection_params('probe_db', connection_options)


class TestEmptyPasswordKeepsPortResolution:
    """Peer auth must not discard where to connect."""

    def test_explicit_port_is_kept(self):
        params = _collect(port=5435)
        assert params['port'] == 5435

    def test_pgport_is_used_when_no_explicit_port(self, monkeypatch):
        monkeypatch.setenv('PGPORT', '5435')
        params = _collect()
        assert params['port'] == 5435

    def test_falls_back_to_5432(self):
        params = _collect()
        assert params['port'] == 5432

    def test_explicit_port_wins_over_pgport(self, monkeypatch):
        monkeypatch.setenv('PGPORT', '5433')
        params = _collect(port=5435)
        assert params['port'] == 5435


class TestEmptyPasswordDefaultsToSocket:
    """The socket is the default that goes with peer auth - a default only."""

    def test_socket_when_no_host_given(self):
        params = _collect()
        assert params['host'] == '', "peer auth should default to a local socket"

    def test_explicit_host_is_kept(self):
        params = _collect(host='db.example.com')
        assert params['host'] == 'db.example.com'

    def test_pghost_is_kept(self, monkeypatch):
        monkeypatch.setenv('PGHOST', 'db.example.com')
        params = _collect()
        assert params['host'] == 'db.example.com'

    def test_password_stays_none_for_trust_auth(self):
        params = _collect()
        assert params['password'] is None
