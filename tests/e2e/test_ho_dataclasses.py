"""
E2E tests for ho_dataclasses.py generation.

Verifies that the DC classes generated in ho_dataclasses.py have correct
FK references in __post_init__: each FK must point to the DC class of the
*target* relation, not to the host class (regression guard for the
_FKey__relation bug).
"""
import re
import pytest


def _parse_dc_fk_refs(content: str) -> dict:
    """
    Parse ho_dataclasses.py and return FK assignments per DC class.

    Returns {dc_class_name: {attr_name: target_dc_class_name}}

    Only considers lines of the form ``self.xxx = DC_Yyy`` inside a
    ``__post_init__`` body, i.e. the FK reference lines (field lines use
    type annotations, not plain assignments).
    """
    result = {}
    class_pattern = re.compile(r'^class (DC_\w+)\(DC_Relation\):', re.MULTILINE)
    fk_pattern = re.compile(r'^\s{8}self\.(\w+) = (DC_\w+)\s*$', re.MULTILINE)

    classes = list(class_pattern.finditer(content))
    for i, match in enumerate(classes):
        dc_name = match.group(1)
        start = match.start()
        end = classes[i + 1].start() if i + 1 < len(classes) else len(content)
        class_body = content[start:end]
        result[dc_name] = {
            m.group(1): m.group(2) for m in fk_pattern.finditer(class_body)
        }
    return result


@pytest.fixture
def ho_dc_content(project_with_fk_patch):
    """Return the content of ho_dataclasses.py for the FK patch project."""
    env = project_with_fk_patch
    path = env['project_dir'] / env['db_name'] / 'ho_dataclasses.py'
    return path.read_text()


@pytest.mark.e2e
def test_ho_dataclasses_exists(project_with_fk_patch):
    """ho_dataclasses.py is generated inside the project package."""
    env = project_with_fk_patch
    path = env['project_dir'] / env['db_name'] / 'ho_dataclasses.py'
    assert path.exists()


@pytest.mark.e2e
def test_ho_dataclasses_contains_dc_classes(ho_dc_content):
    """DC classes for author and post tables are present."""
    assert 'class DC_PublicAuthor(DC_Relation):' in ho_dc_content
    assert 'class DC_PublicPost(DC_Relation):' in ho_dc_content


@pytest.mark.e2e
def test_forward_fk_references_correct_target(ho_dc_content):
    """Forward FK in DC_PublicPost references DC_PublicAuthor, not DC_PublicPost."""
    dc_fk_refs = _parse_dc_fk_refs(ho_dc_content)

    assert 'DC_PublicPost' in dc_fk_refs, "DC_PublicPost not found in ho_dataclasses.py"
    post_refs = dc_fk_refs['DC_PublicPost']
    assert post_refs, "DC_PublicPost has no FK references in __post_init__"

    for attr, target in post_refs.items():
        assert target == 'DC_PublicAuthor', (
            f"DC_PublicPost.{attr} should reference DC_PublicAuthor, got {target!r}"
        )


@pytest.mark.e2e
def test_reverse_fk_references_correct_target(ho_dc_content):
    """Reverse FK in DC_PublicAuthor references DC_PublicPost, not DC_PublicAuthor."""
    dc_fk_refs = _parse_dc_fk_refs(ho_dc_content)

    assert 'DC_PublicAuthor' in dc_fk_refs, "DC_PublicAuthor not found in ho_dataclasses.py"
    author_refs = dc_fk_refs['DC_PublicAuthor']
    assert author_refs, "DC_PublicAuthor has no reverse FK in __post_init__"

    for attr, target in author_refs.items():
        assert target == 'DC_PublicPost', (
            f"DC_PublicAuthor.{attr} should reference DC_PublicPost, got {target!r}"
        )


@pytest.mark.e2e
def test_no_fk_references_host_class(ho_dc_content):
    """No DC class has a FK entry pointing to itself (host-class regression guard)."""
    dc_fk_refs = _parse_dc_fk_refs(ho_dc_content)

    for dc_class, fk_refs in dc_fk_refs.items():
        for attr, target in fk_refs.items():
            assert target != dc_class, (
                f"{dc_class}.{attr} references itself — host-class bug regression!"
            )