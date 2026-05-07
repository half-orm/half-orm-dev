"""
E2E tests for ho_typeddicts.py generation.

Verifies that the TypedDict classes generated in ho_typeddicts.py have:
- Correct class names and TypedDict signature (total=False)
- Correct field types (Optional[T])
- Correct array field types (Optional[List[T]])
- Correct FK references: Optional['TargetDict'] for _fk, Optional[List['TargetDict']] for _rfk
- Required imports (from __future__, typing, external modules)
"""
import re
import pytest


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _parse_typedict_classes(content: str) -> dict:
    """
    Parse ho_typeddicts.py and return fields per TypedDict class.

    Returns {class_name: {field_name: annotation_str}}
    """
    result = {}
    class_pattern = re.compile(r'^class (\w+Dict)\(TypedDict, total=False\):', re.MULTILINE)
    field_pattern = re.compile(r'^\s{4}(\w+): (.+)$', re.MULTILINE)

    classes = list(class_pattern.finditer(content))
    for i, match in enumerate(classes):
        class_name = match.group(1)
        start = match.start()
        end = classes[i + 1].start() if i + 1 < len(classes) else len(content)
        body = content[start:end]
        result[class_name] = {
            m.group(1): m.group(2).strip()
            for m in field_pattern.finditer(body)
        }
    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ho_td_content(project_with_fk_patch):
    """Return the content of ho_typeddicts.py for the FK patch project."""
    env = project_with_fk_patch
    path = env['project_dir'] / env['db_name'] / 'ho_typeddicts.py'
    return path.read_text()


@pytest.fixture
def td_classes(ho_td_content):
    return _parse_typedict_classes(ho_td_content)


# ---------------------------------------------------------------------------
# Tests — file existence and structure
# ---------------------------------------------------------------------------

@pytest.mark.e2e
def test_ho_typedicts_exists(project_with_fk_patch):
    """ho_typeddicts.py is generated inside the project package."""
    env = project_with_fk_patch
    path = env['project_dir'] / env['db_name'] / 'ho_typeddicts.py'
    assert path.exists()


@pytest.mark.e2e
def test_ho_typedicts_has_future_annotations(ho_td_content):
    """from __future__ import annotations must be present for forward refs."""
    assert 'from __future__ import annotations' in ho_td_content


@pytest.mark.e2e
def test_ho_typedicts_has_typing_imports(ho_td_content):
    """TypedDict, Optional, List, Any must be imported from typing."""
    assert 'from typing import' in ho_td_content
    for name in ('TypedDict', 'Optional', 'List', 'Any'):
        assert name in ho_td_content, f"'{name}' missing from typing imports"


# ---------------------------------------------------------------------------
# Tests — class generation
# ---------------------------------------------------------------------------

@pytest.mark.e2e
def test_author_dict_class_present(td_classes):
    """PublicAuthorDict is generated for the author table."""
    assert 'PublicAuthorDict' in td_classes


@pytest.mark.e2e
def test_post_dict_class_present(td_classes):
    """PublicPostDict is generated for the post table."""
    assert 'PublicPostDict' in td_classes


@pytest.mark.e2e
def test_all_dict_classes_have_total_false(ho_td_content):
    """Every TypedDict class uses total=False."""
    classes = re.findall(r'^class \w+\(TypedDict(.*?)\):', ho_td_content, re.MULTILINE)
    assert classes, "No TypedDict classes found"
    for sig in classes:
        assert 'total=False' in sig


# ---------------------------------------------------------------------------
# Tests — field types
# ---------------------------------------------------------------------------

@pytest.mark.e2e
def test_author_id_is_optional_int(td_classes):
    """author.id (SERIAL) maps to Optional[int]."""
    fields = td_classes.get('PublicAuthorDict', {})
    assert 'id' in fields
    assert fields['id'] == 'Optional[int]'


@pytest.mark.e2e
def test_author_name_is_optional_str(td_classes):
    """author.name (TEXT) maps to Optional[str]."""
    fields = td_classes.get('PublicAuthorDict', {})
    assert 'name' in fields
    assert fields['name'] == 'Optional[str]'


@pytest.mark.e2e
def test_post_author_id_is_optional_int(td_classes):
    """post.author_id (INT FK column) maps to Optional[int]."""
    fields = td_classes.get('PublicPostDict', {})
    assert 'author_id' in fields
    assert fields['author_id'] == 'Optional[int]'


# ---------------------------------------------------------------------------
# Tests — FK fields excluded from TypedDict
# ---------------------------------------------------------------------------

@pytest.mark.e2e
def test_post_has_no_fk_fields_in_typedict(td_classes):
    """FK accessor attributes are not row data — excluded from PublicPostDict."""
    fields = td_classes.get('PublicPostDict', {})
    fk_fields = [k for k in fields if k.startswith('fk_')]
    assert not fk_fields, f"fk_ fields should not appear in PublicPostDict: {fk_fields}"


@pytest.mark.e2e
def test_author_has_no_rfk_fields_in_typedict(td_classes):
    """Reverse FK accessor attributes are not row data — excluded from PublicAuthorDict."""
    fields = td_classes.get('PublicAuthorDict', {})
    rfk_fields = [k for k in fields if k.startswith('rfk_')]
    assert not rfk_fields, f"rfk_ fields should not appear in PublicAuthorDict: {rfk_fields}"


@pytest.mark.e2e
def test_no_dict_class_references_itself_via_direct_fk(td_classes):
    """No TypedDict has a non-reverse FK field pointing to itself."""
    for class_name, fields in td_classes.items():
        for attr, annotation in fields.items():
            if attr.endswith('_fk') and not attr.endswith('_rfk'):
                assert class_name not in annotation or 'List[' in annotation, (
                    f"{class_name}.{attr} direct FK should not reference itself"
                )
