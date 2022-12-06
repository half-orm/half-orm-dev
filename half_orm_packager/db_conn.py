"""Provides the DbConn class.
"""

import os
import subprocess
import sys

from getpass import getpass
from configparser import ConfigParser, NoOptionError

from half_orm.model import CONF_DIR
from half_orm_packager import utils


class DbConn:
    """Handles the connection parameters to the database.
    Provides the execute_pg_command."""
    __conf_dir = CONF_DIR # HALFORM_CONF_DIR
    def __init__(self, name):
        self.__name = name
        self.__user = None
        self.__password = None
        self.__host = None
        self.__port = None
        self.__production = None
        if name:
            self.__connection_file = os.path.join(self.__conf_dir, self.__name)
            if not os.path.exists(self.__connection_file):
                raise FileNotFoundError
            self.__init()

    @property
    def production(self):
        "prod"
        return self.__production

    def __init(self):
        "Reads the config file and sets the connection parameters"
        config = ConfigParser()
        config.read([self.__connection_file])
        self.__name = config.get('database', 'name')
        try:
            self.__user = config.get('database', 'user')
            self.__password = config.get('database', 'password')
            self.__host = config.get('database', 'host')
            self.__port = config.get('database', 'port')
        except NoOptionError:
            pass
        try:
            prod = config.get('database', 'production')
        except NoOptionError:
            prod = 'False'
        if prod == 'True':
            self.__production = True
        elif prod == 'False':
            self.__production = False
        else:
            raise Exception('production must be either False or True')

    def set_params(self, name):
        """Asks for the connection parameters.
        """
        self.__name = name
        if not os.access(self.__conf_dir, os.W_OK):
            sys.stderr.write(f"You don't have write access to {self.__conf_dir}.\n")
            if self.__conf_dir == '/etc/half_orm': # only on linux
                utils.error(
                    "Set the HALFORM_CONF_DIR environment variable if you want to use a\n"
                    "different directory.\n", exit=1)
        print(f'Connection parameters to the database {self.__name}:')
        self.__user = os.environ['USER']
        self.__user = input(f'. user ({self.__user}): ') or self.__user
        self.__password = getpass('. password: ')
        if self.__password == '' and \
                (input(
                    '. is it an ident login with a local account? [Y/n] ') or 'Y').upper() == 'Y':
            self.__host = self.__port = ''
        else:
            self.__host = input('. host (localhost): ') or 'localhost'
            self.__port = input('. port (5432): ') or 5432

        self.__production = input('Production (False): ') or False

        self.__write_config()

        return self

    def __write_config(self):
        "Helper: write file in utf8"
        self.__connection_file = os.path.join(self.__conf_dir, self.__name)
        config = ConfigParser()
        config['database'] = {
            'name': self.__name,
            'user': self.__user,
            'password': self.__password,
            'host': self.__host,
            'port': self.__port,
            'production': self.__production
        }
        with open(self.__connection_file, 'w', encoding='utf-8') as configfile:
            config.write(configfile)

    def execute_pg_command(self, cmd, *args, **kwargs):
        """Helper. Executes a postgresql
        """
        if not kwargs.get('stdout'):
            kwargs['stdout'] = subprocess.DEVNULL
        cmd_list = [cmd]
        env = os.environ.copy()
        password = self.__password
        if password:
            env['PGPASSWORD'] = password
        if self.__user:
            cmd_list += ['-U', self.__user]
        if self.__port:
            cmd_list += ['-p', self.__port]
        if self.__host:
            cmd_list += ['-h', self.__host]
        cmd_list.append(self.__name)
        if args:
            cmd_list += args
        try:
            subprocess.run(
                cmd_list, env=env, shell=False, check=True,
                # stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                **kwargs)
        except subprocess.CalledProcessError as err:
            utils.error(f'{err.stderr}\n', exit=err.returncode)
