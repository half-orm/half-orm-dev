#!/usr/bin/env python3
#-*- coding: utf-8 -*-
# pylint: disable=invalid-name, protected-access

"""
Generates/Patches/Synchronizes a hop Python package with a PostgreSQL database
with the `hop` command.

Initiate a new project and repository with the `hop create <project_name>` command.
The <project_name> directory should not exist when using this command.

In the dbname directory generated, the hop command helps you patch, test and
deal with CI.

TODO:
On the 'devel' or any private branch hop applies patches if any, runs tests.
On the 'main' or 'master' branch, hop checks that your git repo is in sync with
the remote origin, synchronizes with devel branch if needed and tags your git
history with the last release applied.
"""

import re
import os
import sys
from keyword import iskeyword
from configparser import ConfigParser

from half_orm.model import camel_case

from half_orm_packager.globals import TEMPLATES_DIR, hop_version

BASE_DIR = os.getcwd()

TMPL_CONF_FILE = """[database]
name = {name}
user = {user}
password = {password}
host = {host}
port = {port}
production = {production}
"""

HALFORM_PATH = os.path.dirname(__file__)
BEGIN_CODE = "#>>> PLACE YOUR CODE BELLOW THIS LINE. DO NOT REMOVE THIS LINE!\n"
END_CODE = "#<<< PLACE YOUR CODE ABOVE THIS LINE. DO NOT REMOVE THIS LINE!\n"

os.chdir(TEMPLATES_DIR)
DB_CONNECTOR_TEMPLATE = open('db_connector.py').read()
MODULE_TEMPLATE_1 = open('module_template_1').read()
MODULE_TEMPLATE_2 = open('module_template_2').read()
MODULE_TEMPLATE_3 = open('module_template_3').read()
FKEYS_PROPS = open('fkeys_properties').read()
WARNING_TEMPLATE = open('warning').read()
BASE_TEST = open('base_test').read()
TEST = open('relation_test').read()
os.chdir(BASE_DIR)

HOP_RELEASE_RE = re.compile("(?<=^# hop release: ).*$")

MODULE_FORMAT = (
    "{rt1}" +
    "{bc_}{global_user_s_code}{ec_}" +
    "{rt2}" +
    "    {bc_}{user_s_class_attr}\n    {ec_}" +
    "{rt3}\n        " +
    "{bc_}{user_s_code}")
AP_EPILOG = """"""
DO_NOT_REMOVE = ['db_connector.py', '__init__.py', 'base_test.py']

MODEL = None

def hop_update():
    """Rename some files an directories. hop upgrade.
    """
    if os.path.exists('.halfORM'):
        os.rename('.halfORM', '.hop')
        sys.stderr.write('WARNING! Renaming .halfORM to .hop.')
    if os.path.exists('README.rst'):
        os.rename('README.rst', 'README.md')
    lines = []
    with open('setup.py') as setup_file:
        for line in setup_file:
            if line.find('README.rst'):
                line = line.replace('README.rst', 'README.md')
            lines.append(line)
    open('setup.py', 'w').write(''.join(lines))

def load_config_file(base_dir=None, ref_dir=None):
    """Try to retrieve the halfORM configuration file for the package.
    This method is called when no half_orm config file is provided.
    It changes to the package base directory if the config file exists.
    """
    config = ConfigParser()

    if not base_dir:
        ref_dir = os.path.abspath(os.path.curdir)
        base_dir = ref_dir
    print(base_dir)
    for base in ['hop', 'halfORM']:
        if os.path.exists('.{}/config'.format(base)):
            config.read('.{}/config'.format(base))
            config_file = config['halfORM']['config_file']
            return config_file

    if os.path.abspath(os.path.curdir) != '/':
        os.chdir('..')
        cur_dir = os.path.abspath(os.path.curdir)
        return load_config_file(cur_dir, ref_dir)
    # restore reference directory.
    os.chdir(ref_dir)
    return None

def get_hop_version(template1):
    """ Returns the release number of hop module (major, minor, release)
    """
    line = template1.split('\n')[0]
    match = re.search(HOP_RELEASE_RE, line)
    major = minor = release = 0
    if match:
        major, minor, release = [val for val in match.group(0).split('.')]
        major = int(major)
        minor = int(minor)
        release = int(re.search('\d+', release).group(0))
    return (major, minor, release)

def get_fkeys(rel):
    """
    """
    fks = '\n    '.join([f"('', '{key}')," for key in rel._fkeys])
    if fks:
        return FKEYS_PROPS.format(fks)
    return ''

def get_inheritance_info(rel, package_name):
    """Returns inheritance informations for the rel relation.
    """
    inheritance_import_list = []
    inherited_classes_aliases_list = []
    for base in rel.__class__.__bases__:
        if base.__name__ != 'Relation':
            inh_sfqrn = list(base.__sfqrn)
            inh_sfqrn[0] = package_name
            inh_cl_alias = "{}{}".format(
                camel_case(inh_sfqrn[1]), camel_case(inh_sfqrn[2]))
            inh_cl_name = "{}".format(camel_case(inh_sfqrn[2]))
            inheritance_import_list.append(
                "from {} import {} as {}".format(".".join(
                    inh_sfqrn), inh_cl_name, inh_cl_alias)
            )
            inherited_classes_aliases_list.append(inh_cl_alias)
    inheritance_import = "\n".join(inheritance_import_list)
    inherited_classes = ", ".join(inherited_classes_aliases_list)
    if inherited_classes.strip():
        inherited_classes = "{}, ".format(inherited_classes)
    return inheritance_import, inherited_classes

