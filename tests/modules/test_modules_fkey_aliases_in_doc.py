"""
Tests for __apply_fkey_aliases_to_doc in modules.py.

Regression: generate() called automatically during migration would regenerate
the docstring Fkeys block with raw constraint names, overwriting developer-defined
aliases and causing spurious merge conflicts.

Fix: __apply_fkey_aliases_to_doc substitutes known aliases in the docstring.
"""
import pytest
from unittest.mock import Mock

import half_orm_dev.modules as _mod

_apply_fkey_aliases_to_doc = _mod.__dict__['__apply_fkey_aliases_to_doc']


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rel(fkey_names):
    """Build a minimal relation mock with the given constraint names."""
    rel = Mock()
    rel._ho_fkeys = {name: Mock() for name in fkey_names}
    return rel


def _make_doc(fkeys_dict):
    """Build a documentation string with a Fkeys block matching fkeys_dict."""
    lines = ["    Some relation description.\n", "        Fkeys = {"]
    for alias, constraint in fkeys_dict.items():
        lines.append(f"            '{alias}': '{constraint}',")
    lines.append("        }")
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestApplyFkeyAliasesInDoc:

    def test_no_existing_fkeys_keeps_default_names(self):
        """Without user aliases the docstring keeps rfk_/fk_ default names."""
        rel = _make_rel(['_reverse_fkey_foo_bar', 'my_constraint'])
        doc = _make_doc({
            'rfk_foo_bar': '_reverse_fkey_foo_bar',
            'fk_my_constraint': 'my_constraint',
        })
        result = _apply_fkey_aliases_to_doc(doc, rel, existing_fkeys={})
        assert "'rfk_foo_bar': '_reverse_fkey_foo_bar'" in result
        assert "'fk_my_constraint': 'my_constraint'" in result

    def test_existing_alias_replaces_default_name(self):
        """A constraint with a user alias uses the alias in the docstring."""
        rel = _make_rel(['_reverse_fkey_odj_access_group_post_data_id'])
        doc = _make_doc({
            'rfk_odj_access_group_post_data_id': '_reverse_fkey_odj_access_group_post_data_id',
        })
        existing_fkeys = {
            'rfk_groups_accesses': '_reverse_fkey_odj_access_group_post_data_id',
        }
        result = _apply_fkey_aliases_to_doc(doc, rel, existing_fkeys)
        assert "'rfk_groups_accesses': '_reverse_fkey_odj_access_group_post_data_id'" in result
        assert 'rfk_odj_access_group_post_data_id' not in result

    def test_mixed_aliased_and_new_constraints(self):
        """Aliased constraints use aliases; new ones fall back to defaults."""
        rel = _make_rel([
            '_reverse_fkey_existing',
            '_reverse_fkey_new',
            'direct_fk',
        ])
        doc = _make_doc({
            'rfk_existing': '_reverse_fkey_existing',
            'rfk_new': '_reverse_fkey_new',
            'fk_direct_fk': 'direct_fk',
        })
        existing_fkeys = {
            'my_alias': '_reverse_fkey_existing',
        }
        result = _apply_fkey_aliases_to_doc(doc, rel, existing_fkeys)
        assert "'my_alias': '_reverse_fkey_existing'" in result
        assert "'rfk_new': '_reverse_fkey_new'" in result
        assert "'fk_direct_fk': 'direct_fk'" in result
        assert 'rfk_existing' not in result

    def test_no_fkeys_returns_documentation_unchanged(self):
        """Relations with no foreign keys: documentation is returned as-is."""
        rel = _make_rel([])
        doc = "    Some relation with no fkeys.\n"
        result = _apply_fkey_aliases_to_doc(doc, rel, existing_fkeys={})
        assert result == doc

    def test_all_constraints_aliased(self):
        """All constraints aliased → docstring shows only aliases, no raw names."""
        rel = _make_rel(['_reverse_fkey_a', '_reverse_fkey_b', 'fk_c'])
        doc = _make_doc({
            'rfk_a': '_reverse_fkey_a',
            'rfk_b': '_reverse_fkey_b',
            'fk_fk_c': 'fk_c',
        })
        existing_fkeys = {
            'alias_a': '_reverse_fkey_a',
            'alias_b': '_reverse_fkey_b',
            'alias_c': 'fk_c',
        }
        result = _apply_fkey_aliases_to_doc(doc, rel, existing_fkeys)
        assert "'alias_a': '_reverse_fkey_a'" in result
        assert "'alias_b': '_reverse_fkey_b'" in result
        assert "'alias_c': 'fk_c'" in result
        assert 'rfk_a' not in result
        assert 'rfk_b' not in result
        assert 'fk_fk_c' not in result