"""Provides the HGit class
"""

import os
import subprocess
import sys
from git import Repo, GitCommandError
from git.exc import InvalidGitRepositoryError
from datetime import date
from time import sleep

class HGit:
    "docstring"
    __hop_main = False
    def __init__(self, hop_cls):
        self.__hop_cls = hop_cls
        self.__project_path = hop_cls.project_path
        self.__model = hop_cls.model
        if not os.path.exists(f'{self.__project_path}/.git'):
            subprocess.run(['git', 'init', self.__project_path], check=True)
        self.__repo = Repo(self.__project_path)
        self.hop_main_branch()

    def hop_main_branch(self):
        if not HGit.__hop_main:
            HGit.__hop_main = 'hop_main' in [str(ref) for ref in self.__repo.references]
        if not  HGit.__hop_main:
            sys.stderr.write('WARN: creating hop_main branch.\n')
            HGit.__hop_main = True
            self.__repo.git.checkout('-b', 'hop_main')

    @property
    def repo(self):
        "Return the git repo object"
        if self.__repo is None:
            self.__repo = Repo(self.__project_path)
        return self.__repo

    @property
    def branch(self):
        "Returns the active branch"
        return self.repo.active_branch

    def init(self):
        "Initiazes the git repo."
        #pylint: disable=import-outside-toplevel
        from .patch import Patch
        from .update import update_modules

        os.chdir(self.__project_path)

        Patch(self.__hop_cls, create_mode=True).patch(force=True)
        self.__model.reconnect()  # we get the new stuff from db metadata here
        update_modules(self.__hop_cls.model, self.__hop_cls.package_name)
        self.repo.git.add('.')
        self.repo.git.commit(m='[0.0.0] First release')
        self.hop_main_branch()
        self.__hop_cls.last_release_s = '0.0.0'
        print("Patch system initialized at release '0.0.0'.")

    @property
    def commit(self):
        return list(self.__repo.iter_commits(self.branch, max_count=1))[0]

    @classmethod
    def exit_if_repo_is_not_clean(cls):
        "Exits if the repo has uncommited got changes."
        repo_is_clean = subprocess.Popen(
            "git status --porcelain", shell=True, stdout=subprocess.PIPE)
        repo_is_clean = repo_is_clean.stdout.read().decode().strip().split('\n')
        repo_is_clean = [line for line in repo_is_clean if line != '']
        if repo_is_clean:
            print("WARNING! Repo is not clean:\n\n{}".format('\n'.join(repo_is_clean)))
            cont = input("\nApply [y/N]?")
            if cont.upper() != 'Y':
                print("Aborting")
                sys.exit(1)


    def set_branch(self, release_s):
        """Checks the branch

        Either hop_main or hop_<release>.
        """
        rel_branch = f'hop_{release_s}'
        if str(self.branch) == 'hop_main' and rel_branch != 'hop_main':
            # creates the new branch
            self.repo.create_head(rel_branch)
            self.repo.git.checkout(rel_branch)
            print(f'NEW branch {rel_branch}')
        elif str(self.branch) == rel_branch:
            print(f'On branch {rel_branch}')
        # else:
        #     sys.stderr.write(f'Current branch is {self.branch}\n')
