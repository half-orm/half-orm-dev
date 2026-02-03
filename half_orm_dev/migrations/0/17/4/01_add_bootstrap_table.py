"""
Migration to add bootstrap tracking table and directory.

This migration:
1. Creates the half_orm_meta.bootstrap table for tracking executed bootstrap scripts
2. Creates the bootstrap/ directory if it doesn't exist
"""

from pathlib import Path


def migrate(repo):
    """Add bootstrap tracking table to half_orm_meta schema."""
    sql = """
    CREATE TABLE IF NOT EXISTS half_orm_meta.bootstrap (
        filename TEXT PRIMARY KEY,
        version TEXT NOT NULL,
        executed_at TIMESTAMP DEFAULT NOW()
    );

    COMMENT ON TABLE half_orm_meta.bootstrap IS
        'Tracks executed bootstrap scripts for data initialization';
    COMMENT ON COLUMN half_orm_meta.bootstrap.filename IS
        'Bootstrap file name (e.g., 1-init-users-0.1.0.sql)';
    COMMENT ON COLUMN half_orm_meta.bootstrap.version IS
        'Release version from filename (e.g., 0.1.0)';
    COMMENT ON COLUMN half_orm_meta.bootstrap.executed_at IS
        'Timestamp when the script was executed';
    """
    repo.database.model.execute_query(sql)

    # Create bootstrap directory if not exists
    bootstrap_dir = Path(repo.base_dir) / 'bootstrap'
    created_dir = not bootstrap_dir.exists()
    bootstrap_dir.mkdir(exist_ok=True)

    # Create README if it doesn't exist
    readme_path = bootstrap_dir / 'README.md'
    created_readme = False
    if not readme_path.exists():
        readme_content = """# Bootstrap Scripts

This directory contains data initialization scripts that run after database setup.

## File Naming Convention

Files are named: `<number>-<patch_id>-<version>.<ext>`

Examples:
- `1-init-users-0.1.0.sql`
- `2-seed-config-0.1.0.py`
- `3-add-roles-0.2.0.sql`

Scripts are executed in numeric order (by the leading number).

## Usage

Run pending bootstrap scripts:
```bash
half_orm dev bootstrap
```

Options:
- `--dry-run`: Show what would be executed without running
- `--force`: Re-execute all files (ignore tracking)

## Creating Bootstrap Files

Mark patch files with `-- @HOP:bootstrap` (SQL) or `# @HOP:bootstrap` (Python)
on the first line to have them automatically copied here during `patch merge`.

Example SQL file in a patch:
```sql
-- @HOP:bootstrap
INSERT INTO roles (name) VALUES ('admin'), ('user') ON CONFLICT DO NOTHING;
```

Example Python file in a patch:
```python
# @HOP:bootstrap
from mypackage import MODEL
# ... initialization code
```

The `@HOP:data` marker is also supported for backwards compatibility.
"""
        readme_path.write_text(readme_content)
        created_readme = True

    # Add bootstrap directory to git
    if created_dir or created_readme:
        repo.hgit.add('bootstrap')

    return {
        'table_created': True,
        'directory_created': created_dir,
        'readme_created': created_readme
    }


def get_description():
    """Return migration description."""
    return "Add bootstrap tracking table (half_orm_meta.bootstrap) and bootstrap/ directory"
