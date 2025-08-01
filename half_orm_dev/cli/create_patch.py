#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Create-Patch CLI - Commande de création de patches

Commande `create-patch` pour le workflow ultra-simplifié Git-centric.
Crée branches, directories, et réservations en une opération atomique.
"""

import click
import sys
from pathlib import Path
from typing import Optional

from half_orm import utils
from half_orm_dev.schema_patches.create_patch import (
    CreatePatchCommand, 
    CreatePatchError, 
    PatchValidationError,
    TicketValidationError,
    ConfigurationError
)


def add_create_patch_commands(dev_group, hop_instance):
    """
    Add create-patch commands to the dev group.
    
    Only registers command when conditions are met:
    - In half-orm-dev repository with meta tables
    - On ho-prod branch
    - Repository is clean
    
    Args:
        dev_group: Click group for dev commands
        hop_instance: HalfOrmDev instance with repo context
    """
    
    # Check if create-patch should be available
    if not _can_create_patch(hop_instance):
        return
    
    @click.command(name='create-patch')
    @click.argument('patch_id')
    @click.option('--force', is_flag=True, help='Force creation even with warnings')
    @click.option('--dry-run', is_flag=True, help='Show what would be created without executing')
    @click.option('--no-ticket', is_flag=True, help='Skip ticket validation (use patch_id as-is)')
    def create_patch(patch_id: str, force: bool = False, dry_run: bool = False, no_ticket: bool = False):
        """
        Create new patch branch and directory for development.
        
        Creates ho-patch/{PATCH_ID} branch from ho-prod, SchemaPatches directory,
        and global patch reservation in one atomic operation.
        
        PATCH_ID can be:
        - Just ticket number: "456" (fetches title from GitHub/GitLab)
        - Full format: "456-performance" (uses as-is)
        - Custom format: "my-custom-patch" (with --no-ticket)
        
        Examples:
        \b
        half_orm dev create-patch "456"                    # Auto: 456-user-authentication
        half_orm dev create-patch "456-custom-name"        # Manual: 456-custom-name  
        half_orm dev create-patch "my-patch" --no-ticket   # Custom: my-patch
        half_orm dev create-patch "456" --dry-run          # Preview what would be created
        """
        try:
            # Create command instance
            cmd = CreatePatchCommand(hop_instance._repo.hgit)
            
            if dry_run:
                _execute_dry_run(cmd, patch_id, no_ticket)
                return
            
            # Execute patch creation
            utils.info(f"🚀 Creating patch '{patch_id}'...")
            
            # Show ticket resolution if applicable
            if not no_ticket and _looks_like_ticket_number(patch_id):
                utils.info(f"🎫 Resolving ticket reference...")
            
            result = cmd.execute(patch_id)
            
            # Success feedback
            _display_success_result(result)
            
        except TicketValidationError as e:
            _handle_ticket_error(e)
            sys.exit(1)
        except PatchValidationError as e:
            _handle_validation_error(e)
            sys.exit(1)
        except CreatePatchError as e:
            _handle_create_patch_error(e)
            sys.exit(1)
        except Exception as e:
            utils.error(f"❌ Unexpected error: {e}")
            utils.info("Please check your repository state and try again.")
            if '--verbose' in sys.argv:  # Simple verbose check
                import traceback
                utils.error(traceback.format_exc())
            sys.exit(1)
    
    # Command is only registered when conditions are met
    dev_group.add_command(create_patch)


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


def _looks_like_ticket_number(patch_id: str) -> bool:
    """
    Check if patch_id looks like a ticket number.
    
    Args:
        patch_id: Patch identifier to check
        
    Returns:
        bool: True if looks like ticket number (just digits)
    """
    return patch_id.isdigit()


def _execute_dry_run(cmd: CreatePatchCommand, patch_id: str, no_ticket: bool):
    """
    Execute dry run showing what would be created.
    
    Args:
        cmd: CreatePatchCommand instance
        patch_id: Patch identifier
        no_ticket: Skip ticket resolution
    """
    utils.info(f"🔍 Dry run: Would create patch '{patch_id}'")
    
    try:
        # Show ticket resolution (if applicable)
        if not no_ticket and _looks_like_ticket_number(patch_id):
            utils.info(f"🎫 Would resolve ticket #{patch_id}:")
            try:
                ticket_info = cmd.fetch_ticket_info(patch_id)
                resolved_patch_id = f"{patch_id}-{cmd.generate_patch_description(ticket_info['title'])}"
                utils.info(f"   Title: {ticket_info['title']}")
                utils.info(f"   Status: {ticket_info.get('state', 'unknown')}")
                utils.info(f"   Resolved to: {resolved_patch_id}")
                final_patch_id = resolved_patch_id
            except (TicketValidationError, ConfigurationError) as e:
                utils.warning(f"   ⚠️ Ticket resolution failed: {e.message}")
                utils.info(f"   Would use patch_id as-is: {patch_id}")
                final_patch_id = patch_id
        else:
            final_patch_id = patch_id
            utils.info(f"🏷️  Using patch_id as-is: {patch_id}")
        
        # Show what would be created
        utils.info(f"\n📦 Would create:")
        utils.info(f"   Branch: {utils.Color.bold(f'ho-patch/{final_patch_id}')}")
        utils.info(f"   Directory: {utils.Color.bold(f'SchemaPatches/{final_patch_id}/')}")
        utils.info(f"   Reservation: {utils.Color.bold(f'create-patch-{final_patch_id}')}")
        
        utils.info(f"\n📝 Files that would be created:")
        utils.info(f"   SchemaPatches/{final_patch_id}/README.md")
        
        utils.success("✅ Dry run completed successfully")
        utils.info(f"Run without --dry-run to create the patch.")
        
    except Exception as e:
        utils.error(f"❌ Dry run failed: {e}")


def _display_success_result(result):
    """
    Display successful patch creation result.
    
    Args:
        result: CreatePatchResult instance
    """
    utils.success("✅ Patch created successfully!")
    utils.info(f"   Branch: {utils.Color.bold(result.branch_name)}")
    utils.info(f"   Directory: {utils.Color.bold(str(result.patch_directory))}")
    utils.info(f"   Reservation: {utils.Color.bold(result.reservation_tag)}")
    
    # Show created files
    if result.created_files:
        utils.info(f"\n📝 Created files:")
        for file_path in result.created_files:
            utils.info(f"   {file_path}")
    
    # Show warnings if any
    if result.warnings:
        utils.info(f"\n⚠️  Warnings:")
        for warning in result.warnings:
            utils.warning(f"   - {warning}")
    
    # Next steps guidance
    utils.info(f"\n📋 Next steps:")
    utils.info(f"   1. Add SQL/Python files to {result.patch_directory}")
    utils.info(f"   2. Run {utils.Color.bold('half_orm dev apply-patch')} to test")
    utils.info(f"   3. Run {utils.Color.bold('half_orm dev add-to-release')} when ready")


def _handle_ticket_error(error: TicketValidationError):
    """
    Handle ticket validation errors with helpful guidance.
    
    Args:
        error: TicketValidationError instance
    """
    utils.error(f"❌ Ticket validation failed: {error.message}")
    
    if error.patch_id:
        utils.info(f"   Ticket: #{error.patch_id}")
    
    utils.info(f"\n💡 Solutions:")
    utils.info(f"   • Check ticket exists and is accessible")
    utils.info(f"   • Verify GitHub/GitLab API configuration")
    utils.info(f"   • Use --no-ticket to skip ticket validation")
    utils.info(f"   • Use full format: '456-custom-name'")


def _handle_validation_error(error: PatchValidationError):
    """
    Handle patch validation errors with helpful guidance.
    
    Args:
        error: PatchValidationError instance
    """
    utils.error(f"❌ Patch validation failed: {error.message}")
    
    if error.patch_id:
        utils.info(f"   Patch ID: {error.patch_id}")
    
    utils.info(f"\n💡 Valid patch ID formats:")
    utils.info(f"   • 456-performance")
    utils.info(f"   • 123-security-fix")  
    utils.info(f"   • 789-new-feature")
    utils.info(f"   • Just numbers for ticket resolution: 456")


def _handle_create_patch_error(error: CreatePatchError):
    """
    Handle general create patch errors.
    
    Args:
        error: CreatePatchError instance
    """
    utils.error(f"❌ Patch creation failed: {error.message}")
    
    if error.patch_id:
        utils.info(f"   Patch ID: {error.patch_id}")
    
    if error.context:
        utils.info(f"   Context:")
        for key, value in error.context.items():
            utils.info(f"     {key}: {value}")
    
    utils.info(f"\n💡 Common solutions:")
    utils.info(f"   • Ensure you're on ho-prod branch")
    utils.info(f"   • Check repository is clean (no uncommitted changes)")
    utils.info(f"   • Verify remote access (git fetch works)")
    utils.info(f"   • Check patch ID is not already reserved")