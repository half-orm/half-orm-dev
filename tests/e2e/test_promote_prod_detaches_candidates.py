"""
End-to-end test: `release promote prod` detaches the candidate patches.

A release goes to production with its staged patches only. When it still
has candidates, the promotion offers to detach them, as `patch detach` would
from each patch branch: out of the release, directory moved to
Patches/orphaned/, branch kept. Attaching them back is proposed, never
automatic: `release create` offers it for each detached patch.

It used to offer to migrate them to the next patch release instead, by
rebasing their branches. The release branch they were rebased from had
already been deleted: the promotion failed with "invalid upstream" after
ho-prod, the tag and the deletion were pushed, and left the candidates in
no release.
"""

import tomllib

import pytest

CANDIDATE_SQL = 'CREATE TABLE candidate_table (id INT);'


@pytest.mark.integration
class TestPromoteProdDetachesCandidates:

    def _release_with_a_staged_patch_and_a_candidate(self, env):
        project_dir, run = env['project_dir'], env['run']

        # A patch merged into 0.1.0...
        run(['half_orm', 'dev', 'patch', 'create', '1-merged'])
        run(['git', 'checkout', 'ho-patch/1-merged'])
        (project_dir / 'Patches' / '1-merged' / '01_table.sql').write_text(
            'CREATE TABLE merged_table (id INT);'
        )
        run(['half_orm', 'dev', 'patch', 'apply'])
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Merged patch'])
        run(['half_orm', 'dev', 'patch', 'merge'], input_text='y\n')

        # ...and a candidate with work of its own, not merged.
        run(['git', 'checkout', 'ho-release/0.1.0'])
        run(['half_orm', 'dev', 'patch', 'create', '2-candidate'])
        run(['git', 'checkout', 'ho-patch/2-candidate'])
        (project_dir / 'Patches' / '2-candidate' / '01_table.sql').write_text(CANDIDATE_SQL)
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', 'Candidate work'])
        run(['git', 'push', 'origin', 'ho-patch/2-candidate'])

        run(['git', 'checkout', 'ho-release/0.1.0'])
        run(['half_orm', 'dev', 'release', 'promote', 'rc'])

    def test_candidates_are_detached_and_production_released(self, project_with_release):
        run = project_with_release['run']
        self._release_with_a_staged_patch_and_a_candidate(project_with_release)

        result = run(['half_orm', 'dev', 'release', 'promote', 'prod'],
                     input_text='y\n', check=False)
        assert result.returncode == 0, (
            f"promote prod failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )

        # Production holds the staged patch only.
        assert 'v0.1.0' in run(['git', 'tag', '-l']).stdout.split()
        assert run(['git', 'show', 'ho-prod:.hop/releases/0.1.0.txt']).stdout == '1-merged\n'
        assert run(['git', 'rev-parse', '--verify', '--quiet', 'ho-prod-0.1.0'],
                   check=False).returncode == 0
        remote = run(['git', 'ls-remote', '--heads', 'origin']).stdout
        assert 'refs/heads/ho-release/0.1.0' not in remote

        # The candidate is orphaned, its work kept, on production and on
        # its own branch, pushed.
        for ref in ('ho-prod', 'ho-patch/2-candidate'):
            assert run(['git', 'show', f'{ref}:Patches/orphaned/2-candidate/01_table.sql']
                       ).stdout == CANDIDATE_SQL
        assert (run(['git', 'rev-parse', 'ho-patch/2-candidate']).stdout
                == run(['git', 'rev-parse', 'origin/ho-patch/2-candidate']).stdout)

        # No release was created behind the user's back.
        assert 'ho-release/' not in remote

    def _promote_then_create_next_release(self, env, answer):
        run = env['run']
        self._release_with_a_staged_patch_and_a_candidate(env)
        run(['half_orm', 'dev', 'release', 'promote', 'prod'], input_text='y\n')
        run(['git', 'checkout', 'ho-prod'])
        return run(['half_orm', 'dev', 'release', 'create', 'patch'], input_text=answer)

    def test_next_release_offers_to_attach_the_candidate(self, project_with_release):
        project_dir, run = project_with_release['project_dir'], project_with_release['run']

        result = self._promote_then_create_next_release(project_with_release, 'y\n')

        assert 'Attach 2-candidate to 0.1.1?' in result.stdout
        toml = run(['git', 'show', 'ho-release/0.1.1:.hop/releases/0.1.1-patches.toml']).stdout
        assert tomllib.loads(toml)['patches'] == {'2-candidate': {'status': 'candidate'}}
        assert run(['git', 'show', 'ho-release/0.1.1:Patches/2-candidate/01_table.sql']
                   ).stdout == CANDIDATE_SQL

    def test_declined_attachment_leaves_the_candidate_orphaned(self, project_with_release):
        run = project_with_release['run']

        result = self._promote_then_create_next_release(project_with_release, 'n\n')

        assert 'Attach 2-candidate to 0.1.1?' in result.stdout
        toml = run(['git', 'show', 'ho-release/0.1.1:.hop/releases/0.1.1-patches.toml']).stdout
        assert tomllib.loads(toml)['patches'] == {}
        assert run(['git', 'show', 'ho-release/0.1.1:Patches/orphaned/2-candidate/01_table.sql']
                   ).stdout == CANDIDATE_SQL

    def test_declining_leaves_the_release_as_it_was(self, project_with_release):
        run = project_with_release['run']
        self._release_with_a_staged_patch_and_a_candidate(project_with_release)

        result = run(['half_orm', 'dev', 'release', 'promote', 'prod'],
                     input_text='n\n', check=False)

        assert result.returncode != 0
        assert 'Promotion cancelled' in result.stdout + result.stderr
        assert 'v0.1.0' not in run(['git', 'tag', '-l']).stdout.split()
        toml = run(['git', 'show', 'ho-release/0.1.0:.hop/releases/0.1.0-patches.toml']).stdout
        assert tomllib.loads(toml)['patches']['2-candidate'] == {'status': 'candidate'}

    def test_promote_after_patch_detach(self, project_with_release):
        """
        A candidate detached beforehand with `patch detach` does not block
        the promotion.

        ho-prod's hook refuses the sync commit of `patch detach` (no lock is
        held), so ho-prod keeps the release TOML as it was, the detached
        patch still listed. Merging the release into ho-prod then conflicted
        on that TOML, which the promotion deletes right after: the release
        branch's version is taken.
        """
        project_dir, run = project_with_release['project_dir'], project_with_release['run']
        self._release_with_a_staged_patch_and_a_candidate(project_with_release)

        run(['git', 'checkout', 'ho-patch/2-candidate'])
        run(['half_orm', 'dev', 'patch', 'detach', '--force'])
        run(['git', 'checkout', 'ho-release/0.1.0'])

        result = run(['half_orm', 'dev', 'release', 'promote', 'prod'], check=False)
        assert result.returncode == 0, (
            f"promote prod failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )
        assert run(['git', 'show', 'ho-prod:.hop/releases/0.1.0.txt']).stdout == '1-merged\n'
        assert run(['git', 'show', 'ho-prod:Patches/orphaned/2-candidate/01_table.sql']
                   ).stdout == CANDIDATE_SQL
        assert run(['git', 'status', '--porcelain']).stdout == ''
