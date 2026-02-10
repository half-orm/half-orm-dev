"""
End-to-end tests for release attach-patch functionality.

Tests the workflow of reattaching an orphaned patch to a release:
- Patch is added back to TOML file as candidate
- Directory is moved from Patches/orphaned/ to Patches/
- CLI command with confirmation
- Error cases (candidate, nonexistent, wrong branch)
"""

import pytest
from pathlib import Path

from tests.e2e.conftest import run_cmd


def _create_and_detach_patch(run, project_dir, patch_id):
    """Helper: create a patch, apply it, then detach it from patch branch."""
    run(['half_orm', 'dev', 'patch', 'create', patch_id])

    patch_dir = project_dir / 'Patches' / patch_id
    (patch_dir / '01_test.sql').write_text(
        f"CREATE TABLE public.test_{patch_id.replace('-', '_')} (id INT);"
    )

    run(['half_orm', 'dev', 'patch', 'apply'])
    run(['git', 'add', '.'])
    run(['git', 'commit', '-m', f'Add patch {patch_id}', '--no-verify'])

    # Detach from patch branch (where directory exists)
    run(['half_orm', 'dev', 'patch', 'detach', '--force'])

    # Go back to release branch
    run(['git', 'checkout', 'ho-release/0.1.0'])


@pytest.mark.integration
class TestReleaseAttachPatch:
    """Test release attach-patch workflow."""

    def test_attach_orphaned_patch_success(self, project_with_release):
        """Test successfully attaching an orphaned patch."""
        env = project_with_release
        run = env['run']
        project_dir = env['project_dir']

        # Create and detach a patch
        _create_and_detach_patch(run, project_dir, '1-attach-test')

        # Verify patch is orphaned
        orphaned_dir = project_dir / 'Patches' / 'orphaned' / '1-attach-test'
        assert orphaned_dir.exists(), "Patch should be in orphaned/ before attach"

        # Attach the patch
        result = run(['half_orm', 'dev', 'release', 'attach-patch', '1-attach-test', '--force'])

        assert result.returncode == 0

        # Verify patch is back at root
        patch_dir = project_dir / 'Patches' / '1-attach-test'
        assert patch_dir.exists(), "Patch should be at Patches/ root after attach"
        assert (patch_dir / '01_test.sql').exists(), "SQL file should be preserved"

        # Verify orphaned directory is cleaned up
        assert not orphaned_dir.exists(), "Patch should NOT be in orphaned/ after attach"

    def test_attach_adds_to_toml(self, project_with_release):
        """Test that attach adds patch back to TOML file."""
        env = project_with_release
        run = env['run']
        project_dir = env['project_dir']

        _create_and_detach_patch(run, project_dir, '2-toml-attach')

        # Verify patch is NOT in TOML
        toml_file = project_dir / '.hop' / 'releases' / '0.1.0-patches.toml'
        toml_content = toml_file.read_text()
        assert '2-toml-attach' not in toml_content, "Patch should not be in TOML before attach"

        # Attach
        run(['half_orm', 'dev', 'release', 'attach-patch', '2-toml-attach', '--force'])

        # Verify patch is in TOML
        toml_content = toml_file.read_text()
        assert '2-toml-attach' in toml_content, "Patch should be in TOML after attach"
        assert 'candidate' in toml_content, "Patch should be candidate"

    def test_attach_candidate_fails(self, project_with_release):
        """Test that attaching a candidate patch fails."""
        env = project_with_release
        run = env['run']
        project_dir = env['project_dir']

        # Create a patch (stays as candidate, don't detach)
        run(['half_orm', 'dev', 'patch', 'create', '3-candidate'])

        patch_dir = project_dir / 'Patches' / '3-candidate'
        (patch_dir / '01_test.sql').write_text("CREATE TABLE candidate (id INT);")
        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Candidate patch', '--no-verify'])

        # Go to release branch
        run(['git', 'checkout', 'ho-release/0.1.0'])

        # Try to attach candidate patch - should fail
        result = run(
            ['half_orm', 'dev', 'release', 'attach-patch', '3-candidate', '--force'],
            check=False
        )

        assert result.returncode != 0, "Attaching candidate patch should fail"
        assert 'candidate' in result.stderr.lower() or 'candidate' in result.stdout.lower(), \
            "Error should mention candidate"

    def test_attach_nonexistent_fails(self, project_with_release):
        """Test that attaching unknown patch fails."""
        env = project_with_release
        run = env['run']

        # Go to release branch
        run(['git', 'checkout', 'ho-release/0.1.0'])

        result = run(
            ['half_orm', 'dev', 'release', 'attach-patch', '999-unknown', '--force'],
            check=False
        )

        assert result.returncode != 0, "Attaching unknown patch should fail"
        assert 'not found' in result.stderr.lower() or 'not found' in result.stdout.lower(), \
            "Error should say not found"

    def test_attach_wrong_branch_fails(self, project_with_release):
        """Test that attach fails when not on release branch."""
        env = project_with_release
        run = env['run']

        # Stay on ho-prod
        run(['git', 'checkout', 'ho-prod'])

        result = run(
            ['half_orm', 'dev', 'release', 'attach-patch', '1-test', '--force'],
            check=False
        )

        assert result.returncode != 0, "Should fail when not on release branch"
        assert 'ho-release' in result.stderr.lower() or 'ho-release' in result.stdout.lower(), \
            "Error should mention ho-release"

    def test_attach_updates_status_map(self, project_with_release):
        """Test that status map is updated after attach."""
        env = project_with_release
        run = env['run']
        project_dir = env['project_dir']

        _create_and_detach_patch(run, project_dir, '4-status-attach')

        # Verify orphaned before attach
        result = run_cmd(
            ['python', '-c', '''
import sys
sys.path.insert(0, ".")
from half_orm_dev.repo import Repo
repo = Repo()
status_map = repo.patch_manager.get_patch_status_map()
patch_info = status_map.get("4-status-attach", {})
print(f"STATUS:{patch_info.get('status', 'NOT_FOUND')}")
'''],
            cwd=str(project_dir),
            env=env['env'],
            check=False
        )
        assert 'STATUS:orphaned' in result.stdout, "Patch should be orphaned before attach"

        # Attach
        run(['half_orm', 'dev', 'release', 'attach-patch', '4-status-attach', '--force'])

        # Verify candidate after attach
        result = run_cmd(
            ['python', '-c', '''
import sys
sys.path.insert(0, ".")
from half_orm_dev.repo import Repo
repo = Repo()
status_map = repo.patch_manager.get_patch_status_map()
patch_info = status_map.get("4-status-attach", {})
print(f"STATUS:{patch_info.get('status', 'NOT_FOUND')}")
'''],
            cwd=str(project_dir),
            env=env['env'],
            check=False
        )
        assert 'STATUS:candidate' in result.stdout, "Patch should be candidate after attach"


