"""
Unit tests for TypedDict generation in modules.py.

Tests __get_type_annotation() and __gen_typedict() via module __dict__
(no name mangling at module level in Python).
"""
import pytest
from unittest.mock import Mock

import half_orm_dev.modules as _mod

# Access private module-level functions via __dict__ (no class name-mangling)
_get_type_annotation = _mod.__dict__['_half_orm_dev__get_type_annotation'] \
    if '_half_orm_dev__get_type_annotation' in _mod.__dict__ \
    else _mod.__dict__['__get_type_annotation']
_gen_typedict = _mod.__dict__['_half_orm_dev__gen_typedict'] \
    if '_half_orm_dev__gen_typedict' in _mod.__dict__ \
    else _mod.__dict__['__gen_typedict']


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_field(fieldtype: str) -> Mock:
    f = Mock()
    f._metadata = {'fieldtype': fieldtype}
    return f


def _make_relation(schema: str, table: str, fields: dict, fkeys: dict = None):
    """Return a callable_relation mock with given fields/fkeys.

    fkeys: {constraint_name: (target_schema, target_table)}
    Use '_reverse_fkey_...' prefix for reverse FKs to match half-orm convention.
    """
    rel = Mock()
    rel._t_fqrn = ('db', schema, table)
    rel._ho_fields = {name: _make_field(ft) for name, ft in fields.items()}
    rel._ho_fkeys = {}
    if fkeys:
        for constraint_name, (target_schema, target_table) in fkeys.items():
            target = Mock()
            target._t_fqrn = ('db', target_schema, target_table)
            fkey = Mock(return_value=target)
            rel._ho_fkeys[constraint_name] = fkey
    relation = Mock(return_value=rel)
    return relation


@pytest.fixture(autouse=True)
def clear_typedicts_globals():
    """Isolate each test: clear the module-level globals before and after."""
    _mod.HO_TYPEDICTS_IMPORTS.clear()
    _mod.HO_TYPEDICTS.clear()
    yield
    _mod.HO_TYPEDICTS_IMPORTS.clear()
    _mod.HO_TYPEDICTS.clear()


# ---------------------------------------------------------------------------
# Tests for __get_type_annotation
# ---------------------------------------------------------------------------

class TestGetTypeAnnotation:

    def test_integer_maps_to_int(self):
        type_str, imports = _get_type_annotation(_make_field('integer'))
        assert type_str == 'int'
        assert imports == set()

    def test_text_maps_to_str(self):
        type_str, imports = _get_type_annotation(_make_field('text'))
        assert type_str == 'str'
        assert imports == set()

    def test_boolean_maps_to_bool(self):
        type_str, imports = _get_type_annotation(_make_field('boolean'))
        assert type_str == 'bool'
        assert imports == set()

    def test_numeric_maps_to_float(self):
        type_str, imports = _get_type_annotation(_make_field('numeric'))
        assert type_str == 'float'
        assert imports == set()

    def test_timestamp_maps_to_datetime(self):
        type_str, imports = _get_type_annotation(_make_field('timestamp'))
        assert 'datetime' in type_str
        assert 'datetime' in imports

    def test_uuid_maps_to_uuid(self):
        type_str, imports = _get_type_annotation(_make_field('uuid'))
        assert 'uuid' in type_str.lower()
        assert 'uuid' in imports

    def test_jsonb_maps_to_any(self):
        type_str, imports = _get_type_annotation(_make_field('jsonb'))
        assert type_str == 'Any'
        assert imports == set()

    def test_unknown_type_falls_back_to_any(self):
        type_str, imports = _get_type_annotation(_make_field('custom_pg_type'))
        assert type_str == 'Any'

    def test_array_int_maps_to_list_int(self):
        type_str, imports = _get_type_annotation(_make_field('_int4'))
        assert type_str == 'List[int]'
        assert imports == set()

    def test_array_text_maps_to_list_str(self):
        type_str, imports = _get_type_annotation(_make_field('_text'))
        assert type_str == 'List[str]'
        assert imports == set()

    def test_array_timestamp_maps_to_list_datetime(self):
        type_str, imports = _get_type_annotation(_make_field('_timestamp'))
        assert type_str.startswith('List[')
        assert 'datetime' in type_str
        assert 'datetime' in imports

    def test_array_uuid_maps_to_list_uuid(self):
        type_str, imports = _get_type_annotation(_make_field('_uuid'))
        assert type_str.startswith('List[')
        assert 'uuid' in type_str.lower()


