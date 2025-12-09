#-*- coding: utf-8 -*-
"""
Minimal setup.py for dynamic half_orm dependency calculation.

Most configuration is in pyproject.toml. This file exists only to add
the dynamically calculated half_orm version constraint.
"""

import re
from pathlib import Path
from setuptools import setup


def get_half_orm_version_constraint():
    """
    Calculate half_orm version constraint from half_orm_dev version.

    For version X.Y.Z[-xxx], returns: half_orm>=X.Y.0,<X.(Y+1).0
    """
    version_file = Path(__file__).parent / "half_orm_dev" / "version.txt"
    version_text = version_file.read_text(encoding="utf-8").strip()

    # Parse version with regex to handle X.Y.Z[-suffix]
    match = re.match(r'^(\d+)\.(\d+)\.(\d+)(?:-.*)?$', version_text)

    if not match:
        raise ValueError(f"Invalid version format in version.txt: {version_text}")

    major, minor, patch = match.groups()
    major, minor = int(major), int(minor)

    # Generate constraint: half_orm>=X.Y.0,<X.(Y+1).0
    min_version = f"{major}.{minor}.0"
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
