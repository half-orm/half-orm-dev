"""The pkg_conf module provides the HopConf and DbConf classes.
"""

from configparser import ConfigParser

class HopConf:
    """Reads and writes the hop repo conf file.
    """
    def __init__(self, path):
        self.__path: str = path
        self.__name: str = None
        self.__load()

    def __load(self):
        config = ConfigParser()
        config.read(f'{self.__path}/.hop/config')
        self.__name = config['halfORM']['package_name']

    @property
    def name(self):
        return self.__name
    @name.setter
    def name(self, name):
        self.__name = name

    def __str__(self):
        return f'''Package: {self.__path}'''

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
        self.__connection_file: str = connection_file
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
        prod = config.get('database', 'production')
        if prod == 'True':
            self.__production = True
        elif prod == 'False':
            self.__production = False
        else:
            raise Exception('production must be either False or True')

    @property
    def name(self):
        return self.__name

    @property
    def user(self):
        return self.__user

    @property
    def password(self):
        return self.__password

    @property
    def host(self):
        return self.__host

    @property
    def port(self):
        return self.__port

    @property
    def production(self):
        return self.__production

    def __str__(self):
        return f"""name: {self.__name}
user: {self.__user}
password: {self.__password}
host: {self.__host}
port: {self.__port}
production: {self.__production}
"""
