"""
Migration 1.0.0a20 — Add production-specific entries to .gitignore

Adds .hop/production and .hop/.fetching to .gitignore so that production
server marker files are not tracked by git.
"""

GITIGNORE_ENTRIES = ['.hop/production', '.hop/.fetching']


def get_description():
    return "Add .hop/production and .hop/.fetching to .gitignore"


def migrate(repo):
    from pathlib import Path

    base_dir = repo._Repo__base_dir
    gitignore_path = Path(base_dir) / '.gitignore'

    if not gitignore_path.exists():
        return {}

    content = gitignore_path.read_text()
    lines = content.splitlines()
    missing = [e for e in GITIGNORE_ENTRIES if e not in lines]

    if not missing:
        return {}

    with gitignore_path.open('a') as f:
        f.write('\n' + '\n'.join(missing) + '\n')

    repo.stage_maintenance_file('.gitignore')

    return {'sync_files': ['.gitignore']}
