"""
Pytest configuration for CLI tests.

CLI tests use unittest.mock.patch() which has different behavior
across Python versions. These tests require Python 3.11+ due to
changes in how mock.patch() resolves attributes in decorated functions.

See: https://github.com/python/cpython/issues/117860
"""

import sys
import pytest


def pytest_collection_modifyitems(session, config, items):
    """
    Skip all CLI tests on Python < 3.11.

    Python 3.11 introduced changes to unittest.mock.patch() attribute
    resolution that affect Click-decorated commands. CLI tests will
    fail on Python 3.8-3.10 with:

        AttributeError: <Command XXX> does not have the attribute 'Repo'

    This is a known Python behavior change, not a bug in our code.
    """
    if sys.version_info >= (3, 11):
        # Python 3.11+: tests work normally
        return

    # Python < 3.11: skip all tests in tests/cli/
    skip_marker = pytest.mark.skip(
        reason=(
            "CLI tests require Python 3.11+ due to unittest.mock.patch() "
            "behavior changes with Click decorators. "
            "See: https://github.com/python/cpython/issues/117860"
        )
    )

    for item in items:
        # Skip only tests in this directory (tests/cli/)
        if "tests/cli" in str(item.fspath) or "tests\\cli" in str(item.fspath):
            item.add_marker(skip_marker)