@pytest.mark.integration
class TestAttachPatchEdgeCases:
    """Test edge cases for release attach-patch."""

    def test_attach_preserves_other_patches(self, project_with_release):
        """Test that attaching one patch doesn't affect others."""
        env = project_with_release
        run = env['run']
        project_dir = env['project_dir']

        # Create and detach first patch
        _create_and_detach_patch(run, project_dir, '51-first')

        # Create second patch (stays as candidate)
        run(['half_orm', 'dev', 'patch', 'create', '52-second'])
        patch_dir2 = project_dir / 'Patches' / '52-second'
        (patch_dir2 / '01_test.sql').write_text("CREATE TABLE second (id INT);")
        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Second patch', '--no-verify'])

        # Go to release branch
        run(['git', 'checkout', 'ho-release/0.1.0'])

        # Attach first patch
        run(['half_orm', 'dev', 'release', 'attach-patch', '51-first', '--force'])

        # Verify both patches are in TOML
        toml_file = project_dir / '.hop' / 'releases' / '0.1.0-patches.toml'
        toml_content = toml_file.read_text()
        assert '51-first' in toml_content, "Attached patch should be in TOML"
        assert '52-second' in toml_content, "Other patch should be preserved"

    def test_detach_then_attach_roundtrip(self, project_with_release):
        """Test full detach → attach roundtrip."""
        env = project_with_release
        run = env['run']
        project_dir = env['project_dir']

        # Create a patch
        run(['half_orm', 'dev', 'patch', 'create', '6-roundtrip'])
        patch_dir = project_dir / 'Patches' / '6-roundtrip'
        (patch_dir / '01_test.sql').write_text("CREATE TABLE roundtrip (id INT);")
        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Roundtrip patch', '--no-verify'])

        # Detach from patch branch
        run(['half_orm', 'dev', 'patch', 'detach', '--force'])
        run(['git', 'checkout', 'ho-release/0.1.0'])

        # Verify orphaned
        toml_file = project_dir / '.hop' / 'releases' / '0.1.0-patches.toml'
        assert '6-roundtrip' not in toml_file.read_text()
        assert (project_dir / 'Patches' / 'orphaned' / '6-roundtrip').exists()

        # Attach back
        run(['half_orm', 'dev', 'release', 'attach-patch', '6-roundtrip', '--force'])

        # Verify candidate again
        assert '6-roundtrip' in toml_file.read_text()
        assert (project_dir / 'Patches' / '6-roundtrip').exists()
        assert not (project_dir / 'Patches' / 'orphaned' / '6-roundtrip').exists()