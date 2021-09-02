#!/usr/bin/env python3
#-*- coding: utf-8 -*-
# pylint: disable=invalid-name, protected-access

"""
Generates/Patches/Synchronizes a hop Python package with a PostgreSQL database
using the `hop` command.

Initiate a new project and repository with the `hop new <project_name>` command.
The <project_name> directory should not exist when using this command.

In the <project name> directory generated, the hop command helps you patch your
model, keep your Python synced with the PostgreSQL model, test your Python code and
deal with CI.

TODO:
On the 'devel' or any private branch hop applies patches if any, runs tests.
On the 'main' or 'master' branch, hop checks that your git repo is in sync with
the remote origin, synchronizes with devel branch if needed and tags your git
history with the last release applied.
"""

import os
import subprocess
import sys
from getpass import getpass
from configparser import ConfigParser

import click
import psycopg2

from half_orm.model import Model, CONF_DIR
from half_orm.model_errors import MissingConfigFile

from half_orm_packager.globals import TEMPLATES_DIR, get_connection_file_name, hop_version
from half_orm_packager.patch import Patch
from half_orm_packager.test import tests

class Hop:
    connection_file_name, package_name = get_connection_file_name()

    def alpha(self, model):
        """Toutes les modifs à faire durant la mise au point de hop
        """
        if not model.has_relation('half_orm_meta.hop_release'):
            try:
                model.get_relation_class('meta.release')
                model.get_relation_class('meta.release_issue')
                model.get_relation_class('meta.view.last_release')
                model.get_relation_class('meta.view.penultimate_release')
                click.echo("ALPHA: Renaming meta.release to half_orm_meta.hop_release, ...")
                model.execute_query("""
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
            except Exception as err:
                print('ALPHA ERR', err)
                pass
        # if not model.has_relation('half_orm_meta.view.hop_penultimate_release'):
        #     TODO: fix missing penultimate_release on some databases.
        return Model(HOP.package_name)


    def __str__(self):
        return f"""
        connection_file_name: {self.connection_file_name}
        package_name: {self.package_name}
        """

HOP = Hop()
# print(HOP)

BASE_DIR = os.getcwd()

TMPL_CONF_FILE = """[database]
name = {name}
user = {user}
password = {password}
host = {host}
port = {port}
production = {production}
"""

def status():
    print('STATUS')
    model = get_model()
    next_release = Patch(model).get_next_release()
    while next_release:
        next_release = Patch(model).get_next_release(next_release)
    print('hop --help to get help.')

def init_package(model, project_name: str):
    """Initialises the package directory.

    model (Model): The loaded model instance
    project_name (str): The project name (hop create argument)
    """
    from git import Repo, GitCommandError

    curdir = os.path.abspath(os.curdir)
    os.chdir(TEMPLATES_DIR)
    README = open('README').read()
    CONFIG_TEMPLATE = open('config').read()
    SETUP_TEMPLATE = open('setup.py').read()
    GIT_IGNORE = open('.gitignore').read()
    PIPFILE = open('Pipfile').read()
    project_path = os.path.join(curdir, project_name)
    if not os.path.exists(project_path):
        os.makedirs(project_path)
    else:
        raise Exception(f'The path {project_path} already exists')

    os.chdir(project_path)

    dbname = model._dbname
    setup = SETUP_TEMPLATE.format(dbname=dbname, package_name=project_name)
    open('./setup.py', 'w').write(setup)
    open('./Pipfile', 'w').write(PIPFILE)
    os.makedirs('./.hop')
    open(f'./.hop/config', 'w').write(
        CONFIG_TEMPLATE.format(
            config_file=project_name, package_name=project_name))
    cmd = " ".join(sys.argv)
    readme = README.format(cmd=cmd, dbname=dbname, package_name=project_name)
    open('./README.md', 'w').write(readme)
    open('./.gitignore', 'w').write(GIT_IGNORE)
    os.mkdir(f'./{project_name}')
    try:
        Repo.init('.', initial_branch='main')
        print("Initializing git with a 'main' branch.")
    except GitCommandError:
        Repo.init('.')
        print("Initializing git with a 'master' branch.")

    repo = Repo('.')
    Patch(model, create_mode=True).patch()
    model.reconnect() # we get the new stuff from db metadata here
    subprocess.run(['hop', 'update', '-f']) # hop creates/updates the modules & ignore tests

    try:
        repo.head.commit
    except ValueError:
        repo.git.add('.')
        repo.git.commit(m='[0.0.0] First release')

    print("Switching to the 'devel' branch.")
    repo.git.checkout(b='devel')

@property
def package_name(self):
    return self.__config.get('package_name')


def set_config_file(project_name: str):
    """ Asks for the connection parameters. Returns a dictionary with the params.
    """

    conf_path = os.path.join(CONF_DIR, project_name)
    if not os.path.isfile(conf_path):
        if not os.access(CONF_DIR, os.W_OK):
            sys.stderr.write(f"You don't have write acces to {CONF_DIR}.\n")
            if CONF_DIR == '/etc/half_orm':
                sys.stderr.write(
                    "Set the HALFORM_CONF_DIR environment variable if you want to use a\n"
                    "different directory.\n")
            sys.exit(1)
        dbname = input(f'Database ({project_name}): ') or project_name
        print(f'Input the connection parameters to the {dbname} database.')
        user = os.environ['USER']
        user = input(f'User ({user}): ') or user
        password = getpass('Password: ')
        if password == '' and \
            (input('Is it an ident login with a local account? [Y/n] ') or 'Y').upper() == 'Y':
                host = port = ''
        else:
            host = input('Host (localhost): ') or 'localhost'
            port = input('Port (5432): ') or 5432

        production = input('Production (False): ') or False

        res = {
            'name': dbname,
            'user': user,
            'password': password,
            'host': host,
            'port': port,
            'production': production
        }
        open(f'{CONF_DIR}/{project_name}', 'w').write(TMPL_CONF_FILE.format(**res))


    try:
        return Model(project_name)
    except psycopg2.OperationalError:
        config = ConfigParser()
        config.read([ conf_path ])
        dbname = config.get('database', 'name')

        sys.stderr.write(f'The {dbname} database does not exist.\n')
        create = input('Do you want to create it (Y/n): ') or "y"
        if create.upper() == 'Y':
            subprocess.run(['createdb', dbname])
            model = Model(project_name)
            return model
        sys.exit(1)

@click.group(invoke_without_command=True)
@click.pass_context
@click.option('-v', '--version', is_flag=True)
def main(ctx, version):
    """
    Generates/Synchronises/Patches a python package from a PostgreSQL database
    """
    if ctx.invoked_subcommand != 'new':
        get_model()

    if ctx.invoked_subcommand is None:
        try:
            status()
        except:
            pass
    if version:
        click.echo(f'hop {hop_version()}')
        sys.exit()

    sys.path.insert(0, '.')


@main.command()
@click.argument('package_name')
def new(package_name):
    """ Creates a new hop project named <package_name>.

    It adds to your database a patch system (by creating the relations:
    * half_orm_meta.hop_release
    * half_orm_meta.hop_release_issue
    and the views
    * "half_orm_meta.view".hop_last_release
    * "half_orm_meta.view".hop_penultimate_release
    """
    # click.echo(f'hop new {package_name}')
    # on cherche un fichier de conf .hop/config dans l'arbre.
    model = set_config_file(package_name)

    init_package(model, package_name)


def get_model():

    # config_file, package_name = get_connection_file_name()

    if not HOP.package_name:
        sys.stderr.write(
            "You're not in a halfORM package directory.\n"
            "Try hop --help.\n")
        sys.exit(1)

    try:
        model = Model(HOP.package_name)
        model = HOP.alpha(model) #XXX To remove after alpha
        return model
    except psycopg2.OperationalError as exc:
        sys.stderr.write(f'The database {HOP.package_name} does not exist.\n')
        raise exc
    except MissingConfigFile:
        sys.stderr.write(f'Cannot find the half_orm config file for this database.\n')
        sys.exit(1)


# @main.command()
def init():
    """ Initialize a cloned hop project by applying the base patch
    """
    try:
        model = get_model()
    except psycopg2.OperationalError as exc:
        # config_file, package_name = get_connection_file_name()
        model = set_config_file(HOP.package_name)

    Patch(model, init_mode=True).patch()
    sys.exit()


@main.command()
def patch():
    """ Applies the next patch.
    """

    model = get_model()
    Patch(model).patch()


    sys.exit()


@main.command()
@click.option('-f', '--force', is_flag=True, help='Updates the package without testing')
def update(force):
    """Updates the Python code with the changes made to the model.
    """
    from half_orm_packager.update import update_modules
    model = get_model()
    if force or tests(model, Hop.package_name):
        update_modules(model, Hop.package_name)
    else:
        print("\nPlease correct the errors before proceeding!")
        sys.exit(1)


@main.command()
def test():
    """ Tests some common pitfalls.
    """
    model = get_model()
    if tests(model, Hop.package_name):
        click.echo('Tests OK')
    else:
        click.echo('Tests failed')


if __name__ == '__main__':
    main(obj={})
