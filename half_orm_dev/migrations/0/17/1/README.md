# Migration 0.17.1: Move to .hop/ directory structure

## Overview

This migration reorganizes the directory structure to consolidate half_orm_dev
files under a single `.hop/` directory.

## Changes

### Directory Moves

- `releases/` → `.hop/releases/`
- `model/` → `.hop/model/`
- `backups/` → `.hop/backups/` (only if using default location)

### Configuration Updates

- Updates `.gitignore` to exclude:
  - `.hop/local_config` (machine-specific settings)
  - `.hop/backups/` (database backups)

## Migration Files

- `00_move_to_hop.py`: Main migration logic

## Idempotency

This migration is idempotent and can be run multiple times safely:
- Skips directories that are already migrated
- Only updates `.gitignore` if entries are missing

## Rollback

To rollback (manual):
1. Move directories back: `.hop/releases/` → `releases/`, etc.
2. Remove `.hop/local_config` and `.hop/backups/` from `.gitignore`
3. Update `.hop/config` hop_version back to `0.17.0`

## Testing

Run tests after migration to ensure all functionality works correctly:
```bash
pytest tests/
```