# ---------------------------------------------------------------------------
# Tests for __gen_typedict
# ---------------------------------------------------------------------------

class TestGenTypedict:

    def test_class_name_schema_table(self):
        relation = _make_relation('public', 'user', {'id': 'integer'})
        result = _gen_typedict(relation, {})
        assert 'class PublicUserDict(TypedDict, total=False):' in result

    def test_class_name_compound_table(self):
        relation = _make_relation('public', 'user_profile', {'id': 'integer'})
        result = _gen_typedict(relation, {})
        assert 'class PublicUserProfileDict(TypedDict, total=False):' in result

    def test_total_false_in_signature(self):
        relation = _make_relation('public', 'item', {'id': 'integer'})
        result = _gen_typedict(relation, {})
        assert 'total=False' in result

    def test_int_field_is_optional_int(self):
        relation = _make_relation('public', 'item', {'id': 'integer', 'qty': 'smallint'})
        result = _gen_typedict(relation, {})
        assert '    id: Optional[int]' in result
        assert '    qty: Optional[int]' in result

    def test_str_field_is_optional_str(self):
        relation = _make_relation('public', 'item', {'name': 'text', 'code': 'varchar'})
        result = _gen_typedict(relation, {})
        assert '    name: Optional[str]' in result
        assert '    code: Optional[str]' in result

    def test_array_field_is_optional_list(self):
        relation = _make_relation('public', 'item', {'tags': '_text', 'scores': '_int4'})
        result = _gen_typedict(relation, {})
        assert '    tags: Optional[List[str]]' in result
        assert '    scores: Optional[List[int]]' in result

    def test_empty_relation_body_is_pass(self):
        relation = _make_relation('public', 'empty_table', {})
        result = _gen_typedict(relation, {})
        assert '    pass' in result

    def test_forward_fk_gets_fk_prefix(self):
        """Raw constraint name gets fk_ prefix (half-orm auto-expose convention)."""
        relation = _make_relation(
            'public', 'post', {'id': 'integer'},
            fkeys={'post_author_id_fkey': ('public', 'author')}
        )
        result = _gen_typedict(relation, {})
        assert "    fk_post_author_id_fkey: Optional['PublicAuthorDict']" in result

    def test_reverse_fk_gets_rfk_prefix(self):
        """_reverse_fkey_* constraint name gets rfk_ prefix (half-orm convention)."""
        relation = _make_relation(
            'public', 'author', {'id': 'integer'},
            fkeys={'_reverse_fkey_public_post_author_id': ('public', 'post')}
        )
        result = _gen_typedict(relation, {})
        assert "    rfk_public_post_author_id: Optional[List['PublicPostDict']]" in result

    def test_fk_with_alias_overrides_auto_prefix(self):
        """User alias from Fkeys class takes precedence over fk_/rfk_ auto-naming."""
        relation = _make_relation(
            'public', 'post', {'id': 'integer'},
            fkeys={'post_author_id_fkey': ('public', 'author')}
        )
        result = _gen_typedict(relation, {'writer': 'post_author_id_fkey'})
        assert "    writer: Optional['PublicAuthorDict']" in result
        assert 'fk_post_author_id_fkey' not in result

    def test_self_referential_fk(self):
        relation = _make_relation(
            'public', 'category', {'id': 'integer'},
            fkeys={'category_parent_fkey': ('public', 'category')}
        )
        result = _gen_typedict(relation, {})
        assert "    fk_category_parent_fkey: Optional['PublicCategoryDict']" in result

    def test_datetime_field_populates_imports(self):
        relation = _make_relation('public', 'event', {'created_at': 'timestamp'})
        _gen_typedict(relation, {})
        assert 'datetime' in _mod.HO_TYPEDICTS_IMPORTS

    def test_uuid_field_populates_imports(self):
        relation = _make_relation('public', 'token', {'id': 'uuid'})
        _gen_typedict(relation, {})
        assert 'uuid' in _mod.HO_TYPEDICTS_IMPORTS

    def test_plain_int_does_not_pollute_imports(self):
        relation = _make_relation('public', 'counter', {'n': 'integer'})
        _gen_typedict(relation, {})
        assert _mod.HO_TYPEDICTS_IMPORTS == set()
