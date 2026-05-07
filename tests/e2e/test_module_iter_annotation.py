"""
E2E tests for .pyi stub files generated alongside relation modules.

Verifies that each generated .pyi stub contains:
- from typing import Iterator
- from <pkg>.ho_typeddicts import <RelationDict>
- def __iter__(self) -> Iterator[<RelationDict>]: ...
- def ho_get(self, *args) -> <RelationDict>: ...
- async def ho_aget(self, *args) -> <RelationDict>: ...
"""
import pytest


@pytest.fixture
def author_stub(project_with_fk_patch):
    env = project_with_fk_patch
    path = env['project_dir'] / env['db_name'] / 'public' / 'author.pyi'
    return path.read_text()


@pytest.fixture
def post_stub(project_with_fk_patch):
    env = project_with_fk_patch
    path = env['project_dir'] / env['db_name'] / 'public' / 'post.pyi'
    return path.read_text()


@pytest.mark.e2e
def test_stub_file_exists(project_with_fk_patch):
    """A .pyi stub is generated alongside each relation module."""
    env = project_with_fk_patch
    path = env['project_dir'] / env['db_name'] / 'public' / 'author.pyi'
    assert path.exists()


@pytest.mark.e2e
def test_stub_has_do_not_edit_header(author_stub):
    """Stub files carry a DO NOT EDIT warning."""
    assert 'DO NOT EDIT' in author_stub


@pytest.mark.e2e
def test_stub_imports_iterator(author_stub):
    """Stub imports Iterator from typing."""
    assert 'from typing import Iterator' in author_stub


@pytest.mark.e2e
def test_stub_imports_typeddict_class(author_stub, project_with_fk_patch):
    """Stub imports the matching TypedDict class directly (no TYPE_CHECKING guard)."""
    db_name = project_with_fk_patch['db_name']
    assert f'from {db_name}.ho_typeddicts import PublicAuthorDict' in author_stub
    assert 'TYPE_CHECKING' not in author_stub


@pytest.mark.e2e
def test_iter_annotation_present(author_stub):
    """__iter__ is annotated with Iterator[<RelationDict>]."""
    assert 'def __iter__(self) -> Iterator[PublicAuthorDict]: ...' in author_stub


@pytest.mark.e2e
def test_ho_get_annotation_present(author_stub):
    """ho_get return type is the relation TypedDict."""
    assert 'def ho_get(self, *args) -> PublicAuthorDict: ...' in author_stub


@pytest.mark.e2e
def test_ho_aget_annotation_present(author_stub):
    """ho_aget return type is the relation TypedDict."""
    assert 'async def ho_aget(self, *args) -> PublicAuthorDict: ...' in author_stub


@pytest.mark.e2e
def test_stub_for_post_exists(project_with_fk_patch):
    """A .pyi stub is generated for every relation, not just the first."""
    env = project_with_fk_patch
    path = env['project_dir'] / env['db_name'] / 'public' / 'post.pyi'
    assert path.exists()


@pytest.mark.e2e
def test_iter_annotation_for_post(post_stub):
    """Annotation uses the correct dict class name for each relation."""
    assert 'def __iter__(self) -> Iterator[PublicPostDict]: ...' in post_stub


@pytest.mark.e2e
def test_ho_get_annotation_for_post(post_stub):
    """ho_get annotation is correct for all relations."""
    assert 'def ho_get(self, *args) -> PublicPostDict: ...' in post_stub


@pytest.mark.e2e
def test_stub_imports_correct_typeddict_for_post(post_stub, project_with_fk_patch):
    """Stub imports the correct TypedDict for each relation."""
    db_name = project_with_fk_patch['db_name']
    assert f'from {db_name}.ho_typeddicts import PublicPostDict' in post_stub
