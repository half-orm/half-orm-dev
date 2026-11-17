"""
Tests for scripts/check_half_orm_release.py: the half-orm constraint under
Semantic Versioning, and the rule that half_orm_dev shares half-orm's major
version.
"""
import importlib.util
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    'check_half_orm_release', ROOT / 'scripts' / 'check_half_orm_release.py')
release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release)


@pytest.mark.parametrize('minimum, expected', [
    ('2.0.0', '>=2.0.0,<3'),
    ('2.3.1', '>=2.3.1,<3'),
    ('2.1.0rc1', '>=2.1.0rc1,<3'),
    ('3.0.0', '>=3.0.0,<4'),
])
def test_compute_constraint_stops_at_the_next_major(minimum, expected):
    assert release.compute_constraint(minimum) == expected


@pytest.mark.parametrize('dev_version', ['2.0.0', '2.0.0-a1', '2.7.3'])
def test_same_major_is_accepted(dev_version):
    release.check_majors(dev_version, '>=2.0.0,<3')


@pytest.mark.parametrize('dev_version', ['1.2.0', '1.2.0-a1', '3.0.0'])
def test_another_major_is_refused(dev_version):
    with pytest.raises(SystemExit):
        release.check_majors(dev_version, '>=2.0.0,<3')


def test_pyproject_and_requirements_agree():
    from_pyproject = release.read_constraint(ROOT / 'pyproject.toml')
    from_requirements = release.read_constraint(ROOT / 'requirements.txt')
    assert from_pyproject == from_requirements


def test_the_declared_dependency_is_the_one_read():
    "the regex must find the dependency, not some other mention of half-orm"
    data = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
    declared = [dep for dep in data['project']['dependencies']
                if dep.startswith('half-orm') and not dep.startswith('half-orm-')]
    assert declared == [f"half-orm{release.read_constraint(ROOT / 'pyproject.toml')}"]


def test_the_repository_follows_its_own_rule():
    version = (ROOT / 'half_orm_dev' / 'version.txt').read_text(encoding='utf-8').strip()
    constraint = release.read_constraint(ROOT / 'pyproject.toml')
    minimum = constraint[len('>='):].split(',')[0]
    assert constraint == release.compute_constraint(minimum)
    # version.txt is bumped by `make release`; until then it may still be 1.x.
    if not version.startswith('1.'):
        release.check_majors(version, constraint)


def test_sync_constraint_rewrites_both_files(tmp_path):
    pyproject = tmp_path / 'pyproject.toml'
    requirements = tmp_path / 'requirements.txt'
    pyproject.write_text(
        '[project.urls]\nHomepage = "https://github.com/half-orm/half-orm-dev"\n'
        '[project]\ndependencies = [\n    "click",\n    "half-orm>=2.0.0,<3",\n]\n',
        encoding='utf-8')
    requirements.write_text('half-orm>=2.0.0,<3\ntomli_w>=1.0.0\n', encoding='utf-8')

    release.sync_constraint('>=2.4.0,<3', paths=(pyproject, requirements))

    assert '"half-orm>=2.4.0,<3",' in pyproject.read_text(encoding='utf-8')
    assert 'half-orm/half-orm-dev' in pyproject.read_text(encoding='utf-8')
    assert requirements.read_text(encoding='utf-8') == 'half-orm>=2.4.0,<3\ntomli_w>=1.0.0\n'


def test_sync_constraint_refuses_a_file_without_the_requirement(tmp_path):
    empty = tmp_path / 'requirements.txt'
    empty.write_text('tomli_w>=1.0.0\n', encoding='utf-8')
    with pytest.raises(SystemExit):
        release.sync_constraint('>=2.0.0,<3', paths=(empty,))


def test_a_release_must_move_forward():
    release.check_new_version('2.0.0-a1', '1.2.0-a1')
    release.check_new_version('2.0.0', '2.0.0-a1')
    for new, current in (('1.2.0-a1', '1.2.0-a1'), ('1.1.0', '1.2.0-a1'), ('2.0.0-a1', '2.0.0')):
        with pytest.raises(SystemExit):
            release.check_new_version(new, current)


def test_a_malformed_version_is_refused():
    with pytest.raises(SystemExit):
        release.check_new_version('two', '1.2.0')


def test_update_codemeta(tmp_path):
    import json
    path = tmp_path / 'codemeta.json'
    path.write_text(json.dumps({
        'version': '0.17.5a7',
        'dateModified': '2026-02-27T09:32:29Z+0100',
        'softwareRequirements': [
            {'identifier': 'click', 'name': 'click'},
            {'identifier': 'half_orm<0.18.0', 'name': 'half_orm<0.18.0'},
            {'identifier': 'half-orm-gen', 'name': 'half-orm-gen'},
        ],
    }), encoding='utf-8')

    release.update_codemeta('2.0.0-a1', '>=2.0.0,<3', path=path)

    data = json.loads(path.read_text(encoding='utf-8'))
    assert data['version'] == '2.0.0-a1'
    assert data['dateModified'] != '2026-02-27T09:32:29Z+0100'
    identifiers = [req['identifier'] for req in data['softwareRequirements']]
    assert identifiers == ['click', 'half-orm', 'half-orm-gen']
    half_orm = data['softwareRequirements'][1]
    assert half_orm['version'] == '>=2.0.0,<3'


def test_nothing_is_written_when_a_check_fails(tmp_path, monkeypatch):
    "a refused release must leave no file to restore"
    written = []
    monkeypatch.setattr(release, 'sync_constraint', lambda *a, **k: written.append('sync'))
    monkeypatch.setattr(release, 'update_codemeta', lambda *a, **k: written.append('codemeta'))
    monkeypatch.setattr(release, '_pypi_versions', lambda package: [release.Version('2.0.0')])
    monkeypatch.setattr('sys.argv', ['check', '--min-half-orm', '2.0.0', '--dev-version', '1.3.0'])
    with pytest.raises(SystemExit):
        release.main()
    assert written == []


def test_everything_is_written_once_the_checks_pass(monkeypatch):
    written = []
    monkeypatch.setattr(release, 'sync_constraint', lambda c, **k: written.append(('sync', c)))
    monkeypatch.setattr(release, 'update_codemeta', lambda v, c, **k: written.append(('codemeta', v, c)))
    monkeypatch.setattr(release, '_pypi_versions', lambda package: [release.Version('2.0.0')])
    monkeypatch.setattr(release, 'VERSION_FILE', type('F', (), {'read_text': lambda self, **k: '1.2.0-a1\n'})())
    monkeypatch.setattr('sys.argv', ['check', '--min-half-orm', '2.0.0', '--dev-version', '2.0.0-a1'])
    release.main()
    assert written == [('sync', '>=2.0.0,<3'), ('codemeta', '2.0.0-a1', '>=2.0.0,<3')]
