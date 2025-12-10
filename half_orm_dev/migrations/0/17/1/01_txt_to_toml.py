"""
Migration: Convert release tracking files from TXT to TOML format.

This migration converts the dual-file system (X.Y.Z-candidates.txt + X.Y.Z-stage.txt)
to the new single-file TOML format (X.Y.Z-patches.toml).

IMPORTANT: This migration only affects development tracking files.
It does NOT touch release/production files (-rc*.txt, .txt, -hotfix*.txt).
"""

from pathlib import Path
import sys

try:
    import tomli_w
except ImportError:
    raise ImportError(
        "tomli_w is required for this migration. "
        "Install it with: pip install tomli_w"
    )


def get_description():
    """Return migration description."""
    return "Convert release tracking files from TXT to TOML format"


def read_patches_from_file(file_path: Path) -> list:
    """
    Read patches from a TXT file.

    Args:
        file_path: Path to candidates.txt or stage.txt

    Returns:
        List of patch IDs in order
    """
    if not file_path.exists():
        return []

    try:
        content = file_path.read_text(encoding='utf-8').strip()
        if not content:
            return []

        # Parse patches, skip empty lines and comments
        patches = [
            line.strip()
            for line in content.split('\n')
            if line.strip() and not line.strip().startswith('#')
        ]
        return patches

    except Exception as e:
        print(f"Warning: Failed to read {file_path}: {e}", file=sys.stderr)
        return []


def migrate(repo):
    """
    Execute migration: Convert TXT files to TOML format.

    For each X.Y.Z release in development:
    1. Find X.Y.Z-candidates.txt
    2. Read X.Y.Z-candidates.txt (if exists)
    3. Read X.Y.Z-stage.txt (if exists)
    4. Create X.Y.Z-patches.toml with:
       - All staged first (status="staged")
       - All candidates second (status="candidate")
    5. Delete old TXT files

    Note: Staged patches are placed first, then candidates.
    This maintains the correct application order where staged patches
    (already integrated) come before candidates (still in development).

    Args:
        repo: Repo instance
    """
    print("Migrating release tracking files from TXT to TOML format...")

    releases_dir = Path(repo.releases_dir)
    if not releases_dir.exists():
        print("  No releases directory found, skipping migration.")
        return

    # Find all candidates files
    candidates_files = list(releases_dir.glob("*-candidates.txt"))

    if not candidates_files:
        print("  No candidates files found, skipping migration.")
        return

    migrated_count = 0

    for candidates_file in candidates_files:
        # Extract version from filename
        version = candidates_file.stem.replace('-candidates', '')
        stage_file = releases_dir / f"{version}-stage.txt"
        toml_file = releases_dir / f"{version}-patches.toml"

        # Skip if TOML file already exists
        if toml_file.exists():
            print(f"  Skipping {version}: TOML file already exists")
            continue

        print(f"  Migrating {version}...")

        try:
            # Read patches from TXT files
            candidates = read_patches_from_file(candidates_file)
            staged = read_patches_from_file(stage_file) if stage_file.exists() else []

            # Create TOML structure
            toml_data = {"patches": {}}

            # Add staged FIRST (they should appear before candidates in application order)
            for patch_id in staged:
                toml_data["patches"][patch_id] = "staged"

            # Add candidates SECOND (they come after staged patches)
            for patch_id in candidates:
                # If a patch appears in both files (shouldn't happen, but handle it)
                if patch_id in toml_data["patches"]:
                    print(f"    Warning: Patch {patch_id} found in both candidates and stage, "
                          f"keeping as staged", file=sys.stderr)
                else:
                    toml_data["patches"][patch_id] = "candidate"

            # Write TOML file
            with toml_file.open('wb') as f:
                tomli_w.dump(toml_data, f)

            print(f"    Created {toml_file.name}")
            print(f"      Candidates: {len(candidates)}")
            print(f"      Staged: {len(staged)}")

            # Delete old TXT files
            candidates_file.unlink()
            print(f"    Deleted {candidates_file.name}")

            if stage_file.exists():
                stage_file.unlink()
                print(f"    Deleted {stage_file.name}")

            migrated_count += 1

        except Exception as e:
            print(f"  Error migrating {version}: {e}", file=sys.stderr)
            # Don't fail the entire migration if one version fails
            continue
    repo.hgit.add('.hop')

    if migrated_count > 0:
        print(f"\nMigration complete: {migrated_count} release(s) converted to TOML format")
    else:
        print("\nNo releases migrated")
