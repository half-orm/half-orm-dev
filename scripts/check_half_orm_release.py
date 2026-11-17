#!/usr/bin/env python3
"""
Verify that a half-orm release compatible with half_orm_dev's constraint
exists on PyPI.

half-orm follows Semantic Versioning from 2.0.0. The constraint is
``>=MIN,<MAJOR+1`` -- MIN the oldest half-orm providing what half_orm_dev
uses, MAJOR its major version -- and half_orm_dev's own major version must be
that same MAJOR: the ``half_orm`` CLI only loads an extension built for the
core's major version.

Without --min-half-orm: reads the constraint from pyproject.toml and validates.
With --min-half-orm VERSION: computes the constraint, validates it, then
    writes it to pyproject.toml and requirements.txt.
With --dev-version VERSION: the release about to be made. It must move
    forward and share half-orm's major version, and is recorded in
    codemeta.json once everything has been checked.

Exits with code 1 (and prints an error) if no compatible release is found,
or if half_orm_dev's major version is not half-orm's.
"""
import argparse
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

ROOT = Path(__file__).parent.parent
PYPROJECT = ROOT / 'pyproject.toml'
REQUIREMENTS = ROOT / 'requirements.txt'
VERSION_FILE = ROOT / 'half_orm_dev' / 'version.txt'
CODEMETA = ROOT / 'codemeta.json'

# `half-orm>=2.0.0,<3` -- the requirement itself, wherever it is written.
_REQUIREMENT_RE = re.compile(r'half-orm(?P<spec>[>=<!~][^"\s]*)')


def _fail(message):
    print(f'ERROR: {message}', file=sys.stderr)
    sys.exit(1)


def _version(text, what):
    try:
        return Version(text)
    except InvalidVersion:
        _fail(f'cannot parse {what} "{text}"')


def compute_constraint(min_half_orm: str) -> str:
    """Return ``>=min_half_orm,<next major``."""
    return f'>={min_half_orm},<{_version(min_half_orm, "half-orm version").major + 1}'


def check_new_version(new: str, current: str) -> None:
    """Refuse a release number that is not a version, or does not move forward."""
    if _version(new, 'new half_orm_dev version') <= _version(current, 'current half_orm_dev version'):
        _fail(f'the new version {new} must be greater than the current one, {current}')


def check_majors(dev_version: str, constraint: str) -> None:
    """Refuse a half_orm_dev whose major version is not half-orm's."""
    match = re.search(r'>=([^,<\s]+)', constraint)
    if not match:
        _fail(f'no lower bound in half-orm{constraint}')
    ho_major = _version(match.group(1), 'half-orm version').major
    dev_major = _version(dev_version, 'half_orm_dev version').major
    if ho_major != dev_major:
        _fail(f'half_orm_dev {dev_version} is not built for half-orm {ho_major}.x: '
              'the half_orm CLI only loads an extension of its own major version')


def read_constraint(path: Path = None) -> str:
    """Read the half-orm constraint declared in pyproject.toml."""
    path = path or PYPROJECT
    match = _REQUIREMENT_RE.search(path.read_text(encoding='utf-8'))
    if not match:
        _fail(f'no half-orm requirement found in {path.name}')
    return match.group('spec')


def _read_current_min_version() -> str:
    """Extract the lower-bound version from the current half-orm constraint.

    e.g. '>=1.0.0rc1,<1.1.0' → '1.0.0rc1'
    Returns empty string if not found or unparseable.
    """
    constraint = read_constraint()
    match = re.search(r'>=([^,<\s]+)', constraint)
    return match.group(1) if match else ''


def sync_constraint(constraint: str, paths=None) -> None:
    """Write the half-orm constraint into pyproject.toml and requirements.txt."""
    for path in paths or (PYPROJECT, REQUIREMENTS):
        text = path.read_text(encoding='utf-8')
        if not _REQUIREMENT_RE.search(text):
            _fail(f'no half-orm requirement found in {path.name}')
        updated = _REQUIREMENT_RE.sub(f'half-orm{constraint}', text, count=1)
        if updated != text:
            path.write_text(updated, encoding='utf-8')
            print(f'  {path.name} updated: half-orm{constraint}')
        else:
            print(f'✓ {path.name} already set to half-orm{constraint}')


def update_codemeta(version: str, constraint: str, path: Path = None) -> None:
    """Record the release in codemeta.json: version, date, half-orm requirement.

    The requirement entry is replaced, or added when there is none, so the
    file says what pyproject.toml says.
    """
    path = path or CODEMETA
    data = json.loads(path.read_text(encoding='utf-8'))
    data['version'] = version
    data['dateModified'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    entry = {
        '@type': 'SoftwareApplication',
        'identifier': 'half-orm',
        'name': 'half-orm',
        'runtimePlatform': 'Python 3',
        'version': constraint,
    }
    requirements = [
        req for req in data.get('softwareRequirements', [])
        if not re.match(r'^half[-_]orm(?![-_]dev)(?![-_]\w)', str(req.get('identifier', '')))
    ]
    data['softwareRequirements'] = sorted(
        requirements + [entry], key=lambda req: str(req.get('identifier', '')).lower())
    path.write_text(json.dumps(data, indent=4, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'  {path.name} updated: version {version}, half-orm{constraint}')


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
    current_min = _read_current_min_version()
    parser.add_argument(
        '--min-half-orm',
        metavar='VERSION',
        default=current_min or None,
        help=(
            f'Minimum half-orm version. Updates pyproject.toml and requirements.txt. '
            f'(current: {current_min or "none"})'
        ),
    )
    parser.add_argument(
        '--dev-version',
        metavar='VERSION',
        help=('The half_orm_dev version about to be released. Checked before '
              'anything is written; defaults to the one in version.txt.'),
    )
    args = parser.parse_args()

    current = VERSION_FILE.read_text(encoding='utf-8').strip()
    if args.dev_version:
        check_new_version(args.dev_version, current)
    dev_version = args.dev_version or current

    if args.min_half_orm:
        constraint = compute_constraint(args.min_half_orm)
    else:
        constraint = read_constraint()
    check_majors(dev_version, constraint)

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

    # Every check passed: only now is anything written, so that a refused
    # release has nothing to undo.
    sync_constraint(constraint)
    if args.dev_version:
        update_codemeta(args.dev_version, constraint)

if __name__ == '__main__':
    main()