def assemble_module_template(module_path):
    """Construct the module after slicing it if it already exists.
    """
    user_s_code = ""
    global_user_s_code = "\n"
    module_template = MODULE_FORMAT
    user_s_class_attr = ''
    if os.path.exists(module_path):
        module_code = open(module_path).read()
        part1 = module_code.split(BEGIN_CODE)[0]
        user_s_code = module_code.rsplit(BEGIN_CODE, 1)[1]
        user_s_code = user_s_code.replace('{', '{{').replace('}', '}}')
        global_user_s_code = module_code.rsplit(END_CODE)[0].split(BEGIN_CODE)[1]
        global_user_s_code = global_user_s_code.replace('{', '{{').replace('}', '}}')
        if get_hop_version(part1) >= (0, 0, 2):
            user_s_class_attr = module_code.split(BEGIN_CODE)[2].split(END_CODE)[0]
            # remove last spaces
            user_s_class_attr = user_s_class_attr.rstrip()
            user_s_class_attr = user_s_class_attr.replace('{', '{{').replace('}', '}}')
    # else:
    #     print('mais ou est passé charlie')
    return module_template.format(
        rt1=MODULE_TEMPLATE_1, rt2=MODULE_TEMPLATE_2, rt3=MODULE_TEMPLATE_3,
        bc_=BEGIN_CODE, ec_=END_CODE,
        global_user_s_code=global_user_s_code,
        user_s_class_attr=user_s_class_attr,
        user_s_code=user_s_code)

def update_this_module(
        model, relation, package_dir, package_name, dirs_list, warning):
    """Updates the module."""
    _, fqtn = relation.split()
    path = fqtn.split('.')
    if path[1] == 'half_orm_meta':
        # hop internal. do nothing
        return
    fqtn = '.'.join(path[1:])
    try:
        rel = model.get_relation_class(fqtn)()
    except TypeError as err:
        sys.stderr.write("{}\n{}\n".format(err, fqtn))
        sys.stderr.flush()
        return

    path[0] = package_dir
    module_path = '{}.py'.format('/'.join(
        [iskeyword(elt) and "{}_".format(elt) or elt for elt in path]))
    schema_dir = os.path.dirname(module_path)
    if not schema_dir in dirs_list:
        dirs_list.append(schema_dir)
    module_name = path[-1]
    path = '/'.join(path[:-1])
    if not os.path.exists(path):
        os.makedirs(path)
    module_template = assemble_module_template(module_path)
    inheritance_import, inherited_classes = get_inheritance_info(
        rel, package_name)
    module = f"{package_name}.{fqtn}"
    open(module_path, 'w').write(
        module_template.format(
            hop_release = hop_version(),
            module=module,
            fkeys_properties=get_fkeys(rel),
            package_name=package_name,
            documentation="\n".join(["    {}".format(line)
                                    for line in str(rel).split("\n")]),
            inheritance_import=inheritance_import,
            inherited_classes=inherited_classes,
            class_name=camel_case(module_name),
            fqtn=fqtn,
            warning=warning))
    test_path = module_path.replace('.py', '_test.py')
    if not os.path.exists(test_path):
        open(test_path, 'w').write(
            TEST.format(
                package_name=package_name,
                module=module,
                class_name=camel_case(module_name))
        )
    return module_path

@property
def package_name(self):
    return self.__config.get('package_name')


def update_modules(model, package_name):
    """Synchronize the modules with the structure of the relation in PG.
    """
    dirs_list = []
    files_list = []

    dbname = model._dbname
    package_dir = package_name
    open(f'{package_dir}/db_connector.py', 'w').write(
        DB_CONNECTOR_TEMPLATE.format(dbname=dbname, package_name=package_name))

    if not os.path.exists(f'{package_dir}/base_test.py'):
        open(f'{package_dir}/base_test.py', 'w').write(
            BASE_TEST.format(package_name=package_name)
        )

    warning = WARNING_TEMPLATE.format(package_name=package_name)

    for relation in model._relations():
        module_path = update_this_module(
            model, relation, package_dir, package_name, dirs_list, warning)
        if module_path:
            files_list.append(module_path)
            if module_path.find('__init__.py') == -1:
                test_file_path = module_path.replace('.py', '_test.py')
                files_list.append(test_file_path)

    update_init_files(package_dir, files_list, warning)

def update_init_files(package_dir, files_list, warning):
    """Update __all__ lists in __init__ files.
    """
    exp = re.compile('/[A-Z]')
    for root, dirs, files in os.walk(package_dir):
        all_ = []
        if exp.search(root):
            continue

        for dir_ in dirs:
            if dir_ != '__pycache__':
                all_.append(dir_)
        for file in files:
            path_ = "{}/{}".format(root, file)
            if path_ not in files_list and file not in DO_NOT_REMOVE:
                if path_.find('__pycache__') == -1 and path_.find('_test.py') == -1:
                    print("REMOVING: {}".format(path_))
                os.remove(path_)
                continue
            if (re.findall('.py$', file) and
                    file != '__init__.py' and
                    file != '__pycache__' and
                    file.find('_test.py') == -1):
                all_.append(file.replace('.py', ''))
        all_.sort()
        with open('{}/__init__.py'.format(root), 'w') as init_file:
            init_file.write('"""{}"""\n\n'.format(warning))
            init_file.write(
                '__all__ = [\n    {}\n]\n'.format(",\n    ".join(
                    ["'{}'".format(elt) for elt in all_])))
