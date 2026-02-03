"""
End-to-end tests for patch directory organization.

Tests the Patches/ directory structure:
- Candidate patches at root: Patches/{patch_id}/
- Staged patches (after merge): Patches/staged/{patch_id}/
"""

import pytest
from pathlib import Path

from tests.e2e.conftest import run_cmd


@pytest.mark.integration
class TestPatchStagedDirectory:
    """Test patch directory organization after merge."""

    def test_patch_created_at_root(self, initialized_project):
        """Test that newly created patches are at Patches/ root."""
        env = initialized_project
        run = env['run']
        project_dir = env['project_dir']

        # Checkout ho-prod and create a release
        run(['git', 'checkout', 'ho-prod'])
        run(['half_orm', 'dev', 'release', 'create', 'minor'])  # 0.1.0

        # Create a patch
        run(['half_orm', 'dev', 'patch', 'create', '1-test-feature'])

        # Verify patch is at root (on patch branch)
        patch_dir = project_dir / 'Patches' / '1-test-feature'
        assert patch_dir.exists(), "Patch should be created at Patches/ root"
        assert (patch_dir / 'README.md').exists(), "Patch should have README.md"

        # Verify staged/ directory doesn't exist yet or is empty
        staged_dir = project_dir / 'Patches' / 'staged'
        if staged_dir.exists():
            staged_patches = list(staged_dir.iterdir())
            assert len(staged_patches) == 0, "staged/ should be empty initially"

    def test_patch_moved_to_staged_after_merge(self, initialized_project):
        """Test that patches are moved to Patches/staged/ after merge."""
        env = initialized_project
        run = env['run']
        project_dir = env['project_dir']

        # Checkout ho-prod and create a release
        run(['git', 'checkout', 'ho-prod'])
        run(['half_orm', 'dev', 'release', 'create', 'minor'])  # 0.1.0

        # Create a patch
        run(['half_orm', 'dev', 'patch', 'create', '1-staged-test'])

        # Add SQL file to patch
        patch_dir = project_dir / 'Patches' / '1-staged-test'
        sql_file = patch_dir / '01_test.sql'
        sql_file.write_text("""
            CREATE TABLE public.test_staged (
                id SERIAL PRIMARY KEY,
                name TEXT
            );
        """)

        # Apply and merge
        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Add test patch', '--no-verify'])
        run(['half_orm', 'dev', 'patch', 'merge', '--force'])

        # Go back to release branch to check directory structure
        run(['git', 'checkout', 'ho-release/0.1.0'])

        # Verify patch is now in staged/
        staged_patch_dir = project_dir / 'Patches' / 'staged' / '1-staged-test'
        root_patch_dir = project_dir / 'Patches' / '1-staged-test'

        assert staged_patch_dir.exists(), "Patch should be in Patches/staged/ after merge"
        assert not root_patch_dir.exists(), "Patch should NOT be at root after merge"
        assert (staged_patch_dir / 'README.md').exists(), "Patch README should be preserved"
        assert (staged_patch_dir / '01_test.sql').exists(), "Patch SQL file should be preserved"

    def test_multiple_patches_organization(self, initialized_project):
        """Test organization with multiple patches - some merged, some not."""
        env = initialized_project
        run = env['run']
        project_dir = env['project_dir']

        # Create release
        run(['git', 'checkout', 'ho-prod'])
        run(['half_orm', 'dev', 'release', 'create', 'minor'])  # 0.1.0

        # Create and merge first patch
        run(['half_orm', 'dev', 'patch', 'create', '1-first-patch'])
        patch1_dir = project_dir / 'Patches' / '1-first-patch'
        (patch1_dir / '01_first.sql').write_text("CREATE TABLE first (id INT);")
        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'First patch', '--no-verify'])
        run(['half_orm', 'dev', 'patch', 'merge', '--force'])

        # Create second patch (don't merge yet)
        run(['git', 'checkout', 'ho-release/0.1.0'])
        run(['half_orm', 'dev', 'patch', 'create', '2-second-patch'])

        # On patch branch, second patch is at root
        patch2_dir = project_dir / 'Patches' / '2-second-patch'
        assert patch2_dir.exists(), "Second patch should be at root on patch branch"

        # Go to release branch to check organization
        run(['git', 'checkout', 'ho-release/0.1.0'])

        # First patch should be in staged/
        staged_patch1 = project_dir / 'Patches' / 'staged' / '1-first-patch'
        assert staged_patch1.exists(), "Merged patch should be in staged/"

        # Second patch should NOT be visible on release branch yet
        # (it's only on the patch branch)


