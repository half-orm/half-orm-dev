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


def migrate(repo):
    """
    Execute migration: Move staged patches to Patches/staged/.

    For each staged patch found in TOML or TXT files:
    1. Check if patch directory exists at Patches/{patch_id}/
    2. Create Patches/staged/ directory if needed
    3. Move patch directory with git mv

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

    # Collect all staged patches from both TOML and TXT files
    staged_patches = {}
    staged_patches.update(_get_staged_patches_from_toml(releases_dir))
    staged_patches.update(_get_staged_patches_from_txt(releases_dir))

    if not staged_patches:
        print("  No staged patches found, skipping migration.")
        return

    moved_count = 0
    skipped_count = 0

    for patch_id, version in staged_patches.items():
        old_path = patches_dir / patch_id
        new_path = staged_dir / patch_id

        # Skip if already moved
        if new_path.exists():
            print(f"    {patch_id}: already in staged/, skipping")
            skipped_count += 1
            continue

        # Skip if source doesn't exist
        if not old_path.exists():
            print(f"    {patch_id}: not found at root, skipping")
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

    if moved_count > 0:
        # Stage all changes
        repo.hgit.add('Patches')
        print(f"\nMigration complete: {moved_count} patch(es) moved to Patches/staged/")
    else:
        print(f"\nNo patches needed moving ({skipped_count} already in place)")
