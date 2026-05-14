"""
E2E tests for TypedDict annotations in generated modules.

Verifies that ho_baseclasses.py contains:
- TypedDict-typed method overrides (BC_* classes)
- DC_* dataclasses
- TYPE_CHECKING guard importing ho_typeddicts

And that relation modules are simplified to:
- @register class X(ho_baseclasses.BC_X):
"""
import pytest


@pytest.fixture
def baseclasses(project_with_fk_patch):
    env = project_with_fk_patch
    path = env['project_dir'] / env['db_name'] / 'ho_baseclasses.py'
    return path.read_text()


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


# --- ho_baseclasses.py checks ---

@pytest.mark.e2e
def test_baseclasses_type_checking_guard(baseclasses, project_with_fk_patch):
    """ho_baseclasses.py imports TypedDicts under TYPE_CHECKING."""
    db_name = project_with_fk_patch['db_name']
    assert 'if TYPE_CHECKING:' in baseclasses
    assert f'from {db_name}.ho_typeddicts import (' in baseclasses


@pytest.mark.e2e
def test_baseclasses_contains_author_dict_import(baseclasses):
    """ho_baseclasses.py imports PublicAuthorDict."""
    assert 'PublicAuthorDict,' in baseclasses


@pytest.mark.e2e
def test_baseclasses_contains_dc_author(baseclasses):
    """ho_baseclasses.py defines DC_PublicAuthor dataclass."""
    assert 'class DC_PublicAuthor(DC_Relation):' in baseclasses


@pytest.mark.e2e
def test_baseclasses_iter_annotation(baseclasses):
    """BC_PublicAuthor.__iter__ is annotated with Iterator[PublicAuthorDict]."""
    assert 'def __iter__(self) -> Iterator[PublicAuthorDict]:' in baseclasses


@pytest.mark.e2e
def test_baseclasses_ho_select_annotation(baseclasses):
    """BC_PublicAuthor.ho_select is annotated with Iterator[PublicAuthorDict]."""
    assert '-> Iterator[PublicAuthorDict]:' in baseclasses


@pytest.mark.e2e
def test_baseclasses_ho_get_annotation(baseclasses):
    """BC_PublicAuthor.ho_get is annotated with PublicAuthorDict."""
    assert 'def ho_get(self, *args) -> PublicAuthorDict:' in baseclasses


@pytest.mark.e2e
def test_baseclasses_ho_insert_annotation(baseclasses):
    """BC_PublicAuthor.ho_insert is annotated with PublicAuthorDict."""
    assert 'def ho_insert(self, *args' in baseclasses
    assert '-> PublicAuthorDict:' in baseclasses


@pytest.mark.e2e
def test_baseclasses_ho_aselect_annotation(baseclasses):
    """BC_PublicAuthor.ho_aselect is annotated with List[PublicAuthorDict]."""
    assert '-> List[PublicAuthorDict]:' in baseclasses


@pytest.mark.e2e
def test_baseclasses_ho_aget_annotation(baseclasses):
    """BC_PublicAuthor.ho_aget is annotated with PublicAuthorDict."""
    assert 'async def ho_aget(self, *args) -> PublicAuthorDict:' in baseclasses


@pytest.mark.e2e
def test_baseclasses_ho_ainsert_annotation(baseclasses):
    """BC_PublicAuthor.ho_ainsert is annotated with PublicAuthorDict."""
    assert 'async def ho_ainsert(self, *args' in baseclasses


@pytest.mark.e2e
def test_baseclasses_post_dict_import(baseclasses):
    """ho_baseclasses.py imports PublicPostDict too."""
    assert 'PublicPostDict,' in baseclasses


@pytest.mark.e2e
def test_no_ho_dataclasses_file(project_with_fk_patch):
    """ho_dataclasses.py is no longer generated (merged into ho_baseclasses.py)."""
    env = project_with_fk_patch
    path = env['project_dir'] / env['db_name'] / 'ho_dataclasses.py'
    assert not path.exists()


# --- relation module checks ---

@pytest.mark.e2e
def test_module_inherits_from_bc(author_module):
    """Generated relation module inherits from ho_baseclasses.BC_*."""
    assert 'ho_baseclasses.BC_PublicAuthor' in author_module


@pytest.mark.e2e
def test_module_imports_ho_baseclasses(author_module):
    """Generated relation module imports ho_baseclasses."""
    assert 'ho_baseclasses' in author_module


@pytest.mark.e2e
def test_module_no_typing_overrides(author_module):
    """Generated relation module no longer contains inline TypedDict overrides."""
    assert 'TYPE_CHECKING' not in author_module
    assert 'ho_typeddicts' not in author_module


@pytest.mark.e2e
def test_post_module_inherits_from_bc(post_module):
    """post.py inherits from BC_PublicPost."""
    assert 'ho_baseclasses.BC_PublicPost' in post_module
