"""
End-to-end tests for the complete half-orm-dev workflow.

These tests execute real CLI commands with a real PostgreSQL database,
validating the entire development lifecycle from project initialization
through release promotion.

Inspired by tmp/test_native_pg script.
"""

import pytest
from pathlib import Path


pytestmark = pytest.mark.e2e


class TestProjectInitialization:
    """Test project initialization workflow."""

    def test_init_creates_project_structure(self, initialized_project):
        """Test that init creates proper project structure."""
        project_dir = initialized_project['project_dir']

        # Check directory structure
        assert project_dir.exists()
        assert (project_dir / '.hop').is_dir()
        assert (project_dir / '.hop' / 'config').is_file()
        assert (project_dir / '.hop' / 'model').is_dir()
        assert (project_dir / '.hop' / 'releases').is_dir()
        assert (project_dir / 'Patches').is_dir()
        assert (project_dir / '.git').is_dir()

    def test_init_creates_git_branches(self, initialized_project):
        """Test that init creates ho-prod branch."""
        run = initialized_project['run']

        result = run(['git', 'branch', '-a'])
        assert 'ho-prod' in result.stdout


class TestReleaseWorkflow:
    """Test release creation and management."""

    def test_create_release_creates_branch_and_file(self, project_with_release):
        """Test that release create creates branch and TOML file."""
        project_dir = project_with_release['project_dir']
        run = project_with_release['run']

        # Check branch exists
        result = run(['git', 'branch', '-a'])
        assert 'ho-release/0.1.0' in result.stdout

        # Check TOML file exists
        toml_file = project_dir / '.hop' / 'releases' / '0.1.0-patches.toml'
        assert toml_file.exists()


class TestPatchWorkflow:
    """Test patch creation, application, and merge workflow."""

    def test_create_patch_creates_branch_and_directory(self, project_with_release):
        """Test that patch create creates branch and Patches directory."""
        project_dir = project_with_release['project_dir']
        run = project_with_release['run']

        # Create patch
        run(['half_orm', 'dev', 'patch', 'create', '1-first'])

        # Check branch exists
        result = run(['git', 'branch', '-a'])
        assert 'ho-patch/1-first' in result.stdout

        # Check patch directory exists
        patch_dir = project_dir / 'Patches' / '1-first'
        assert patch_dir.is_dir()
        assert (patch_dir / 'README.md').is_file()

    def test_patch_apply_executes_sql(self, project_with_release):
        """Test that patch apply executes SQL files."""
        project_dir = project_with_release['project_dir']
        run = project_with_release['run']
        db_name = project_with_release['db_name']
        db_user = project_with_release['db_user']
        env = project_with_release['env']

        # Create and checkout patch
        run(['half_orm', 'dev', 'patch', 'create', '1-tables'])
        run(['git', 'checkout', 'ho-patch/1-tables'])

        # Create SQL file
        patch_dir = project_dir / 'Patches' / '1-tables'
        sql_file = patch_dir / '01_create_table.sql'
        sql_file.write_text('CREATE TABLE test_table (id SERIAL PRIMARY KEY, name TEXT);')

        # Apply patch
        run(['half_orm', 'dev', 'patch', 'apply'])

        # Verify table exists in database
        from tests.e2e.conftest import run_cmd
        result = run_cmd(
            ['psql', '-U', db_user, '-d', db_name, '-tAc',
             "SELECT EXISTS (SELECT FROM pg_tables WHERE tablename = 'test_table')"],
            env=env
        )
        assert 't' in result.stdout

    def test_patch_merge_moves_to_staged(self, project_with_release):
        """Test that patch merge moves patch to staged status."""
        project_dir = project_with_release['project_dir']
        run = project_with_release['run']

        # Create and checkout patch
        run(['half_orm', 'dev', 'patch', 'create', '1-feature'])
        run(['git', 'checkout', 'ho-patch/1-feature'])

        # Create SQL file
        patch_dir = project_dir / 'Patches' / '1-feature'
        sql_file = patch_dir / '01_feature.sql'
        sql_file.write_text('CREATE TABLE feature (id SERIAL PRIMARY KEY);')

        # Apply patch
        run(['half_orm', 'dev', 'patch', 'apply'])

        # Commit changes
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Add feature table'])

        # Merge patch (answer 'y' to confirmation)
        run(['half_orm', 'dev', 'patch', 'merge'], input_text='y\n')

        # Verify patch is staged in TOML
        toml_file = project_dir / '.hop' / 'releases' / '0.1.0-patches.toml'
        content = toml_file.read_text()
        assert '1-feature' in content
        assert 'staged' in content

    def test_patch_apply_idempotent(self, project_with_release):
        """Test that patch apply can be run multiple times (idempotent)."""
        project_dir = project_with_release['project_dir']
        run = project_with_release['run']

        # Create and checkout patch
        run(['half_orm', 'dev', 'patch', 'create', '1-idem'])
        run(['git', 'checkout', 'ho-patch/1-idem'])

        # Create SQL file
        patch_dir = project_dir / 'Patches' / '1-idem'
        sql_file = patch_dir / '01_table.sql'
        sql_file.write_text('CREATE TABLE idem_table (id SERIAL PRIMARY KEY);')

        # Apply patch twice - should not fail
        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['half_orm', 'dev', 'patch', 'apply'])


