"""
Unit tests for BC_* base class generation in modules.py.

BC_ classes contain only MODEL.get_relation_class() and DC_ — no parent BC_.
DB-level inheritance is expressed in the user module via {inherited_classes}
so that AccessAccess → BC_AccessAccess is visible to IDEs through the user
class hierarchy, not through BC_ itself.
"""
import half_orm_dev.modules as _mod

_gen_baseclass = (
    _mod.__dict__.get('_half_orm_dev__gen_baseclass')
    or _mod.__dict__['__gen_baseclass']
)


class _SimpleRelation:
    _t_fqrn = ('db', 'public', 'item')
    _ho_fkeys = {}
    _ho_fields = {}

    def _ho_dataclass_name(self):
        return 'DC_PublicItem'


class _ParentRelation:
    _t_fqrn = ('db', 'access', 'access')
    _ho_fkeys = {}
    _ho_fields = {}

    def _ho_dataclass_name(self):
        return 'DC_AccessAccess'


class _ChildRelation(_ParentRelation):
    _t_fqrn = ('db', 'access', 'user_group')
    _ho_fkeys = {}
    _ho_fields = {}

    def _ho_dataclass_name(self):
        return 'DC_AccessUserGroup'


class TestGenBaseclass:
    """BC_ class generation — simple and inherited relations."""

    def test_class_name(self):
        result = _gen_baseclass(lambda: _SimpleRelation(), {})
        assert 'class BC_PublicItem(' in result

    def test_base_goes_through_the_bc_base_helper(self):
        """The base is resolved by _bc_base, not by MODEL directly.

        _bc_base degrades a relation missing from the database to a
        placeholder; resolving the base eagerly here would make importing
        the package fail outright (see TestBcBaseHelper).
        """
        result = _gen_baseclass(lambda: _SimpleRelation(), {})
        assert "_bc_base('public.item')" in result
        assert 'MODEL.get_relation_class' not in result

    def test_includes_dc_class(self):
        result = _gen_baseclass(lambda: _SimpleRelation(), {})
        assert 'DC_PublicItem' in result

    def test_no_parent_bc_class_even_with_db_inheritance(self):
        """BC_ never embeds parent BC_; inheritance lives in the user module."""
        result = _gen_baseclass(lambda: _ChildRelation(), {})
        assert 'BC_AccessAccess' not in result
        assert 'class BC_AccessUserGroup(' in result
        assert "_bc_base('access.user_group')" in result


class TestGenBaseclassOverrideSignatures:
    """The typed overrides must stay in step with half_orm's own signatures.

    Each BC_ override exists only to narrow a return type for IDEs; it must
    therefore accept exactly the keyword-only parameters the real
    half_orm.relation.Relation method accepts, and forward every one of
    them. A parameter missing here is not a typing nit: the override
    shadows the real method, so calling it with that keyword raises
    TypeError at runtime — which is how json_agg, added to ho_select but
    not to ho_aselect, broke every async list query going through a
    generated class.
    """

    def _overrides(self):
        import ast
        src = _gen_baseclass(lambda: _SimpleRelation(), {})
        cls = ast.parse(src).body[0]
        return {
            node.name: node
            for node in cls.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

    def test_kwonly_params_match_relation(self):
        import inspect
        from half_orm.relation import Relation

        for name, node in self._overrides().items():
            real = getattr(Relation, name, None)
            if real is None:          # __iter__ and friends: nothing to match
                continue
            expected = [
                p.name for p in inspect.signature(real).parameters.values()
                if p.kind == p.KEYWORD_ONLY
            ]
            generated = [a.arg for a in node.args.kwonlyargs]
            assert generated == expected, (
                f"{name}: generated override declares {generated}, "
                f"half_orm's own signature has {expected}")

    def test_every_declared_kwonly_param_is_forwarded(self):
        import ast

        for name, node in self._overrides().items():
            declared = {a.arg for a in node.args.kwonlyargs}
            if not declared:
                continue
            calls = [n for n in ast.walk(node) if isinstance(n, ast.Call)]
            forwarded = {kw.arg for call in calls for kw in call.keywords}
            assert declared <= forwarded, (
                f"{name}: declares {sorted(declared - forwarded)} but never "
                f"forwards it to super() — the value would be silently dropped")


class TestBcOverrideDerivation:
    """_bc_override reads its parameters off Relation, so a parameter added
    upstream needs no change here.

    The six real methods never exercise **kwargs, and since the refactor
    both sides of test_kwonly_params_match_relation come from
    inspect.signature — this drives the derivation itself with a stand-in
    method instead.
    """

    def test_new_and_variadic_params_are_declared_and_forwarded(self, monkeypatch):
        from half_orm.relation import Relation

        def ho_select(self, *args, distinct: bool = False, brand_new=None, **extra):
            ...

        monkeypatch.setattr(Relation, 'ho_select', ho_select)
        signature, call = _mod._bc_override(
            'ho_select', 'Iterator[PublicItemDict]', False).splitlines()

        assert 'brand_new=None' in signature
        assert '**extra' in signature
        assert 'brand_new=brand_new' in call
        assert '**extra' in call
        assert '*args' in call
        assert signature.endswith('-> Iterator[PublicItemDict]:')

    def test_async_methods_keep_async_def_and_await(self):
        signature, call = _mod._bc_override(
            'ho_aselect', 'List[PublicItemDict]', False).splitlines()
        assert signature.lstrip().startswith('async def ')
        assert 'return await super().ho_aselect(' in call


class TestBcBaseHelper:
    """The _bc_base helper emitted at the top of ho_baseclasses.py.

    ho_baseclasses.py resolves one base class per relation at *import*
    time, from the schema as of the last generation. `patch apply` rebuilds
    the database from the production baseline and replays staged patches
    one at a time, so a table created by a later patch is missing while an
    earlier patch's Python script imports the package — which used to abort
    the apply with UnknownRelation.
    """

    def _helper(self, model):
        import sys
        from half_orm.model_errors import UnknownRelation

        namespace = {'sys': sys, 'UnknownRelation': UnknownRelation, 'MODEL': model}
        exec(compile(_mod.BC_BASE_HELPER, 'ho_baseclasses.py', 'exec'), namespace)
        return namespace['_bc_base']

    def test_existing_relation_returns_the_real_base(self):
        class Item:
            pass

        class Model:
            def get_relation_class(self, fqrn, fields_aliases=None):
                assert fqrn == 'public.item'
                return Item

        assert self._helper(Model())('public.item') is Item

    def test_missing_relation_is_logged(self, capsys):
        from half_orm.model_errors import UnknownRelation

        class Model:
            def get_relation_class(self, fqrn, fields_aliases=None):
                raise UnknownRelation(('bug', 'public', 'thing'))

        self._helper(Model())('public.thing')
        assert 'public.thing' in capsys.readouterr().err

    def test_missing_relation_raises_only_when_used(self):
        from half_orm.model_errors import UnknownRelation
        import pytest

        class Model:
            def get_relation_class(self, fqrn, fields_aliases=None):
                raise UnknownRelation(('bug', 'public', 'thing'))

        placeholder = self._helper(Model())('public.thing')

        # Subclassing it is what ho_baseclasses.py does on import: it must work.
        class BC_PublicThing(placeholder):
            pass

        with pytest.raises(UnknownRelation, match="public.thing"):
            BC_PublicThing()
