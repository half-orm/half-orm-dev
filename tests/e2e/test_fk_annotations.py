"""
E2E tests for FK type annotations in generated modules.

Verifies that after 'hop patch apply', generated modules contain:
- from __future__ import annotations at the top
- TYPE_CHECKING imports pointing to the correct package modules
- FK attribute annotations in __init__ with correct class names
"""

import pytest


@pytest.mark.e2e
class TestFkTypeImports:
    """Generated modules contain correct TYPE_CHECKING imports."""

    def test_post_imports_author(self, project_with_fk_patch):
        """post.py must import Author under TYPE_CHECKING."""
        env = project_with_fk_patch
        db_name = env['db_name']
        post_module = env['project_dir'] / db_name / 'public' / 'post.py'
        assert post_module.exists(), "post.py should be generated"
        content = post_module.read_text()
        assert 'TYPE_CHECKING' in content
        assert f'from {db_name}.public.author import Author' in content

    def test_author_imports_post(self, project_with_fk_patch):
        """author.py must import Post under TYPE_CHECKING for the reverse FK."""
        env = project_with_fk_patch
        db_name = env['db_name']
        author_module = env['project_dir'] / db_name / 'public' / 'author.py'
        assert author_module.exists(), "author.py should be generated"
        content = author_module.read_text()
        assert 'TYPE_CHECKING' in content
        assert f'from {db_name}.public.post import Post' in content

    def test_future_annotations_before_imports(self, project_with_fk_patch):
        """from __future__ import annotations must precede other imports."""
        env = project_with_fk_patch
        db_name = env['db_name']
        for name in ('post.py', 'author.py'):
            content = (env['project_dir'] / db_name / 'public' / name).read_text()
            future_pos = content.find('from __future__ import annotations')
            regular_pos = content.find('from half_orm.model import register')
            assert future_pos != -1, f"{name}: missing __future__ import"
            assert future_pos < regular_pos, (
                f"{name}: __future__ import must come before regular imports"
            )


@pytest.mark.e2e
class TestFkAnnotationsInInit:
    """Generated __init__ methods contain FK attribute annotations."""

    def test_post_has_author_annotation(self, project_with_fk_patch):
        """post.py __init__ must annotate the FK to Author."""
        env = project_with_fk_patch
        db_name = env['db_name']
        content = (env['project_dir'] / db_name / 'public' / 'post.py').read_text()
        assert ": 'Author'" in content, (
            "post.py __init__ should have an FK annotation of type 'Author'"
        )

    def test_author_has_post_annotation(self, project_with_fk_patch):
        """author.py __init__ must annotate the reverse FK to Post."""
        env = project_with_fk_patch
        db_name = env['db_name']
        content = (env['project_dir'] / db_name / 'public' / 'author.py').read_text()
        assert ": 'Post'" in content, (
            "author.py __init__ should have a reverse FK annotation of type 'Post'"
        )

    def test_no_object_fallback(self, project_with_fk_patch):
        """No FK annotation should fall back to object (type resolution failure)."""
        env = project_with_fk_patch
        db_name = env['db_name']
        for name in ('post.py', 'author.py'):
            content = (env['project_dir'] / db_name / 'public' / name).read_text()
            if 'def __init__' in content:
                init_body = content.split('def __init__')[1]
                assert ': object' not in init_body, (
                    f"{name}: FK annotation fell back to 'object' — type resolution failed"
                )