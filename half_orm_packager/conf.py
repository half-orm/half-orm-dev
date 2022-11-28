"""The pkg_conf module provides the Config and DbConf classes.
"""

import os
from configparser import ConfigParser, NoOptionError
from half_orm_packager.db_conf import DbConf
from half_orm_packager.git_conf import GitConf

class Config:
    """Reads and writes the hop repo conf file.
    """
    __base_dir: str = None;
    __name: str = None;
    __db_conf: DbConf = DbConf()
    __file: str;
    def __init__(self):
        self.__check_repo()

    @property
    def version(self):
        return self.__hop_version

    @property
    def production(self):
        return self.__db_conf.production

    @property
    def model(self):
        return self.__db_conf.model

    def __check_repo(self):
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
                self.__load()
                self.__db_conf = DbConf(self.__name)
                self.__git_conf = GitConf(self.__base_dir)
                return True
            par_dir = os.path.split(base_dir)[0]
            if par_dir == base_dir:
                return False
            base_dir = par_dir
        return False

    def __load(self):
        config = ConfigParser()
        config.read(self.__file)
        self.__name = config['halfORM']['package_name']
        self.__repo_hop_version = config['halfORM'].get('hop_version')

    @property
    def name(self):
        return self.__name
    @name.setter
    def name(self, name):
        self.__name = name

    @property
    def repo_hop_version(self):
        return self.__repo_hop_version
    @repo_hop_version.setter
    def repo_hop_version(self, version):
        self.__repo_hop_version = version

    def write(self):
        open(self.__file, 'w').write(str(self))

    def __str__(self):
        res = [
            '[halfORM]',
            f'package_name = {self.__name}',
            f'hop_version = {self.__repo_hop_version}'
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
