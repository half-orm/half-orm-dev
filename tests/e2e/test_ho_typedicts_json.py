"""
E2E tests for ho_typeddicts.py JSON schema TypedDict generation.

Verifies that jsonb columns annotated with a @json YAML block in their
PostgreSQL column comment generate nested TypedDict classes in ho_typeddicts.py.
"""
import re
import pytest


def _parse_typedict_classes(content: str) -> dict:
    """Return {class_name: {field_name: annotation_str}} from ho_typeddicts.py."""
    result = {}
    class_pattern = re.compile(r'^class (\w+Dict)\(TypedDict, total=False\):', re.MULTILINE)
    field_pattern = re.compile(r'^\s{4}(\w+): (.+)$', re.MULTILINE)
    classes = list(class_pattern.finditer(content))
    for i, match in enumerate(classes):
        class_name = match.group(1)
        start = match.start()
        end = classes[i + 1].start() if i + 1 < len(classes) else len(content)
        body = content[start:end]
        result[class_name] = {m.group(1): m.group(2).strip() for m in field_pattern.finditer(body)}
    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ho_td_content(project_with_fk_patch):
    env = project_with_fk_patch
    path = env['project_dir'] / env['db_name'] / 'ho_typeddicts.py'
    return path.read_text()


@pytest.fixture
def td_classes(ho_td_content):
    return _parse_typedict_classes(ho_td_content)


# ---------------------------------------------------------------------------
# Tests — nested TypedDict classes from @json schema
# ---------------------------------------------------------------------------

@pytest.mark.e2e
def test_json_nested_class_exists(ho_td_content):
    """PublicPostMetadataDict is generated from the @json block on post.metadata."""
    assert 'class PublicPostMetadataDict(TypedDict, total=False):' in ho_td_content


@pytest.mark.e2e
def test_json_items_nested_class_exists(ho_td_content):
    """PublicPostMetadataItemsDict is generated for the items array-of-objects."""
    assert 'class PublicPostMetadataItemsDict(TypedDict, total=False):' in ho_td_content


@pytest.mark.e2e
def test_json_field_annotation_in_parent(ho_td_content):
    """post.metadata field in PublicPostDict references PublicPostMetadataDict."""
    assert 'metadata: Optional[PublicPostMetadataDict]' in ho_td_content


@pytest.mark.e2e
def test_json_scalar_fields_in_metadata_dict(ho_td_content):
    """lang and views scalar fields are correctly typed in PublicPostMetadataDict."""
    assert '    lang: Optional[str]' in ho_td_content
    assert '    views: Optional[int]' in ho_td_content


@pytest.mark.e2e
def test_json_array_scalar_field_in_metadata_dict(ho_td_content):
    """tags ([text]) maps to Optional[List[str]] in PublicPostMetadataDict."""
    assert '    tags: Optional[List[str]]' in ho_td_content


@pytest.mark.e2e
def test_json_array_of_objects_field_in_metadata_dict(ho_td_content):
    """items ([{...}]) maps to Optional[List['PublicPostMetadataItemsDict']]."""
    assert "    items: Optional[List['PublicPostMetadataItemsDict']]" in ho_td_content


@pytest.mark.e2e
def test_json_nested_classes_defined_before_parent(ho_td_content):
    """Nested TypedDicts appear in the file before the class that uses them."""
    items_pos = ho_td_content.find('class PublicPostMetadataItemsDict')
    meta_pos = ho_td_content.find('class PublicPostMetadataDict')
    post_pos = ho_td_content.find('class PublicPostDict')
    assert items_pos < meta_pos < post_pos, (
        "Nested TypedDicts must be defined before their parents"
    )


@pytest.mark.e2e
def test_json_items_nested_class_fields(td_classes):
    """PublicPostMetadataItemsDict has id (int) and title (str) fields."""
    assert 'PublicPostMetadataItemsDict' in td_classes
    fields = td_classes['PublicPostMetadataItemsDict']
    assert fields.get('id') == 'Optional[int]'
    assert fields.get('title') == 'Optional[str]'


@pytest.mark.e2e
def test_json_metadata_dict_has_all_fields(td_classes):
    """PublicPostMetadataDict has lang, views, tags and items fields."""
    assert 'PublicPostMetadataDict' in td_classes
    fields = td_classes['PublicPostMetadataDict']
    assert fields.get('lang') == 'Optional[str]'
    assert fields.get('views') == 'Optional[int]'
    assert fields.get('tags') == 'Optional[List[str]]'
    assert fields.get('items') == "Optional[List['PublicPostMetadataItemsDict']]"


@pytest.mark.e2e
def test_json_post_metadata_field_type(td_classes):
    """post.metadata in PublicPostDict is Optional[PublicPostMetadataDict] (no quotes)."""
    assert 'PublicPostDict' in td_classes
    fields = td_classes['PublicPostDict']
    assert fields.get('metadata') == 'Optional[PublicPostMetadataDict]'
