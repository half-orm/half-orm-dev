#!/usr/bin/env python3
"""
Drop PostgreSQL databases left behind by interrupted e2e test runs.

An e2e test creates its database through `half_orm dev init` / `clone`
and drops it in fixture teardown. A hard interruption (Ctrl-C, SIGKILL,
a machine going down) skips that teardown, and the databases pile up -
enough of them to fill a disk.

Only names matching the patterns the e2e fixtures generate are ever
touched, and every match is printed before anything is dropped:

    hop_e2e_<8 hex>            e2e_environment
    hop_e2e_<8 hex>_prod       production_environment
    hop_actor2_<8 hex>         test_partial_sync_recovery
    hop_clone_<8 hex>          test_clone_workflow
    hop_custom_<8 hex>         test_clone_workflow
    alt_db_<8 hex>             test_clone_workflow
    patch_alt_<8 hex>          test_clone_workflow

Databases with an open connection are skipped: they most likely belong
to a test run in progress.

Usage:
    scripts/drop-stale-e2e-databases.py            # list, then confirm
    scripts/drop-stale-e2e-databases.py --dry-run  # list only
    scripts/drop-stale-e2e-databases.py --yes      # no confirmation

Connection settings come from the usual PG* environment variables
(PGHOST, PGPORT, PGUSER, PGPASSWORD).
"""

import argparse
import os
import re
import subprocess
import sys

# Anchored on the exact shapes the fixtures generate: a random 8-hex
# suffix. A real database is never named like this by accident.
STALE_DB_PATTERN = re.compile(
    r'^(?:'
    r'hop_e2e_[0-9a-f]{8}(?:_prod)?'
    r'|hop_actor[12]_[0-9a-f]{8}'
    r'|hop_clone_[0-9a-f]{8}'
    r'|hop_custom_[0-9a-f]{8}'
    r'|alt_db_[0-9a-f]{8}'
    r'|patch_alt_[0-9a-f]{8}'
    r')$'
)

LIST_QUERY = """
SELECT d.datname,
       pg_size_pretty(pg_database_size(d.datname)),
       (SELECT count(*) FROM pg_stat_activity a WHERE a.datname = d.datname)
FROM pg_database d
WHERE NOT d.datistemplate
ORDER BY d.datname
"""


def psql_env():
    env = os.environ.copy()
    env.setdefault('PGHOST', 'localhost')
    return env


def list_databases():
    """Return [(name, size, connections)] for every non-template database."""
    result = subprocess.run(
        ['psql', '-d', 'postgres', '-tAF', '|', '-c', LIST_QUERY],
        capture_output=True, text=True, env=psql_env()
    )
    if result.returncode != 0:
        sys.exit(f"Could not list databases:\n{result.stderr.strip()}")

    rows = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        name, size, connections = line.split('|')
        rows.append((name, size, int(connections)))
    return rows


def drop(db_name):
    """Drop one database; returns an error message, or None on success."""
    result = subprocess.run(
        ['dropdb', '--if-exists', '--force', db_name],
        capture_output=True, text=True, env=psql_env()
    )
    return None if result.returncode == 0 else result.stderr.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    parser.add_argument('--dry-run', action='store_true',
                        help="list the stale databases and stop")
    parser.add_argument('--yes', '-y', action='store_true',
                        help="drop without asking for confirmation")
    args = parser.parse_args()

    stale = []
    busy = []
    for name, size, connections in list_databases():
        if not STALE_DB_PATTERN.match(name):
            continue
        (busy if connections else stale).append((name, size, connections))

    for name, size, connections in busy:
        print(f"  skipped {name} ({size}) - {connections} open connection(s), "
              f"a test run may be using it")

    if not stale:
        print("No stale e2e database to drop.")
        return 0

    print(f"\n{len(stale)} stale e2e database(s) on "
          f"{psql_env()['PGHOST']}:{os.environ.get('PGPORT', '5432')}:")
    for name, size, _ in stale:
        print(f"  {name} ({size})")

    if args.dry_run:
        return 0

    if not args.yes:
        answer = input(f"\nDrop these {len(stale)} database(s)? [y/N] ")
        if answer.strip().lower() not in ('y', 'yes'):
            print("Aborted, nothing dropped.")
            return 1

    dropped = 0
    for name, _, _ in stale:
        error = drop(name)
        if error:
            print(f"  ✗ {name}: {error}", file=sys.stderr)
        else:
            dropped += 1

    print(f"\nDropped {dropped}/{len(stale)} database(s).")
    return 0 if dropped == len(stale) else 1


if __name__ == '__main__':
    sys.exit(main())
