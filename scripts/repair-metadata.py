#!/usr/bin/env python3
"""
Repair script for half-orm-dev metadata files.

This script regenerates all metadata-X.Y.Z.sql files with correct hop_release
entries by:
1. Clearing half_orm_meta.hop_release (keeping only 0.0.0)
2. For each version tag (vX.Y.Z or vX.Y.Z-rcN):
   - Insert the version with the tag's date
   - Generate metadata-X.Y.Z.sql (or metadata-X.Y.Z-rcN.sql)

Usage:
    cd /path/to/your/project
    python /path/to/half-orm-dev/scripts/repair-metadata.py [--dry-run]

Options:
    --dry-run    Show what would be done without modifying anything
    --verbose    Show detailed information
"""

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional


def get_version_tags() -> List[Tuple[str, str, datetime]]:
    """
    Get all version tags with their dates from git.

    Returns:
        List of (tag_name, version_string, date) tuples sorted by version.
        tag_name: e.g., "v0.1.0", "v0.1.0-rc1"
        version_string: e.g., "0.1.0", "0.1.0-rc1"
        date: datetime object
    """
    result = subprocess.run(
        ['git', 'tag', '--format=%(refname:short) %(creatordate:iso)'],
        capture_output=True, text=True, check=True
    )

    tags = []
    for line in result.stdout.strip().split('\n'):
        if not line.strip():
            continue

        parts = line.split(' ', 1)
        if len(parts) != 2:
            continue

        tag_name, date_str = parts

        # Match vX.Y.Z or vX.Y.Z-rcN
        match = re.match(r'^v(\d+\.\d+\.\d+(?:-rc\d+)?)$', tag_name)
        if not match:
            continue

        version_str = match.group(1)

        # Parse date (format: "2025-11-21 15:09:14 +0100")
        try:
            # Remove timezone for simpler parsing
            date_part = ' '.join(date_str.split()[:2])
            date = datetime.strptime(date_part, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            continue

        tags.append((tag_name, version_str, date))

    # Sort by version (handle X.Y.Z and X.Y.Z-rcN)
    def version_key(item):
        version_str = item[1]
        # Split base version and rc part
        if '-rc' in version_str:
            base, rc = version_str.split('-rc')
            rc_num = int(rc)
        else:
            base = version_str
            rc_num = 9999  # Production comes after all RCs

        parts = [int(p) for p in base.split('.')]
        return (*parts, rc_num)

    return sorted(tags, key=version_key)


def parse_version_string(version_str: str) -> Tuple[int, int, int, str, str]:
    """
    Parse version string into components.

    Args:
        version_str: e.g., "0.1.0" or "0.1.0-rc1"

    Returns:
        Tuple of (major, minor, patch, pre_release, pre_release_num)
    """
    if '-rc' in version_str:
        base, rc = version_str.split('-rc')
        pre_release = 'rc'
        pre_release_num = rc
    else:
        base = version_str
        pre_release = ''
        pre_release_num = ''

    parts = base.split('.')
    return (int(parts[0]), int(parts[1]), int(parts[2]), pre_release, pre_release_num)


def find_model_dir() -> Optional[Path]:
    """Find the .hop/model directory in current working directory."""
    cwd = Path.cwd()
    model_dir = cwd / ".hop" / "model"

    if model_dir.is_dir():
        return model_dir
    return None


def get_database_name() -> Optional[str]:
    """Get database name from half_orm config."""
    try:
        from half_orm.model import Model
        model = Model._model
        if model:
            return model._dbname
    except:
        pass

    # Try reading from .hop/config
    config_path = Path.cwd() / ".hop" / "config"
    if config_path.exists():
        import configparser
        config = configparser.ConfigParser()
        config.read(config_path)
        if 'database' in config and 'name' in config['database']:
            return config['database']['name']

    return None


def clear_hop_release_table(db_name: str, dry_run: bool = False) -> None:
    """
    Clear hop_release table keeping only 0.0.0.

    Args:
        db_name: Database name
        dry_run: If True, only show what would be done
    """
    sql = "DELETE FROM half_orm_meta.hop_release WHERE NOT (major = 0 AND minor = 0 AND patch = 0);"

    if dry_run:
        print(f"Would execute: {sql}")
        return

    subprocess.run(
        ['psql', '-d', db_name, '-c', sql],
        check=True, capture_output=True
    )


def insert_version(db_name: str, major: int, minor: int, patch: int,
                   pre_release: str, pre_release_num: str,
                   date: datetime, dry_run: bool = False) -> None:
    """
    Insert a version into hop_release table.

    Args:
        db_name: Database name
        major, minor, patch: Version components
        pre_release: 'rc' or ''
        pre_release_num: RC number or ''
        date: Release date
        dry_run: If True, only show what would be done
    """
    date_str = date.strftime('%Y-%m-%d')
    time_str = date.strftime('%H:%M:%S')

    sql = f"""INSERT INTO half_orm_meta.hop_release
              (major, minor, patch, pre_release, pre_release_num, date, time)
              VALUES ({major}, {minor}, {patch}, '{pre_release}', '{pre_release_num}', '{date_str}', '{time_str}');"""

    if dry_run:
        print(f"Would execute: {sql}")
        return

    subprocess.run(
        ['psql', '-d', db_name, '-c', sql],
        check=True, capture_output=True
    )


def generate_metadata_file(db_name: str, version_str: str, model_dir: Path,
                           dry_run: bool = False) -> Path:
    """
    Generate metadata-X.Y.Z.sql file using pg_dump.

    Only keeps COPY blocks to avoid version-specific SET commands
    and ensure compatibility across PostgreSQL versions.

    Args:
        db_name: Database name
        version_str: Version string (e.g., "0.1.0" or "0.1.0-rc1")
        model_dir: Path to model directory
        dry_run: If True, only show what would be done

    Returns:
        Path to generated file
    """
    metadata_file = model_dir / f"metadata-{version_str}.sql"

    if dry_run:
        print(f"Would generate: {metadata_file}")
        return metadata_file

    # Dump to stdout
    result = subprocess.run([
        'pg_dump', db_name,
        '--data-only',
        '--table=half_orm_meta.database',
        '--table=half_orm_meta.hop_release',
        '--table=half_orm_meta.hop_release_issue',
    ], check=True, capture_output=True, text=True)

    # Filter to keep only COPY blocks (COPY ... FROM stdin; ... \.)
    filtered_lines = []
    in_copy_block = False
    for line in result.stdout.split('\n'):
        if line.startswith('COPY '):
            in_copy_block = True
        if in_copy_block:
            filtered_lines.append(line)
        if line == '\\.':
            in_copy_block = False
            filtered_lines.append('')  # Empty line between blocks

    metadata_file.write_text('\n'.join(filtered_lines))

    return metadata_file


def main():
    parser = argparse.ArgumentParser(
        description="Regenerate half-orm-dev metadata files from git tags.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without modifying anything'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show detailed information'
    )
    parser.add_argument(
        '--database',
        type=str,
        help='Database name (auto-detected if not specified)'
    )
    parser.add_argument(
        '--model-dir',
        type=Path,
        help='Path to model directory (default: .hop/model)'
    )

    args = parser.parse_args()

    # Find model directory
    if args.model_dir:
        model_dir = args.model_dir
    else:
        model_dir = find_model_dir()

    if model_dir is None or not model_dir.is_dir():
        print("Error: Could not find .hop/model directory", file=sys.stderr)
        print("Make sure you're in a half-orm-dev managed project directory", file=sys.stderr)
        sys.exit(1)

    # Get database name
    db_name = args.database or get_database_name()
    if not db_name:
        print("Error: Could not determine database name", file=sys.stderr)
        print("Use --database option to specify it", file=sys.stderr)
        sys.exit(1)

    print(f"Model directory: {model_dir}")
    print(f"Database: {db_name}")
    print()

    if args.dry_run:
        print("=== DRY RUN MODE - No changes will be made ===")
        print()

    # Get version tags
    tags = get_version_tags()

    if not tags:
        print("No version tags found (expected format: vX.Y.Z or vX.Y.Z-rcN)")
        sys.exit(0)

    print(f"Found {len(tags)} version tags")
    print()

    # Step 1: Clear hop_release table (keep 0.0.0)
    print("Step 1: Clearing hop_release table (keeping 0.0.0)...")
    clear_hop_release_table(db_name, dry_run=args.dry_run)
    print("  Done")
    print()

    # Step 2: Process each version
    print("Step 2: Processing versions...")
    for tag_name, version_str, date in tags:
        major, minor, patch, pre_release, pre_release_num = parse_version_string(version_str)

        if args.verbose:
            print(f"  {tag_name} -> {version_str} ({date})")

        # Insert version with correct date
        insert_version(
            db_name, major, minor, patch,
            pre_release, pre_release_num, date,
            dry_run=args.dry_run
        )

        # Generate metadata file
        metadata_file = generate_metadata_file(
            db_name, version_str, model_dir,
            dry_run=args.dry_run
        )

        print(f"  ✓ {version_str} ({date.strftime('%Y-%m-%d')})")

    print()
    print("=" * 50)
    print(f"Summary:")
    print(f"  Versions processed: {len(tags)}")

    if not args.dry_run:
        print()
        print("Next steps:")
        print("  1. Review the changes: git status")
        print("  2. Commit: git add .hop/model/metadata-*.sql && git commit -m 'fix: regenerate metadata files'")


if __name__ == "__main__":
    main()
