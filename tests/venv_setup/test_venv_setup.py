"""
Tests for half_orm_dev.venv_setup.create_project_venv().

Focused on testing:
- Correct subprocess commands for venv creation and pip install
- Error handling (VenvSetupError) on failure of either step
- Platform-aware python/pip path resolution
"""

import subprocess
import sys
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from half_orm_dev.venv_setup import create_project_venv, VenvSetupError, _venv_bin_paths


class TestVenvBinPaths:
    def test_posix_paths(self):
        with patch('half_orm_dev.venv_setup.sys.platform', 'linux'):
            python, pip = _venv_bin_paths(Path('/proj/.venv'))
        assert python == Path('/proj/.venv/bin/python')
        assert pip == Path('/proj/.venv/bin/pip')

    def test_windows_paths(self):
        with patch('half_orm_dev.venv_setup.sys.platform', 'win32'):
            python, pip = _venv_bin_paths(Path('C:/proj/.venv'))
        assert python == Path('C:/proj/.venv/Scripts/python.exe')
        assert pip == Path('C:/proj/.venv/Scripts/pip.exe')


class TestCreateProjectVenv:
    @patch('half_orm_dev.venv_setup.subprocess.run')
    def test_creates_venv_and_installs_project(self, mock_run, tmp_path):
        mock_run.return_value = Mock(returncode=0)

        result = create_project_venv(tmp_path)

        assert mock_run.call_count == 2

        venv_call = mock_run.call_args_list[0]
        assert venv_call.args[0] == [sys.executable, '-m', 'venv', str(tmp_path / '.venv')]

        install_call = mock_run.call_args_list[1]
        python, pip = _venv_bin_paths(tmp_path / '.venv')
        assert install_call.args[0] == [str(pip), 'install', '-e', '.']
        assert install_call.kwargs['cwd'] == tmp_path

        assert result == python

    @patch('half_orm_dev.venv_setup.subprocess.run')
    def test_venv_creation_failure_raises(self, mock_run, tmp_path):
        mock_run.side_effect = subprocess.CalledProcessError(
            1, ['python', '-m', 'venv'], stderr='disk full'
        )

        with pytest.raises(VenvSetupError, match="disk full"):
            create_project_venv(tmp_path)

    @patch('half_orm_dev.venv_setup.subprocess.run')
    def test_pip_install_failure_raises(self, mock_run, tmp_path):
        def side_effect(cmd, **kwargs):
            if 'venv' in cmd:
                return Mock(returncode=0)
            raise subprocess.CalledProcessError(1, cmd, stderr='no such package')

        mock_run.side_effect = side_effect

        with pytest.raises(VenvSetupError, match="no such package"):
            create_project_venv(tmp_path)

    @patch('half_orm_dev.venv_setup.subprocess.run')
    def test_pip_install_not_attempted_when_venv_creation_fails(self, mock_run, tmp_path):
        mock_run.side_effect = subprocess.CalledProcessError(1, ['python', '-m', 'venv'], stderr='boom')

        with pytest.raises(VenvSetupError):
            create_project_venv(tmp_path)

        assert mock_run.call_count == 1
