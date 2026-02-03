"""
Migration: Move staged patches to Patches/staged/ subdirectory.

This migration reorganizes the Patches/ directory structure:
- candidate patches remain at Patches/{patch_id}/
- staged patches are moved to Patches/staged/{patch_id}/

This improves IDE navigation by keeping active patches at the root
for quick access while archiving merged patches in a subdirectory.
"""

from pathlib import Path

try:
    import tomli
except ImportError:
    import tomllib as tomli


def get_description():
    """Return migration description."""
    return "Move staged patches to Patches/staged/ subdirectory"


def _get_staged_patches_from_toml(releases_dir: Path) -> dict:
    """
    Read TOML files to identify staged patches.

    Returns:
        Dict mapping patch_id to version for all staged patches
    """
    staged = {}

    for toml_file in releases_dir.glob("*-patches.toml"):
        version = toml_file.stem.replace('-patches', '')

        try:
            with toml_file.open('rb') as f:
                data = tomli.load(f)

            patches = data.get("patches", {})
            for patch_id, patch_data in patches.items():
                if isinstance(patch_data, dict):
                    if patch_data.get("status") == "staged":
                        staged[patch_id] = version
                elif patch_data == "staged":
                    # Old format (should already be migrated)
                    staged[patch_id] = version

        except Exception:
            continue

    return staged


def _get_staged_patches_from_txt(releases_dir: Path) -> dict:
    """
    Read TXT files to identify production patches (all staged).

    Returns:
        Dict mapping patch_id to version for all patches in TXT files
    """
    staged = {}

    for txt_file in releases_dir.glob("*.txt"):
        # Skip -patches.toml companion files
        if '-patches' in txt_file.stem:
            continue

        version = txt_file.stem

        try:
            content = txt_file.read_text()
            for line in content.strip().split('\n'):
                patch_id = line.strip()
                if patch_id and not patch_id.startswith('#'):
                    staged[patch_id] = version

        except Exception:
            continue

    return staged


def _move_patches_on_branch(repo, patches_dir: Path, staged_dir: Path, releases_dir: Path) -> tuple:
    """
    Move staged patches on current branch.

    Returns:
        Tuple of (moved_count, skipped_count)
    """
    # Collect all staged patches from both TOML and TXT files
    staged_patches = {}
    staged_patches.update(_get_staged_patches_from_toml(releases_dir))
    staged_patches.update(_get_staged_patches_from_txt(releases_dir))

    if not staged_patches:
        return 0, 0

    moved_count = 0
    skipped_count = 0

    for patch_id, version in staged_patches.items():
        old_path = patches_dir / patch_id
        new_path = staged_dir / patch_id

        # Skip if already moved
        if new_path.exists():
            skipped_count += 1
            continue

        # Skip if source doesn't exist
        if not old_path.exists():
            skipped_count += 1
            continue

        try:
            # Ensure staged/ directory exists
            staged_dir.mkdir(exist_ok=True)

            # Use git mv to preserve history
            repo.hgit.mv(str(old_path), str(new_path))

            print(f"    {patch_id}: moved to staged/ (version {version})")
            moved_count += 1

        except Exception as e:
            print(f"    {patch_id}: error moving - {e}")
            continue

    return moved_count, skipped_count


def migrate(repo):
    """
    Execute migration: Move staged patches to Patches/staged/.

    For each staged patch found in TOML or TXT files:
    1. Check if patch directory exists at Patches/{patch_id}/
    2. Create Patches/staged/ directory if needed
    3. Move patch directory with git mv

    This migration runs on all active branches (ho-prod, ho-release/*, ho-patch/*).

    Args:
        repo: Repo instance
    """
    print("Moving staged patches to Patches/staged/ subdirectory...")

    patches_dir = Path(repo.base_dir) / "Patches"
    staged_dir = patches_dir / "staged"
    releases_dir = Path(repo.releases_dir)

    if not patches_dir.exists():
        print("  No Patches/ directory found, skipping migration.")
        return

    if not releases_dir.exists():
        print("  No releases directory found, skipping migration.")
        return

    # Save current branch
    original_branch = repo.hgit.branch
    total_moved = 0

    # Get all active branches
    try:
        branches_status = repo.hgit.get_active_branches_status()
        patch_branches = [b['name'] for b in branches_status.get('patch_branches', [])]
        release_branches = [b['name'] for b in branches_status.get('release_branches', [])]
        all_branches = ['ho-prod'] + release_branches + patch_branches
    except Exception as e:
        print(f"  Warning: Could not get active branches: {e}")
        all_branches = [original_branch]

    # Process each branch
    for branch in all_branches:
        try:
            repo.hgit.checkout(branch)

            moved, skipped = _move_patches_on_branch(repo, patches_dir, staged_dir, releases_dir)

            if moved > 0:
                # Commit changes on this branch
                repo.hgit.add('Patches')
                repo.hgit.commit('-m', f'[HOP] Move {moved} staged patch(es) to Patches/staged/')
                print(f"  {branch}: moved {moved} patch(es)")
                total_moved += moved

        except Exception as e:
            print(f"  {branch}: error - {e}")
            continue

    # Return to original branch
    try:
        repo.hgit.checkout(original_branch)
    except Exception:
        pass

    if total_moved > 0:
        print(f"\nMigration complete: {total_moved} patch(es) moved across all branches")
    else:
        print(f"\nNo patches needed moving")
