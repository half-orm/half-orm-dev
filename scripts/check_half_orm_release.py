#!/usr/bin/env python3
"""
Verify that a half-orm release compatible with the current constraint exists
on PyPI.

Without --min-half-orm: reads the constraint from requirements.txt and validates.
With --min-half-orm VERSION: computes >=VERSION,<X.Y+1.0 (X.Y from version.txt),
    updates requirements.txt, then validates.

Exits with code 1 (and prints an error) if no compatible release is found.
"""
import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

from packaging.specifiers import SpecifierSet
from packaging.version import Version

ROOT = Path(__file__).parent.parent
REQUIREMENTS = ROOT / 'requirements.txt'


def _upper_bound() -> str:
    """Return the exclusive upper bound derived from half_orm_dev/version.txt."""
    version_text = (ROOT / 'half_orm_dev' / 'version.txt').read_text(encoding='utf-8').strip()
    match = re.match(r'^(\d+)\.(\d+)\.', version_text)
    if not match:
        print(f'ERROR: cannot parse version "{version_text}"', file=sys.stderr)
        sys.exit(1)
    major, minor = int(match.group(1)), int(match.group(2))
    return f'{major}.{minor + 1}.0'


def _compute_constraint(min_half_orm: str) -> str:
    """Return >=min_half_orm,<upper."""
    return f'>={min_half_orm},<{_upper_bound()}'


def _read_constraint() -> str:
    """Read the current half-orm constraint from requirements.txt."""
    for line in REQUIREMENTS.read_text(encoding='utf-8').splitlines():
        if re.match(r'^half-orm[>=<!]', line):
            return line[len('half-orm'):]
    print('ERROR: no half-orm constraint found in requirements.txt', file=sys.stderr)
    sys.exit(1)


def _sync_requirements(constraint: str) -> None:
    """Update the half-orm line in requirements.txt."""
    expected_line = f'half-orm{constraint}'
    lines = REQUIREMENTS.read_text(encoding='utf-8').splitlines()
    new_lines = []
    updated = False
    for line in lines:
        if re.match(r'^half-orm[>=<!]', line):
            if line != expected_line:
                new_lines.append(expected_line)
                updated = True
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
    if updated:
        REQUIREMENTS.write_text('\n'.join(new_lines) + '\n', encoding='utf-8')
        print(f'  requirements.txt updated: half-orm{constraint}')
    else:
        print(f'✓ requirements.txt already set to half-orm{constraint}')


def _pypi_versions(package: str) -> list:
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--min-half-orm',
        metavar='VERSION',
        help='Minimum half-orm version (e.g. 1.0.0rc1). Updates requirements.txt.',
    )
    args = parser.parse_args()

    if args.min_half_orm:
        constraint = _compute_constraint(args.min_half_orm)
        _sync_requirements(constraint)
    else:
        constraint = _read_constraint()
        print(f'✓ requirements.txt: half-orm{constraint}')

    spec = SpecifierSet(constraint, prereleases=True)
    versions = _pypi_versions('half-orm')
    compatible = sorted([v for v in versions if v in spec], reverse=True)

    if not compatible:
        recent = sorted(versions, reverse=True)[:8]
        print(f'ERROR: no half-orm release satisfies half-orm{constraint}')
        print(f'  Most recent available: {[str(v) for v in recent]}')
        print()
        print('  Release half-orm first, then rebuild half-orm-dev.')
        sys.exit(1)

    print(f'✓ half-orm {compatible[0]} satisfies half-orm{constraint}')


if __name__ == '__main__':
    main()
