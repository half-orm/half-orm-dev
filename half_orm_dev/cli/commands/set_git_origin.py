"""
set-git-origin command - Update the git remote origin URL
"""

import re
import click
from pathlib import Path
from half_orm_dev.repo import Repo, _git_origin_to_https


@click.command('set-git-origin')
@click.argument('new_origin')
def set_git_origin(new_origin):
    """Update the git remote origin URL.

    Updates .hop/config, pyproject.toml Homepage, the git remote,
    and synchronizes all active branches.

    \b
    Examples:
        half_orm dev set-git-origin git@github.com:user/repo.git
        half_orm dev set-git-origin https://github.com/user/repo.git
    """
    repo = Repo()

    try:
        repo._validate_git_origin_url(new_origin)
    except ValueError as e:
        raise click.BadParameter(str(e), param_hint='new_origin')

    old_origin = repo.git_origin
    if old_origin == new_origin:
        click.echo(f"git-origin is already '{new_origin}'. Nothing to do.")
        return

    additional_files = []

    # 1. Update .hop/config
    repo.git_origin = new_origin
    repo._Repo__config.write()
    click.echo(f"  ✓ .hop/config updated")

    # 2. Update pyproject.toml Homepage
    pyproject_path = Path(repo.base_dir) / 'pyproject.toml'
    if pyproject_path.exists():
        content = pyproject_path.read_text()
        new_homepage = _git_origin_to_https(new_origin)
        new_content = re.sub(
            r'^(Homepage\s*=\s*).*$',
            f'\\1"{new_homepage}"',
            content,
            flags=re.MULTILINE
        )
        if new_content != content:
            pyproject_path.write_text(new_content)
            additional_files.append('pyproject.toml')
            click.echo(f"  ✓ pyproject.toml Homepage → '{new_homepage}'")

    # 3. Update git remote
    try:
        repo.hgit._HGit__git_repo.git.remote('set-url', 'origin', new_origin)
        click.echo(f"  ✓ git remote origin updated")
    except Exception as e:
        click.echo(f"  ⚠️  Could not update git remote: {e}", err=True)
        click.echo(f"     Run manually: git remote set-url origin {new_origin}", err=True)

    # 3.5. Push ho-prod to the new remote before acquiring the lock.
    # The lock mechanism pushes a tag — this requires the remote to already
    # have at least one ref. Pushing ho-prod first seeds the new remote.
    try:
        repo.hgit._HGit__git_repo.git.push('--force', 'origin', 'ho-prod')
        click.echo(f"  ✓ ho-prod pushed to new remote")
    except Exception as e:
        click.echo(f"  ⚠️  Could not push ho-prod to new remote: {e}", err=True)
        click.echo(f"     Run manually: git push --force origin ho-prod", err=True)

    # 4. Commit on ho-prod (requires the lock for the pre-commit hook).
    lock_tag = None
    commit_hash = None
    try:
        lock_tag = repo.hgit.acquire_branch_lock('ho-prod')

        all_files = ['.hop/'] + additional_files
        for f in all_files:
            repo.hgit.add(f)

        repo.hgit.commit('-m', f"[HOP] set git-origin to {new_origin}")
        commit_hash = repo.hgit._HGit__git_repo.git.rev_parse('HEAD')
        repo.hgit.push_branch('ho-prod')
        click.echo(f"  ✓ Committed on ho-prod ({commit_hash[:8]})")
    except Exception as e:
        click.echo(f"  ⚠️  Commit on ho-prod failed: {e}", err=True)
    finally:
        if lock_tag:
            repo.hgit.release_branch_lock(lock_tag)

    # 5. Cherry-pick the ho-prod commit onto every active branch and push.
    # This is the simplest and most reliable way to ensure the same change
    # (new git-origin) appears on every branch, not just on ho-prod.
    if commit_hash:
        branches_status = repo.hgit.get_active_branches_status()
        active_branches = (
            branches_status.get('patch_branches', []) +
            branches_status.get('release_branches', [])
        )
        for branch_info in active_branches:
            branch = branch_info['name']
            try:
                repo.hgit.checkout(branch)
                repo.hgit._HGit__git_repo.git.cherry_pick(commit_hash)
                repo.hgit.push_branch(branch)
                click.echo(f"  ✓ {branch} updated and pushed")
            except Exception as e:
                click.echo(f"  ⚠️  Could not update {branch}: {e}", err=True)
                # Abort cherry-pick if it left the repo in a bad state
                try:
                    repo.hgit._HGit__git_repo.git.cherry_pick('--abort')
                except Exception:
                    pass
        # Return to ho-prod
        try:
            repo.hgit.checkout('ho-prod')
        except Exception:
            pass

    click.echo(f"\n✓ git-origin: '{old_origin}' → '{new_origin}'")
