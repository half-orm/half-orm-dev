"""
Migration 2.0.0a2 — half-orm 2.0.1 is required: review writes through | and -

half-orm 2.0.0 compiled ho_update() and ho_delete() wrongly on a predicate
built with | or - whose operands navigate a foreign key: the joins were
dropped and the write touched other rows than the predicate denotes. A
delete on the union of two navigated predicates emptied the table; an
update on a difference updated no row, or the wrong ones. The
delete_all/update_all guard did not stop it, the operands being
constrained. half-orm 2.0.1 fixes it (and 1.2.2, 0.18.15).

half_orm_dev 2.0.0a2 requires half-orm>=2.0.1, so upgrading half_orm_dev
has upgraded half-orm. This migration changes nothing in the repository:
it tells the developer what the upgrade means for the code already
written, and checks that the half-orm actually imported is the fixed one
(an editable install or a pinned requirement can hold it back).
"""

from packaging import version

FIXED_IN = "2.0.1"

NOTICE = """\
  ⚠️  half-orm 2.0.1 is required: it fixes a data-loss bug.

  With half-orm 2.0.0, ho_update() and ho_delete() on a predicate built
  with |, - or ^ whose operands follow a foreign key dropped the joins and
  touched other rows than the predicate denotes, without an error:

      (alices.rfk_posts() | bobs.rfk_posts()).ho_delete()   # deleted every post

  What to do: look in your code for ho_update() or ho_delete() called on
  such an expression. A write that used to update nothing now updates the
  rows it names: check that this is what the code meant.

  https://github.com/half-orm/half-orm/blob/main/CHANGELOG.md
"""


def get_description():
    return "half-orm 2.0.1 required: review ho_update/ho_delete through | and - (data-loss fix)"


def migrate(repo):
    import half_orm

    print(NOTICE)
    if version.parse(half_orm.__version__) < version.parse(FIXED_IN):
        print(
            f"  ❌ half-orm {half_orm.__version__} is installed: upgrade it with\n"
            f"     pip install --upgrade 'half-orm>={FIXED_IN},<3'\n")
    return {}
