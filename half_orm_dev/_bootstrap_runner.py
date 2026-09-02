"""
Internal entrypoint for running a single bootstrap script in a project's
own virtual environment, as a subprocess.

Invoked as:
    <venv_python> -m half_orm_dev._bootstrap_runner <script_path> <database_name>

Not a public API - used exclusively by
half_orm_dev.file_executor.execute_python_bootstrap() when a venv_python
is provided (i.e. the project declared its own dependencies via
requirements.txt). Running via -m rather than a bare script path avoids
needing to locate this file on disk from inside the target venv; it only
needs half_orm_dev importable there, which pip install -e . already
guarantees (pyproject.toml always depends on half_orm_dev).
"""

import importlib.util
import sys

from half_orm.model import Model


def main() -> None:
    script_path, database_name = sys.argv[1], sys.argv[2]

    spec = importlib.util.spec_from_file_location('_bootstrap_script', script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    run = getattr(module, 'run', None)
    if run is not None:
        model = Model(database_name)
        result = run(model)
        if result is not None:
            print(result)


if __name__ == '__main__':
    main()
