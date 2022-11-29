from configparser import ConfigParser, NoOptionError
from half_orm.model import Model, CONF_DIR

class Database:
    """Reads and writes the halfORM connection file
    """

    def __init__(self, connection_file: str = None):
        self.__connection_file = None
        self.__model = None
        # self.__name = None
        # self.__user = None
        # self.__password = None
        # self.__host = None
        # self.__port = None
        self.__production = None
        self.__patch_release = None
        if connection_file:
            self.__init(connection_file)

    def __call__(self, connection_file):
        return self.__class__(connection_file)

    def __init(self, file_name):
        self.__model = Model(file_name)
        self.__last_release = next(self.__model.get_relation_class('half_orm_meta.view.hop_last_release')().select())
        self.__connection_file = f'{CONF_DIR}/{file_name}'
        config = ConfigParser()
        config.read([self.__connection_file])
        # self.__name = config.get('database', 'name')
        # self.__user = config.get('database', 'user')
        # self.__password = config.get('database', 'password')
        # self.__host = config.get('database', 'host')
        # self.__port = config.get('database', 'port')
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
        return '{major}.{minor}.{patch} ({date})'.format(**self.__last_release)

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

    def __repr(self, show_password=False):
        db_conf_keys = ['production']
        res = ['[database]']
        for key in db_conf_keys:
            value = eval(f'self.{key}')
            if not show_password and key == 'password':
                value = 'xxxxxxxx'
            res.append(f'{key}: {value}')
        # res.append('\n')
        # res.append('[model]')
        # res.append(str(self.__model))
        res.append(f'last release: {self.__last_release_s}')
        return '\n'.join(res)

    __str__ = __repr

    def write(self):
        open(self.__connection_file, 'w').write(str(self.__repr, True))
