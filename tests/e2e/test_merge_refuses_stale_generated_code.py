"""
Regression test: `patch merge` refuses a patch whose generated code is out
of date (#58).

Merge validation applies the patch in a temporary branch and regenerates
the package. Generated files used to be excluded from the "apply changes
nothing" check, then discarded with the temporary branch: a patch branch
whose generated code was stale passed, and its stale code reached the
release. Seen on a project where Fkeys aliases were added in a developer
zone without running `patch apply`: the docstrings and ho_baseclasses.py
only caught up on the next patch's apply.
"""
import pytest

CLASS_ZONE_MARKER = "    #>>> PLACE YOUR CODE BELOW THIS LINE. DO NOT REMOVE THIS LINE!\n"


@pytest.mark.e2e
def test_merge_refuses_stale_generated_code_until_apply(project_with_release):
    env = project_with_release
    run = env['run']
    project_dir = env['project_dir']
    db = env['db_name']

    run(['half_orm', 'dev', 'patch', 'create', '1-blog'])
    (project_dir / 'Patches' / '1-blog' / '01_blog.sql').write_text(
        "CREATE TABLE author (id SERIAL PRIMARY KEY, name TEXT);\n"
        "CREATE TABLE post (id SERIAL PRIMARY KEY,"
        " author_id INTEGER REFERENCES author(id), title TEXT);\n")
    run(['half_orm', 'dev', 'patch', 'apply'])
    run(['git', 'add', '-A'])
    run(['git', 'commit', '--no-verify', '-m', 'blog tables'])

    # ── An Fkeys alias added by hand, committed without `patch apply`
    post_module = project_dir / db / 'public' / 'post.py'
    source = post_module.read_text()
    assert source.count(CLASS_ZONE_MARKER) >= 2, "generated module layout changed"
    class_zone = source.index(CLASS_ZONE_MARKER, source.index(CLASS_ZONE_MARKER) + 1)
    insert_at = class_zone + len(CLASS_ZONE_MARKER)
    post_module.write_text(
        source[:insert_at]
        + "    Fkeys = {'_fk_author': 'post_author_id_fkey'}\n"
        + source[insert_at:])
    run(['git', 'commit', '--no-verify', '-am', 'alias the author foreign key'])

    release_before = run(['git', 'rev-parse', 'ho-release/0.1.0']).stdout.strip()
    refused = run(['half_orm', 'dev', 'patch', 'merge', '--force'], check=False)
    output = refused.stdout + refused.stderr

    assert refused.returncode != 0, (
        "patch merge accepted stale generated code:\n" + output)
    assert 'generated code is out of date' in output, output
    assert f'{db}/ho_baseclasses.py' in output, output
    assert 'half_orm dev patch apply' in output, output

    # Nothing was merged: the patch is still a candidate on its branch
    assert run(['git', 'branch', '--show-current']).stdout.strip() == 'ho-patch/1-blog'
    assert run(['git', 'rev-parse', 'ho-release/0.1.0']).stdout.strip() == release_before

    # ── Regenerated and committed, the patch merges
    run(['half_orm', 'dev', 'patch', 'apply'])
    assert '_fk_author' in (project_dir / db / 'ho_baseclasses.py').read_text()
    run(['git', 'add', '-A'])
    run(['git', 'commit', '--no-verify', '-m', 'regenerate'])

    merged = run(['half_orm', 'dev', 'patch', 'merge', '--force'], check=False)
    assert merged.returncode == 0, merged.stdout + merged.stderr
