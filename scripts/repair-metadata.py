#!/usr/bin/env python3
"""
Repair script for half-orm-dev metadata files.

This script fixes the bug where half_orm_meta.hop_release entries were not
being added during RC/production promotions (fixed in 0.17.3-a5+).

It updates all metadata-X.Y.Z.sql files to include the missing INSERT
statement for the corresponding version.

IMPORTANT: This script modifies files on the ho-prod branch which is typically
protected. You may need to temporarily disable branch protection or pre-commit
hooks before running this script.

Usage:
    cd /path/to/your/project
    python /path/to/half-orm-dev/scripts/repair-metadata.py [--dry-run]

Options:
    --dry-run    Show what would be changed without modifying files
    --verbose    Show detailed information about each file
"""

import argparse
import re
import sys
from pathlib import Path
from typing import List, Tuple, Optional


def parse_version(filename: str) -> Optional[Tuple[int, int, int]]:
    """
    Extract version tuple from metadata filename.

    Args:
        filename: e.g., "metadata-1.2.3.sql"

    Returns:
        Tuple (major, minor, patch) or None if not parseable
    """
    match = re.match(r'metadata-(\d+)\.(\d+)\.(\d+)\.sql$', filename)
    if match:
        return (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return None


def find_hop_release_inserts(content: str) -> List[Tuple[int, int, int]]:
    """
    Find all hop_release INSERT statements in metadata file content.

    Handles both formats:
    - COPY half_orm_meta.hop_release ... FROM stdin;
    - INSERT INTO half_orm_meta.hop_release ...

    Args:
        content: File content

    Returns:
        List of (major, minor, patch) tuples found
    """
    versions = []

    # Pattern for INSERT statements
    # INSERT INTO half_orm_meta.hop_release (major, minor, patch, ...) VALUES (1, 2, 3, ...);
    insert_pattern = re.compile(
        r"INSERT INTO half_orm_meta\.hop_release\s*\([^)]+\)\s*VALUES\s*\((\d+),\s*(\d+),\s*(\d+)",
        re.IGNORECASE
    )

    for match in insert_pattern.finditer(content):
        versions.append((int(match.group(1)), int(match.group(2)), int(match.group(3))))

    # Pattern for COPY format (pg_dump default)
    # COPY half_orm_meta.hop_release (major, minor, patch, ...) FROM stdin;
    # 1	2	3	...
    copy_pattern = re.compile(
        r"COPY half_orm_meta\.hop_release\s*\([^)]+\)\s*FROM stdin;",
        re.IGNORECASE
    )

    for match in copy_pattern.finditer(content):
        # Find the data lines after COPY statement
        start_pos = match.end()
        end_marker = content.find("\\.", start_pos)
        if end_marker == -1:
            continue

        data_section = content[start_pos:end_marker]

        # Parse each data line (tab-separated)
        for line in data_section.strip().split('\n'):
            if line.strip():
                parts = line.split('\t')
                if len(parts) >= 3:
                    try:
                        versions.append((int(parts[0]), int(parts[1]), int(parts[2])))
                    except ValueError:
                        continue

    return versions


def generate_insert_statement(major: int, minor: int, patch: int) -> str:
    """
    Generate INSERT statement for hop_release.

    Args:
        major, minor, patch: Version numbers

    Returns:
        SQL INSERT statement
    """
    return (
        f"-- Added by repair-metadata.py (fix for missing hop_release entries)\n"
        f"INSERT INTO half_orm_meta.hop_release (major, minor, patch, pre_release, pre_release_num) "
        f"VALUES ({major}, {minor}, {patch}, '', '');\n"
    )


def repair_metadata_file(
    filepath: Path,
    dry_run: bool = False,
    verbose: bool = False
) -> Tuple[bool, str]:
    """
    Repair a single metadata file by adding missing hop_release INSERT.

    Args:
        filepath: Path to metadata-X.Y.Z.sql file
        dry_run: If True, don't modify file
        verbose: If True, show detailed output

    Returns:
        Tuple of (was_modified, message)
    """
    filename = filepath.name
    version = parse_version(filename)

    if version is None:
        return False, f"Skipped: cannot parse version from {filename}"

    major, minor, patch = version

    try:
        content = filepath.read_text()
    except Exception as e:
        return False, f"Error reading {filename}: {e}"

    # Find existing hop_release entries
    existing_versions = find_hop_release_inserts(content)

    if verbose:
        print(f"  Found {len(existing_versions)} existing hop_release entries")
        for v in existing_versions:
            print(f"    - {v[0]}.{v[1]}.{v[2]}")

    # Check if this version is already present
    if version in existing_versions:
        return False, f"OK: {filename} already contains entry for {major}.{minor}.{patch}"

    # Generate the INSERT statement
    insert_stmt = generate_insert_statement(major, minor, patch)

    if dry_run:
        return True, f"Would add INSERT for {major}.{minor}.{patch} to {filename}"

    # Add the INSERT at the end of the file
    try:
        with filepath.open('a') as f:
            f.write('\n')
            f.write(insert_stmt)
        return True, f"Fixed: added INSERT for {major}.{minor}.{patch} to {filename}"
    except Exception as e:
        return False, f"Error writing to {filename}: {e}"


def find_model_dir() -> Optional[Path]:
    """
    Find the .hop/model directory in current working directory.

    Returns:
        Path to model directory or None if not found
    """
    cwd = Path.cwd()
    model_dir = cwd / ".hop" / "model"

    if model_dir.is_dir():
        return model_dir

    return None


def main():
    parser = argparse.ArgumentParser(
        description="Repair half-orm-dev metadata files by adding missing hop_release entries.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be changed without modifying files'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show detailed information about each file'
    )
    parser.add_argument(
        '--model-dir',
        type=Path,
        help='Path to model directory (default: .hop/model in current directory)'
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

    print(f"Model directory: {model_dir}")
    print()

    if args.dry_run:
        print("=== DRY RUN MODE - No files will be modified ===")
        print()

    # Warning about branch protection
    print("WARNING: This script modifies files that may be on a protected branch (ho-prod).")
    print("If your pre-commit hooks block the changes, you may need to:")
    print("  1. Temporarily disable branch protection")
    print("  2. Or use: git commit --no-verify")
    print()

    # Find all metadata files
    metadata_files = sorted(model_dir.glob("metadata-*.sql"))

    if not metadata_files:
        print("No metadata-X.Y.Z.sql files found")
        sys.exit(0)

    print(f"Found {len(metadata_files)} metadata files")
    print()

    # Process each file
    modified_count = 0
    ok_count = 0
    error_count = 0

    for filepath in metadata_files:
        if args.verbose:
            print(f"Processing: {filepath.name}")

        modified, message = repair_metadata_file(
            filepath,
            dry_run=args.dry_run,
            verbose=args.verbose
        )

        if "Error" in message:
            error_count += 1
            print(f"  ERROR: {message}")
        elif modified:
            modified_count += 1
            print(f"  {message}")
        else:
            ok_count += 1
            if args.verbose:
                print(f"  {message}")

    # Summary
    print()
    print("=" * 50)
    print(f"Summary:")
    print(f"  Files checked:  {len(metadata_files)}")
    print(f"  Already OK:     {ok_count}")
    print(f"  {'Would fix' if args.dry_run else 'Fixed'}:       {modified_count}")
    if error_count > 0:
        print(f"  Errors:         {error_count}")

    if args.dry_run and modified_count > 0:
        print()
        print("Run without --dry-run to apply changes")

    if modified_count > 0 and not args.dry_run:
        print()
        print("Next steps:")
        print("  1. Review the changes: git diff .hop/model/")
        print("  2. Commit: git add .hop/model/metadata-*.sql && git commit -m 'fix: add missing hop_release entries'")
        print("     (Use --no-verify if pre-commit hooks block the commit)")


if __name__ == "__main__":
    main()
