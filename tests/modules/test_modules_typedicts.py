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
_gen_typedict_raw = _mod.__dict__['_half_orm_dev__gen_typedict'] \
    if '_half_orm_dev__gen_typedict' in _mod.__dict__ \
    else _mod.__dict__['__gen_typedict']
_gen_json_typedicts = _mod.__dict__['_half_orm_dev__gen_json_typedicts'] \
    if '_half_orm_dev__gen_json_typedicts' in _mod.__dict__ \
    else _mod.__dict__['__gen_json_typedicts']
_json_scalar_type = _mod.__dict__['_half_orm_dev__json_scalar_type'] \
    if '_half_orm_dev__json_scalar_type' in _mod.__dict__ \
    else _mod.__dict__['__json_scalar_type']


def _gen_typedict(relation, fkeys):
    """Wrapper: joins the list returned by __gen_typedict into a single string."""
    return '\n\n'.join(_gen_typedict_raw(relation, fkeys))


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

    def test_forward_fk_not_in_typedict(self):
        """FK accessor attributes are not part of a row dict — excluded from TypedDict."""
        relation = _make_relation(
            'public', 'post', {'id': 'integer'},
            fkeys={'post_author_id_fkey': ('public', 'author')}
        )
        result = _gen_typedict(relation, {})
        assert 'fk_post_author_id_fkey' not in result
        assert 'PublicAuthorDict' not in result

    def test_reverse_fk_not_in_typedict(self):
        """Reverse FK accessor attributes are not part of a row dict — excluded."""
        relation = _make_relation(
            'public', 'author', {'id': 'integer'},
            fkeys={'_reverse_fkey_public_post_author_id': ('public', 'post')}
        )
        result = _gen_typedict(relation, {})
        assert 'rfk_public_post_author_id' not in result
        assert 'PublicPostDict' not in result

    def test_fk_alias_not_in_typedict(self):
        """User-defined FK aliases are also excluded from TypedDict."""
        relation = _make_relation(
            'public', 'post', {'id': 'integer'},
            fkeys={'post_author_id_fkey': ('public', 'author')}
        )
        result = _gen_typedict(relation, {'writer': 'post_author_id_fkey'})
        assert 'writer' not in result
        assert 'PublicAuthorDict' not in result

    def test_self_referential_fk_not_in_typedict(self):
        """Self-referential FKs are also excluded from TypedDict."""
        relation = _make_relation(
            'public', 'category', {'id': 'integer'},
            fkeys={'category_parent_fkey': ('public', 'category')}
        )
        result = _gen_typedict(relation, {})
        assert 'fk_category_parent_fkey' not in result

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


# ---------------------------------------------------------------------------
# Tests for __gen_json_typedicts
# ---------------------------------------------------------------------------

class TestGenJsonTypedict:

    def test_simple_scalar_fields(self):
        classes, top = _gen_json_typedicts('Prefix', {'lang': 'text', 'views': 'integer'})
        assert top == 'PrefixDict'
        assert len(classes) == 1
        body = classes[0]
        assert 'class PrefixDict(TypedDict, total=False):' in body
        assert '    lang: Optional[str]' in body
        assert '    views: Optional[int]' in body

    def test_array_of_scalars(self):
        classes, top = _gen_json_typedicts('Post', {'tags': ['text']})
        assert len(classes) == 1
        assert '    tags: Optional[List[str]]' in classes[0]

    def test_nested_dict_generates_child_class(self):
        classes, top = _gen_json_typedicts('Post', {'meta': {'created': 'timestamp'}})
        assert len(classes) == 2
        assert classes[0].startswith('class PostMetaDict(TypedDict, total=False):')
        assert classes[1].startswith('class PostDict(TypedDict, total=False):')
        assert "    meta: Optional['PostMetaDict']" in classes[1]

    def test_array_of_objects_generates_child_class(self):
        classes, top = _gen_json_typedicts('Post', {'items': [{'id': 'uuid', 'name': 'text'}]})
        assert len(classes) == 2
        assert classes[0].startswith('class PostItemsDict(TypedDict, total=False):')
        assert "    items: Optional[List['PostItemsDict']]" in classes[1]

    def test_deep_nesting_dependency_order(self):
        schema = {'outer': {'inner': {'val': 'integer'}}}
        classes, top = _gen_json_typedicts('Root', schema)
        assert len(classes) == 3
        assert classes[0].startswith('class RootOuterInnerDict')
        assert classes[1].startswith('class RootOuterDict')
        assert classes[2].startswith('class RootDict')

    def test_non_dict_schema_returns_any(self):
        classes, top = _gen_json_typedicts('Post', 'not a dict')
        assert classes == []
        assert top == 'Any'

    def test_empty_schema_generates_pass(self):
        classes, top = _gen_json_typedicts('Empty', {})
        assert len(classes) == 1
        assert '    pass' in classes[0]

    def test_uuid_type_adds_import(self):
        _gen_json_typedicts('Token', {'id': 'uuid'})
        assert 'uuid' in _mod.HO_TYPEDICTS_IMPORTS

    def test_timestamp_type_adds_import(self):
        _gen_json_typedicts('Event', {'created_at': 'timestamp'})
        assert 'datetime' in _mod.HO_TYPEDICTS_IMPORTS

    def test_plain_scalar_no_import(self):
        _gen_json_typedicts('Counter', {'n': 'integer'})
        assert _mod.HO_TYPEDICTS_IMPORTS == set()

    def test_snake_case_key_builds_camel_prefix(self):
        classes, top = _gen_json_typedicts('Post', {'some_data': {'val': 'text'}})
        assert classes[0].startswith('class PostSomeDataDict')

    def test_unknown_sql_type_falls_back_to_any(self):
        classes, top = _gen_json_typedicts('X', {'col': 'custom_pg_type'})
        assert '    col: Optional[Any]' in classes[0]
