"""
Tests for __get_fkeys in modules.py.

The function reads the Fkeys dict from a module file using AST — without
importing the module.  This avoids sys.path issues during `hop migrate`
where the project package may not be importable.
"""
import pytest
from pathlib import Path
from unittest.mock import Mock

import half_orm_dev.modules as _mod

_get_fkeys = _mod.__dict__['__get_fkeys']


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_module(tmp_path: Path, class_name: str, fkeys: str | None = None,
                  extra_class: str = '') -> str:
    """Write a minimal module file and return its path as a string."""
    fkeys_block = f'    Fkeys = {fkeys}\n' if fkeys is not None else ''
    content = f'''\
from half_orm.model import register

class {class_name}:
    """Docstring."""
{fkeys_block}{extra_class}
'''
    module_path = tmp_path / f'{class_name.lower()}.py'
    module_path.write_text(content, encoding='utf-8')
    return str(module_path)


def _make_repo(tmp_path: Path) -> Mock:
    repo = Mock()
    repo.base_dir = str(tmp_path)
    return Mock()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGetFkeys:

    def test_returns_empty_when_file_does_not_exist(self, tmp_path):
        repo = _make_repo(tmp_path)
        result = _get_fkeys(repo, 'Post', str(tmp_path / 'missing.py'))
        assert result == {}

    def test_returns_empty_when_class_has_no_fkeys(self, tmp_path):
        repo = _make_repo(tmp_path)
        path = _write_module(tmp_path, 'Post')
        result = _get_fkeys(repo, 'Post', path)
        assert result == {}

    def test_reads_fkeys_with_user_aliases(self, tmp_path):
        repo = _make_repo(tmp_path)
        fkeys = "{'rfk_groups': '_reverse_fkey_group', 'fk_owner': 'fk_post_owner'}"
        path = _write_module(tmp_path, 'Post', fkeys=fkeys)
        result = _get_fkeys(repo, 'Post', path)
        assert result == {
            'rfk_groups': '_reverse_fkey_group',
            'fk_owner': 'fk_post_owner',
        }

    def test_returns_empty_for_wrong_class_name(self, tmp_path):
        repo = _make_repo(tmp_path)
        fkeys = "{'rfk_foo': '_reverse_fkey_foo'}"
        path = _write_module(tmp_path, 'Post', fkeys=fkeys)
        result = _get_fkeys(repo, 'Comment', path)
        assert result == {}

    def test_reads_fkeys_with_raw_default_names(self, tmp_path):
        """Raw default names (no user aliases) are returned as-is."""
        repo = _make_repo(tmp_path)
        fkeys = "{'rfk_odj_access_group_post_data_id': '_reverse_fkey_odj_access_group_post_data_id'}"
        path = _write_module(tmp_path, 'Post', fkeys=fkeys)
        result = _get_fkeys(repo, 'Post', path)
        assert result == {
            'rfk_odj_access_group_post_data_id': '_reverse_fkey_odj_access_group_post_data_id',
        }

    def test_does_not_require_package_on_sys_path(self, tmp_path):
        """AST parsing works even if the package is not importable.

        Regression test: the previous importlib-based implementation would
        silently return {} when the project package was not on sys.path
        (e.g. during `hop migrate`), causing developer aliases to be lost.
        """
        import sys
        repo = _make_repo(tmp_path)
        fkeys = "{'my_alias': '_reverse_fkey_constraint'}"
        # Use a package name that is definitely not installed
        pkg_dir = tmp_path / 'not_a_real_package_xyzzy'
        pkg_dir.mkdir()
        module_path = pkg_dir / 'somemodel.py'
        module_path.write_text(
            f'class SomeModel:\n    Fkeys = {fkeys}\n', encoding='utf-8'
        )
        assert 'not_a_real_package_xyzzy' not in sys.modules
        result = _get_fkeys(repo, 'SomeModel', str(module_path))
        assert result == {'my_alias': '_reverse_fkey_constraint'}

    def test_returns_empty_on_syntax_error(self, tmp_path):
        """Malformed files return {} gracefully."""
        repo = _make_repo(tmp_path)
        bad_path = tmp_path / 'bad.py'
        bad_path.write_text('class Broken(\n    invalid syntax {{{\n', encoding='utf-8')
        result = _get_fkeys(repo, 'Broken', str(bad_path))
        assert result == {}
