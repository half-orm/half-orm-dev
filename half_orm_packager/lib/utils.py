import os
import sys
import subprocess
from configparser import ConfigParser

import psycopg2

from half_orm.model import Model, CONF_DIR

from half_orm_packager.globals import HOP_PATH, TEMPLATES_DIR
from half_orm_packager.hgit import HGit



class Hop:
    "XXX: The hop class doc..."
    __connection_file_name = None
    __package_name = None
    __project_path = None
    __model = None

    def __init__(self, ref_dir):
        self.__last_release_s = None
        self.__release = None
        self.__release_s = ''
        self.__release_path = None
        Hop.__connection_file_name, Hop.__package_name, Hop.__project_path = get_connection_file_name(ref_dir=ref_dir)
        self.__production = False
        if self.__package_name and self.__model is None:
            self.__model = self.get_model()
            self.__production = self.__model.production

    def __get_last_release_s(self):
        return self.__last_release_s
    def __set_last_release_s(self, last_release_s):
        self.__last_release_s = last_release_s

    last_release_s = property(__get_last_release_s, __set_last_release_s)

    @property
    def release(self):
        return self.__release

    def __get_release_s(self):
        return self.__release_s
    
    def __set_release_s(self, release_s):
        self.__release_s = release_s

    release_s = property(__get_release_s, __set_release_s)

    @property
    def release_path(self):
        return self.__release_path

    def get_model(self):
        "Returns the half_orm model"

        if not self.package_name:
            sys.stderr.write(
                "You're not in a hop package directory.\n"
                "Try hop new <package directory> or change directory.\n")

        try:
            self.__model = Model(self.package_name)
            model = self.alpha()  # XXX To remove after alpha
            return model
        except psycopg2.OperationalError as exc:
            sys.stderr.write(f'The database {self.package_name} does not exist.\n')
            raise exc
        except MissingConfigFile:
            sys.stderr.write(
                'Cannot find the half_orm config file for this database.\n')
            sys.exit(1)

    def get_next_release(self, last_release=None):
        "Renvoie en fonction de part le numéro de la prochaine release"
        if last_release is None:
            last_release = self.get_current_release()
            msg = "CURRENT RELEASE: {major}.{minor}.{patch} at {time}"
            if 'date' in last_release:
                msg = "CURRENT RELEASE: {major}.{minor}.{patch}: {date} at {time}"
            print(msg.format(**last_release))
        self.__last_release_s = '{major}.{minor}.{patch}'.format(**last_release)
        to_zero = []
        tried = []
        for part in ['patch', 'minor', 'major']:
            next_release = dict(last_release)
            next_release[part] = last_release[part] + 1
            for sub_part in to_zero:
                next_release[sub_part] = 0
            to_zero.append(part)
            next_release_path = '{major}/{minor}/{patch}'.format(**next_release)
            next_release_s = self.get_release_s(next_release)
            tried.append(next_release_s)
            if os.path.exists('Patches/{}'.format(next_release_path)):
                print(f"NEXT RELEASE: {next_release_s}")
                self.__release = next_release
                self.__release_s = next_release_s
                self.__release_path = next_release_path
                return next_release
        print(f"No new release to apply after {self.__last_release_s}.")
        print(f"Next possible releases: {', '.join(tried)}.")
        return None

    def get_current_release(self):
        """Returns the current release (dict)
        """
        return next(self.model.get_relation_class('half_orm_meta.view.hop_last_release')().select())

    def get_release_s(cls, release):
        """Returns the current release (str)
        """
        return '{major}.{minor}.{patch}'.format(**release)

    def status(self):
        """Prints the status"""
        print('STATUS')
        print(self)
        next_release = self.get_next_release()
        while next_release:
            next_release = self.get_next_release(next_release)
        print('hop --help to get help.')

    @property
    def production(self):
        return self.__production

    @property
    def connection_file_name(self):
        "returns the connection file name"
        return self.__connection_file_name

    @property
    def package_name(self):
        "returns the package name"
        return self.__package_name

    @package_name.setter
    def package_name(self, package_name):
        self.__package_name = package_name

    @property
    def project_path(self):
        return self.__project_path

    @project_path.setter
    def project_path(self, project_path):
        if self.__project_path is None:
            self.__project_path = project_path

    @property
    def package_path(self):
        return f'{self.project_path}/{self.package_name}'

    @property
    def model(self):
        "model getter"
        if self.__model is None and self.__package_name:
            self.model = self.get_model()
        return self.__model

    @model.setter
    def model(self, model):
        "model setter"
        self.__model = model

    def alpha(self):
        """Toutes les modifs à faire durant la mise au point de hop
        """
        if not self.model.has_relation('half_orm_meta.hop_release'):
            if self.model.has_relation('meta.release'):
                click.echo(
                    "ALPHA: Renaming meta.release to half_orm_meta.hop_release, ...")
                self.model.execute_query("""
                create schema half_orm_meta;
                create schema "half_orm_meta.view";
                alter table meta.release set schema half_orm_meta;
                alter table meta.release_issue set schema half_orm_meta ;
                alter table half_orm_meta.release rename TO hop_release ;
                alter table half_orm_meta.release_issue rename TO hop_release_issue ;
                alter view "meta.view".last_release set schema "half_orm_meta.view" ;
                alter view "meta.view".penultimate_release set schema "half_orm_meta.view" ;
                alter view "half_orm_meta.view".last_release rename TO hop_last_release ;
                alter view "half_orm_meta.view".penultimate_release rename TO hop_penultimate_release ;
                """)
                click.echo("Please re-run the command.")
                sys.exit()
        # if not model.has_relation('half_orm_meta.view.hop_penultimate_release'):
        #     TODO: fix missing penultimate_release on some databases.
        return Model(self.package_name)

    def __str__(self):
        return f"""
        connection_file_name: {self.connection_file_name}
        package_name: {self.package_name}
        """

