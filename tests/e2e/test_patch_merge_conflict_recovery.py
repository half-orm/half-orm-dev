"""
E2E regression test: a conflicting `patch merge` must leave the
repository usable.

Reported symptom: merging a patch whose branch conflicted with the
release branch left the developer stranded on the temporary validation
branch, mid-merge:

    ho-validate/263-...|MERGING
    ⚠️  Warning: Failed to cleanup temp branch ho-validate/263-...:
        stdout: '.hop/model/release-0.3.10.sql: needs merge'
        stderr: 'error: you need to resolve your current index first'

The failed merge left a conflicted index, so the cleanup could neither
check the original branch back out nor delete the temporary branch. The
merge is now aborted before cleanup, so a conflict costs the developer
an error message and nothing else.
"""
import pytest


pytestmark = pytest.mark.e2e


def _branches(run):
    """Local branch names."""
    result = run(['git', 'branch', '--format=%(refname:short)'])
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


class TestPatchMergeConflictRecovery:
    """A conflicting merge must not strand the developer mid-merge."""

    def test_conflicting_merge_leaves_repo_clean_on_patch_branch(
        self, project_with_release
    ):
        env = project_with_release
        run = env['run']
        project_dir = env['project_dir']
        version = env['release_version']
        release_branch = f'ho-release/{version}'

        # Both patches are cut from the release branch before either is
        # merged, so neither has the other's commit.
        run(['git', 'checkout', release_branch])
        run(['half_orm', 'dev', 'patch', 'create', '1-alpha'])
        run(['git', 'checkout', release_branch])
        run(['half_orm', 'dev', 'patch', 'create', '2-beta'])

        # Each writes the same file with different content: an add/add
        # conflict on a file that is neither generated nor derived.
        run(['git', 'checkout', 'ho-patch/1-alpha'])
        (project_dir / 'Patches' / '1-alpha' / '01_alpha.sql').write_text(
            'CREATE TABLE alpha (id SERIAL PRIMARY KEY);'
        )
        (project_dir / 'shared_notes.txt').write_text('written by alpha\n')
        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Add alpha'])
        run(['half_orm', 'dev', 'patch', 'merge'], input_text='y\n')

        run(['git', 'checkout', 'ho-patch/2-beta'])
        (project_dir / 'Patches' / '2-beta' / '01_beta.sql').write_text(
            'CREATE TABLE beta (id SERIAL PRIMARY KEY);'
        )
        (project_dir / 'shared_notes.txt').write_text('written by beta\n')
        # No `patch apply` here on purpose: this branch was cut before
        # 1-alpha was staged, so it does not carry Patches/staged/1-alpha
        # and cannot replay the release context. The merge below validates
        # in a branch cut from the release, where it can.
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Add beta'])

        release_sha_before = run(
            ['git', 'rev-parse', release_branch]
        ).stdout.strip()

        result = run(['half_orm', 'dev', 'patch', 'merge'],
                     input_text='y\n', check=False)

        assert result.returncode != 0, (
            f"the conflicting merge should fail.\n"
            f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )

        # The developer is back on their patch branch...
        current = run(['git', 'rev-parse', '--abbrev-ref', 'HEAD']).stdout.strip()
        assert current == 'ho-patch/2-beta', (
            f"should be back on ho-patch/2-beta, not {current}"
        )

        # ...with no merge in progress...
        assert not (project_dir / '.git' / 'MERGE_HEAD').exists(), (
            "a merge was left in progress; the next git command will fail "
            "with 'you need to resolve your current index first'"
        )
        unmerged = run(['git', 'diff', '--name-only', '--diff-filter=U']).stdout
        assert not unmerged.strip(), f"unmerged paths left behind: {unmerged}"

        # ...no leftover validation branch...
        leftovers = [b for b in _branches(run) if b.startswith('ho-validate/')]
        assert not leftovers, f"validation branch(es) left behind: {leftovers}"

        # ...and the release branch untouched.
        release_sha_after = run(
            ['git', 'rev-parse', release_branch]
        ).stdout.strip()
        assert release_sha_after == release_sha_before, (
            f"{release_branch} moved despite the failed merge"
        )
