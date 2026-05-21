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

    def test_includes_model_get_relation_class(self):
        result = _gen_baseclass(lambda: _SimpleRelation(), {})
        assert "MODEL.get_relation_class('public.item'" in result

    def test_includes_dc_class(self):
        result = _gen_baseclass(lambda: _SimpleRelation(), {})
        assert 'DC_PublicItem' in result

    def test_no_parent_bc_class_even_with_db_inheritance(self):
        """BC_ never embeds parent BC_; inheritance lives in the user module."""
        result = _gen_baseclass(lambda: _ChildRelation(), {})
        assert 'BC_AccessAccess' not in result
        assert 'class BC_AccessUserGroup(' in result
        assert "MODEL.get_relation_class('access.user_group'" in result
