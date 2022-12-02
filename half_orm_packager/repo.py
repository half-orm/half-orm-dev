"""The pkg_conf module provides the Repo class.
"""

import os
import sys
from configparser import ConfigParser, NoOptionError
from half_orm_packager.globals import HOP_PATH, TEMPLATES_DIR
from half_orm_packager.database import Database
from half_orm_packager.hgit import HGit 
from half_orm_packager.utils import Color
from half_orm_packager.hgit import HGit
from half_orm_packager import modules

class Repo:
    """Reads and writes the hop repo conf file.
    """
    __hop_version = open(f'{HOP_PATH}/version.txt').read().strip()
    __base_dir: str = None;
    __name: str = None;
    __database: Database = Database()
    __file: str;
    def __init__(self):
        self.__check()

    @property
    def production(self):
        return self.__database.production

    @property
    def model(self):
        return self.__database.model

    @property
    def hop_version(self):
        return self.__hop_version

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
                self.__database = Database(self.__name)
                self.__hgit = HGit(self.__base_dir)
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
    def base_dir(self):
        return self.__base_dir

    @property
    def name(self):
        return self.__name
    @name.setter
    def name(self, name):
        self.__name = name

    def __write(self):
        open(self.__file, 'w').write(str(self))

    def __hop_version_mismatch(self):
        return self.__hop_version != self.__self_hop_version

    @property
    def status(self, verbose=True):
        res = [f'Half-ORM packager: {self.__hop_version}\n']
        hop_version = self.__hop_version_mismatch() and \
            Color.red(self.__self_hop_version) or \
            Color.green(self.__self_hop_version)
        res += [
            '[Hop repository]',
            f'- base directory: {self.__base_dir}',
            f'- package name: {self.__name}',
            f'- hop version: {hop_version}'
        ]
        # verbose and res.append('\n')
        verbose and res.append(str(self.__database.status))
        # res.append('\n')
        res.append(str(self.__hgit))
        return '\n'.join(res)

    @property
    def database(self):
        return self.__database

    def init(self, package_name):
        self.__name = package_name
        self.__self_hop_version=self.__hop_version
        cur_dir = os.path.abspath(os.path.curdir)
        self.__base_dir = os.path.join(cur_dir, package_name)
        print(f"Installing new hop repo in {self.__base_dir}.")

        if not os.path.exists(self.__base_dir):
            os.makedirs(self.__base_dir)
        else:
            sys.stderr.write(f"ERROR! The path '{self.__base_dir}' already exists!\n")
            sys.exit(1)
        README = open(f'{TEMPLATES_DIR}/README').read()
        CONFIG_TEMPLATE = open(f'{TEMPLATES_DIR}/config').read()
        SETUP_TEMPLATE = open(f'{TEMPLATES_DIR}/setup.py').read()
        GIT_IGNORE = open(f'{TEMPLATES_DIR}/.gitignore').read()
        PIPFILE = open(f'{TEMPLATES_DIR}/Pipfile').read()

        setup = SETUP_TEMPLATE.format(
                dbname=self.__name,
                package_name=self.__name,
                half_orm_version=self.__hop_version)
        open(f'{self.__base_dir}/setup.py', 'w').write(setup)

        PIPFILE = PIPFILE.format(
                half_orm_version=self.__hop_version)
        open(f'{self.__base_dir}/Pipfile', 'w').write(PIPFILE)

        os.mkdir(f'{self.__base_dir}/.hop')
        config = ConfigParser()
        config['halfORM'] = {
            'config_file': self.__name,
            'package_name': self.__name,
            'hop_version': self.__hop_version
        }
        with open(f'{self.__base_dir}/.hop/config', 'w') as configfile:
            config.write(configfile)
        self.__database = Database().init(self.__name)
        modules.generate(self)

        cmd = " ".join(sys.argv)
        readme = README.format(cmd=cmd, dbname=self.__name, package_name=self.__name)
        open(f'{self.__base_dir}/README.md', 'w').write(readme)
        open(f'{self.__base_dir}/.gitignore', 'w').write(GIT_IGNORE)
        self.__hgit = HGit().init(self.__base_dir)

        print(f"\nThe hop project '{self.__name}' has been created.")
        print(self.status)


    def upgrade(self):
        print('XXX WIP')
        return
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

    def patch(self):
        print('XXX WIP')
        modules.generate(self)
        sys.exit(1)