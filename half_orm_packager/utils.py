import sys

class Color:
    @staticmethod
    def red(text):
        return(f"\033[31m{text}\033[0m")
    @staticmethod
    def green(text):
        return(f"\033[32m{text}\033[0m")
    @staticmethod
    def blue(text):
        return(f"\033[34m{text}\033[0m")

if False:
    import json
    import os
    import sys
    import subprocess
    from getpass import getpass
    from configparser import ConfigParser

    import half_orm
    from half_orm.model import Model, CONF_DIR
    from half_orm.model_errors import UnknownRelation, MissingConfigFile

    from half_orm_packager.globals import HOP_PATH, TEMPLATES_DIR
    from half_orm_packager.hgit import HGit
    from half_orm_packager.conf import HopConf, DbConf
    from half_orm_packager.patch import Patch
    from half_orm.manifest import Manifest

    class Hop:
        raise NotImplemented
        "The Hop class"
        __available_cmds = []

        @property
        def version(self):
            return open(f'{HOP_PATH}/version.txt').read().strip()

        def __init__(self):
            self.__config: HopConf = None
            self.__db_conf: DbConf = DbConf()
            self.__model: Model = None
            self.__manifest = None
            self.__hgit: HGit = None
            self.__cur_dir = os.path.abspath(os.path.curdir)
            self.__hgit = None

            self.__check()
            if self.__is_hop_repo:
                self.__hgit = HGit(self)
                self.__db_conf = DbConf(self.__config.name)

        def __check(self):
            """Checks the status of the current dir.
            * is it a hop repo?
            * what are the next available commands?
            """
            # If we are not in a hop directory, only hop new is available.
            if not self.__is_hop_repo:
                Hop.__available_cmds = ['new']
            else:
                if not self.__db_conf.production:
                    Hop.__available_cmds = ['patch']
                else:
                    Hop.__available_cmds = ['upgrade']
                self.__check_version()

        def __check_version(self):
            if self.version != self.__config.hop_version:
                print(f'HOP VERSION MISMATCH!\n- hop: {self.version}\n- repo: {self.__config.hop_version}')
                self.__hop_upgrade()
                self.__config.hop_version = self.version
                self.__config.write()

        def __hop_upgrade(self):
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

        @property
        def available_cmds(self):
            return self.__available_cmds

        @property
        def __is_hop_repo(self):
            """Searches the hop configuration file for the package.
            This method is called when no hop config file is provided.
            It changes to the package base directory if the config file exists.

            Sets the __project_path and __config attributes

            Returns True if we are in a repo, False otherwise.
            """
            path_list = self.__cur_dir.split('/')
            idx = len(path_list)
            while idx > 0:
                base_dir = '/'.join(path_list[:idx]) or '/'
                if os.path.exists(f'{base_dir}/.hop/config'):
                    self.__project_path = base_dir
                    self.__config = HopConf(base_dir)
                    try:
                        self.__db_conf = DbConf(self.__config.name)
                    except Exception as err:
                        pass
                    return True
                idx -= 1
            return False

        def execute_pg_command(self, cmd, *args, **kwargs):
            self.__dbname = self.__db_conf.name
            self.__user = self.__db_conf.user
            self.__password = self.__db_conf.password
            self.__host = self.__db_conf.host
            self.__port = self.__db_conf.port
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
            self.__model.disconnect()
            self.execute_pg_command('dropdb')
            self.execute_pg_command('createdb')
            self.execute_pg_command('psql', '-f', self.backup_path)
            # subprocess.run(['rm', svg_file])
            sys.exit(1)

        @property
        def backup_path(self) -> str:
            "Returns the absolute path of the backup file"
            return f"{self.project_path}/Backups/{self.__db_conf.name}-{self.last_release_s}.sql"


        def __get_last_release_s(self):
            return self.__last_release_s
        def __set_last_release_s(self, last_release_s):
            self.__last_release_s = last_release_s

        last_release_s = property(__get_last_release_s, __set_last_release_s)

        @property
        def patch_path(self):
            if self.release_path is None:
                return None
            return f'{self.project_path}/Patches/{self.release_path}/'

        @property
        def release(self):
            return self.__release

        @property
        def release_s(self):
            return self.__release['release_s']
        @release_s.setter
        def release_s(self, release_s):
            self.__release['release_s'] = release_s

        @property
        def command(self):
            return self.__cmd
        @command.setter
        def command(self, cmd):
            self.__cmd = cmd

        @property
        def manifest(self):
            if not self.__manifest and self.__cmd != 'new' and self.patch_path:
                try:
                    Manifest(self).read()
                    with open(os.path.join(self.patch_path, 'MANIFEST.json'), encoding='utf-8') as manifest:
                        self.__manifest = json.load(manifest)
                except FileNotFoundError as err:
                    # transform CHANGELOG.md into MANIFEST.json
                    Manifest(self)
                    print(self.release_path)
                    print(self.release_s)
                    sys.exit(1)
            return self.__manifest

        @property
        def changelog(self):
            return self.manifest['changelog_msg']

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
            if show and not self.__db_conf.production and str(self.__hgit.branch) == 'hop_main':
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
            if 1:#try:
                return next(self.__model.get_relation_class('half_orm_meta.view.hop_last_release')().select())
            else:#except UnknownRelation:
                sys.stderr.write("WARNING! The database doesn't have the hop metadata!")
                return None

        def get_previous_release(self):
            "Returns the penultimate release"
            #pylint: disable=invalid-name
            if self.get_current_db_release() is None:
                return None
            Previous = self.__model.get_relation_class(
                'half_orm_meta.view.hop_penultimate_release')
            try:
                return next(Previous().select())
            except StopIteration:
                Current = self.__model.get_relation_class('half_orm_meta.view.hop_last_release')
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
            if self.__db_conf.production:
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
            if self.__db_conf.production:
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
            return self.__db_conf.production

        @property
        def config_file(self):
            "returns the connection file name"
            return self.__config_file

        @property
        def package_name(self):
            "returns the package name"
            return self.__config.name

        @package_name.setter
        def package_name(self, package_name):
            self.__config.name = package_name

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
            if self.__model is None and self.__config:
                self.__model = self.get_model()
            return self.__model

        @model.setter
        def model(self, model):
            "model setter"
            self.__model = model

        def init_package(self, project_name: str):
            """Initialises the package directory.

            project_name (str): The project name (hop create argument)
            """
            self.__package_name = project_name
            self.__set_config_file()
            project_path = f'{self.__cur_dir}/{project_name}'
            self.__project_path = project_path
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

            half_orm_version = half_orm.VERSION

            setup = SETUP_TEMPLATE.format(
                    dbname=self.__db_conf.name,
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
            self.__config = HopConf(project_path)
            self.__db_conf = DbConf(self.__config.name)

            cmd = " ".join(sys.argv)
            readme = README.format(cmd=cmd, dbname=self.__db_conf.name, package_name=project_name)
            write_file(f'{project_path}/README.md', readme)
            write_file(f'{project_path}/.gitignore', GIT_IGNORE)
            os.mkdir(f'{project_path}/{project_name}')
            self.project_path = project_path
            self.__hgit = HGit(self)

            print(f"\nThe hop project '{project_name}' has been created.")

        def __set_config_file(self):
            """ Asks for the connection parameters. Returns a dictionary with the params.
            """
            print(f'HALFORM_CONF_DIR: {CONF_DIR}')
            conf_path = os.path.join(CONF_DIR, self.__package_name)
            if not os.path.isfile(conf_path):
                if not os.access(CONF_DIR, os.W_OK):
                    sys.stderr.write(f"You don't have write access to {CONF_DIR}.\n")
                    if CONF_DIR == '/etc/half_orm':
                        sys.stderr.write(
                            "Set the HALFORM_CONF_DIR environment variable if you want to use a\n"
                            "different directory.\n")
                    sys.exit(1)
                print('Connection parameters to the database:')
                dbname = input(f'. database name ({self.__package_name}): ') or self.__package_name
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
                open(f'{CONF_DIR}/{self.__package_name}',
                    'w', encoding='utf-8').write(self.__db_conf.TMPL_CONF_FILE.format(**res))
            else:
                print(f"Using '{CONF_DIR}/{self.__package_name}' file for connexion.")

            try:
                self.__model = Model(self.__package_name)
            except psycopg2.OperationalError:
                config = ConfigParser()
                config.read([conf_path])
                dbname = config.get('database', 'name')

                sys.stderr.write(f"The database '{dbname}' does not exist.\n")
                create = input('Do you want to create it (Y/n): ') or "y"
                if create.upper() == 'Y':
                    self.__db_conf = DbConf(self.__package_name)
                    self.execute_pg_command('createdb')
                    self.__model = Model(self.__package_name)

        def __str__(self):
            return str(self.__available_cmds)
            commit_message = None
            if self.__hgit:
                commit_message = self.__hgit.commit.message.strip().split('\n')[0]
            ret = []
            ret.append(f"""Production: {self.__db_conf.production}

            Package name: {self.package_name}
            Project path: {self.project_path}
            DB connection file: {CONF_DIR}/{self.connection_file_name}
            """)
            try:
                ret.append(f"""DB release: {self.current_db_release_s}

            GIT branch: {self.__hgit.branch}
            GIT last commit: 
            -  {self.__hgit.commit.author}. {self.__hgit.commit.committed_datetime.strftime("%A, %d. %B %Y %I:%M%p")}
            -  #{self.__hgit.commit.hexsha[:8]}: {commit_message}
                """)
            except:
                pass
            ret.append(f"""hop path: {HOP_PATH}
            hop version: {self.__version}
            """)
            return ''.join(ret)

    def read_template(file_path):
        "helper"
        raise NotImplemented
        with open(file_path, encoding='utf-8') as file_:
            return file_.read()

    def write_file(file_path, content):
        "helper"
        raise NotImplemented
        with open(file_path, 'w', encoding='utf-8') as file_:
            file_.write(content)
