from configparser import ConfigParser, NoOptionError
from half_orm.model import Model, CONF_DIR

class DbConf:
    """Reads and writes the halfORM connection file
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

    @property
    def model(self):
        if self.__name:
            return Model(self.__name)

    def __repr(self, show_password=False):
        db_conf_keys = ['name', 'user', 'password', 'host', 'port', 'production']
        res = ['[database]']
        for key in db_conf_keys:
            value = eval(f'self.{key}')
            if not show_password and key == 'password':
                value = 'xxxxxxxx'
            res.append(f'{key}: {value}')
        res.append('\n')
        res.append('[model]')
        res.append(str(self.model))
        return '\n'.join(res)

    __str__ = __repr

    def write(self):
        open(self.__connection_file, 'w').write(str(self.__repr, True))
