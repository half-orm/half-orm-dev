"""
Migration: Add async support to project __init__.py, conftest.py and pyproject.toml.

This migration (opt-in):
1. Adds aconnect() / adisconnect() helpers to <package>/__init__.py
2. Adds _async_pool fixture and pytest-asyncio import to tests/conftest.py
3. Adds pytest-asyncio to [project.optional-dependencies] dev in pyproject.toml
4. Sets asyncio_mode = "auto" in [tool.pytest.ini_options]

All changes are proposed interactively — the user can decline each step.
See 01_update_default_tests.py for relation test file regeneration.
"""

import re
from pathlib import Path


def get_description():
    """Return migration description."""
    return "Add async support (aconnect/adisconnect, pytest-asyncio)"


_ACONNECT_BLOCK = '''

async def aconnect():
    """Establish the async connection pool.

    Call once at application startup (tests: handled by conftest.py fixture).
    Cannot be called at module level — requires a running event loop.

    Example (FastAPI):
        @asynccontextmanager
        async def lifespan(app):
            await {package_name}.aconnect()
            yield
            await {package_name}.adisconnect()
    """
    await MODEL.aconnect()


async def adisconnect():
    """Close the async connection pool. Call at application shutdown."""
    await MODEL.adisconnect()
'''

_ASYNC_POOL_FIXTURE = '''

@pytest_asyncio.fixture(scope="session", autouse=True)
async def _async_pool():
    """Establish and tear down the async connection pool for the test session."""
    await aconnect()
    yield
    await adisconnect()
'''


def migrate(repo):
    """Execute migration: add async support to the project."""
    import click

    base_dir = Path(repo.base_dir)
    package_name = repo._Repo__config.package_name

    _migrate_init(repo, base_dir, package_name, click)
    _migrate_conftest(repo, base_dir, package_name, click)
    _migrate_pyproject(repo, base_dir, click)


def _migrate_init(repo, base_dir, package_name, click):
    """Add aconnect/adisconnect to <package>/__init__.py."""
    init_path = base_dir / package_name / '__init__.py'
    if not init_path.exists():
        print(f"  ⚠️  {init_path} not found, skipping.")
        return

    content = init_path.read_text()
    if 'aconnect' in content:
        print(f"  ✓ {package_name}/__init__.py already has async support.")
        return

    if not click.confirm(
        f"  Add aconnect()/adisconnect() to {package_name}/__init__.py?",
        default=True
    ):
        return

    block = _ACONNECT_BLOCK.format(package_name=package_name)
    init_path.write_text(content + block)
    repo.hgit.add(str(init_path))
    print(f"  ✓ Added aconnect()/adisconnect() to {package_name}/__init__.py")


def _migrate_conftest(repo, base_dir, package_name, click):
    """Add pytest-asyncio import and _async_pool fixture to tests/conftest.py."""
    conftest_path = base_dir / 'tests' / 'conftest.py'
    if not conftest_path.exists():
        print(f"  ⚠️  tests/conftest.py not found, skipping.")
        return

    content = conftest_path.read_text()
    if '_async_pool' in content:
        print(f"  ✓ tests/conftest.py already has async fixture.")
        return

    if not click.confirm(
        "  Add _async_pool fixture to tests/conftest.py?",
        default=True
    ):
        return

    # Add pytest_asyncio import after existing imports
    if 'import pytest_asyncio' not in content:
        content = content.replace(
            'import pytest\n',
            'import pytest\nimport pytest_asyncio\n'
        )

    # Add aconnect/adisconnect to import from package
    if f'from {package_name} import' in content:
        content = re.sub(
            rf'from {package_name} import ([^\n]+)',
            lambda m: (
                m.group(0)
                if 'aconnect' in m.group(1)
                else f'from {package_name} import {m.group(1).rstrip()}, aconnect, adisconnect'
            ),
            content
        )
    elif f'import {package_name}' not in content:
        content += f'\nfrom {package_name} import aconnect, adisconnect\n'

    # Append fixture before the custom_conftest try/except block (or at end)
    if 'custom_conftest' in content:
        content = content.replace(
            '\ntry:\n    from .custom_conftest import *',
            _ASYNC_POOL_FIXTURE + '\ntry:\n    from .custom_conftest import *'
        )
    else:
        content += _ASYNC_POOL_FIXTURE

    conftest_path.write_text(content)
    repo.hgit.add(str(conftest_path))
    print(f"  ✓ Added _async_pool fixture to tests/conftest.py")


def _migrate_pyproject(repo, base_dir, click):
    """Add pytest-asyncio to pyproject.toml."""
    pyproject_path = base_dir / 'pyproject.toml'
    if not pyproject_path.exists():
        print(f"  ⚠️  pyproject.toml not found, skipping.")
        return

    content = pyproject_path.read_text()

    if 'pytest-asyncio' in content:
        print(f"  ✓ pyproject.toml already has pytest-asyncio.")
    elif click.confirm(
        "  Add pytest-asyncio to [project.optional-dependencies] dev in pyproject.toml?",
        default=True
    ):
        if '[project.optional-dependencies]' in content:
            content = re.sub(
                r'(\[project\.optional-dependencies\]\s*\ndev\s*=\s*\[)',
                r'\1\n    "pytest-asyncio",',
                content
            )
        else:
            content += (
                '\n[project.optional-dependencies]\n'
                'dev = [\n'
                '    "pytest",\n'
                '    "pytest-asyncio",\n'
                ']\n'
            )
        print(f"  ✓ Added pytest-asyncio to pyproject.toml")

    if 'asyncio_mode' not in content:
        if '[tool.pytest.ini_options]' in content:
            content = content.replace(
                '[tool.pytest.ini_options]\n',
                '[tool.pytest.ini_options]\nasyncio_mode = "auto"\n'
            )
            print(f"  ✓ Set asyncio_mode = \"auto\" in [tool.pytest.ini_options]")

    pyproject_path.write_text(content)
    repo.hgit.add(str(pyproject_path))
