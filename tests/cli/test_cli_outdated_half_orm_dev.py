"""
When the repository requires another half_orm_dev than the one installed,
the CLI installs it on a development machine, and refuses on a production
server: nothing is installed behind an operator's back there.
"""
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from half_orm_dev.repo import OutdatedHalfORMDevError
from half_orm_dev.utils import is_production_checkout


# -- telling a production checkout apart, without a database ------------------

@pytest.fixture
def checkout(tmp_path, monkeypatch):
    base = tmp_path / 'project'
    (base / '.hop').mkdir(parents=True)
    conf_dir = tmp_path / 'conf'
    conf_dir.mkdir()
    import half_orm.model
    monkeypatch.setattr(half_orm.model, 'CONF_DIR', str(conf_dir))
    return base, conf_dir


def test_a_development_checkout(checkout):
    base, _ = checkout
    assert is_production_checkout(base) is False


def test_the_production_marker(checkout):
    base, _ = checkout
    (base / '.hop' / 'production').touch()
    assert is_production_checkout(base) is True


@pytest.mark.parametrize('value, expected', [
    ('true', True), ('True', True), ('1', True), ('yes', True),
    ('false', False), ('False', False), ('0', False),
])
def test_the_connection_file(checkout, value, expected):
    base, conf_dir = checkout
    (conf_dir / 'project').write_text(f'[database]\nname = project\nproduction = {value}\n')
    assert is_production_checkout(base) is expected


@pytest.mark.parametrize('content', ['not an ini file', '[database]\nproduction = maybe\n'])
def test_an_unreadable_connection_file_is_not_production(checkout, content):
    base, conf_dir = checkout
    (conf_dir / 'project').write_text(content)
    assert is_production_checkout(base) is False


# -- what the CLI does about it ----------------------------------------------

def _invoke(base_dir, production):
    from half_orm_dev.cli import main as cli_main
    error = OutdatedHalfORMDevError('2.0.0-a1', '1.2.0-a1', base_dir=str(base_dir))
    with patch.object(cli_main, 'Repo', side_effect=error), \
         patch.object(cli_main, 'is_production_checkout', return_value=production), \
         patch.object(cli_main.subprocess, 'run') as run, \
         patch.object(cli_main.os, 'execv') as execv:
        result = CliRunner().invoke(cli_main.create_cli_group(), ['upgrade'])
    return result, run, execv


def test_production_refuses_to_install(tmp_path):
    result, run, execv = _invoke(tmp_path, production=True)
    assert result.exit_code == 1
    assert 'pip install half-orm-dev==2.0.0-a1' in result.output
    assert 'nothing is installed automatically' in result.output
    run.assert_not_called()
    execv.assert_not_called()


def test_development_installs_and_restarts(tmp_path):
    result, run, execv = _invoke(tmp_path, production=False)
    run.assert_called_once()
    assert run.call_args[0][0][-1] == 'half-orm-dev==2.0.0-a1'
    execv.assert_called_once()
