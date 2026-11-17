"""
Unit tests for the helpers that keep database text from becoming code in
the generated package (see tests/e2e/test_generated_code_hostile_names.py
for the same thing end to end).
"""
import ast

import pytest

import half_orm_dev.modules as _mod

_gen_json_typedicts = _mod.__dict__['__gen_json_typedicts']
_get_full_class_name = _mod.__dict__['__get_full_class_name']
_attribute_line = _mod.__dict__['__attribute_line']


@pytest.mark.parametrize('text', [
    'plain comment',
    'three """ quotes',
    '"""',
    'four """" quotes',
    'ends with a quote"',
    'ends with a backslash\\',
    'backslash then quotes \\"""',
    'C:\\new\\table',
    '"""\nimport os\n"""',
])
def test_docstring_safe_round_trips(text):
    source = f'"""\n{_mod._docstring_safe(text)}\n"""\n'
    tree = ast.parse(source)
    assert len(tree.body) == 1
    assert ast.literal_eval(tree.body[0].value) == f'\n{text}\n'


def test_docstring_safe_leaves_ordinary_text_alone():
    text = "SCHEMA: public\nTABLE: post\n'fk_author': 'post_author_id_fkey',"
    assert _mod._docstring_safe(text) == text


@pytest.mark.parametrize('name', ['author', 'Post', 'été', '_x', 'a1'])
def test_safe_identifier_keeps_identifiers(name):
    assert _mod._safe_identifier(name) == name


@pytest.mark.parametrize('name', [
    "it's", 'a-b', 'a/b', '../x', '/tmp/x', 'a b', '1abc', 'class', 'x\nimport os', ''])
def test_safe_identifier_sanitizes_everything_else(name):
    result = _mod._safe_identifier(name)
    assert result.isidentifier()
    assert '/' not in result and '.' not in result


def test_full_class_name_is_always_an_identifier():
    assert _get_full_class_name('public', 'user_profile') == 'PublicUserProfile'
    assert _get_full_class_name('my.schema', 'post') == 'MySchemaPost'
    assert _get_full_class_name('esc/aped', "it's").isidentifier()


def test_json_key_that_is_not_an_identifier_is_commented_out():
    classes, name = _gen_json_typedicts(
        'PublicPostMeta', {'lang': 'text', "x = __import__('os')  #": 'text'})
    tree = ast.parse('\n'.join(classes))
    cls = tree.body[-1]
    assert cls.name == name
    assert [type(node) for node in cls.body] == [ast.AnnAssign]
    assert 'FIX ME' in classes[-1]


def test_json_key_with_a_line_break_cannot_leave_its_comment():
    classes, _ = _gen_json_typedicts('PublicPostMeta', {'a\nimport os': 'text'})
    tree = ast.parse('\n'.join(classes))
    assert not any(isinstance(node, ast.Import) for node in ast.walk(tree))


def test_attribute_line():
    assert _attribute_line('    ', 'fk_author', 'self.fk_author = DC') == \
        '    self.fk_author = DC'
    line = _attribute_line('    ', 'fk_x = 1\nimport os', 'self.fk_x = 1\nimport os = DC')
    assert line.lstrip().startswith('#') and '\n' not in line
