"""
Migration 2.0.0a3 — `patch apply` and `patch merge` stop instead of losing work

Two behaviours change, and the second can stop a merge that used to pass:

- `patch apply` (#59) no longer deletes a module whose relation is absent
  from the database when it holds code git cannot give back: it stops
  before modifying anything and lists the modules to put away.
- `patch merge` (#58) refuses a patch whose generated code moves when
  validation regenerates the package. A patch branch behind the release
  must take the release in and regenerate before merging.

This migration changes nothing in the repository: it tells the developer,
once, what to expect.
"""

NOTICE = """\
  ⚠️  half_orm_dev 2.0.0a3: `patch apply` and `patch merge` stop instead of
  losing work.

  • `patch apply` no longer deletes uncommitted business code in a module
    whose relation is absent from the database: it stops, lists the modules,
    and says how to put the work away.

  • `patch merge` refuses a patch whose generated code is out of date. A
    patch cut before another one was merged must, on its branch:
        git merge ho-release/X.Y.Z    # generated files: keep either side
        half_orm dev patch apply
        git add -A && git commit
    then be merged again. The refusal message gives these commands.
"""


def get_description():
    return "patch apply and patch merge stop instead of losing work (#59, #58)"


def migrate(repo):
    print(NOTICE)
    return {}
