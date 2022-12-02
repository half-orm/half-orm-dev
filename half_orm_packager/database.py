import os
import subprocess
import sys
from getpass import getpass

from psycopg2 import OperationalError
from configparser import ConfigParser, NoOptionError
from half_orm.model import Model, CONF_DIR
from half_orm.model_errors import UnknownRelation
from half_orm_packager.globals import HOP_PATH

class Database:
    """Reads and writes the halfORM connection file
    """
    __conf_dir = CONF_DIR # HALFORM_CONF_DIR
    def __init__(self, name: str = None):
        self.__connection_file = None
        self.__model = None
        self.__name = name
        self.__user = None
        self.__password = None
        self.__host = None
        self.__port = None
        self.__production = None
        self.__patch_release = None
        if name:
            self.__model = Model(name)
            self.__init(name)

    def __call__(self, name):
        return self.__class__(name)

    def __init(self, name, get_release=True):
        self.__name = name
        self.__connection_file = f'{self.__conf_dir}/{self.__name}'
        if not os.path.exists(self.__connection_file):
            raise FileNotFoundError
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
        if get_release:
            self.__last_release = next(self.__model.get_relation_class('half_orm_meta.view.hop_last_release')().select())
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

    @property
    def __last_release_s(self):
        return '{major}.{minor}.{patch}'.format(**self.__last_release)

    @property
    def name(self):
        return self.__name
    @name.setter
    def name(self, name):
        self.__name = name

    @property
    def user(self):
        return self.__user
    @user.setter
    def user(self, user):
        self.__user = user

    @property
    def password(self):
        return self.__password
    @password.setter
    def password(self, password):
        self.__password = password

    @property
    def host(self):
        return self.__host
    @host.setter
    def host(self, host):
        self.__host = host

    @property
    def port(self):
        return self.__port
    @port.setter
    def port(self, port):
        self.__port = port

    @property
    def production(self):
        return self.__production
    @production.setter
    def production(self, production):
        self.__production = production

    @property
    def model(self):
        return self.__model

    @property
    def status(self):
        db_conf_keys = ['production']
        res = ['[database]']
        res.append(f'production: {self.production}')
        res.append(f'last release: {self.__last_release_s}')
        return '\n'.join(res)

    def __repr(self, show_password=False):
        db_conf_keys = ['name', 'user', 'password', 'host', 'port', 'production']
        res = ['[database]']
        for key in db_conf_keys:
            value = eval(f'self.{key}')
            if not show_password and key == 'password':
                value = 'xxxxxxxx'
            res.append(f'{key} = {value}')
        return '\n'.join(res)

    def write(self):
        open(self.__connection_file, 'w').write(str(self.__repr, True))

    def init(self, name):
        try:
            self.__init(name, get_release=False)
        except FileNotFoundError:
            self.__set_config_file()
        return self.__init_db()

    def __init_db(self):
        try:
            self.__model = Model(self.__name)
        except OperationalError as err:
            sys.stderr.write(f"The database '{self.__name}' does not exist.\n")
            create = input('Do you want to create it (Y/n): ') or "y"
            if create.upper() == 'Y':
                self.execute_pg_command('createdb')
            else:
                sys.stderr.write(f'Aborting! Please remove {self.__base_dir}/{self.__name} directory.\n')
                sys.exit(1)
        self.__model = Model(self.__name)
        try:
            self.__model.get_relation_class('half_orm_meta.hop_release')
        except UnknownRelation:
            hop_init_sql_file = f'{HOP_PATH}/sql/half_orm_meta_schemas.sql'
            self.execute_pg_command('psql', '-f', hop_init_sql_file, stdout=subprocess.DEVNULL)
            self.__model.reconnect(reload=True)
            self.__last_release = self.__model.get_relation_class('half_orm_meta.hop_release')(
                major=0, minor=0, patch=0, changelog='Initial release'
            ).insert()[0]
        self = self(self.__name)
        return self

    def __set_config_file(self):
        """Asks for the connection parameters.
        """
        if not os.access(CONF_DIR, os.W_OK):
            sys.stderr.write(f"You don't have write access to {CONF_DIR}.\n")
            if CONF_DIR == '/etc/half_orm':
                sys.stderr.write(
                    "Set the HALFORM_CONF_DIR environment variable if you want to use a\n"
                    "different directory.\n")
            sys.exit(1)
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

        open(f'{CONF_DIR}/{self.__name}',
            'w', encoding='utf-8').write(self.__repr(show_password=True))

        return self

    def execute_pg_command(self, cmd, *args, **kwargs):
        if not kwargs.get('stdout'):
            kwargs['stdout']=subprocess.DEVNULL
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
        if args and len(args):
            cmd_list += args
        ret = subprocess.run(cmd_list, env=env, shell=False, **kwargs)
        if ret.returncode:
            raise
            sys.exit(ret.returncode)
