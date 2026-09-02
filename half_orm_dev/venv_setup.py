"""
Project virtual environment setup.

Creates a dedicated .venv for a cloned project when it declares its own
runtime dependencies (requirements.txt), so bootstrap scripts and other
project code can import them - separate from whatever environment
half_orm_dev itself happens to be running under.
"""

import subprocess
import sys
from pathlib import Path


class VenvSetupError(Exception):
    """Raised when creating or populating a project virtual environment fails."""
    pass


def _venv_bin_paths(venv_dir: Path) -> tuple[Path, Path]:
    """Return (python, pip) paths for a venv, platform-aware."""
    if sys.platform == 'win32':
        bin_dir = venv_dir / 'Scripts'
        return bin_dir / 'python.exe', bin_dir / 'pip.exe'
    bin_dir = venv_dir / 'bin'
    return bin_dir / 'python', bin_dir / 'pip'


def create_project_venv(project_dir: Path) -> Path:
    """
    Create project_dir/.venv and install the project into it (editable),
    pulling in requirements.txt and pyproject.toml dependencies.

    Uses sys.executable (the interpreter running half_orm_dev) to create
    the venv - there is no per-project Python version selection anywhere
    else in half_orm_dev, so this stays consistent with that.

    Args:
        project_dir: Project root (contains pyproject.toml)

    Returns:
        Path to the venv's python executable

    Raises:
        VenvSetupError: If venv creation or `pip install -e .` fails
    """
    venv_dir = project_dir / '.venv'

    try:
        subprocess.run(
            [sys.executable, '-m', 'venv', str(venv_dir)],
            check=True, capture_output=True, text=True
        )
    except subprocess.CalledProcessError as e:
        raise VenvSetupError(
            f"Failed to create virtual environment in {venv_dir}: {e.stderr.strip()}"
        ) from e

    venv_python, venv_pip = _venv_bin_paths(venv_dir)

    try:
        subprocess.run(
            [str(venv_pip), 'install', '-e', '.'],
            cwd=project_dir, check=True, capture_output=True, text=True
        )
    except subprocess.CalledProcessError as e:
        raise VenvSetupError(
            f"Failed to install project into {venv_dir}: {e.stderr.strip()}"
        ) from e

    return venv_python
