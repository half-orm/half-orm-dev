#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
New Project CLI - Commande de création de projets

Commande `new` pour créer de nouveaux projets halfORM avec support half-orm-dev.
"""

import click
from pathlib import Path

from half_orm import utils


def add_new_commands(dev_group, hop_instance):
    """
    Add new project commands to the dev group.
    
    Args:
        dev_group: Click group for dev commands
        hop_instance: Hop instance with repo context
    """
    
    @click.command()
    @click.argument('package_name')
    @click.option('-d', '--devel', is_flag=True, help="Development mode (deprecated, use --full)")
    @click.option('-f', '--full', is_flag=True, help="Full development mode with half-orm-dev")
    def new(package_name, devel=False, full=False):
        """Creates a new halfORM project with half-orm-dev support."""
        try:
            if devel:
                utils.warning("--devel option is deprecated. Please use --full instead.")
            
            # Initialize halfORM project
            utils.info(f"🚀 Creating halfORM project '{package_name}'...")
            hop_instance._repo.init(package_name, devel or full)
            
            # If full mode, setup half-orm-dev structure
            if devel or full:
                _setup_half_orm_dev_structure(package_name)
            
            utils.success(f"✅ Project '{package_name}' created successfully!")
            
            # Show next steps
            _show_next_steps(package_name, devel or full)
            
        except Exception as e:
            utils.error(f"❌ Project creation failed: {e}")
            utils.info("Please check your parameters and try again.")
    
    # Add to dev group
    dev_group.add_command(new)


def _setup_half_orm_dev_structure(package_name: str):
    """
    Setup half-orm-dev directory structure for full development mode.
    
    Args:
        package_name: Name of the package being created
    """
    project_path = Path(package_name)
    
    # Create SchemaPatches directory
    schema_patches_dir = project_path / "SchemaPatches"
    if not schema_patches_dir.exists():
        schema_patches_dir.mkdir(parents=True)
        utils.info(f"📁 Created SchemaPatches directory")
        
        # Create SchemaPatches README
        _create_schema_patches_readme(schema_patches_dir)
    
    # Create releases directory
    releases_dir = project_path / "releases"
    if not releases_dir.exists():
        releases_dir.mkdir(parents=True)
        utils.info(f"�� Created releases directory")
        
        # Create releases README
        _create_releases_readme(releases_dir)


def _create_schema_patches_readme(schema_patches_dir: Path):
    """Create README.md for SchemaPatches directory."""
    readme_content = """# SchemaPatches

Database schema patches for half-orm-dev Git-centric workflow.

## Quick Start

```bash
# Create new patch
half_orm dev create-patch "456-feature-name"

# Apply patch (from ho-patch/456-feature-name branch)
half_orm dev apply-patch

# Add to release when ready
half_orm dev add-to-release "456"
```

## File Naming Convention

Files in patch directories should follow: `seq_description.ext`

Examples:
- `01_create_tables.sql`
- `02_add_indexes.sql` 
- `03_populate_data.py`

Files are executed in lexicographic order.

## Workflow

1. **ho-prod** → main production branch
2. **ho-patch/name** → individual patch development
3. **releases/X.Y.Z-stage.txt** → development releases
4. **releases/X.Y.Z-rc1.txt** → release candidates
5. **releases/X.Y.Z.txt** → production releases

See documentation for complete workflow details.
"""
    (schema_patches_dir / "README.md").write_text(readme_content)
    utils.info(f"📝 Created SchemaPatches/README.md")


def _create_releases_readme(releases_dir: Path):
    """Create README.md for releases directory."""
    readme_content = """# Releases

Release files for half-orm-dev ultra-simplified workflow.

## File Types

- `X.Y.Z-stage.txt` - Development releases (mutable)
- `X.Y.Z-rc1.txt` - Release candidates (immutable) 
- `X.Y.Z.txt` - Production releases (immutable)
- `X.Y.Z-hotfix1.txt` - Emergency hotfixes

## Content Format

Each release file contains patch names, one per line:

```
456-user-authentication
789-security-fix
234-performance-optimization
```

## Evolution

Files evolve through Git operations:
```
1.3.4-stage.txt → git mv → 1.3.4-rc1.txt → git mv → 1.3.4.txt
```

This preserves complete history with `git log --follow`.
"""
    (releases_dir / "README.md").write_text(readme_content)
    utils.info(f"📝 Created releases/README.md")


def _show_next_steps(package_name: str, full_mode: bool):
    """Show next steps after project creation."""
    utils.info(f"\n📋 Next steps:")
    utils.info(f"   1. cd {package_name}")
    utils.info(f"   2. Configure database connection")
    
    if full_mode:
        utils.info(f"   3. half_orm dev status  # Check half-orm-dev status")
        utils.info(f"   4. half_orm dev create-patch \"456-first-feature\"")
        utils.info(f"\n🔧 Half-orm-dev workflow enabled!")
        utils.info(f"   • SchemaPatches/ for database patches")
        utils.info(f"   • releases/ for release management")
        utils.info(f"   • Ultra-simplified Git-centric workflow")
    else:
        utils.info(f"   3. half_orm dev status  # Check project status")
        utils.info(f"\n💡 For full development features:")
        utils.info(f"   Use --full flag for half-orm-dev workflow support")
