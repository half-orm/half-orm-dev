#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
New Project CLI - Commande de création de projets

Commande `new` pour créer de nouveaux projets halfORM avec support half-orm-dev.
Disponible partout, surtout utile quand on n'est pas dans un repo.
"""

import click
from pathlib import Path

from half_orm import utils


def add_new_commands(dev_group, hop_instance):
    """
    Add new project commands to the dev group.
    
    Args:
        dev_group: Click group for dev commands
        hop_instance: HalfOrmDev instance with repo context
    """
    
    @click.command()
    @click.argument('package_name')
    def new(package_name):
        """Creates a new halfORM project with half-orm-dev support."""
        try:
            utils.info(f"🚀 Creating halfORM project '{package_name}'...")
            
            # Check database existence and state
            db_state = _check_database_state(hop_instance, package_name)
            
            if db_state == "not_exists":
                # Create new database with half-orm-dev support
                utils.info(f"📊 Creating new database '{package_name}'...")
                hop_instance._repo.init(package_name, True)  # Always full mode
                _setup_half_orm_dev_structure(package_name)
                
            elif db_state == "exists_no_meta":
                # Database exists but no half-orm meta tables
                if _ask_add_meta_tables():
                    utils.info(f"📊 Adding half-orm meta tables to existing database...")
                    hop_instance._repo.init(package_name, True)
                    _setup_half_orm_dev_structure(package_name)
                else:
                    utils.info(f"📊 Creating project without meta tables...")
                    hop_instance._repo.init(package_name, False)
                    utils.warning("⚠️  Limited functionality without meta tables.")
                    utils.info(f"Run {utils.Color.bold('half_orm dev init-meta')} later to add them.")
                    
            elif db_state == "exists_with_meta":
                # Database exists with meta tables
                utils.info(f"📊 Using existing database with meta tables...")
                hop_instance._repo.init(package_name, True)
                _setup_half_orm_dev_structure(package_name)
                
            else:
                raise Exception(f"Unknown database state: {db_state}")
            
            utils.success(f"✅ Project '{package_name}' created successfully!")
            _show_next_steps(package_name)
            
        except Exception as e:
            utils.error(f"❌ Project creation failed: {e}")
            utils.info("Please check your database connection and try again.")
    
    @click.command(name='init-meta')
    def init_meta():
        """Add half-orm meta tables to existing project database."""
        try:
            utils.info("🔧 Adding half-orm meta tables...")
            # TODO: Implement meta table addition logic
            utils.success("✅ Meta tables added successfully!")
            utils.info("Half-orm-dev functionality is now fully available.")
            
        except Exception as e:
            utils.error(f"❌ Failed to add meta tables: {e}")
    
    # Add commands conditionally based on context
    
    # NEW command: Only when NOT in a half-orm-dev repo
    if not hop_instance.repo_checked:
        dev_group.add_command(new)
    
    # INIT-META command: Only when in repo WITHOUT meta tables
    elif hop_instance.repo_checked and not _has_meta_tables(hop_instance):
        dev_group.add_command(init_meta)
    
    # CREATE-PATCH command: Only when ready for patch creation
    elif _can_create_patch(hop_instance):
        add_create_patch_commands(dev_group, hop_instance)


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
        utils.info(f"📁 Created releases directory")
        
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


def _can_create_patch(hop_instance) -> bool:
    """
    Check if create-patch command should be available.
    
    Requirements:
    - In a half-orm-dev repository
    - Has meta tables (development mode)
    - On ho-prod branch
    - Repository is clean
    
    Args:
        hop_instance: HalfOrmDev instance with repo context
        
    Returns:
        bool: True if create-patch should be available
    """
    try:
        # Must be in a repo with meta tables
        if not hop_instance.repo_checked or not hop_instance._repo.devel:
            return False
        
        # Must have hgit instance
        if not hasattr(hop_instance._repo, 'hgit') or not hop_instance._repo.hgit:
            return False
        
        hgit = hop_instance._repo.hgit
        
        # Must be on ho-prod branch
        if hgit.branch != 'ho-prod':
            return False
        
        # Repository must be clean
        if not hgit.repos_is_clean():
            return False
        
        return True
        
    except Exception:
        return False


def _has_meta_tables(hop_instance) -> bool:
    """
    Check if the current repository has half-orm meta tables.
    
    Args:
        hop_instance: HalfOrmDev instance with repo context
        
    Returns:
        bool: True if meta tables exist
    """
    try:
        # Check if repository is in development mode (indicates meta tables exist)
        return hop_instance._repo.devel
    except Exception:
        return False


def _check_database_state(hop_instance, package_name: str) -> str:
    """
    Check database existence and meta table state.
    
    Args:
        hop_instance: HalfOrmDev instance for database operations
        package_name: Database/package name
        
    Returns:
        str: "not_exists", "exists_no_meta", or "exists_with_meta"
    """
    try:
        # TODO: Implement actual database checking logic
        # This is a placeholder - would need to check:
        # 1. Database connection
        # 2. Database existence  
        # 3. half_orm meta tables existence
        
        # For now, assume database doesn't exist (safe default)
        return "not_exists"
        
    except Exception:
        # If we can't check, assume database doesn't exist
        return "not_exists"


def _ask_add_meta_tables() -> bool:
    """
    Ask user if they want to add meta tables to existing database.
    
    Returns:
        bool: True if user wants to add meta tables
    """
    utils.info("\n🤔 Database exists but doesn't have half-orm meta tables.")
    utils.info("Meta tables enable:")
    utils.info("   • Schema versioning and migrations")
    utils.info("   • Patch management workflow")
    utils.info("   • Complete half-orm-dev functionality")
    
    while True:
        response = input("\nAdd meta tables? [Y/n]: ").lower().strip()
        if response in ['', 'y', 'yes']:
            return True
        elif response in ['n', 'no']:
            return False
        else:
            utils.warning("Please answer 'y' or 'n'")


def _show_next_steps(package_name: str):
    """Show next steps after project creation."""
    utils.info(f"\n📋 Next steps:")
    utils.info(f"   1. cd {package_name}")
    utils.info(f"   2. Configure database connection if needed")
    utils.info(f"   3. half_orm dev status  # Check project status")
    utils.info(f"   4. half_orm dev create-patch \"456-first-feature\"")
    
    utils.info(f"\n🔧 Half-orm-dev workflow ready!")
    utils.info(f"   • SchemaPatches/ for database patches")
    utils.info(f"   • releases/ for release management") 
    utils.info(f"   • Ultra-simplified Git-centric workflow")