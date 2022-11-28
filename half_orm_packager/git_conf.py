from half_orm_packager.hgit import HGit

class GitConf:
    def __init__(self, base_dir):
        self.__hgit = HGit(base_dir)
        self.__current_branch = self.__hgit.branch
        self.__is_clean = self.__hgit.repos_is_clean()
        self.__last_commit = self.__hgit.commit

    def __str__(self):
        res = ['[git]']
        res.append(f'current branch: {self.__current_branch}')
        res.append(f'repo is clean: {self.__is_clean}')
        res.append(f'last commit: {self.__last_commit}')
        return '\n'.join(res)
