"""
E2E tests for TypedDict annotations in generated relation modules.

Verifies that each generated module file contains:
- from typing import TYPE_CHECKING, Iterator
- if TYPE_CHECKING: from <pkg>.ho_typeddicts import <RelationDict>
- def __iter__(self) -> 'Iterator[<RelationDict>]':
- def ho_get(self, *args) -> '<RelationDict>':
- async def ho_aget(self, *args) -> '<RelationDict>':
"""
import pytest


@pytest.fixture
def author_module(project_with_fk_patch):
    env = project_with_fk_patch
    path = env['project_dir'] / env['db_name'] / 'public' / 'author.py'
    return path.read_text()


@pytest.fixture
def post_module(project_with_fk_patch):
    env = project_with_fk_patch
    path = env['project_dir'] / env['db_name'] / 'public' / 'post.py'
    return path.read_text()


@pytest.mark.e2e
def test_type_checking_import_present(author_module):
    """Generated module imports TYPE_CHECKING and Iterator from typing."""
    assert 'from typing import TYPE_CHECKING, Iterator' in author_module


@pytest.mark.e2e
def test_type_checking_guard_imports_typeddict(author_module, project_with_fk_patch):
    """TYPE_CHECKING guard imports the matching TypedDict class."""
    db_name = project_with_fk_patch['db_name']
    assert 'if TYPE_CHECKING:' in author_module
    assert f'from {db_name}.ho_typeddicts import PublicAuthorDict' in author_module


@pytest.mark.e2e
def test_iter_annotation_present(author_module):
    """__iter__ is annotated with Iterator[<RelationDict>]."""
    assert "def __iter__(self) -> 'Iterator[PublicAuthorDict]':" in author_module


@pytest.mark.e2e
def test_iter_calls_super(author_module):
    """__iter__ delegates to super().__iter__()."""
    assert 'return super().__iter__()' in author_module


@pytest.mark.e2e
def test_iter_annotation_for_post(post_module):
    """Annotation is generated for all relations, not just the first one."""
    assert "def __iter__(self) -> 'Iterator[PublicPostDict]':" in post_module


@pytest.mark.e2e
def test_type_checking_guard_for_post(post_module, project_with_fk_patch):
    """TYPE_CHECKING guard uses the correct dict class name for each relation."""
    db_name = project_with_fk_patch['db_name']
    assert f'from {db_name}.ho_typeddicts import PublicPostDict' in post_module


@pytest.mark.e2e
def test_ho_get_annotation_present(author_module):
    """ho_get is annotated with the relation TypedDict return type."""
    assert "def ho_get(self, *args) -> 'PublicAuthorDict':" in author_module


@pytest.mark.e2e
def test_ho_get_calls_super(author_module):
    """ho_get delegates to super().ho_get()."""
    assert 'return super().ho_get(*args)' in author_module


@pytest.mark.e2e
def test_ho_aget_annotation_present(author_module):
    """ho_aget is annotated with the relation TypedDict return type."""
    assert "async def ho_aget(self, *args) -> 'PublicAuthorDict':" in author_module


@pytest.mark.e2e
def test_ho_aget_calls_super(author_module):
    """ho_aget delegates to super().ho_aget()."""
    assert 'return await super().ho_aget(*args)' in author_module


@pytest.mark.e2e
def test_ho_get_annotation_for_post(post_module):
    """ho_get annotation is correct for all relations."""
    assert "def ho_get(self, *args) -> 'PublicPostDict':" in post_module
