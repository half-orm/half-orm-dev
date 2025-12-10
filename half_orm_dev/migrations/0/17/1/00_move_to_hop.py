"""
Migration 0.17.1: Move directories to .hop/

Migrates legacy directory structure to new .hop/ structure:
- releases/ → .hop/releases/
- model/ → .hop/model/
- backups/ → .hop/backups/ (only if using default location)

Also updates .gitignore to include .hop/local_config and .hop/backups/
"""

import os
import shutil


def migrate(repo):
    """
    Execute migration: move directories to .hop/ and update .gitignore.

    This migration is idempotent - it can be run multiple times safely.

    Args:
        repo: Repo instance
    """
    base_dir = repo.base_dir

    result = {
        'migrated': [],
        'skipped': [],
        'errors': []
    }

    # Define migrations
    migrations = [
        ('releases', os.path.join(base_dir, 'releases'),
         os.path.join(base_dir, '.hop', 'releases')),
        ('model', os.path.join(base_dir, 'model'),
         os.path.join(base_dir, '.hop', 'model')),
    ]

    # Only migrate backups if using default location (no custom config)
    env_backups = os.environ.get('HALF_ORM_BACKUPS_DIR')
    has_custom_backups = (env_backups or
                         (hasattr(repo, '_Repo__local_config') and
                          repo._Repo__local_config and
                          repo._Repo__local_config.backups_dir))

    if not has_custom_backups:
        migrations.append(
            ('backups', os.path.join(base_dir, 'backups'),
             os.path.join(base_dir, '.hop', 'backups'))
        )

    # Execute migrations
    for name, old_path, new_path in migrations:
        # Skip if old directory doesn't exist
        if not os.path.exists(old_path):
            continue

        # Skip if new directory already exists (already migrated)
        if os.path.exists(new_path):
            result['skipped'].append({
                'name': name,
                'reason': 'target already exists',
                'old_path': old_path,
                'new_path': new_path
            })
            continue

        try:
            # Ensure .hop directory exists
            hop_dir = os.path.join(base_dir, '.hop')
            os.makedirs(hop_dir, exist_ok=True)

            # Move directory
            shutil.move(old_path, new_path)
            result['migrated'].append({
                'name': name,
                'old_path': old_path,
                'new_path': new_path
            })
        except Exception as e:
            result['errors'].append({
                'name': name,
                'old_path': old_path,
                'new_path': new_path,
                'error': str(e)
            })

    # Update .gitignore
    _update_gitignore(base_dir)
    repo.hgit.add('.gitignore')
    repo.hgit.add('.hop')
    repo.hgit.add('model')
    repo.hgit.add('releases')

    return result


def _update_gitignore(base_dir):
    """
    Update .gitignore to include .hop/local_config and .hop/backups/.

    Only adds entries if they don't already exist in the file.
    Safe to call multiple times (idempotent).

    Args:
        base_dir: Base directory of the repository
    """
    gitignore_path = os.path.join(base_dir, '.gitignore')

    # Skip if .gitignore doesn't exist
    if not os.path.exists(gitignore_path):
        return

    # Read current content
    with open(gitignore_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Check what needs to be added
    entries_to_add = []
    if '.hop/local_config' not in content:
        entries_to_add.append('.hop/local_config')
    if '.hop/backups/' not in content:
        entries_to_add.append('.hop/backups/')

    # Nothing to add
    if not entries_to_add:
        return

    # Add entries at the end
    new_content = content.rstrip() + '\n' + '\n'.join(entries_to_add) + '\n'

    with open(gitignore_path, 'w', encoding='utf-8') as f:
        f.write(new_content)


def get_description():
    """Return migration description."""
    return "Move releases/, model/, backups/ directories to .hop/ structure"
