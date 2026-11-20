"""
Regression test: applying a patch must not delete a developer's
uncommitted business logic.

generate() removes any module in the package whose relation is absent from
the database, and `patch apply` rebuilds the database from the production
baseline — so a module written for a table created by *another* patch
matches no relation and used to be deleted outright, business logic
included, with only a warning on stderr. Since that logic is typically
written in the same session as the patch, it was usually not committed
anywhere: the code was simply gone.

`patch apply` now stops before modifying the package, lists such modules,
and says what to do; once the work is put away, applying goes through.
"""
import pytest


@pytest.mark.e2e
def test_apply_stops_rather_than_delete_uncommitted_business_code(project_with_release):
    env = project_with_release
    run = env['run']
    project_dir = env['project_dir']
    db = env['db_name']

    # ── Two patches in flight, as when working on one and switching to the other
    run(['half_orm', 'dev', 'patch', 'create', '1-author'])
    run(['git', 'checkout', 'ho-release/0.1.0'])
    run(['half_orm', 'dev', 'patch', 'create', '2-thing'])

    # Patch A creates author, so applying it generates mydb/public/author.py
    run(['git', 'checkout', 'ho-patch/1-author'])
    (project_dir / 'Patches' / '1-author' / '01_author.sql').write_text(
        "CREATE TABLE author (id SERIAL PRIMARY KEY, name TEXT);\n")
    run(['half_orm', 'dev', 'patch', 'apply'])

    # The developer writes business logic in it, and does not commit it
    author_module = project_dir / db / 'public' / 'author.py'
    source = author_module.read_text()
    marker = "#>>> PLACE YOUR CODE BELOW THIS LINE. DO NOT REMOVE THIS LINE!\n"
    assert source.count(marker) == 3, "generated module layout changed"
    business_code = "\n        def shout(self):\n            return self.name.value.upper()\n"
    author_module.write_text(source + business_code)

    # ── Back to patch B: the database it rebuilds has no author table
    run(['git', 'checkout', 'ho-patch/2-thing'])
    (project_dir / 'Patches' / '2-thing' / '01_thing.sql').write_text(
        "CREATE TABLE thing (id SERIAL PRIMARY KEY, label TEXT);\n")
    applied = run(['half_orm', 'dev', 'patch', 'apply'], check=False)
    output = applied.stdout + applied.stderr

    # ── The apply stops, names the module, and leaves it untouched
    assert applied.returncode != 0, (
        "patch apply went through and deleted uncommitted business logic:\n" + output)
    assert f"{db}/public/author.py" in output, output
    assert 'commit the work' in output, output
    assert author_module.exists(), "the module must be left where it is"
    assert 'def shout(self):' in author_module.read_text()

    # ── Once the work is put away, the apply goes through
    parked = project_dir.parent / 'author.py.parked'
    author_module.rename(parked)
    run(['half_orm', 'dev', 'patch', 'apply'])

    assert (project_dir / db / 'public' / 'thing.py').exists()
    assert not author_module.exists()
    assert 'def shout(self):' in parked.read_text()
