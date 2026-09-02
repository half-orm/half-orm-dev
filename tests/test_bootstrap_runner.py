"""
Tests for half_orm_dev._bootstrap_runner.main().

Invoked as `<venv_python> -m half_orm_dev._bootstrap_runner <script> <db>`
by file_executor.execute_python_bootstrap() when a project venv is
required. Covers both script shapes: with a run(model) entrypoint, and
legacy scripts with only top-level code.
"""

import sys
import pytest
from unittest.mock import Mock, patch

from half_orm_dev import _bootstrap_runner


class TestBootstrapRunnerMain:
    def test_run_entrypoint_called_with_reconnected_model(self, tmp_path, capsys):
        script = tmp_path / '01-seed.py'
        script.write_text(
            'def run(model):\n'
            '    return "seeded"\n'
        )
        mock_model_cls = Mock()
        mock_model_instance = Mock()
        mock_model_cls.return_value = mock_model_instance

        with patch.object(sys, 'argv', ['runner', str(script), 'my_db']):
            with patch.object(_bootstrap_runner, 'Model', mock_model_cls):
                _bootstrap_runner.main()

        mock_model_cls.assert_called_once_with('my_db')
        assert capsys.readouterr().out.strip() == 'seeded'

    def test_run_returning_none_prints_nothing(self, tmp_path, capsys):
        script = tmp_path / '01-seed.py'
        script.write_text('def run(model):\n    pass\n')

        with patch.object(sys, 'argv', ['runner', str(script), 'my_db']):
            with patch.object(_bootstrap_runner, 'Model', Mock()):
                _bootstrap_runner.main()

        assert capsys.readouterr().out == ''

    def test_legacy_script_without_run_just_executes(self, tmp_path, capsys):
        """No run() defined: top-level code executes, Model is never constructed."""
        script = tmp_path / '01-legacy.py'
        script.write_text('print("legacy output")')
        mock_model_cls = Mock()

        with patch.object(sys, 'argv', ['runner', str(script), 'my_db']):
            with patch.object(_bootstrap_runner, 'Model', mock_model_cls):
                _bootstrap_runner.main()

        mock_model_cls.assert_not_called()
        assert capsys.readouterr().out.strip() == 'legacy output'

    def test_script_error_propagates(self, tmp_path):
        script = tmp_path / '01-bad.py'
        script.write_text('def run(model):\n    raise ValueError("boom")\n')

        with patch.object(sys, 'argv', ['runner', str(script), 'my_db']):
            with patch.object(_bootstrap_runner, 'Model', Mock()):
                with pytest.raises(ValueError, match="boom"):
                    _bootstrap_runner.main()
