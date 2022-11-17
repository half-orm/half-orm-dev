import json
import os
import sys
import subprocess
from getpass import getpass
from configparser import ConfigParser

import click
import psycopg2

from half_orm.model import Model, CONF_DIR
from half_orm.model_errors import UnknownRelation, MissingConfigFile

from half_orm_packager.globals import HOP_PATH, TEMPLATES_DIR
from half_orm_packager.hgit import HGit
# from half_orm_packager.patch import Patch

TMPL_CONF_FILE = """
[database]
name = {name}
user = {user}
password = {password}
host = {host}
port = {port}
production = {production}
""" 

class Hop:
    "XXX: The hop class doc..."
    __connection_file_name = None
    __package_name = None
    __project_path = None
    __model = None
    __manifest = None
    __version = open(f'{HOP_PATH}/version.txt').read().strip()

    @property
    def version(self):
        return self.__version

    def __init__(self, ref_dir):
        # __release = self.get_next_possible_releases()
        self.__last_release_s = None
        Hop.__connection_file_name, Hop.__package_name, Hop.__project_path = get_connection_file_name(ref_dir=ref_dir)
        self.__production = False
        if self.__package_name and self.__model is None:
            self.__model = self.get_model()
            self.__production = self.__model.production
        self.__hgit = None
        try:
            self.__hgit = HGit(self)
        except TypeError:
            pass
        self.__params = {}
        if self.__model is not None:
            self.__params = self.__model._Model__dbinfo

    def read_params(self, conf_path):
        config = ConfigParser()
        config.read([conf_path])
        self.__params['name'] = config.get('database', 'name')
        self.__params['user'] = config.get('database', 'user')
        self.__params['password'] = config.get('database', 'password')
        self.__params['host'] = config.get('database', 'host')
        self.__params['port'] = config.get('database', 'port')


    def execute_pg_command(self, cmd, *args, **kwargs):
        self.__dbname = self.__params['name']
        self.__user = self.__params.get('user')
        self.__password = self.__params.get('password')
        self.__host = self.__params.get('host')
        self.__port = self.__params.get('port')
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
        cmd_list.append(self.__dbname)
        if len(args):
            cmd_list += args
        ret = subprocess.run(cmd_list, env=env, shell=False, **kwargs)
        if ret.returncode:
            sys.exit(ret.returncode)

    def abort(self):
        print('RESTORING', self.backup_path)
        self.model.disconnect()
        self.execute_pg_command('dropdb')
        self.execute_pg_command('createdb')
        self.execute_pg_command('psql', '-f', self.backup_path)
        # subprocess.run(['rm', svg_file])
        sys.exit(1)

    @property
    def backup_path(self) -> str:
        "Returns the absolute path of the backup file"
        return f"{self.project_path}/Backups/{self.__params['name']}-{self.last_release_s}.sql"


    def __get_last_release_s(self):
        return self.__last_release_s
    def __set_last_release_s(self, last_release_s):
        self.__last_release_s = last_release_s

    last_release_s = property(__get_last_release_s, __set_last_release_s)

    @property
    def patch_path(self):
        return f'{self.project_path}/Patches/{self.release_path}/'

    @property
    def release(self):
        return self.__release

    def __get_release_s(self):
        return self.__release['release_s']


    @property
    def manifest(self):
        if not Hop.__manifest:
            with open(os.path.join(self.patch_path, 'MANIFEST.json'), encoding='utf-8') as manifest:
                Hop.__manifest = json.load(manifest)
        return Hop.__manifest

    @property
    def changelog(self):
        return self.manifest['changelog_msg']

    def __set_release_s(self, release_s):
        self.__release['release_s'] = release_s

    release_s = property(__get_release_s, __set_release_s)

    @property
    def release_path(self):
        return self.__hgit.get_patch_path

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

    def get_next_possible_releases(self, last_release, show):
        "Returns the next possible releases regarding the current db release"
        patch_types = ['patch', 'minor', 'major']
        to_zero = []
        tried = []
        for part in patch_types:
            next_release = dict(last_release)
            next_release[part] = last_release[part] + 1
            for sub_part in to_zero:
                next_release[sub_part] = 0
            next_release['release_s'] = self.get_release_s(next_release)
            next_release['path'] = next_release['release_s'].replace('.', '/')
            to_zero.append(part)
            tried.append(next_release)
        if show and not self.__production and str(self.__hgit.branch) == 'hop_main':
            print(f"Prepare a new patch:")
            idx = 0
            for release in tried:
                print(f"* hop patch -p {patch_types[idx]} -> {release['release_s']}")
                idx += 1
            print("* (TODO) hop patch -p <major>.<minor>")
        return tried

    def get_next_release(self, last_release=None, show=False):
        "Renvoie en fonction de part le numéro de la prochaine release"
        if self.get_current_db_release() is None:
            return None
        if last_release is None:
            last_release = self.get_current_db_release()
            # msg = "CURRENT DB RELEASE: {major}.{minor}.{patch}: {date} at {time}"
            # if show:
            #     print(msg.format(**last_release))
        self.__last_release_s = '{major}.{minor}.{patch}'.format(**last_release)
        to_zero = []
        tried = []
        for release in self.get_next_possible_releases(last_release, show):
            if os.path.exists('Patches/{}'.format(release['path'])):
                if show:
                    print(f"NEXT RELEASE: {release['release_s']}")
                self.__release = release
                return release
        return None

    def get_current_db_release(self):
        """Returns the current database release (dict)
        """
        try:
            return next(self.model.get_relation_class('half_orm_meta.view.hop_last_release')().select())
        except UnknownRelation:
            sys.stderr.write("WARNING! The database doesn't have the hop metadata!")
            return None

    def get_previous_release(self):
        "Returns the penultimate release"
        #pylint: disable=invalid-name
        if self.get_current_db_release() is None:
            return None
        Previous = self.model.get_relation_class(
            'half_orm_meta.view.hop_penultimate_release')
        try:
            return next(Previous().select())
        except StopIteration:
            Current = self.model.get_relation_class('half_orm_meta.view.hop_last_release')
            return next(Current().select())

    @classmethod
    def get_release_s(cls, release):
        """Returns the current release (str)
        """
        if release:
            return '{major}.{minor}.{patch}'.format(**release)

    def status(self, verbose=False):
        """Prints the status"""
        if verbose:
            print(self)
        if self.__production:
            next_release = self.get_next_release()
            while next_release:
                next_release = self.get_next_release(next_release)
        else:
            self.what_next()
        print('\nhop --help to get help.')

    def what_next(self):
        "Shows what are the next possible actions and how to do them."
        print("\nNext possible hop command(s):\n")
        if self.__hgit is None:
            self.__hgit = HGit(self)
        if self.__production:
            return
        else:
            if str(self.__hgit.branch) == 'hop_main':
                self.get_next_release(show=True)
            else:
                if self.git_branch_is_db_release():
                    print('hop patch -f: re-apply the patch.')
                    print('hop patch -r: revert the DB to the previous release.')
                    print('(TODO) hop patch -A: Abort. Remove the patch.')
                    print()
                    print('(TODO) hop commit: Git repo must be clean.')
                    print(f'            Reapplies commits on top of hop_main <=> git rebase {self.__hgit.branch} hop_main.')
                if self.git_branch_is_db_next_release():
                    print('hop patch [-f]: apply the patch.')
                    print('(TODO) hop patch -A: Abort. Remove the patch.')

    @property
    def current_db_release_s(self):
        return self.get_release_s(self.get_current_db_release())

    def git_branch_is_db_release(self):
        return f'hop_{self.current_db_release_s}' == str(self.__hgit.branch)

    def git_branch_is_db_next_release(self):
        return f'hop_{self.current_db_release_s}' < str(self.__hgit.branch)

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
        # if not self.model.has_relation('half_orm_meta.database'):
        #     self.model_execute_query()
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

    def init_package(self, project_name: str):
        """Initialises the package directory.

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

        dbname = self.model._dbname
        import half_orm
        half_orm_version = half_orm.VERSION

        setup = SETUP_TEMPLATE.format(
                dbname=dbname,
                package_name=project_name,
                half_orm_version=half_orm_version)
        write_file(f'{project_path}/setup.py', setup)

        PIPFILE = PIPFILE.format(
                half_orm_version=half_orm_version)
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
        self.project_path = project_path
        HGit(self).init()

        print(f"\nThe hop project '{project_name}' has been created.")

    def __str__(self):
        commit_message = self.__hgit.commit.message.strip().split('\n')[0]
        return f"""Production: {self.__production}

        Package name: {self.package_name}
        Project path: {self.project_path}
        DB connection file: {CONF_DIR}/{self.connection_file_name}
        DB release: {self.current_db_release_s}

        GIT branch: {self.__hgit.branch}
        GIT last commit: 
        -  {self.__hgit.commit.author}. {self.__hgit.commit.committed_datetime.strftime("%A, %d. %B %Y %I:%M%p")}
        -  #{self.__hgit.commit.hexsha[:8]}: {commit_message}

        hop path: {HOP_PATH}
        hop version: {self.__version}"""

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
            HOP.read_params(conf_path)
            HOP.execute_pg_command('createdb')
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
