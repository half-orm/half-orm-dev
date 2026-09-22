"""
Regression test: `patch apply` must survive generated code that is ahead
of the database.

Bug scenario (reported 2026-09-15):
  Two patches in the same release - one seeding data through the generated
  package, one creating a new table. The first `patch apply` succeeds; every
  later one aborts with

      UnknownRelation: 'public.thing' does not exist in the database

  because apply rebuilds the database from the production baseline and
  replays the staged patches one at a time, while the generated package on
  disk still dates from the previous apply. ho_baseclasses.py resolves a
  base class per relation *at import time*, so the seeding script - run
  before the table-creating patch - drags in a relation the database does
  not have yet.

  The generated _bc_base() helper now degrades such a relation to a
  placeholder (and logs it) instead of raising on import.
"""
import pytest


@pytest.mark.e2e
def test_apply_is_repeatable_when_a_later_patch_adds_a_table(project_with_release):
    env = project_with_release
    run = env['run']
    project_dir = env['project_dir']
    db = env['db_name']

    # ── Patch A: creates author, then seeds it through the generated package
    run(['half_orm', 'dev', 'patch', 'create', '1-author'])
    patch_a = project_dir / 'Patches' / '1-author'
    (patch_a / '01_author.sql').write_text(
        "CREATE TABLE author (id SERIAL PRIMARY KEY, name TEXT);\n")
    run(['half_orm', 'dev', 'patch', 'apply'])

    (patch_a / '02_seed.py').write_text(
        f"from {db}.public.author import Author\n"
        "Author(name='alice').ho_insert()\n"
        "print('seeded')\n"
    )
    run(['half_orm', 'dev', 'patch', 'apply'])

    run(['git', 'add', '-A'])
    run(['git', 'commit', '--no-verify', '-m', 'patch A'], check=False)
    run(['half_orm', 'dev', 'patch', 'merge', '--force'])

    # ── Patch B: creates a table the seeding script knows nothing about
    run(['git', 'stash', '-u'], check=False)
    run(['git', 'checkout', 'ho-release/0.1.0'])
    run(['half_orm', 'dev', 'patch', 'create', '2-thing'])
    (project_dir / 'Patches' / '2-thing' / '01_thing.sql').write_text(
        "CREATE TABLE thing (id SERIAL PRIMARY KEY, label TEXT);\n")

    # First apply generates public/thing.py and puts thing in ho_baseclasses.py
    first = run(['half_orm', 'dev', 'patch', 'apply'], check=False)
    assert first.returncode == 0, first.stdout + first.stderr
    assert 'public.thing' in (project_dir / db / 'ho_baseclasses.py').read_text()

    # Second apply replays 02_seed.py while public.thing does not exist yet
    second = run(['half_orm', 'dev', 'patch', 'apply'], check=False)
    assert second.returncode == 0, (
        "second apply failed - generated code ahead of the database:\n"
        f"{second.stdout}\n{second.stderr}")

    # The degradation is logged, never silent
    output = second.stdout + second.stderr
    assert "relation 'public.thing' is not in the database" in output, output
