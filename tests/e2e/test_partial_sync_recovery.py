"""
End-to-end test for partial sync recovery between two actors.

Scenario: when sync_hop_to_active_branches partially fails (network, Ctrl+C),
the next locked operation by any actor should repair the .hop/ state on all branches.

This test:
1. Actor 1 creates two patches, merges the first
2. Sabotages the bare repo so ho-patch/2-feat-b has stale .hop/
3. Actor 2 clones, checks out the stale branch, merges patch 2
4. Verifies .hop/ is consistent across all branches after the merge
"""

import os
import shutil
import uuid

import pytest

from tests.e2e.conftest import run_cmd


pytestmark = pytest.mark.e2e


class TestPartialSyncRecovery:
    """Test that a partial .hop/ sync is auto-repaired by the next locked operation."""

    def test_stale_hop_repaired_after_second_actor_merge(self, project_with_release):
        env = project_with_release
        run = env['run']
        project_dir = env['project_dir']
        work_dir = env['work_dir']
        git_origin = env['git_origin']
        config_dir = env['config_dir']
        db_user = env['db_user']
        db_password = env['db_password']
        version = env['release_version']  # "0.1.0"

        # ── Actor 1: create and merge patch 1 ──────────────────────────

        run(['git', 'checkout', f'ho-release/{version}'])
        run(['half_orm', 'dev', 'patch', 'create', '1-feat-a'])
        run(['git', 'checkout', 'ho-patch/1-feat-a'])

        patch_dir_a = project_dir / 'Patches' / '1-feat-a'
        (patch_dir_a / '01_table_a.sql').write_text(
            'CREATE TABLE table_a (id SERIAL PRIMARY KEY, name TEXT);'
        )

        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Add table_a'])
        run(['half_orm', 'dev', 'patch', 'merge'], input_text='y\n')

        # ── Actor 1: create patch 2 (do NOT merge) ────────────────────

        run(['git', 'checkout', f'ho-release/{version}'])
        run(['half_orm', 'dev', 'patch', 'create', '2-feat-b'])
        run(['git', 'checkout', 'ho-patch/2-feat-b'])

        patch_dir_b = project_dir / 'Patches' / '2-feat-b'
        (patch_dir_b / '01_table_b.sql').write_text(
            'CREATE TABLE table_b (id SERIAL PRIMARY KEY, value TEXT);'
        )

        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Add table_b'])

        # Push patch branch so actor 2 can see it
        run(['git', 'push', '-u', 'origin', 'ho-patch/2-feat-b'])

        # ── Capture the current (good) .hop/ state for later comparison ─
        toml_file = f'.hop/releases/{version}-patches.toml'
        good_hop = run(['git', 'show', f'ho-prod:{toml_file}']).stdout

        # Verify patch 1-feat-a is staged in the good state
        assert '1-feat-a' in good_hop, "1-feat-a should be staged after merge"

        # ── Sabotage: make ho-patch/2-feat-b stale on the bare repo ────

        sabotage_dir = work_dir.parent / 'sabotage_clone'
        run_cmd(['git', 'clone', str(git_origin), str(sabotage_dir)])
        run_cmd(['git', 'config', 'user.email', 'saboteur@test.com'], cwd=sabotage_dir)
        run_cmd(['git', 'config', 'user.name', 'Saboteur'], cwd=sabotage_dir)
        run_cmd(['git', 'checkout', 'ho-patch/2-feat-b'], cwd=sabotage_dir)

        # Overwrite the toml with a version that does NOT have 1-feat-a staged
        stale_toml = sabotage_dir / toml_file
        stale_toml.parent.mkdir(parents=True, exist_ok=True)
        # Write a toml where 1-feat-a is still candidate (not staged)
        stale_toml.write_text(
            '[patches]\n'
            '"1-feat-a" = {status = "candidate"}\n'
            '"2-feat-b" = {status = "candidate"}\n'
        )

        run_cmd(['git', 'add', toml_file], cwd=sabotage_dir)
        run_cmd(['git', 'commit', '-m', 'Sabotage: stale .hop/'], cwd=sabotage_dir)
        run_cmd(['git', 'push', 'origin', 'ho-patch/2-feat-b'], cwd=sabotage_dir)

        shutil.rmtree(sabotage_dir)

        # ── Actor 2: clone and verify stale state ──────────────────────

        actor2_db = f"hop_actor2_{str(uuid.uuid4())[:8]}"
        actor2_work = work_dir.parent / 'actor2_workspace'
        actor2_work.mkdir()

        # Create half_orm config for actor 2
        actor2_config = config_dir / actor2_db
        config_content = f"""[database]
name = {actor2_db}
user = {db_user}
host = localhost
port = 5432
"""
        if db_password:
            config_content += f"password = {db_password}\n"
        actor2_config.write_text(config_content)

        cmd_env = env['env'].copy()
        cmd_env['HALFORM_CONF_DIR'] = str(config_dir)
        cmd_env['PGPASSWORD'] = db_password

        run_cmd(
            [
                'half_orm', 'dev', 'clone', str(git_origin),
                '--database-name', actor2_db,
                '--user', db_user,
                '--password', db_password or ''
            ],
            cwd=actor2_work,
            env=cmd_env
        )

        clone_dir = actor2_work / 'origin'
        assert clone_dir.exists()

        # Configure git for actor 2
        run_cmd(['git', 'config', 'user.email', 'actor2@test.com'], cwd=clone_dir)
        run_cmd(['git', 'config', 'user.name', 'Actor 2'], cwd=clone_dir)

        # Checkout the stale branch
        run_cmd(['git', 'checkout', 'ho-patch/2-feat-b'], cwd=clone_dir, env=cmd_env)

        # Verify .hop/ IS stale: 1-feat-a should NOT be staged
        stale_content = (clone_dir / toml_file).read_text()
        assert '"1-feat-a" = {status = "candidate"}' in stale_content, \
            f"Expected stale .hop/ with 1-feat-a as candidate, got:\n{stale_content}"

        # ── Actor 2: merge patch 2 (should repair .hop/) ──────────────

        cmd_env['PYTHONPATH'] = str(clone_dir)
        run_cmd(
            ['half_orm', 'dev', 'patch', 'merge'],
            cwd=clone_dir,
            env=cmd_env,
            input_text='y\n'
        )

        # ── Verify: .hop/ is now consistent ───────────────────────────

        # On ho-prod: both patches should be staged
        hop_on_prod = run_cmd(
            ['git', 'show', f'ho-prod:{toml_file}'],
            cwd=clone_dir,
            env=cmd_env
        ).stdout

        assert 'staged' in hop_on_prod, \
            f"ho-prod .hop/ should have staged patches:\n{hop_on_prod}"
        assert '1-feat-a' in hop_on_prod, \
            f"1-feat-a should be in ho-prod .hop/:\n{hop_on_prod}"
        assert '2-feat-b' in hop_on_prod, \
            f"2-feat-b should be in ho-prod .hop/:\n{hop_on_prod}"

        # On ho-release/0.1.0: same content
        hop_on_release = run_cmd(
            ['git', 'show', f'ho-release/{version}:{toml_file}'],
            cwd=clone_dir,
            env=cmd_env
        ).stdout

        assert '1-feat-a' in hop_on_release, \
            f"1-feat-a should be in release .hop/:\n{hop_on_release}"
        assert '2-feat-b' in hop_on_release, \
            f"2-feat-b should be in release .hop/:\n{hop_on_release}"

        # ── Actor 1: creates patch 3 after actor 2's merge ──────────
        # Actor 1's local ho-release and ho-prod are behind origin.
        # The sync in create_patch should reset to origin and push cleanly.

        run(['git', 'checkout', f'ho-release/{version}'])
        run(['git', 'pull', 'origin', f'ho-release/{version}'])
        run(['half_orm', 'dev', 'patch', 'create', '3-feat-c'])

        # Verify: all 3 patches visible on ho-prod
        hop_on_prod_after = run(['git', 'show', f'ho-prod:{toml_file}']).stdout
        assert '1-feat-a' in hop_on_prod_after, \
            f"1-feat-a should be in ho-prod .hop/:\n{hop_on_prod_after}"
        assert '2-feat-b' in hop_on_prod_after, \
            f"2-feat-b should be in ho-prod .hop/:\n{hop_on_prod_after}"
        assert '3-feat-c' in hop_on_prod_after, \
            f"3-feat-c should be in ho-prod .hop/:\n{hop_on_prod_after}"

        # ── Cleanup ───────────────────────────────────────────────────

        run_cmd(
            ['dropdb', '-U', db_user, '-h', 'localhost',
             '--if-exists', '--force', actor2_db],
            env=cmd_env,
            check=False
        )

    def test_actor1_creates_patch_after_actor2_merge(self, project_with_release):
        """Actor 1's sync succeeds when local branches are behind origin.

        Scenario:
        1. Actor 1 merges patch 1 (partial sync: ho-patch/2-feat-b stale on origin)
        2. Actor 2 clones, merges patch 2 (pushes to ho-release, ho-prod)
        3. Actor 1 creates patch 3 → sync must reset to origin and push cleanly
        """
        env = project_with_release
        run = env['run']
        project_dir = env['project_dir']
        work_dir = env['work_dir']
        git_origin = env['git_origin']
        config_dir = env['config_dir']
        db_user = env['db_user']
        db_password = env['db_password']
        version = env['release_version']  # "0.1.0"
        toml_file = f'.hop/releases/{version}-patches.toml'

        # ── Actor 1: create patches 1 and 2 ───────────────────────────

        run(['git', 'checkout', f'ho-release/{version}'])
        run(['half_orm', 'dev', 'patch', 'create', '1-feat-a'])
        run(['git', 'checkout', 'ho-patch/1-feat-a'])
        patch_dir = project_dir / 'Patches' / '1-feat-a'
        (patch_dir / '01_schema_a.sql').write_text(
            'CREATE SCHEMA schema_a;\n'
            'CREATE TABLE schema_a.table_a (id SERIAL PRIMARY KEY, name TEXT);'
        )
        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Add schema_a.table_a'])

        run(['git', 'checkout', f'ho-release/{version}'])
        run(['half_orm', 'dev', 'patch', 'create', '2-feat-b'])
        run(['git', 'checkout', 'ho-patch/2-feat-b'])
        patch_dir = project_dir / 'Patches' / '2-feat-b'
        (patch_dir / '01_schema_b.sql').write_text(
            'CREATE SCHEMA schema_b;\n'
            'CREATE TABLE schema_b.table_b (id SERIAL PRIMARY KEY, value TEXT);'
        )
        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Add schema_b.table_b'])
        run(['git', 'push', '-u', 'origin', 'ho-patch/2-feat-b'])

        # ── Actor 1: merge patch 1 ────────────────────────────────────

        run(['git', 'checkout', 'ho-patch/1-feat-a'])
        run(['half_orm', 'dev', 'patch', 'merge'], input_text='y\n')

        # ── Actor 2: clone and merge patch 2 ──────────────────────────
        # This pushes new commits to ho-release, ho-prod
        # that actor 1 doesn't have locally.

        actor2_db = f"hop_actor2_{str(uuid.uuid4())[:8]}"
        actor2_work = work_dir.parent / 'actor2_workspace'
        actor2_work.mkdir()

        actor2_config = config_dir / actor2_db
        config_content = f"""[database]
name = {actor2_db}
user = {db_user}
host = localhost
port = 5432
"""
        if db_password:
            config_content += f"password = {db_password}\n"
        actor2_config.write_text(config_content)

        cmd_env = env['env'].copy()
        cmd_env['HALFORM_CONF_DIR'] = str(config_dir)
        cmd_env['PGPASSWORD'] = db_password

        run_cmd(
            [
                'half_orm', 'dev', 'clone', str(git_origin),
                '--database-name', actor2_db,
                '--user', db_user,
                '--password', db_password or ''
            ],
            cwd=actor2_work,
            env=cmd_env
        )

        clone_dir = actor2_work / 'origin'
        run_cmd(['git', 'config', 'user.email', 'actor2@test.com'], cwd=clone_dir)
        run_cmd(['git', 'config', 'user.name', 'Actor 2'], cwd=clone_dir)

        cmd_env['PYTHONPATH'] = str(clone_dir)
        run_cmd(['git', 'checkout', 'ho-patch/2-feat-b'], cwd=clone_dir, env=cmd_env)
        run_cmd(
            ['half_orm', 'dev', 'patch', 'merge'],
            cwd=clone_dir, env=cmd_env, input_text='y\n'
        )

        # ── Actor 1: creates patch 3 ─────────────────────────────────
        # Actor 1's local ho-release and ho-prod are behind origin
        # (actor 2 pushed). The sync in create_patch should reset
        # local branches to origin and push without conflict.

        run(['git', 'checkout', f'ho-release/{version}'])
        run(['git', 'pull', 'origin', f'ho-release/{version}'])
        run(['half_orm', 'dev', 'patch', 'create', '3-feat-c'])

        # ── Verify: .hop/ consistent on all branches ──────────────────

        hop_on_prod = run(['git', 'show', f'ho-prod:{toml_file}']).stdout
        assert '1-feat-a' in hop_on_prod, \
            f"1-feat-a should be in ho-prod .hop/:\n{hop_on_prod}"
        assert '2-feat-b' in hop_on_prod, \
            f"2-feat-b should be in ho-prod .hop/:\n{hop_on_prod}"
        assert '3-feat-c' in hop_on_prod, \
            f"3-feat-c should be in ho-prod .hop/:\n{hop_on_prod}"

        # ── Cleanup ───────────────────────────────────────────────────

        run_cmd(
            ['dropdb', '-U', db_user, '-h', 'localhost',
             '--if-exists', '--force', actor2_db],
            env=cmd_env,
            check=False
        )
