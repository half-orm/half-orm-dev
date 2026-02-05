"""
Migration: Convert pyproject.toml dependency from half_orm to half_orm_dev.

This migration:
1. Creates pyproject.toml from template if it doesn't exist
2. Converts half_orm dependency to half_orm_dev (if present)
3. Deletes Pipfile if it exists (deprecated)

Note: Version update of half_orm_dev is handled automatically by MigrationManager
after each migration.
"""

import os
import re
from pathlib import Path

import click

from half_orm_dev.utils import TEMPLATE_DIRS, hop_version
from half_orm import utils


def get_description():
    """Return migration description."""
    return "Convert pyproject.toml dependency from half_orm to half_orm_dev"


def migrate(repo):
    """
    Execute migration: Convert half_orm to half_orm_dev in pyproject.toml.

    Args:
        repo: Repo instance
    """
    print("Converting pyproject.toml dependency...")

    base_dir = Path(repo.base_dir)
    pyproject_path = base_dir / "pyproject.toml"
    pipfile_path = base_dir / "Pipfile"
    current_version = hop_version()

    # Delete Pipfile if it exists (deprecated)
    if pipfile_path.exists():
        if click.confirm("  Pipfile found (deprecated). Delete it?", default=True):
            try:
                pipfile_path.unlink()
                repo.hgit.add(str(pipfile_path))
                print(f"  ✓ Deleted Pipfile")
            except Exception as e:
                print(f"  Warning: Could not delete Pipfile: {e}")

    # Create pyproject.toml from template if it doesn't exist
    if not pyproject_path.exists():
        print(f"  pyproject.toml not found.")
        if click.confirm("  Create pyproject.toml from template?", default=True):
            try:
                package_name = repo._Repo__config.package_name
                template_path = os.path.join(TEMPLATE_DIRS, 'pyproject.toml')
                template = utils.read(template_path)

                pyproject_content = template.format(
                    dbname=package_name,
                    package_name=package_name,
                    half_orm_dev_version=current_version
                )

                pyproject_path.write_text(pyproject_content)
                repo.hgit.add(str(pyproject_path))
                print(f"  ✓ Created pyproject.toml with half_orm_dev=={current_version}")
                print(f"  ℹ️  Remember to add your other project dependencies to pyproject.toml")
            except Exception as e:
                print(f"  ⚠️  Could not create pyproject.toml: {e}")
        else:
            print(f"  ⚠️  Please create pyproject.toml manually with dependency:")
            print(f'     "half_orm_dev=={current_version}"')
        return

    # Read current content
    content = pyproject_path.read_text()
    modified = False

    # Remove half_orm dependency if present (no confirmation needed)
    if 'half_orm==' in content or 'half_orm>=' in content:
        content = re.sub(
            r'\s*"half_orm[>=]=[\d.a-zA-Z-]+",?\n?',
            '',
            content
        )
        modified = True
        print(f"  ✓ Removed half_orm dependency")

    # Add half_orm_dev if not already present
    if 'half_orm_dev==' not in content and 'half_orm_dev>=' not in content:
        # Find dependencies section and add half_orm_dev
        if 'dependencies = [' in content:
            content = re.sub(
                r'(dependencies = \[)\n',
                f'\\1\n    "half_orm_dev=={current_version}",\n',
                content
            )
            modified = True
            print(f"  ✓ Added half_orm_dev=={current_version}")
        else:
            print(f"  ⚠️  Could not find dependencies section in pyproject.toml")
            print(f"     Please add manually:")
            print(f'     "half_orm_dev=={current_version}"')
    else:
        print(f"  ✓ half_orm_dev already present")

    # Write changes if modified
    if modified:
        pyproject_path.write_text(content)
        repo.hgit.add(str(pyproject_path))