class TestMultiplePatchesWorkflow:
    """Test workflow with multiple patches and dependencies."""

    def test_second_patch_sees_first_patch_tables(self, project_with_release):
        """Test that a second patch can reference tables from first patch."""
        project_dir = project_with_release['project_dir']
        run = project_with_release['run']

        # Create and merge first patch
        run(['half_orm', 'dev', 'patch', 'create', '1-base'])
        run(['git', 'checkout', 'ho-patch/1-base'])

        patch1_dir = project_dir / 'Patches' / '1-base'
        (patch1_dir / '01_base.sql').write_text(
            'CREATE TABLE base_table (id SERIAL PRIMARY KEY);'
        )

        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Add base table'])
        run(['half_orm', 'dev', 'patch', 'merge'], input_text='y\n')

        # Create second patch that references first
        run(['git', 'checkout', 'ho-release/0.1.0'])
        run(['half_orm', 'dev', 'patch', 'create', '2-dependent'])
        run(['git', 'checkout', 'ho-patch/2-dependent'])

        patch2_dir = project_dir / 'Patches' / '2-dependent'
        (patch2_dir / '01_dependent.sql').write_text(
            'CREATE TABLE dependent_table (id SERIAL PRIMARY KEY, base_id INT REFERENCES base_table(id));'
        )

        # This should succeed because release schema includes base_table
        run(['half_orm', 'dev', 'patch', 'apply'])

        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Add dependent table'])
        run(['half_orm', 'dev', 'patch', 'merge'], input_text='y\n')

        # Verify both patches are staged
        toml_file = project_dir / '.hop' / 'releases' / '0.1.0-patches.toml'
        content = toml_file.read_text()
        assert '1-base' in content
        assert '2-dependent' in content

    def test_patch_apply_after_merge_still_works(self, project_with_release):
        """Test that patch apply works correctly after another patch is merged."""
        project_dir = project_with_release['project_dir']
        run = project_with_release['run']

        # Create and merge first patch
        run(['half_orm', 'dev', 'patch', 'create', '1-alpha'])
        run(['git', 'checkout', 'ho-patch/1-alpha'])

        patch1_dir = project_dir / 'Patches' / '1-alpha'
        (patch1_dir / '01_alpha.sql').write_text(
            'CREATE TABLE alpha (id SERIAL PRIMARY KEY, val TEXT);'
        )

        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Add alpha'])
        run(['half_orm', 'dev', 'patch', 'merge'], input_text='y\n')

        # Create second patch
        run(['git', 'checkout', 'ho-release/0.1.0'])
        run(['half_orm', 'dev', 'patch', 'create', '2-beta'])
        run(['git', 'checkout', 'ho-patch/2-beta'])

        patch2_dir = project_dir / 'Patches' / '2-beta'
        (patch2_dir / '01_beta.sql').write_text(
            'CREATE TABLE beta (id SERIAL PRIMARY KEY, alpha_id INT REFERENCES alpha(id));'
        )

        # Apply should work
        run(['half_orm', 'dev', 'patch', 'apply'])

        # Apply again should still work (idempotent)
        run(['half_orm', 'dev', 'patch', 'apply'])


