#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Status CLI - Commande universelle adaptative + comportement par défaut

Commande `status` disponible partout qui s'adapte au contexte ET
gère l'affichage par défaut quand aucune sous-commande n'est invoquée.
"""

import click
import sys
from pathlib import Path
from typing import Optional

from half_orm import utils


def add_status_commands(dev_group, hop_instance):
    """
    Add status commands to the dev group and configure default behavior.
    
    Args:
        dev_group: Click group for dev commands
        hop_instance: Hop instance with repo context
    """
    
    @click.command()
    @click.option('--verbose', '-v', is_flag=True, help='Show detailed information')
    @click.option('--patch-id', help='Show status for specific patch')
    def status(verbose, patch_id):
        """Show comprehensive repository and development status"""
        try:
            status_info = _get_comprehensive_status(hop_instance, verbose)
            _display_status(status_info, patch_id, verbose)
            
        except Exception as e:
            utils.error(f"Failed to get status: {e}")
            if verbose:
                import traceback
                utils.error(traceback.format_exc())
            sys.exit(1)
    
    # Add status command
    dev_group.add_command(status)
    
    # ==================== CONFIGURE DEFAULT BEHAVIOR ====================
    
    # Store original callback
    original_callback = dev_group.callback
    
    @click.pass_context
    def enhanced_callback(ctx, *args, **kwargs):
        """Enhanced callback that shows status when no subcommand is provided."""
        if ctx.invoked_subcommand is None:
            # No subcommand invoked - show status and available commands
            _display_default_behavior(hop_instance)
        else:
            # Call original callback if there is one
            if original_callback:
                return original_callback(*args, **kwargs)
    
    # Replace dev group callback
    dev_group.callback = enhanced_callback


def _display_default_behavior(hop_instance):
    """
    Display default behavior when no subcommand is invoked.
    
    Args:
        hop_instance: Hop instance with repo context
    """
    # Show basic repo state
    if hop_instance.repo_checked:
        click.echo(hop_instance.state)
        
        # Show available commands based on context
        click.echo(f"\n📋 Available commands:")
        
        # Status is always available
        click.echo(f"   {utils.Color.bold('status')}: Show repository and development status")
        
        # Context-specific commands
        if 'create-patch' in hop_instance.available_commands:
            click.echo(f"   {utils.Color.bold('create-patch')}: Create new patch branch and directory")
        
        if 'new' in hop_instance.available_commands:
            click.echo(f"   {utils.Color.bold('new')}: Create new halfORM project")
        
        # Show context info
        if hop_instance._repo.devel:
            click.echo(f"\n🔧 Development mode enabled - full half-orm-dev workflow available")
        else:
            click.echo(f"\n📋 Limited mode - use 'half_orm dev new <name>' for development features")
        
    else:
        click.echo(hop_instance.state)
        click.echo("\n❌ Not in a half-orm-dev repository.")
        click.echo(f"Try {utils.Color.bold('half_orm dev new <package_name>')} to get started.\n")


def _get_comprehensive_status(hop_instance, verbose=False) -> dict:
    """
    Get comprehensive status information adaptively.
    
    Returns:
        dict: Status information with context
    """
    status = {
        'context': 'unknown',
        'repo_exists': False,
        'schema_patches_exists': False,
        'current_directory': Path.cwd(),
        'repo_path': None,
        'schema_patches_dir': None,
        'git_info': {},
        'patches_info': {},
        'suggestions': []
    }
    
    # Check if we're in a halfORM repo
    if hop_instance.repo_checked:
        status['repo_exists'] = True
        status['context'] = 'in_repo'
        status['repo_path'] = Path(hop_instance._repo.base_dir)
        
        # Check for SchemaPatches directory
        schema_patches_dir = status['repo_path'] / "SchemaPatches"
        status['schema_patches_dir'] = schema_patches_dir
        status['schema_patches_exists'] = schema_patches_dir.exists()
        
        if status['schema_patches_exists']:
            status['context'] = 'schema_patches_ready'
            status['patches_info'] = _get_patches_info(schema_patches_dir)
        else:
            status['context'] = 'repo_no_schema_patches'
            status['suggestions'].append("Initialize SchemaPatches with directory creation")
        
        # Get Git information
        try:
            hgit = hop_instance._repo.hgit
            status['git_info'] = {
                'current_branch': hgit.branch,
                'branch_type': hgit.get_branch_type(),
                'is_clean': hgit.repos_is_clean(),
                'last_commit': hgit.last_commit()
            }
        except Exception as e:
            status['git_info'] = {'error': str(e)}
    
    else:
        status['context'] = 'no_repo'
        status['suggestions'].append("Create new halfORM project with 'half_orm dev new <project_name>'")
    
    return status


def _get_patches_info(schema_patches_dir: Path) -> dict:
    """
    Get information about existing patches.
    
    Args:
        schema_patches_dir: Path to SchemaPatches directory
        
    Returns:
        dict: Patches information
    """
    patches_info = {
        'total_patches': 0,
        'patch_directories': [],
        'has_readme': False
    }
    
    try:
        # Count patch directories (exclude files)
        patch_dirs = [d for d in schema_patches_dir.iterdir() 
                     if d.is_dir() and not d.name.startswith('.')]
        
        patches_info['total_patches'] = len(patch_dirs)
        patches_info['patch_directories'] = [d.name for d in patch_dirs]
        
        # Check for README
        readme_file = schema_patches_dir / "README.md"
        patches_info['has_readme'] = readme_file.exists()
        
    except Exception as e:
        patches_info['error'] = str(e)
    
    return patches_info


def _display_status(status_info: dict, patch_id: Optional[str], verbose: bool):
    """
    Display status information adaptively based on context.
    
    Args:
        status_info: Status information
        patch_id: Specific patch to show (if any)
        verbose: Show detailed information
    """
    context = status_info['context']
    
    # Header with context
    utils.info("📊 SchemaPatches Status")
    utils.info(f"   📁 Current directory: {status_info['current_directory']}")
    
    # Adaptive display based on context
    if context == 'no_repo':
        _display_no_repo_status(status_info, verbose)
    elif context == 'repo_no_schema_patches':
        _display_repo_no_schema_patches_status(status_info, verbose)
    elif context == 'schema_patches_ready':
        _display_full_status(status_info, patch_id, verbose)
    else:
        utils.warning(f"⚠️ Unknown context: {context}")
    
    # Show suggestions
    if status_info['suggestions']:
        utils.info("\n💡 Suggestions:")
        for suggestion in status_info['suggestions']:
            utils.info(f"   • {suggestion}")


def _display_no_repo_status(status_info: dict, verbose: bool):
    """Display status when not in a halfORM repo."""
    utils.warning("⚠️ Not in a halfORM repository")
    utils.info("   SchemaPatches requires a halfORM project.")
    utils.info("")
    utils.info("🚀 To get started:")
    utils.info("   1. Create new project: half_orm dev new my_project")
    utils.info("   2. Navigate to project: cd my_project")
    utils.info("   3. Check status again: half_orm dev status")


def _display_repo_no_schema_patches_status(status_info: dict, verbose: bool):
    """Display status when in repo but no SchemaPatches."""
    utils.success("✅ In halfORM repository")
    utils.info(f"   📁 Repository: {status_info['repo_path']}")
    
    if status_info['git_info']:
        git_info = status_info['git_info']
        utils.info(f"   🌿 Branch: {git_info.get('current_branch', 'unknown')}")
        utils.info(f"   🏷️  Type: {git_info.get('branch_type', 'unknown')}")
        if verbose and 'last_commit' in git_info:
            utils.info(f"   📍 Last commit: {git_info['last_commit']}")
    
    utils.warning("⚠️ SchemaPatches not initialized")
    utils.info(f"   📁 Expected directory: {status_info['schema_patches_dir']}")
    utils.info("")
    utils.info("🚀 To initialize SchemaPatches:")
    utils.info("   mkdir SchemaPatches")
    utils.info("   # Then start creating patches...")


def _display_full_status(status_info: dict, patch_id: Optional[str], verbose: bool):
    """Display full status when SchemaPatches is ready."""
    utils.success("✅ SchemaPatches ready")
    utils.info(f"   📁 Repository: {status_info['repo_path']}")
    utils.info(f"   📁 SchemaPatches: {status_info['schema_patches_dir']}")
    
    # Git information
    if status_info['git_info']:
        git_info = status_info['git_info']
        clean_status = "clean" if git_info.get('is_clean', False) else "dirty"
        utils.info(f"   🌿 Branch: {git_info.get('current_branch', 'unknown')} ({clean_status})")
        utils.info(f"   🏷️  Type: {git_info.get('branch_type', 'unknown')}")
        if verbose and 'last_commit' in git_info:
            utils.info(f"   📍 Last commit: {git_info['last_commit']}")
    
    # Patches information
    patches_info = status_info['patches_info']
    if 'error' in patches_info:
        utils.error(f"   ❌ Error reading patches: {patches_info['error']}")
    else:
        total = patches_info['total_patches']
        utils.info(f"   📦 Patches: {total} directories found")
        
        if patch_id:
            _display_specific_patch_status(status_info, patch_id, verbose)
        elif verbose and total > 0:
            _display_all_patches_summary(patches_info)
        elif total > 0:
            utils.info(f"   📋 Use --patch-id or --verbose for details")
    
    # Available operations based on branch type
    if status_info['git_info']:
        branch_type = status_info['git_info'].get('branch_type', 'unknown')
        _display_available_operations(branch_type)


def _display_specific_patch_status(status_info: dict, patch_id: str, verbose: bool):
    """Display status for a specific patch."""
    schema_patches_dir = status_info['schema_patches_dir']
    patch_dir = schema_patches_dir / patch_id
    
    utils.info(f"\n📦 Patch: {patch_id}")
    
    if not patch_dir.exists():
        utils.warning(f"   ⚠️ Directory not found: {patch_dir}")
        return
    
    utils.success(f"   ✅ Directory exists: {patch_dir}")
    
    # Count SQL/Python files
    try:
        sql_files = list(patch_dir.glob("*.sql"))
        py_files = list(patch_dir.glob("*.py"))
        other_files = [f for f in patch_dir.iterdir() 
                      if f.is_file() and f.suffix not in ['.sql', '.py']]
        
        utils.info(f"   📄 Files: {len(sql_files)} SQL, {len(py_files)} Python, {len(other_files)} other")
        
        if verbose:
            for sql_file in sql_files:
                utils.info(f"      📄 {sql_file.name}")
            for py_file in py_files:
                utils.info(f"      🐍 {py_file.name}")
    
    except Exception as e:
        utils.error(f"   ❌ Error reading patch directory: {e}")


def _display_all_patches_summary(patches_info: dict):
    """Display summary of all patches."""
    utils.info(f"\n📋 All patches:")
    for patch_dir in patches_info['patch_directories']:
        utils.info(f"   📦 {patch_dir}")


def _display_available_operations(branch_type: str):
    """Display available operations based on branch type."""
    utils.info(f"\n🔧 Available operations (on {branch_type} branch):")
    
    if branch_type == 'patch':
        utils.info("   • Apply patches: half_orm dev apply-patch")
        utils.info("   • Run tests: half_orm dev test")
        utils.info("   • Add to release: half_orm dev add-to-release")
    elif branch_type == 'prod':
        utils.info("   • Create patches: half_orm dev create-patch")
        utils.info("   • Manage releases: half_orm dev prepare-release")
        utils.info("   • Deploy to production: half_orm dev deploy-to-prod")
    else:
        utils.info("   • Check repository status: half_orm dev status")
        utils.info("   • Switch to appropriate branch for development")