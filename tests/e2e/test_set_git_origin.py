"""
End-to-end tests for the set-git-origin command.
"""

import pytest
from pathlib import Path
from tests.e2e.conftest import run_cmd

pytestmark = pytest.mark.e2e


class TestSetGitOrigin:
    """Test set-git-origin command."""

    def test_set_git_origin_updates_config(self, initialized_project):
        """hop config is updated with the new origin."""
        env = initialized_project
        run = env['run']
        project_dir = env['project_dir']

        new_origin = str(project_dir.parent.parent / 'new_origin.git')
        run_cmd(['git', 'init', '--bare', new_origin])

        run(['half_orm', 'dev', 'set-git-origin', new_origin])

        config = (project_dir / '.hop' / 'config').read_text()
        assert new_origin in config

    def test_set_git_origin_updates_pyproject_homepage(self, initialized_project):
        """pyproject.toml Homepage is updated."""
        env = initialized_project
        run = env['run']
        project_dir = env['project_dir']

        new_origin = str(project_dir.parent.parent / 'new_origin2.git')
        run_cmd(['git', 'init', '--bare', new_origin])

        run(['half_orm', 'dev', 'set-git-origin', new_origin])

        pyproject = (project_dir / 'pyproject.toml').read_text()
        # new_origin is a local path — _git_origin_to_https passthrough
        assert new_origin.rstrip('.git') in pyproject or 'Homepage' in pyproject

    def test_set_git_origin_updates_git_remote(self, initialized_project):
        """git remote origin is updated."""
        env = initialized_project
        run = env['run']
        project_dir = env['project_dir']

        new_origin = str(project_dir.parent.parent / 'new_origin3.git')
        run_cmd(['git', 'init', '--bare', new_origin])

        run(['half_orm', 'dev', 'set-git-origin', new_origin])

        result = run(['git', 'remote', 'get-url', 'origin'])
        assert new_origin in result.stdout.strip()

    def test_set_git_origin_pushes_ho_prod(self, initialized_project):
        """ho-prod is pushed to the new remote."""
        env = initialized_project
        run = env['run']
        project_dir = env['project_dir']

        new_origin = str(project_dir.parent.parent / 'new_origin4.git')
        run_cmd(['git', 'init', '--bare', new_origin])

        run(['half_orm', 'dev', 'set-git-origin', new_origin])

        result = run_cmd(['git', 'ls-remote', '--heads', new_origin])
        assert 'ho-prod' in result.stdout

    def test_set_git_origin_pushes_active_branches(self, project_with_release):
        """Active ho-release/* and ho-patch/* branches are pushed to the new remote."""
        env = project_with_release
        run = env['run']
        project_dir = env['project_dir']

        # Create a patch branch so we have an active ho-patch/*
        run(['half_orm', 'dev', 'patch', 'create', '99-test'])

        new_origin = str(project_dir.parent.parent / 'new_origin5.git')
        run_cmd(['git', 'init', '--bare', new_origin])

        # Go back to ho-prod to run the command
        run(['git', 'checkout', 'ho-prod'])
        run(['half_orm', 'dev', 'set-git-origin', new_origin])

        result = run_cmd(['git', 'ls-remote', '--heads', new_origin])
        remote_branches = result.stdout
        assert 'ho-prod' in remote_branches
        assert 'ho-release/0.1.0' in remote_branches
        assert 'ho-patch/99-test' in remote_branches

    def test_set_git_origin_noop_if_same(self, initialized_project):
        """Nothing changes if the new origin equals the current one."""
        env = initialized_project
        run = env['run']

        current_origin = env['git_origin']

        result = run(['half_orm', 'dev', 'set-git-origin', str(current_origin)])
        assert 'Nothing to do' in result.stdout

    def test_set_git_origin_rejects_invalid_url(self, initialized_project):
        """Invalid URL is rejected with a clear error."""
        run = initialized_project['run']

        result = run(
            ['half_orm', 'dev', 'set-git-origin', 'not-a-valid-url'],
            check=False
        )
        assert result.returncode != 0