#-*- coding: utf-8 -*-
"""
Minimal setup.py for dynamic half_orm dependency calculation.

Most configuration is in pyproject.toml. This file exists only to add
the dynamically calculated half_orm version constraint.
"""

import re
from pathlib import Path
from setuptools import setup


# Special minimum version requirements for half_orm
# List of (major, minor, min_patch, max_patch, required_half_orm_version)
# Example: (0, 17, 3, 5, '0.17.1') means:
#   for half_orm_dev 0.17.x where 3 <= x < 5, require half_orm >= 0.17.1
HALF_ORM_MIN_VERSIONS = [
    (0, 17, 3, None, '0.17.1'),  # 0.17.3+ requires half_orm >= 0.17.1 (CustomGroup support)
]


def get_half_orm_version_constraint():
    """
    Calculate half_orm version constraint from half_orm_dev version.

    For version X.Y.Z[-xxx], returns: half_orm>=X.Y.MIN,<X.(Y+1).0
    where MIN is determined by HALF_ORM_MIN_VERSIONS or defaults to 0
    """
    version_file = Path(__file__).parent / "half_orm_dev" / "version.txt"
    version_text = version_file.read_text(encoding="utf-8").strip()

    # Parse version with regex to handle X.Y.Z[-suffix]
    match = re.match(r'^(\d+)\.(\d+)\.(\d+)(?:-.*)?$', version_text)

    if not match:
        raise ValueError(f"Invalid version format in version.txt: {version_text}")

    major, minor, patch = match.groups()
    major, minor, patch = int(major), int(minor), int(patch)

    # Check for special minimum version requirements
    min_version = f"{major}.{minor}.0"  # Default
    for req_major, req_minor, min_patch, max_patch, required_version in HALF_ORM_MIN_VERSIONS:
        if major == req_major and minor == req_minor:
            # Check if patch is in range [min_patch, max_patch)
            if patch >= min_patch:
                if max_patch is None or patch < max_patch:
                    min_version = required_version
                    break

    max_version = f"{major}.{minor + 1}.0"

    return f"half_orm>={min_version},<{max_version}"


# Call setup with all dependencies (including dynamic half_orm constraint)
# All other configuration is in pyproject.toml
setup(
    install_requires=[
        "GitPython",
        "click",
        "pydash",
        "pytest",
        get_half_orm_version_constraint(),
        'tomli>=2.0.0; python_version < "3.11"',
        "tomli_w>=1.0.0",
    ]
)
