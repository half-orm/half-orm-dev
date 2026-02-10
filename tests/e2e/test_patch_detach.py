"""
End-to-end tests for patch detach functionality.

Tests the workflow of detaching a candidate patch from its release:
- Patch is removed from TOML file
- Directory is moved to Patches/orphaned/
- Git branch is preserved for future reattachment
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

        # Verify branch still exists
        result = run(['git', 'branch', '-a'])
        assert 'ho-patch/3-branch-test' in result.stdout, "Git branch should be preserved"

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

        assert '5-orphan-check' in result.stdout, "Check should show orphaned patch"
        assert 'orphan' in result.stdout.lower(), "Check should mention 'orphan'"

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