"""
E2E test: two patches developed in parallel.

Both branches are cut from the release before either is merged, so
neither carries the other's patch directory. Once the first is merged,
rebuilding the release context means replaying it - and `patch merge`
propagates Patches/staged/{id} to every active branch precisely so the
second branch can.

Before that propagation existed, the second developer's `patch apply`
died on:

    Error: Cannot apply invalid patch 1-alpha: Patch directory does not
           exist: 1-alpha

because .hop/ said 1-alpha was staged while the directory it points at
had been propagated nowhere.
"""
import pytest


pytestmark = pytest.mark.e2e


class TestParallelPatchDevelopment:
    """A branch cut before another patch was staged can still be applied."""

    def test_apply_after_another_patch_was_staged(self, project_with_release):
        env = project_with_release
        run = env['run']
        project_dir = env['project_dir']
        version = env['release_version']
        release_branch = f'ho-release/{version}'

        # Both branches cut before either is merged.
        run(['git', 'checkout', release_branch])
        run(['half_orm', 'dev', 'patch', 'create', '1-alpha'])
        run(['git', 'checkout', release_branch])
        run(['half_orm', 'dev', 'patch', 'create', '2-beta'])

        run(['git', 'checkout', 'ho-patch/1-alpha'])
        (project_dir / 'Patches' / '1-alpha' / '01_alpha.sql').write_text(
            'CREATE TABLE alpha (id SERIAL PRIMARY KEY);'
        )
        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Add alpha'])
        run(['half_orm', 'dev', 'patch', 'merge'], input_text='y\n')

        # 2-beta received the staged patch directory through the same
        # sync that told it 1-alpha is staged.
        run(['git', 'checkout', 'ho-patch/2-beta'])
        staged_dir = project_dir / 'Patches' / 'staged' / '1-alpha'
        assert staged_dir.exists(), (
            "Patches/staged/1-alpha/ should have been propagated to "
            "ho-patch/2-beta by the merge of 1-alpha"
        )
        assert not (project_dir / 'Patches' / '1-alpha').exists(), (
            "the stale candidate copy of 1-alpha should be gone from "
            "ho-patch/2-beta"
        )

        # ...so the release context can be replayed here.
        (project_dir / 'Patches' / '2-beta' / '01_beta.sql').write_text(
            'CREATE TABLE beta (id SERIAL PRIMARY KEY, '
            'alpha_id INT REFERENCES alpha(id));'
        )
        result = run(['half_orm', 'dev', 'patch', 'apply'], check=False)
        assert result.returncode == 0, (
            f"patch apply should replay 1-alpha then apply 2-beta.\n"
            f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )

        # The FK proves alpha existed when beta was applied.
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Add beta'])
        run(['half_orm', 'dev', 'patch', 'merge'], input_text='y\n')

        toml_content = (
            project_dir / '.hop' / 'releases' / f'{version}-patches.toml'
        ).read_text()
        assert '1-alpha' in toml_content and '2-beta' in toml_content
