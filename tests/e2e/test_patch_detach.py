"""
End-to-end tests for patch detach functionality.

Tests the workflow of detaching a candidate patch from its release:
- Patch is removed from TOML file
- Directory is moved to Patches/orphaned/
- Git branch is kept, renamed ho-detached/<id>, for future reattachment
- CLI command with confirmation
- Check command shows orphaned patches
"""

import pytest
from pathlib import Path

from tests.e2e.conftest import run_cmd


@pytest.mark.integration
class TestPatchDetach:
    """Test patch detach workflow."""

    def test_detach_candidate_patch_success(self, project_with_release):
        """Test successfully detaching a candidate patch from patch branch."""
        env = project_with_release
        run = env['run']
        project_dir = env['project_dir']

        # Create a patch (becomes candidate)
        run(['half_orm', 'dev', 'patch', 'create', '1-feature-to-detach'])

        # Add SQL file to patch
        patch_dir = project_dir / 'Patches' / '1-feature-to-detach'
        sql_file = patch_dir / '01_test.sql'
        sql_file.write_text("CREATE TABLE public.test_detach (id INT);")

        # Apply patch (but don't merge - keep as candidate)
        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Add detach test patch', '--no-verify'])

        # Detach from patch branch (where directory exists)
        # The --force skips confirmation
        result = run(['half_orm', 'dev', 'patch', 'detach', '--force'])

        # Verify success message
        assert 'detached' in result.stdout.lower() or result.returncode == 0

        # Go to release branch to verify changes
        run(['git', 'checkout', 'ho-release/0.1.0'])

        # Verify patch is in orphaned/
        orphaned_dir = project_dir / 'Patches' / 'orphaned' / '1-feature-to-detach'
        root_dir = project_dir / 'Patches' / '1-feature-to-detach'

        assert orphaned_dir.exists(), "Patch should be moved to Patches/orphaned/"
        assert not root_dir.exists(), "Patch should NOT be at root anymore"
        assert (orphaned_dir / '01_test.sql').exists(), "SQL file should be preserved"

    def test_detach_removes_from_toml(self, project_with_release):
        """Test that detach removes patch from TOML file."""
        env = project_with_release
        run = env['run']
        project_dir = env['project_dir']

        # Create a patch
        run(['half_orm', 'dev', 'patch', 'create', '2-toml-test'])

        patch_dir = project_dir / 'Patches' / '2-toml-test'
        (patch_dir / '01_test.sql').write_text("CREATE TABLE toml_test (id INT);")
        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'TOML test patch', '--no-verify'])

        # Go to release branch
        run(['git', 'checkout', 'ho-release/0.1.0'])

        # Verify patch is in TOML before detach
        toml_file = project_dir / '.hop' / 'releases' / '0.1.0-patches.toml'
        toml_content = toml_file.read_text()
        assert '2-toml-test' in toml_content, "Patch should be in TOML before detach"

        # Detach
        run(['half_orm', 'dev', 'patch', 'detach', '2-toml-test', '--force'])

        # Verify patch is removed from TOML
        toml_content = toml_file.read_text()
        assert '2-toml-test' not in toml_content, "Patch should be removed from TOML"

    def test_detach_preserves_git_branch(self, project_with_release):
        """Test that git branch is preserved after detach."""
        env = project_with_release
        run = env['run']
        project_dir = env['project_dir']

        # Create a patch
        run(['half_orm', 'dev', 'patch', 'create', '3-branch-test'])

        patch_dir = project_dir / 'Patches' / '3-branch-test'
        (patch_dir / '01_test.sql').write_text("CREATE TABLE branch_test (id INT);")
        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Branch test patch', '--no-verify'])

        # Go to release branch and detach
        run(['git', 'checkout', 'ho-release/0.1.0'])
        run(['half_orm', 'dev', 'patch', 'detach', '3-branch-test', '--force'])

        # The branch is kept, frozen under ho-detached/, locally and on origin
        result = run(['git', 'branch', '-a'])
        assert 'ho-detached/3-branch-test' in result.stdout, "Git branch should be preserved"
        assert 'ho-patch/3-branch-test' not in result.stdout, "ho-patch/ name should be gone"

    def test_detach_staged_patch_fails(self, project_with_release):
        """Test that detaching a staged patch fails."""
        env = project_with_release
        run = env['run']
        project_dir = env['project_dir']

        # Create and merge a patch (becomes staged)
        run(['half_orm', 'dev', 'patch', 'create', '4-staged-patch'])

        patch_dir = project_dir / 'Patches' / '4-staged-patch'
        (patch_dir / '01_test.sql').write_text("CREATE TABLE staged_test (id INT);")
        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Staged test patch', '--no-verify'])
        run(['half_orm', 'dev', 'patch', 'merge', '--force'])

        # Go to release branch
        run(['git', 'checkout', 'ho-release/0.1.0'])

        # Try to detach staged patch - should fail
        result = run(['half_orm', 'dev', 'patch', 'detach', '4-staged-patch', '--force'], check=False)

        assert result.returncode != 0, "Detaching staged patch should fail"
        assert 'staged' in result.stdout.lower() or 'staged' in result.stderr.lower(), \
            "Error message should mention staged"

    def test_detach_nonexistent_patch_fails(self, project_with_release):
        """Test that detaching unknown patch fails."""
        env = project_with_release
        run = env['run']

        # Go to release branch
        run(['git', 'checkout', 'ho-release/0.1.0'])

        # Try to detach nonexistent patch
        result = run(['half_orm', 'dev', 'patch', 'detach', '999-unknown', '--force'], check=False)

        assert result.returncode != 0, "Detaching unknown patch should fail"
        assert 'not found' in result.stdout.lower() or 'not found' in result.stderr.lower(), \
            "Error message should say not found"

    def test_check_shows_orphaned_patches(self, project_with_release):
        """Test that 'check' command displays orphaned patches."""
        env = project_with_release
        run = env['run']
        project_dir = env['project_dir']

        # Create a patch
        run(['half_orm', 'dev', 'patch', 'create', '5-orphan-check'])

        patch_dir = project_dir / 'Patches' / '5-orphan-check'
        (patch_dir / '01_test.sql').write_text("CREATE TABLE orphan_check (id INT);")
        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Orphan check patch', '--no-verify'])

        # Go to release branch and detach
        run(['git', 'checkout', 'ho-release/0.1.0'])
        run(['half_orm', 'dev', 'patch', 'detach', '5-orphan-check', '--force'])

        # Run check and verify orphaned patches are shown
        result = run(['half_orm', 'dev', 'check'])

        # (The patch name contains "orphan": look for the section itself.)
        assert 'Orphaned patches' in result.stdout, "Check should list orphaned patches"
        section = result.stdout.split('Orphaned patches', 1)[1]
        assert '5-orphan-check' in section, "Check should show orphaned patch"

    def test_detach_from_release_records_the_patch_directory(self, project_with_release):
        """Detached from the release branch, where the patch directory is
        not: it is taken from the patch branch, so the release records the
        patch as orphaned, with its work. The move is propagated: no branch
        is left with both Patches/<id> and Patches/orphaned/<id>."""
        env = project_with_release
        run = env['run']
        project_dir = env['project_dir']

        run(['half_orm', 'dev', 'patch', 'create', '10-from-release'])
        sql = "CREATE TABLE from_release (id INT);"
        (project_dir / 'Patches' / '10-from-release' / '01_test.sql').write_text(sql)
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Work', '--no-verify'])
        run(['git', 'checkout', 'ho-release/0.1.0'])

        run(['half_orm', 'dev', 'patch', 'detach', '10-from-release', '--force'])

        for ref in ('ho-release/0.1.0', 'ho-prod', 'ho-detached/10-from-release'):
            assert run(['git', 'show', f'{ref}:Patches/orphaned/10-from-release/01_test.sql']
                       ).stdout == sql, ref
            assert run(['git', 'ls-tree', '-d', ref, 'Patches/10-from-release']).stdout == '', ref
        assert run(['git', 'status', '--porcelain']).stdout == ''

        # And it can be attached back
        result = run(['half_orm', 'dev', 'release', 'attach-patch', '10-from-release', '--force'])
        assert result.returncode == 0
        assert run(['git', 'show', 'ho-patch/10-from-release:Patches/10-from-release/01_test.sql']
                   ).stdout == sql

    def test_detach_from_current_branch(self, project_with_release):
        """Test detach from current patch branch (auto-detect patch_id)."""
        env = project_with_release
        run = env['run']
        project_dir = env['project_dir']

        # Create a patch
        run(['half_orm', 'dev', 'patch', 'create', '6-auto-detect'])

        patch_dir = project_dir / 'Patches' / '6-auto-detect'
        (patch_dir / '01_test.sql').write_text("CREATE TABLE auto_detect (id INT);")
        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Auto detect patch', '--no-verify'])

        # Stay on patch branch and detach (should auto-detect patch_id)
        # Note: We're on ho-patch/6-auto-detect
        result = run(['half_orm', 'dev', 'patch', 'detach', '--force'])

        # Verify success message mentions the patch
        assert '6-auto-detect' in result.stdout or result.returncode == 0

        # Checkout release branch to see orphaned directory
        run(['git', 'checkout', 'ho-release/0.1.0'])

        # Verify patch is in orphaned/
        orphaned_dir = project_dir / 'Patches' / 'orphaned' / '6-auto-detect'
        assert orphaned_dir.exists(), "Patch should be moved to orphaned/"

        # Verify patch is removed from TOML
        toml_file = project_dir / '.hop' / 'releases' / '0.1.0-patches.toml'
        toml_content = toml_file.read_text()
        assert '6-auto-detect' not in toml_content, "Patch should be removed from TOML"


