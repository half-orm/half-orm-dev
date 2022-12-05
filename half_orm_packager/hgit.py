"Provides the HGit class"

import os
import subprocess
from git import Repo

from half_orm_packager import utils
from half_orm_packager.manifest import Manifest

class HGit:
    "Manages the git operations on the repo."
    def __init__(self, repo=None):
        self.__repo = repo
        self.__base_dir = None
        self.__git_repo: Repo = None
        if repo:
            self.__base_dir = repo.base_dir
            self.__post_init()

    def __post_init(self):
        self.__git_repo = Repo(self.__base_dir)
        self.__current_branch = self.branch
        self.__is_clean = self.repos_is_clean()
        self.__last_commit = self.last_commit()

    def __str__(self):
        res = ['[Git]']
        res.append(f'- current branch: {self.__current_branch}')
        clean = utils.Color.green(self.__is_clean) \
            if self.__is_clean else utils.Color.red(self.__is_clean)
        res.append(f'- repo is clean: {clean}')
        res.append(f'- last commit: {self.__last_commit}')
        return '\n'.join(res)

    def init(self, base_dir, release='0.0.0'):
        "Initiazes the git repo."
        cur_dir = os.path.abspath(os.path.curdir)
        self.__base_dir = base_dir
        subprocess.run(['git', 'init', base_dir], check=True)
        self.__git_repo = Repo(base_dir)
        os.chdir(base_dir)
        # Patch(self.__hop_cls, create_mode=True).patch(force=True, create=True)
        self.__git_repo.git.add('.')
        self.__git_repo.git.commit(m=f'[{release}] hop new {os.path.basename(base_dir)}')
        self.__git_repo.git.checkout('-b', 'hop_main')
        self.__post_init()
        os.chdir(cur_dir)
        return self

    @property
    def branch(self):
        "Returns the active branch"
        return str(self.__git_repo.active_branch)

    @property
    def current_release(self):
        "Returns the current branch name without 'hop_'"
        return self.branch.replace('hop_', '')

    @property
    def is_hop_patch_branch(self):
        "Returns True if we are on a hop patch branch hop_X.Y.Z."
        try:
            major, minor, patch = self.current_release.split('.')
            return bool(1 + int(major) + int(minor) + int(patch))
        except ValueError:
            return False

    @staticmethod
    def repos_is_clean():
        "Returns True if the git repository is clean, False otherwise."
        with subprocess.Popen(
            "git status --porcelain", shell=True, stdout=subprocess.PIPE) as repo_is_clean:
            repo_is_clean = repo_is_clean.stdout.read().decode().strip().split('\n')
            repo_is_clean = [line for line in repo_is_clean if line != '']
            return not bool(repo_is_clean)

    def last_commit(self):
        """Returns the last commit
        """
        return list(self.__git_repo.iter_commits(self.branch, max_count=1))[0]

    def set_branch(self, release_s):
        """Checks the branch

        Either hop_main or hop_<release>.
        """
        rel_branch = f'hop_{release_s}'
        if str(self.branch) == 'hop_main' and rel_branch != 'hop_main':
            # creates the new branch
            self.__git_repo.create_head(rel_branch)
            self.__git_repo.git.checkout(rel_branch)
            print(f'NEW branch {rel_branch}')
        elif str(self.branch) == rel_branch:
            print(f'On branch {rel_branch}')

    def rebase_to_hop_main(self, push=False):
        "Rebase a hop_X.Y.Z branch to hop_main"
        release = self.current_release
        self.__git_repo.git.checkout('hop_main')
        self.__git_repo.git.rebase(f'hop_{release}')
        version_file = os.path.join(self.__base_dir, self.__repo.name, 'version.txt')
        utils.write(version_file, release)
        self.__git_repo.git.add(version_file)
        patch_dir = os.path.join(self.__base_dir, 'Patches', *release.split('.'))
        manifest = Manifest(patch_dir)
        message = f'[{release}] {manifest.changelog_msg}'
        self.__git_repo.git.commit('-m', message)
        self.__git_repo.git.tag(release, '-m', release)
        if push:
            self.__git_repo.git.push()
            self.__git_repo.git.push('-uf', 'origin', release)
