"""
Migration: Convert TOML patches to dict format with merge_commit.

This migration converts the old TOML format:
    [patches]
    "1-auth" = "staged"
    "2-api" = "candidate"

To the new dict format:
    [patches]
    "1-auth" = { status = "staged", merge_commit = "abc123de" }
    "2-api" = { status = "candidate" }

For staged patches, the merge_commit hash is retrieved from git history.
"""

from pathlib import Path
import subprocess
import sys

try:
    import tomli
except ImportError:
    import tomllib as tomli

try:
    import tomli_w
except ImportError:
    raise ImportError(
        "tomli_w is required for this migration. "
        "Install it with: pip install tomli_w"
    )


def get_description():
    """Return migration description."""
    return "Convert TOML patches to dict format with merge_commit"


def find_merge_commit(repo, patch_id: str, version: str) -> str:
    """
    Find the merge commit hash for a staged patch.

    Searches git history for the commit that merged the patch branch
    into the release branch.

    Args:
        repo: Repo instance
        patch_id: Patch identifier (e.g., "456-user-auth")
        version: Release version (e.g., "0.17.0")

    Returns:
        Commit hash (8 characters) or empty string if not found
    """
    release_branch = f"ho-release/{version}"

    try:
        # Search for merge commit message pattern
        # Pattern: [HOP] Merge #PATCH_ID into %"VERSION"
        result = subprocess.run(
            ['git', 'log', '--all', '--grep', f'Merge #{patch_id}',
             '--format=%H', '-n', '1'],
            cwd=repo.base_dir,
            capture_output=True,
            text=True,
            check=True
        )

        commit_hash = result.stdout.strip()
        if commit_hash:
            return commit_hash[:8]

        # Fallback: search for the move to stage commit
        # Pattern: [HOP] move patch #PATCH_ID from candidate to stage
        result = subprocess.run(
            ['git', 'log', '--all', '--grep', f'move patch #{patch_id}',
             '--format=%H', '-n', '1'],
            cwd=repo.base_dir,
            capture_output=True,
            text=True,
            check=True
        )

        commit_hash = result.stdout.strip()
        if commit_hash:
            # Get the parent commit (the merge commit is the one before the move)
            result = subprocess.run(
                ['git', 'rev-parse', f'{commit_hash}^'],
                cwd=repo.base_dir,
                capture_output=True,
                text=True,
                check=True
            )
            parent_hash = result.stdout.strip()
            if parent_hash:
                return parent_hash[:8]

    except subprocess.CalledProcessError:
        pass

    return ""


def migrate(repo):
    """
    Execute migration: Convert TOML patches to dict format.

    For each X.Y.Z-patches.toml file:
    1. Read current content
    2. Check if already in dict format
    3. Convert to dict format:
       - candidates: { status = "candidate" }
       - staged: { status = "staged", merge_commit = "..." }
    4. Find merge_commit from git history for staged patches
    5. Write updated TOML file

    Args:
        repo: Repo instance
    """
    print("Migrating TOML patches to dict format with merge_commit...")

    releases_dir = Path(repo.releases_dir)
    if not releases_dir.exists():
        print("  No releases directory found, skipping migration.")
        return

    # Find all TOML patches files
    toml_files = list(releases_dir.glob("*-patches.toml"))

    if not toml_files:
        print("  No TOML patches files found, skipping migration.")
        return

    migrated_count = 0

    for toml_file in toml_files:
        # Extract version from filename
        version = toml_file.stem.replace('-patches', '')

        print(f"  Processing {version}...")

        try:
            # Read current TOML content
            with toml_file.open('rb') as f:
                data = tomli.load(f)

            patches = data.get("patches", {})

            if not patches:
                print(f"    No patches in {version}, skipping")
                continue

            # Check if already in dict format
            first_value = next(iter(patches.values()))
            if isinstance(first_value, dict):
                print(f"    Already in dict format, skipping")
                continue

            # Convert to dict format
            new_patches = {}
            staged_without_commit = []

            for patch_id, status in patches.items():
                if status == "candidate":
                    new_patches[patch_id] = {"status": "candidate"}
                elif status == "staged":
                    # Find merge commit from git history
                    merge_commit = find_merge_commit(repo, patch_id, version)
                    if merge_commit:
                        new_patches[patch_id] = {
                            "status": "staged",
                            "merge_commit": merge_commit
                        }
                    else:
                        # No merge_commit found, store without it
                        new_patches[patch_id] = {"status": "staged"}
                        staged_without_commit.append(patch_id)
                else:
                    # Unknown status, preserve as-is in dict format
                    new_patches[patch_id] = {"status": status}

            # Update data and write
            data["patches"] = new_patches

            with toml_file.open('wb') as f:
                tomli_w.dump(data, f)

            print(f"    Converted {len(patches)} patch(es)")
            if staged_without_commit:
                print(f"    Warning: No merge_commit found for: {', '.join(staged_without_commit)}",
                      file=sys.stderr)

            migrated_count += 1

        except Exception as e:
            print(f"  Error processing {version}: {e}", file=sys.stderr)
            continue

    repo.hgit.add('.hop')

    if migrated_count > 0:
        print(f"\nMigration complete: {migrated_count} file(s) converted to dict format")
    else:
        print("\nNo files needed migration")
