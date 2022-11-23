"""The pkg_conf module provides the HopConf and DbConf classes.
"""

from configparser import ConfigParser, NoOptionError
from half_orm.model import CONF_DIR

class HopConf:
    """Reads and writes the hop repo conf file.
    """
    def __init__(self, path):
        self.__path: str = path
        self.__file: str = f'{self.__path}/.hop/config'
        self.__name: str = None
        self.__hop_version: str = None
        self.__load()

    def __load(self):
        config = ConfigParser()
        config.read(self.__file)
        self.__name = config['halfORM']['package_name']
        self.__hop_version = config['halfORM'].get('hop_version')

    @property
    def name(self):
        return self.__name
    @name.setter
    def name(self, name):
        self.__name = name

    @property
    def hop_version(self):
        return self.__hop_version
    @hop_version.setter
    def hop_version(self, version):
        self.__hop_version = version

    def write(self):
        open(self.__file, 'w').write(str(self))

    def __str__(self):
        return f'''[halfORM]
config_file = {self.__name}
package_name = {self.__name}
hop_version = {self.__hop_version}
'''

class DbConf:
    """Reads and writes the halfORM connection file
    """
    TMPL_CONF_FILE = """[database]
name = {name}
user = {user}
password = {password}
host = {host}
port = {port}
production = {production}
""" 

    def __init__(self, connection_file: str = None):
        self.__connection_file: str = connection_file and f'{CONF_DIR}/{connection_file}' or None
        self.__name = None
        self.__user = None
        self.__password = None
        self.__host = None
        self.__port = None
        self.__production = None
        if connection_file:
            self.__read_conf_file()

    def __read_conf_file(self):
        config = ConfigParser()
        config.read([self.__connection_file])
        self.__name = config.get('database', 'name')
        self.__user = config.get('database', 'user')
        self.__password = config.get('database', 'password')
        self.__host = config.get('database', 'host')
        self.__port = config.get('database', 'port')
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

    def __str__(self):
        return f"""name: {self.__name}
user: {self.__user}
password: {self.__password}
host: {self.__host}
port: {self.__port}
production: {self.__production}
"""

    def write(self):
        open(self.__connection_file, 'w').write(str(self))
