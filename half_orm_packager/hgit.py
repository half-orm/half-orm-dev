"""Provides the HGit class
"""

import os
import subprocess
import sys
from git import Repo, GitCommandError
from datetime import date

class HGit:
    "docstring"
    def __init__(self, project_path, hop_cls):
        self.__hop_cls = hop_cls
        self.__package_name = hop_cls.package_name
        self.__project_path = project_path
        self.__model = hop_cls.model

    def init(self):
        "Initiazes the git repo."
        #pylint: disable=import-outside-toplevel
        from .patch import Patch

        os.chdir(self.__project_path)
        try:
            Repo.init('.', initial_branch='main')
            print("Initializing git with a 'main' branch.")
        except GitCommandError:
            Repo.init('.')
            print("Initializing git with a 'master' branch.")

        repo = Repo('.')
        Patch(self.__hop_cls, create_mode=True).patch(self.__package_name, force=True)
        self.__model.reconnect()  # we get the new stuff from db metadata here
        subprocess.run(['hop', 'update', '-f'], check=True)  # ignore tests

        try:
            repo.head.commit
        except ValueError:
            repo.git.add('.')
            repo.git.commit(m='[0.0.0] First release')

        repo.git.checkout('-b', 'hop_main')

    @classmethod
    def get_sha1_commit(cls, patch_script):
        "Returns the sha1 of the last commmit"
        commit = subprocess.Popen(
            "git log --oneline --abbrev=-1 --max-count=1 {}".format(
            os.path.dirname(patch_script)
        ), shell=True, stdout=subprocess.PIPE)
        commit = commit.stdout.read().decode()
        if commit.strip():
            commit = commit.split()[0] # commit is the commit sha1
        else:
            sys.stderr.write("WARNING! Running in test mode (logging the date as commit).\n")
            commit = "{}".format(date.today())
        return commit