@pytest.mark.integration
class TestPatchDirectoryPathWithStatus:
    """Test get_patch_directory_path with status parameter."""

    def test_get_path_for_candidate(self, initialized_project):
        """Test getting path for candidate status."""
        env = initialized_project
        run = env['run']
        project_dir = env['project_dir']

        # Create release and patch
        run(['git', 'checkout', 'ho-prod'])
        run(['half_orm', 'dev', 'release', 'create', 'minor'])
        run(['half_orm', 'dev', 'patch', 'create', '1-test'])

        # Use Python to test the method
        result = run_cmd(
            ['python', '-c', '''
import sys
sys.path.insert(0, ".")
from half_orm_dev.repo import Repo
repo = Repo()
path = repo.patch_manager.get_patch_directory_path("1-test")
print(f"PATH:{path}")
'''],
            cwd=str(project_dir),
            env=env['env'],
            check=False
        )

        assert 'Patches/1-test' in result.stdout
        assert 'staged' not in result.stdout

    def test_get_path_with_explicit_staged_status(self, initialized_project):
        """Test getting path with explicit staged status."""
        env = initialized_project
        run = env['run']
        project_dir = env['project_dir']

        # Create release
        run(['git', 'checkout', 'ho-prod'])
        run(['half_orm', 'dev', 'release', 'create', 'minor'])

        # Use Python to test the method with status parameter
        result = run_cmd(
            ['python', '-c', '''
import sys
sys.path.insert(0, ".")
from half_orm_dev.repo import Repo
repo = Repo()
path = repo.patch_manager.get_patch_directory_path("1-test", "staged")
print(f"PATH:{path}")
'''],
            cwd=str(project_dir),
            env=env['env'],
            check=False
        )

        assert 'Patches/staged/1-test' in result.stdout


@pytest.mark.integration
class TestProductionTxtFilesWithStagedDirectory:
    """Test that patches from TXT files (production) work with staged/ directory."""

    def test_production_txt_patches_recognized_as_staged(self, initialized_project):
        """Test that patches in TXT files are recognized as staged without merge_commit."""
        env = initialized_project
        run = env['run']
        project_dir = env['project_dir']

        # Create release and patch
        run(['git', 'checkout', 'ho-prod'])
        run(['half_orm', 'dev', 'release', 'create', 'minor'])  # 0.1.0

        run(['half_orm', 'dev', 'patch', 'create', '1-prod-test'])

        # Add SQL file to patch
        patch_dir = project_dir / 'Patches' / '1-prod-test'
        sql_file = patch_dir / '01_test.sql'
        sql_file.write_text("CREATE TABLE public.prod_test (id INT);")

        # Apply and merge
        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Add prod test patch', '--no-verify'])
        run(['half_orm', 'dev', 'patch', 'merge', '--force'])

        # Promote to production (creates TXT file)
        run(['git', 'checkout', 'ho-prod'])
        run(['half_orm', 'dev', 'release', 'promote', 'prod'])

        # Verify TXT file was created (no merge_commit in TXT format)
        txt_file = project_dir / '.hop' / 'releases' / '0.1.0.txt'
        assert txt_file.exists(), "Production TXT file should exist"
        txt_content = txt_file.read_text()
        assert '1-prod-test' in txt_content, "Patch should be in TXT file"

        # Verify patch is in staged/ directory
        staged_patch = project_dir / 'Patches' / 'staged' / '1-prod-test'
        assert staged_patch.exists(), "Patch should be in Patches/staged/"

        # Verify get_patch_status_map() recognizes it as staged
        result = run_cmd(
            ['python', '-c', '''
import sys
sys.path.insert(0, ".")
from half_orm_dev.repo import Repo
repo = Repo()
status_map = repo.patch_manager.get_patch_status_map()
patch_info = status_map.get("1-prod-test", {})
print(f"STATUS:{patch_info.get('status', 'NOT_FOUND')}")
print(f"VERSION:{patch_info.get('version', 'NOT_FOUND')}")
print(f"MERGE_COMMIT:{patch_info.get('merge_commit', 'NONE')}")
'''],
            cwd=str(project_dir),
            env=env['env'],
            check=False
        )

        assert 'STATUS:staged' in result.stdout, "Patch should have staged status"
        assert 'VERSION:0.1.0' in result.stdout, "Patch should have version 0.1.0"
        # TXT files don't have merge_commit - verify it's handled gracefully
        assert 'MERGE_COMMIT:NONE' in result.stdout or 'MERGE_COMMIT:None' in result.stdout

    def test_get_patch_directory_path_for_txt_patch(self, initialized_project):
        """Test that get_patch_directory_path returns staged/ path for TXT patches."""
        env = initialized_project
        run = env['run']
        project_dir = env['project_dir']

        # Create release, patch, merge, and promote to production
        run(['git', 'checkout', 'ho-prod'])
        run(['half_orm', 'dev', 'release', 'create', 'minor'])  # 0.1.0

        run(['half_orm', 'dev', 'patch', 'create', '1-path-test'])

        patch_dir = project_dir / 'Patches' / '1-path-test'
        sql_file = patch_dir / '01_test.sql'
        sql_file.write_text("CREATE TABLE public.path_test (id INT);")

        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Add path test patch', '--no-verify'])
        run(['half_orm', 'dev', 'patch', 'merge', '--force'])

        run(['git', 'checkout', 'ho-prod'])
        run(['half_orm', 'dev', 'release', 'promote', 'prod'])

        # Test get_patch_directory_path returns staged/ path
        result = run_cmd(
            ['python', '-c', '''
import sys
sys.path.insert(0, ".")
from half_orm_dev.repo import Repo
repo = Repo()
path = repo.patch_manager.get_patch_directory_path("1-path-test")
print(f"PATH:{path}")
'''],
            cwd=str(project_dir),
            env=env['env'],
            check=False
        )

        assert 'Patches/staged/1-path-test' in result.stdout, \
            "get_patch_directory_path should return staged/ path for TXT patches"
