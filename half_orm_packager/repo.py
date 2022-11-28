"""The pkg_conf module provides the Repo and DbConf classes.
"""

import os
from configparser import ConfigParser, NoOptionError
from half_orm_packager.globals import HOP_PATH
from half_orm_packager.db_conf import DbConf
from half_orm_packager.git_conf import GitConf

class Repo:
    """Reads and writes the hop repo conf file.
    """
    __hop_version = open(f'{HOP_PATH}/version.txt').read().strip()
    __base_dir: str = None;
    __name: str = None;
    __db_conf: DbConf = DbConf()
    __file: str;
    def __init__(self):
        self.__check()

    @property
    def production(self):
        return self.__db_conf.production

    @property
    def model(self):
        return self.__db_conf.model

    def __check(self):
        """Searches the hop configuration file for the package.
        This method is called when no hop config file is provided.
        Returns True if we are in a repo, False otherwise.
        """
        base_dir = os.path.abspath(os.path.curdir)
        while base_dir:
            conf_file = os.path.join(base_dir, '.hop', 'config')
            if os.path.exists(conf_file):
                self.__base_dir = base_dir
                self.__file: str = conf_file
                self.__load_config()
                self.__db_conf = DbConf(self.__name)
                self.__git_conf = GitConf(self.__base_dir)
                return True
            par_dir = os.path.split(base_dir)[0]
            if par_dir == base_dir:
                return False
            base_dir = par_dir
        return False

    def __check_version(self):
        """Verify that the current hop version is the one that was last used in the
        hop repository. If not tries to upgrade the repository to the current version of hop.
        """
        if self.__hop_version < self.__self_hop_version:
            print("Can't downgrade hop.")
        if self.__hop_version != self._self_hop_version:
            print(f'HOP VERSION MISMATCH!\n- hop: {self.__hop_version}\n- repo: {self.__self_hop_version}')
            sys.exit(1)
            # self.__hop_upgrade()
            # self.__config.hop_version = self.__config.repo_hop_version
            # self.__config.write()


    def __load_config(self):
        "Sets __name and __hop_version"
        config = ConfigParser()
        config.read(self.__file)
        self.__name = config['halfORM']['package_name']
        self.__self_hop_version = config['halfORM'].get('hop_version')

    @property
    def name(self):
        return self.__name
    @name.setter
    def name(self, name):
        self.__name = name

    def __write(self):
        open(self.__file, 'w').write(str(self))

    def __str__(self):
        res = [f'Half-ORM packager {self.__hop_version}', '\n']
        res += [
            '[hop repo]',
            f'package_name = {self.__name}',
            f'hop_version = {self.__self_hop_version}'
        ]
        res.append('\n')
        res.append(str(self.__db_conf))
        res.append('\n')
        res.append(str(self.__git_conf))
        return '\n'.join(res)

    @property
    def db_conf(self):
        return self.__db_conf
    @db_conf.setter
    def db_conf(self, dbname):
        self.__db_conf = DbConf(dbname)


    def init(self, package_name):
        cur_dir = os.path.abspath(os.path.curdir)
        path = os.path.join(cur_dir, package_name)
        print(f"Installing new hop repo in {path}.")
        raise NotImplemented

    def upgrade(self):
        raise NotImplemented
        versions = [line.split()[0] for line in open(f'{HOP_PATH}/patches/log').readlines()]
        if self.__config.hop_version:
            to_apply = False
            for version in versions:
                if self.__config.hop_version.find(version) == 0:
                    to_apply = True
                    continue
            if to_apply:
                print('UPGRADE HOP to', version)
                Patch(self, create_mode=True).apply(f'{HOP_PATH}/patches/{self.version.replace(".", "/")}')
        self.__hop_version = self.__hop_version
        self.__write()
