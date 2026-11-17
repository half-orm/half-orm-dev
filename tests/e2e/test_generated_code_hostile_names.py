"""
E2E tests: text read from the database must never become code in the
generated package.

Comments, constraint names, schema and relation names are database content,
and PostgreSQL accepts anything in them. Each one below is crafted so that,
written as it is into a generated file, it would create a marker file when
that file is imported - or send a module outside the package.
"""
import ast
import subprocess
import sys

import pytest


def _sql_literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def _sql_ident(text: str) -> str:
    return '"' + text.replace('"', '""') + '"'


@pytest.fixture
def hostile_project(project_with_release):
    env = project_with_release
    run = env['run']
    project_dir = env['project_dir']
    markers = {
        name: project_dir / f'PWNED_{name}'
        for name in ('table_comment', 'json_key', 'constraint')
    }

    def touch(name):
        return f"__import__('pathlib').Path({str(markers[name])!r}).touch()"

    table_comment = f'Nice table """\n{touch("table_comment")}\n"""'
    json_key = f"x = {touch('json_key')}  #"
    column_comment = (
        'Payload.\n@json\n```yaml\n'
        f'"{json_key}": text\n'
        'fine: text\n'
        '```\n')
    constraint = f"x = 1\n{touch('constraint')}\n#"

    patch_id = '1-hostile-names'
    run(['half_orm', 'dev', 'patch', 'create', patch_id])
    (project_dir / 'Patches' / patch_id / '01_hostile.sql').write_text(
        'CREATE TABLE parent (id int PRIMARY KEY);\n'
        'CREATE TABLE hostile (\n'
        '    id int PRIMARY KEY,\n'
        '    payload jsonb,\n'
        f'    parent_id int CONSTRAINT {_sql_ident(constraint)} REFERENCES parent(id)\n'
        ');\n'
        f'COMMENT ON TABLE hostile IS {_sql_literal(table_comment)};\n'
        f'COMMENT ON COLUMN hostile.payload IS {_sql_literal(column_comment)};\n'
        'CREATE TABLE "it\'s" (id int PRIMARY KEY);\n'
        'CREATE SCHEMA "esc/aped";\n'
        'CREATE TABLE "esc/aped".t (id int PRIMARY KEY);\n'
    )
    run(['half_orm', 'dev', 'patch', 'apply'])

    env['markers'] = markers
    env['package_dir'] = project_dir / env['db_name']
    return env


def _generated_files(env):
    return sorted(
        path for path in env['package_dir'].rglob('*.py')
        if '__pycache__' not in path.parts)


@pytest.mark.e2e
def test_generated_package_is_valid_python(hostile_project):
    for path in _generated_files(hostile_project):
        ast.parse(path.read_text(), filename=str(path))


@pytest.mark.e2e
def test_table_comment_stays_inside_the_docstring(hostile_project):
    path = hostile_project['package_dir'] / 'public' / 'hostile.py'
    tree = ast.parse(path.read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    assert 'PWNED_table_comment' in ast.get_docstring(cls, clean=False)
    assert not any(isinstance(node, (ast.Import, ast.ImportFrom)) for node in cls.body)


@pytest.mark.e2e
def test_json_key_is_not_emitted_as_a_statement(hostile_project):
    content = (hostile_project['package_dir'] / 'ho_typeddicts.py').read_text()
    tree = ast.parse(content)
    cls = next(node for node in tree.body
               if isinstance(node, ast.ClassDef) and node.name == 'PublicHostilePayloadDict')
    # Only annotations: the hostile key is reported in a comment, the valid
    # one is kept.
    assert [type(node) for node in cls.body] == [ast.AnnAssign]
    assert cls.body[0].target.id == 'fine'
    assert 'FIX ME' in content


@pytest.mark.e2e
def test_constraint_name_is_not_emitted_as_a_statement(hostile_project):
    content = (hostile_project['package_dir'] / 'ho_baseclasses.py').read_text()
    tree = ast.parse(content)
    cls = next(node for node in tree.body
               if isinstance(node, ast.ClassDef) and node.name == 'DC_PublicHostile')
    calls = [node for node in ast.walk(cls) if isinstance(node, ast.Call)]
    assert not any('__import__' in ast.unparse(call) for call in calls)


@pytest.mark.e2e
def test_schema_name_does_not_choose_the_directory(hostile_project):
    package_dir = hostile_project['package_dir']
    assert not (package_dir / 'esc').exists()
    assert (package_dir / 'esc_aped' / 't.py').is_file()


@pytest.mark.e2e
def test_importing_the_package_runs_nothing_from_the_database(hostile_project):
    env = hostile_project
    package = env['db_name']
    code = (
        f'import {package}.ho_typeddicts, {package}.ho_baseclasses\n'
        f'from {package}.public.hostile import Hostile\n'
        f'from {package}.ho_baseclasses import DC_PublicHostile\n'
        'Hostile()\n'
        'DC_PublicHostile()\n')
    result = subprocess.run(
        [sys.executable, '-c', code], cwd=env['project_dir'], env=env['env'] | {
            'PYTHONPATH': str(env['project_dir']),
            'HALFORM_CONF_DIR': str(env['config_dir'])},
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    created = [name for name, path in env['markers'].items() if path.exists()]
    assert created == []
