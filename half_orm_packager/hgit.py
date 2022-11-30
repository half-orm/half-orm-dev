import os
import subprocess
from git import Repo

from half_orm_packager.utils import Color

class HGit:
    def __init__(self, base_dir=None):
        self.__base_dir = base_dir
        if base_dir:
            self.__post_init()

    def __post_init(self):
        self.__repo = Repo(self.__base_dir)
        self.__current_branch = self.branch
        self.__is_clean = self.repos_is_clean()
        self.__last_commit = self.commit

    def __str__(self):
        res = ['[git]']
        res.append(f'current branch: {self.__current_branch}')
        res.append(f'repo is clean: {self.__is_clean and Color.green(self.__is_clean) or Color.red(self.__is_clean)}')
        res.append(f'last commit: {self.__last_commit}')
        return '\n'.join(res)

    def init(self, base_dir, release='0.0.0'):
        "Initiazes the git repo."
        cur_dir = os.path.abspath(os.path.curdir)
        self.__base_dir = base_dir
        subprocess.run(['git', 'init', base_dir], check=True)
        self.__repo = Repo(base_dir)
        os.chdir(base_dir)
        # Patch(self.__hop_cls, create_mode=True).patch(force=True, create=True)
        self.__repo.git.add('.')
        self.__repo.git.commit(m=f'[{release}] First release')
        self.__repo.git.checkout('-b', 'hop_main')
        self.__post_init()
        os.chdir(cur_dir)
        return self

    @property
    def branch(self):
        "Returns the active branch"
        return str(self.__repo.active_branch)

    @staticmethod
    def repos_is_clean():
        with subprocess.Popen(
            "git status --porcelain", shell=True, stdout=subprocess.PIPE) as repo_is_clean:
            repo_is_clean = repo_is_clean.stdout.read().decode().strip().split('\n')
            repo_is_clean = [line for line in repo_is_clean if line != '']
            return not(bool(repo_is_clean))

    @property
    def commit(self):
        """Returns the last commit
        """
        return list(self.__repo.iter_commits(self.branch, max_count=1))[0]