def hop_version():
    return open(f'{HOP_PATH}/version.txt').read().strip()

def get_connection_file_name(base_dir=None, ref_dir=None):
    """searches the hop configuration file for the package.
    This method is called when no hop config file is provided.
    It changes to the package base directory if the config file exists.
    """
    config = ConfigParser()

    cur_dir = base_dir
    if not base_dir:
        ref_dir = os.path.abspath(os.path.curdir)
        cur_dir = base_dir = ref_dir
    for base in ['hop', 'halfORM']:
        if os.path.exists('.{}/config'.format(base)):
            config.read('.{}/config'.format(base))
            config_file = config['halfORM']['config_file']
            package_name = config['halfORM']['package_name']
            return config_file, package_name, cur_dir

    if os.path.abspath(os.path.curdir) != '/':
        os.chdir('..')
        cur_dir = os.path.abspath(os.path.curdir)
        return get_connection_file_name(cur_dir, ref_dir)
    # restore reference directory.
    os.chdir(ref_dir)
    return None, None, None

def set_config_file(HOP, project_name: str):
    """ Asks for the connection parameters. Returns a dictionary with the params.
    """
    print(f'HALFORM_CONF_DIR: {CONF_DIR}')
    HOP.package_name = project_name
    conf_path = os.path.join(CONF_DIR, project_name)
    if not os.path.isfile(conf_path):
        if not os.access(CONF_DIR, os.W_OK):
            sys.stderr.write(f"You don't have write acces to {CONF_DIR}.\n")
            if CONF_DIR == '/etc/half_orm':
                sys.stderr.write(
                    "Set the HALFORM_CONF_DIR environment variable if you want to use a\n"
                    "different directory.\n")
            sys.exit(1)
        print('Connection parameters to the database:')
        dbname = input(f'. database name ({project_name}): ') or project_name
        user = os.environ['USER']
        user = input(f'. user ({user}): ') or user
        password = getpass('. password: ')
        if password == '' and \
                (input(
                    '. is it an ident login with a local account? [Y/n] ') or 'Y').upper() == 'Y':
            host = port = ''
        else:
            host = input('. host (localhost): ') or 'localhost'
            port = input('. port (5432): ') or 5432

        production = input('Production (False): ') or False

        res = {
            'name': dbname,
            'user': user,
            'password': password,
            'host': host,
            'port': port,
            'production': production
        }
        open(f'{CONF_DIR}/{project_name}',
             'w', encoding='utf-8').write(TMPL_CONF_FILE.format(**res))
    else:
        print(f"Using '{CONF_DIR}/{project_name}' file for connexion.")

    try:
        return Model(project_name)
    except psycopg2.OperationalError:
        config = ConfigParser()
        config.read([conf_path])
        dbname = config.get('database', 'name')

        sys.stderr.write(f"The database '{dbname}' does not exist.\n")
        create = input('Do you want to create it (Y/n): ') or "y"
        if create.upper() == 'Y':
            subprocess.run(['createdb', dbname], check=True)
            return Model(project_name)
        print(f'Please create the database an rerun hop new {project_name}')
        sys.exit(1)

def read_template(file_path):
    "helper"
    with open(file_path, encoding='utf-8') as file_:
        return file_.read()

def write_file(file_path, content):
    "helper"
    with open(file_path, 'w', encoding='utf-8') as file_:
        file_.write(content)

def init_package(HOP, project_name: str):
    """Initialises the package directory.

    HOP.model (Model): The loaded model instance
    project_name (str): The project name (hop create argument)
    """
    curdir = os.path.abspath(os.curdir)
    project_path = os.path.join(curdir, project_name)
    if not os.path.exists(project_path):
        os.makedirs(project_path)
    else:
        sys.stderr.write(f"ERROR! The path '{project_path}' already exists!\n")
        sys.exit(1)
    README = read_template(f'{TEMPLATES_DIR}/README')
    CONFIG_TEMPLATE = read_template(f'{TEMPLATES_DIR}/config')
    SETUP_TEMPLATE = read_template(f'{TEMPLATES_DIR}/setup.py')
    GIT_IGNORE = read_template(f'{TEMPLATES_DIR}/.gitignore')
    PIPFILE = read_template(f'{TEMPLATES_DIR}/Pipfile')

    dbname = HOP.model._dbname
    setup = SETUP_TEMPLATE.format(dbname=dbname, package_name=project_name)
    write_file(f'{project_path}/setup.py', setup)
    write_file(f'{project_path}/Pipfile', PIPFILE)
    os.mkdir(f'{project_path}/.hop')
    write_file(f'{project_path}/.hop/config',
        CONFIG_TEMPLATE.format(
            config_file=project_name, package_name=project_name))
    cmd = " ".join(sys.argv)
    readme = README.format(cmd=cmd, dbname=dbname, package_name=project_name)
    write_file(f'{project_path}/README.md', readme)
    write_file(f'{project_path}/.gitignore', GIT_IGNORE)
    os.mkdir(f'{project_path}/{project_name}')
    HOP.project_path = project_path
    HGit(HOP).init()
    print(f"\nThe hop project '{project_name}' has been created.")

