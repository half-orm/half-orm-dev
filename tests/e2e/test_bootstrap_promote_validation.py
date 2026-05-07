"""
End-to-end tests for bootstrap validation during promote_to_prod.

Verifies that promote_to_prod (Passe 2) restores a fresh DB from the final
schema and runs all bootstrap scripts.  A stale bootstrap script that
references a renamed column must block the promotion until it is fixed.
"""

import pytest
from pathlib import Path


@pytest.mark.integration
class TestBootstrapPromoteValidation:
    """Bootstrap scripts are validated against the final schema during promote."""

    def test_stale_bootstrap_blocks_promote(self, project_with_release):
        """
        Promote fails when a bootstrap references a column renamed in a later patch.

        Scenario
        --------
        1. Release 0.1.0: table ``items(id, old_name)`` + bootstrap INSERT
        2. Promote 0.1.0 → succeeds.
        3. Release 0.2.0: patch renames ``old_name`` → ``new_name``.
        4. Promote 0.2.0 → FAILS (bootstrap still uses ``old_name``).
        5. Fix bootstrap: replace ``old_name`` with ``new_name``.
        6. Promote 0.2.0 again → succeeds.
        """
        env = project_with_release  # 0.1.0 release ready, on ho-release/0.1.0
        run = env['run']
        project_dir = env['project_dir']

        # ── Release 0.1.0 ───────────────────────────────────────────────
        run(['half_orm', 'dev', 'patch', 'create', '1-create-items'])
        run(['git', 'checkout', 'ho-patch/1-create-items'])

        patch_dir = project_dir / 'Patches' / '1-create-items'
        (patch_dir / '01_schema.sql').write_text(
            "CREATE TABLE public.items (\n"
            "    id        SERIAL PRIMARY KEY,\n"
            "    old_name  TEXT NOT NULL\n"
            ");\n"
        )
        (patch_dir / '02_bootstrap.sql').write_text(
            "-- @HOP:bootstrap\n"
            "INSERT INTO public.items (old_name) VALUES ('hello')\n"
            "ON CONFLICT DO NOTHING;\n"
        )

        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Add items table', '--no-verify'])
        run(['half_orm', 'dev', 'patch', 'merge', '--force'])

        run(['git', 'checkout', 'ho-prod'])
        run(['half_orm', 'dev', 'release', 'promote', 'prod'])
        run(['git', 'push', 'origin', '--all'])
        run(['git', 'push', 'origin', '--tags'])

        # ── Release 0.2.0 ───────────────────────────────────────────────
        run(['half_orm', 'dev', 'release', 'create', 'minor'])

        run(['half_orm', 'dev', 'patch', 'create', '2-rename-column'])
        run(['git', 'checkout', 'ho-patch/2-rename-column'])

        patch_dir2 = project_dir / 'Patches' / '2-rename-column'
        (patch_dir2 / '01_rename.sql').write_text(
            "ALTER TABLE public.items RENAME COLUMN old_name TO new_name;\n"
        )

        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Rename items.old_name to new_name', '--no-verify'])
        run(['half_orm', 'dev', 'patch', 'merge', '--force'])

        # Promote 0.2.0 → must fail because bootstrap uses old_name
        run(['git', 'checkout', 'ho-prod'])
        result = run(['half_orm', 'dev', 'release', 'promote', 'prod'], check=False)
        assert result.returncode != 0, (
            "Promote must fail: bootstrap references column old_name "
            "which was renamed to new_name.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # ── Fix the stale bootstrap ──────────────────────────────────────
        run(['git', 'checkout', 'ho-release/0.2.0'])

        bootstrap_dir = project_dir / 'bootstrap'
        stale_files = list(bootstrap_dir.glob('*1-create-items*.sql'))
        assert len(stale_files) == 1, (
            f"Expected one bootstrap file for patch 1-create-items, "
            f"found: {[f.name for f in stale_files]}"
        )

        fixed = stale_files[0].read_text().replace('old_name', 'new_name')
        stale_files[0].write_text(fixed)

        run(['git', 'add', 'bootstrap/'])
        run(['git', 'commit', '-m', 'Fix stale bootstrap: old_name → new_name', '--no-verify'])
        run(['git', 'push', 'origin', 'ho-release/0.2.0'])

        # Promote again → must succeed now
        run(['git', 'checkout', 'ho-prod'])
        run(['half_orm', 'dev', 'release', 'promote', 'prod'])

    def test_valid_bootstrap_does_not_block_promote(self, project_with_release):
        """
        Promote succeeds when all bootstrap scripts are compatible with the schema.

        Happy-path: single release with a correct bootstrap.
        """
        env = project_with_release
        run = env['run']
        project_dir = env['project_dir']

        run(['half_orm', 'dev', 'patch', 'create', '1-setup'])
        run(['git', 'checkout', 'ho-patch/1-setup'])

        patch_dir = project_dir / 'Patches' / '1-setup'
        (patch_dir / '01_schema.sql').write_text(
            "CREATE TABLE public.config (\n"
            "    key   TEXT PRIMARY KEY,\n"
            "    value TEXT NOT NULL\n"
            ");\n"
        )
        (patch_dir / '02_bootstrap.sql').write_text(
            "-- @HOP:bootstrap\n"
            "INSERT INTO public.config (key, value) VALUES ('env', 'prod')\n"
            "ON CONFLICT DO NOTHING;\n"
        )

        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Add config table', '--no-verify'])
        run(['half_orm', 'dev', 'patch', 'merge', '--force'])

        run(['git', 'checkout', 'ho-prod'])
        run(['half_orm', 'dev', 'release', 'promote', 'prod'])
