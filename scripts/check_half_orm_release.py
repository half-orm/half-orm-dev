#!/usr/bin/env python3
"""
Verify that a half-orm release compatible with the current half-orm-dev
version constraint exists on PyPI.

Exits with code 1 (and prints an error) if no compatible release is found.
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

from packaging.specifiers import SpecifierSet
from packaging.version import Version

ROOT = Path(__file__).parent.parent


def _compute_constraint() -> str:
    """Return the half-orm version constraint for the current half-orm-dev version."""
    version_text = (ROOT / 'half_orm_dev' / 'version.txt').read_text(encoding='utf-8').strip()
    match = re.match(r'^(\d+)\.(\d+)\.(\d+)(?:-(.*))?$', version_text)
    if not match:
        print(f'ERROR: cannot parse version "{version_text}"', file=sys.stderr)
        sys.exit(1)

    major, minor, patch, pre_release = match.groups()
    major, minor, patch = int(major), int(minor), int(patch)

    min_ver = f'{major}.{minor}.{patch}a1' if pre_release else f'{major}.{minor}.0'
    max_ver = f'{major}.{minor + 1}.0'
    return f'>={min_ver},<{max_ver}'


def _pypi_versions(package: str) -> list[Version]:
    """Return all versions of *package* available on PyPI."""
    url = f'https://pypi.org/pypi/{package}/json'
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.load(resp)
    except Exception as exc:
        print(f'ERROR: could not reach PyPI ({exc})', file=sys.stderr)
        sys.exit(1)
    return [Version(v) for v in data['releases']]


def main() -> None:
    constraint = _compute_constraint()
    spec = SpecifierSet(constraint, prereleases=True)

    versions = _pypi_versions('half-orm')
    compatible = sorted([v for v in versions if v in spec], reverse=True)

    if not compatible:
        recent = sorted(versions, reverse=True)[:8]
        print(f'ERROR: no half-orm release satisfies {constraint}')
        print(f'  Most recent available: {[str(v) for v in recent]}')
        print()
        print('  Release half-orm first, then rebuild half-orm-dev.')
        sys.exit(1)

    print(f'✓ half-orm {compatible[0]} satisfies {constraint}')


if __name__ == '__main__':
    main()
