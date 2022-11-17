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

from half_orm.pg_meta import camel_case, normalize_fqrn
from half_orm.model_errors import UnknownRelation

from half_orm_packager.globals import TEMPLATES_DIR, BEGIN_CODE, END_CODE

def read_template(file_name):
    "helper"
    with open(f'{TEMPLATES_DIR}/{file_name}', encoding='utf-8') as file_:
        return file_.read()

DB_CONNECTOR_TEMPLATE = read_template('db_connector.py')
MODULE_TEMPLATE_1 = read_template('module_template_1')
MODULE_TEMPLATE_2 = read_template('module_template_2')
MODULE_TEMPLATE_3 = read_template('module_template_3')
# FKEYS_PROPS = read_template('fkeys_properties')
WARNING_TEMPLATE = read_template('warning')
BASE_TEST = read_template('base_test')
TEST = read_template('relation_test')

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
    with open('setup.py', encoding='utf-8') as tmpl_setup_file:
        lines = []
        for line in tmpl_setup_file:
            if line.find('README.rst'):
                line = line.replace('README.rst', 'README.md')
            lines.append(line)
        with open('setup.py', 'w', encoding='utf-8') as setup_file:
            setup_file.write(''.join(lines))

def load_config_file(base_dir=None, ref_dir=None):
    """Try to retrieve the halfORM configuration file for the package.
    This method is called when no half_orm config file is provided.
    It changes to the package base directory if the config file exists.
    """
    config = ConfigParser()

    if not base_dir:
        ref_dir = os.path.abspath(os.path.curdir)
        base_dir = ref_dir
    # print(base_dir)
    for base in ['hop', 'halfORM']:
        if os.path.exists(f'.{base}/config'):
            config.read(f'.{base}/config')
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
        major, minor, release = list(match.group(0).split('.'))
        major = int(major)
        minor = int(minor)
        release = int(re.search(r'\d+', release).group(0))
    return (major, minor, release)

# def get_fkeys(rel):
#     """Generates FKEYS properties string.
#     """
#     fks = '\n    '.join([f"('', '{key}')," for key in rel._fkeys])
#     if fks:
#         return FKEYS_PROPS.format(fks)
#     return ''

def get_inheritance_info(rel, package_name):
    """Returns inheritance informations for the rel relation.
    """
    inheritance_import_list = []
    inherited_classes_aliases_list = []
    for base in rel.__class__.__bases__:
        if base.__name__ != 'Relation':
            inh_sfqrn = list(base._t_fqrn)
            inh_sfqrn[0] = package_name
            inh_cl_alias = f"{camel_case(inh_sfqrn[1])}{camel_case(inh_sfqrn[2])}"
            inh_cl_name = f"{camel_case(inh_sfqrn[2])}"
            from_import = f"from {'.'.join(inh_sfqrn)} import {inh_cl_name} as {inh_cl_alias}"
            inheritance_import_list.append(from_import)
            inherited_classes_aliases_list.append(inh_cl_alias)
    inheritance_import = "\n".join(inheritance_import_list)
    inherited_classes = ", ".join(inherited_classes_aliases_list)
    if inherited_classes.strip():
        inherited_classes = f"{inherited_classes}, "
    return inheritance_import, inherited_classes

def assemble_module_template(module_path):
    """Construct the module after slicing it if it already exists.
    """
    user_s_code = ""
    global_user_s_code = "\n"
    module_template = MODULE_FORMAT
    user_s_class_attr = ''
    if os.path.exists(module_path):
        with open(module_path, encoding='utf-8') as module_file:
            module_code = module_file.read()
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
        model, relation, package_dir, package_name, dirs_list):
    """Updates the module."""
    _, fqtn = relation
    path = list(fqtn)
    if path[1].find('half_orm_meta') == 0:
        # hop internal. do nothing
        return None
    fqtn = '.'.join(path[1:])
    try:
        rel = model.get_relation_class(fqtn)()
    except (TypeError, UnknownRelation) as err:
        sys.stderr.write(f"{err}\n{fqtn}\n")
        sys.stderr.flush()
        return None

    path[0] = package_dir
    path[1] = path[1].replace('.', '/')

    module_path = f"{'/'.join([iskeyword(elt) and f'{elt}_' or elt for elt in path])}.py"
    if not os.path.dirname(module_path) in dirs_list:
        dirs_list.append(os.path.dirname(module_path))
    if not os.path.exists('/'.join(path[:-1])):
        os.makedirs('/'.join(path[:-1]))
    module_template = assemble_module_template(module_path)
    inheritance_import, inherited_classes = get_inheritance_info(
        rel, package_name)
    with open(module_path, 'w', encoding='utf-8') as file_:
        documentation = "\n".join([line and f"    {line}" or "" for line in str(rel).split("\n")])
        file_.write(
            module_template.format(
                hop_release = self.__hop_cls.version,
                module=f"{package_name}.{fqtn}",
                # fkeys_properties=get_fkeys(rel),
                package_name=package_name,
                documentation=documentation,
                inheritance_import=inheritance_import,
                inherited_classes=inherited_classes,
                class_name=camel_case(path[-1]),
                fqtn=fqtn,
                warning=WARNING_TEMPLATE.format(package_name=package_name)))
    if not os.path.exists(module_path.replace('.py', '_test.py')):
        with open(module_path.replace('.py', '_test.py'), 'w', encoding='utf-8') as file_:
            file_.write(TEST.format(
                package_name=package_name,
                module=f"{package_name}.{fqtn}",
                class_name=camel_case(path[-1]))
            )
    return module_path

def update_modules(model, package_name, release):
    """Synchronize the modules with the structure of the relation in PG.
    """
    dirs_list = []
    files_list = []

    model._reload()
    dbname = model._dbname
    package_dir = package_name
    with open(f'{package_dir}/db_connector.py', 'w', encoding='utf-8') as file_:
        file_.write(DB_CONNECTOR_TEMPLATE.format(dbname=dbname, package_name=package_name))

    if not os.path.exists(f'{package_dir}/base_test.py'):
        with open(f'{package_dir}/base_test.py', 'w', encoding='utf-8') as file_:
            file_.write(BASE_TEST.format(package_name=package_name))

    warning = WARNING_TEMPLATE.format(package_name=package_name)
    for relation in model._relations():
        module_path = update_this_module(model, relation, package_dir, package_name, dirs_list)
        if module_path:
            files_list.append(module_path)
            if module_path.find('__init__.py') == -1:
                test_file_path = module_path.replace('.py', '_test.py')
                files_list.append(test_file_path)

    update_init_files(package_dir, files_list, warning, release)

def update_init_files(package_dir, files_list, warning, release):
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
            path_ = f"{root}/{file}"
            if path_ not in files_list and file not in DO_NOT_REMOVE:
                if path_.find('__pycache__') == -1 and path_.find('_test.py') == -1:
                    print(f"REMOVING: {path_}")
                os.remove(path_)
                continue
            if (re.findall('.py$', file) and
                    file != '__init__.py' and
                    file != '__pycache__' and
                    file.find('_test.py') == -1):
                all_.append(file.replace('.py', ''))
        all_.sort()
        with open(f'{root}/__init__.py', 'w', encoding='utf-8') as init_file:
            init_file.write(f'"""{warning}"""\n\n')

            all_ = ",\n    ".join([f"'{elt}'" for elt in all_])
            init_file.write(f'__all__ = [\n    {all_}\n]\n')

    with open(os.path.join(package_dir, 'version.txt'), 'w') as fh:
        fh.write(release)