class TestReleasePromotion:
    """Test release promotion workflow (RC and production)."""

    def test_promote_to_rc_creates_tag(self, project_with_release):
        """Test that promote rc creates RC tag."""
        project_dir = project_with_release['project_dir']
        run = project_with_release['run']

        # Create and merge a patch first
        run(['half_orm', 'dev', 'patch', 'create', '1-for-rc'])
        run(['git', 'checkout', 'ho-patch/1-for-rc'])

        patch_dir = project_dir / 'Patches' / '1-for-rc'
        (patch_dir / '01_table.sql').write_text('CREATE TABLE rc_table (id INT);')

        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'For RC'])
        run(['half_orm', 'dev', 'patch', 'merge'], input_text='y\n')

        # Promote to RC
        run(['git', 'checkout', 'ho-release/0.1.0'])
        run(['half_orm', 'dev', 'release', 'promote', 'rc'])

        # Check tag exists
        result = run(['git', 'tag', '-l'])
        assert 'v0.1.0-rc1' in result.stdout

        # Check RC file exists
        rc_file = project_dir / '.hop' / 'releases' / '0.1.0-rc1.txt'
        assert rc_file.exists()

    def test_promote_to_prod_creates_tag_and_merges(self, project_with_release):
        """Test that promote prod creates tag and merges to ho-prod."""
        project_dir = project_with_release['project_dir']
        run = project_with_release['run']

        # Create and merge a patch
        run(['half_orm', 'dev', 'patch', 'create', '1-for-prod'])
        run(['git', 'checkout', 'ho-patch/1-for-prod'])

        patch_dir = project_dir / 'Patches' / '1-for-prod'
        (patch_dir / '01_table.sql').write_text('CREATE TABLE prod_table (id INT);')

        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'For prod'])
        run(['half_orm', 'dev', 'patch', 'merge'], input_text='y\n')

        # Promote to RC first
        run(['git', 'checkout', 'ho-release/0.1.0'])
        run(['half_orm', 'dev', 'release', 'promote', 'rc'])

        # Promote to production
        run(['half_orm', 'dev', 'release', 'promote', 'prod'])

        # Check production tag exists
        result = run(['git', 'tag', '-l'])
        assert 'v0.1.0' in result.stdout

        # Check production file exists and TOML is deleted
        prod_file = project_dir / '.hop' / 'releases' / '0.1.0.txt'
        toml_file = project_dir / '.hop' / 'releases' / '0.1.0-patches.toml'
        assert prod_file.exists()
        assert not toml_file.exists()

        # Verify on ho-prod branch
        result = run(['git', 'branch', '--show-current'])
        assert 'ho-prod' in result.stdout


class TestHotfixWorkflow:
    """Test hotfix workflow after production release."""

    def test_hotfix_after_production(self, project_with_release):
        """Test complete hotfix workflow after production promotion."""
        project_dir = project_with_release['project_dir']
        run = project_with_release['run']

        # Create, merge, promote to prod
        run(['half_orm', 'dev', 'patch', 'create', '1-initial'])
        run(['git', 'checkout', 'ho-patch/1-initial'])

        patch_dir = project_dir / 'Patches' / '1-initial'
        (patch_dir / '01_init.sql').write_text('CREATE TABLE initial (id INT);')

        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Initial'])
        run(['half_orm', 'dev', 'patch', 'merge'], input_text='y\n')

        run(['git', 'checkout', 'ho-release/0.1.0'])
        run(['half_orm', 'dev', 'release', 'promote', 'rc'])
        run(['half_orm', 'dev', 'release', 'promote', 'prod'])

        # Now create hotfix
        run(['git', 'checkout', 'ho-prod'])
        run(['half_orm', 'dev', 'release', 'hotfix'])

        # Create hotfix patch
        run(['half_orm', 'dev', 'patch', 'create', '2-hotfix'])
        run(['git', 'checkout', 'ho-patch/2-hotfix'])

        hotfix_dir = project_dir / 'Patches' / '2-hotfix'
        (hotfix_dir / '01_fix.sql').write_text('ALTER TABLE initial ADD COLUMN fixed BOOLEAN;')

        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Hotfix'])

        # Merge with --force for hotfix
        run(['half_orm', 'dev', 'patch', 'merge', '--force'], input_text='y\n')

        # Promote hotfix
        run(['git', 'checkout', 'ho-release/0.1.0'])
        run(['half_orm', 'dev', 'release', 'promote', 'hotfix'])

        # Verify hotfix file exists
        hotfix_file = project_dir / '.hop' / 'releases' / '0.1.0-hotfix1.txt'
        assert hotfix_file.exists()