@pytest.mark.integration
class TestPatchDetachEdgeCases:
    """Test edge cases for patch detach."""

    def test_detach_updates_status_map(self, project_with_release):
        """Test that status map is updated after detach."""
        env = project_with_release
        run = env['run']
        project_dir = env['project_dir']

        # Create a patch
        run(['half_orm', 'dev', 'patch', 'create', '7-status-test'])

        patch_dir = project_dir / 'Patches' / '7-status-test'
        (patch_dir / '01_test.sql').write_text("CREATE TABLE status_test (id INT);")
        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Status test patch', '--no-verify'])

        # Check status before detach (on patch branch)
        result = run_cmd(
            ['python', '-c', '''
import sys
sys.path.insert(0, ".")
from half_orm_dev.repo import Repo
repo = Repo()
status_map = repo.patch_manager.get_patch_status_map()
patch_info = status_map.get("7-status-test", {})
print(f"STATUS:{patch_info.get('status', 'NOT_FOUND')}")
'''],
            cwd=str(project_dir),
            env=env['env'],
            check=False
        )
        assert 'STATUS:candidate' in result.stdout, "Patch should be candidate before detach"

        # Detach from patch branch (where directory exists)
        run(['half_orm', 'dev', 'patch', 'detach', '--force'])

        # Check status after detach (go to release branch to verify)
        run(['git', 'checkout', 'ho-release/0.1.0'])
        result = run_cmd(
            ['python', '-c', '''
import sys
sys.path.insert(0, ".")
from half_orm_dev.repo import Repo
repo = Repo()
status_map = repo.patch_manager.get_patch_status_map()
patch_info = status_map.get("7-status-test", {})
print(f"STATUS:{patch_info.get('status', 'NOT_FOUND')}")
'''],
            cwd=str(project_dir),
            env=env['env'],
            check=False
        )
        assert 'STATUS:orphaned' in result.stdout, "Patch should be orphaned after detach"

    def test_detach_preserves_other_patches(self, project_with_release):
        """Test that detaching one patch doesn't affect others."""
        env = project_with_release
        run = env['run']
        project_dir = env['project_dir']

        # Create first patch
        run(['half_orm', 'dev', 'patch', 'create', '81-first'])
        patch_dir1 = project_dir / 'Patches' / '81-first'
        (patch_dir1 / '01_test.sql').write_text("CREATE TABLE first (id INT);")
        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'First patch', '--no-verify'])

        # Go to release branch and create second patch (different number)
        run(['git', 'checkout', 'ho-release/0.1.0'])
        run(['half_orm', 'dev', 'patch', 'create', '82-second'])
        patch_dir2 = project_dir / 'Patches' / '82-second'
        (patch_dir2 / '01_test.sql').write_text("CREATE TABLE second (id INT);")
        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Second patch', '--no-verify'])

        # Detach first patch from second patch branch (directory not available)
        # Go to release branch where both are listed in TOML
        run(['git', 'checkout', 'ho-release/0.1.0'])

        # First patch's directory doesn't exist here, but TOML entry will be removed
        run(['half_orm', 'dev', 'patch', 'detach', '81-first', '--force'])

        # Verify second patch is still in TOML
        toml_file = project_dir / '.hop' / 'releases' / '0.1.0-patches.toml'
        toml_content = toml_file.read_text()
        assert '81-first' not in toml_content, "First patch should be removed"
        assert '82-second' in toml_content, "Second patch should be preserved"
    def test_detach_two_patches_one_after_the_other(self, project_with_release):
        """
        Detaching a second patch after a first one succeeds and leaves the
        working tree clean.

        ho-prod's pre-commit hook refuses the sync commit of a detach (no
        lock is held). Cleaning up after that refusal used to restore .hop/
        only: Patches/orphaned/<first> stayed in the working tree, untracked,
        and the second detach failed checking out the release branch, which
        tracks it ("untracked working tree files would be overwritten").
        """
        env = project_with_release
        run = env['run']
        project_dir = env['project_dir']

        for patch_id in ('91-first', '92-second'):
            run(['git', 'checkout', 'ho-release/0.1.0'])
            run(['half_orm', 'dev', 'patch', 'create', patch_id])
            run(['git', 'checkout', f'ho-patch/{patch_id}'])
            (project_dir / 'Patches' / patch_id / '01_test.sql').write_text(
                f"CREATE TABLE t_{patch_id.replace('-', '_')} (id INT);"
            )
            run(['git', 'add', '.'])
            run(['git', 'commit', '-m', f'Patch {patch_id}', '--no-verify'])

        for patch_id in ('91-first', '92-second'):
            run(['git', 'checkout', f'ho-patch/{patch_id}'])
            result = run(['half_orm', 'dev', 'patch', 'detach', '--force'], check=False)
            assert result.returncode == 0, (
                f"detach {patch_id} failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
            )
            status = run(['git', 'status', '--porcelain', '--untracked-files=all']).stdout
            assert status == '', f"working tree not clean after detaching {patch_id}:\n{status}"

        run(['git', 'checkout', 'ho-release/0.1.0'])
        toml = (project_dir / '.hop' / 'releases' / '0.1.0-patches.toml').read_text()
        assert '91-first' not in toml and '92-second' not in toml
        for patch_id in ('91-first', '92-second'):
            assert (project_dir / 'Patches' / 'orphaned' / patch_id / '01_test.sql').exists()

    def test_detach_syncs_ho_prod_under_the_lock(self, project_with_release):
        """
        `patch detach` holds the ho-prod lock: its sync commit goes through
        ho-prod's hook, and ho-prod's TOML no longer lists the patch. The
        lock is released afterwards.
        """
        env = project_with_release
        run = env['run']
        project_dir = env['project_dir']

        run(['half_orm', 'dev', 'patch', 'create', '93-detached'])
        run(['git', 'checkout', 'ho-patch/93-detached'])
        (project_dir / 'Patches' / '93-detached' / '01_test.sql').write_text(
            "CREATE TABLE t_93 (id INT);"
        )
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Patch 93', '--no-verify'])

        run(['half_orm', 'dev', 'patch', 'detach', '--force'])

        prod_toml = run(['git', 'show', 'ho-prod:.hop/releases/0.1.0-patches.toml']).stdout
        assert '93-detached' not in prod_toml
        assert run(['git', 'show', 'ho-prod:Patches/orphaned/93-detached/01_test.sql']
                   ).stdout == "CREATE TABLE t_93 (id INT);"
        assert run(['git', 'tag', '-l', 'lock-*']).stdout == ''
        assert 'refs/tags/lock-' not in run(['git', 'ls-remote', '--tags', 'origin']).stdout
