#!/usr/bin/env python3
#-*- coding: utf-8 -*-
# pylint: disable=invalid-name, protected-access

"""
Generates/Patches/Synchronizes a hop Python package with a PostgreSQL database
with the `hop` command.

Enhanced with standard Python test structure for professional development workflow.
"""

import importlib
import os
import re
import shutil
import sys
import time
from keyword import iskeyword
from typing import Any

from half_orm.pg_meta import camel_case
from half_orm.model_errors import UnknownRelation
from half_orm.sql_adapter import SQL_ADAPTER

from half_orm import utils
from .utils import TEMPLATE_DIRS, hop_version

def read_template(file_name):
    "helper"
    with open(os.path.join(TEMPLATE_DIRS, file_name), encoding='utf-8') as file_:
        return file_.read()

NO_APAPTER = {}
HO_DATACLASSES = [
'''import dataclasses
from half_orm.relation import DC_Relation
from half_orm.field import Field''']
HO_DATACLASSES_IMPORTS = set()
INIT_MODULE_TEMPLATE = read_template('init_module_template')
MODULE_TEMPLATE_1 = read_template('module_template_1')
MODULE_TEMPLATE_2 = read_template('module_template_2')
MODULE_TEMPLATE_3 = read_template('module_template_3')
WARNING_TEMPLATE = read_template('warning')
BASE_TEST = read_template('base_test')
TEST = read_template('relation_test')
SQL_ADAPTER_TEMPLATE = read_template('sql_adapter')
SKIP = re.compile('[A-Z]')

MODULE_FORMAT = (
    "{rt1}" +
    "{bc_}{global_user_s_code}{ec_}" +
    "{rt2}" +
    "    {bc_}{user_s_class_attr}    {ec_}" +
    "{rt3}\n        " +
    "{bc_}{user_s_code}")
AP_EPILOG = """"""
INIT_PY = '__init__.py'
BASE_TEST_PY = 'base_test.py'
DO_NOT_REMOVE = [INIT_PY, BASE_TEST_PY]

MODEL = None

def _get_full_class_name(schemaname, relationname):
    schemaname = ''.join([elt.capitalize() for elt in schemaname.split('.')])
    relationname = ''.join([elt.capitalize() for elt in relationname.split('_')])
    return f'{schemaname}{relationname}'

def _get_field_desc(field_name, field):
    #TODO: REFACTOR
    sql_type = field._metadata['fieldtype']
    field_desc = SQL_ADAPTER.get(sql_type)
    if field_desc is None:
        if not NO_APAPTER.get(sql_type):
            NO_APAPTER[sql_type] = 0
        NO_APAPTER[sql_type] += 1
        field_desc = Any
    if field_desc.__module__ != 'builtins':
        HO_DATACLASSES_IMPORTS.add(field_desc.__module__)
        ext = 'Any'
        if hasattr(field_desc, '__name__'):
            ext = field_desc.__name__
        field_desc = f'{field_desc.__module__}.{ext}'
    else:
        field_desc = field_desc.__name__
    value = 'dataclasses.field(default=None)'
    if field._metadata['fieldtype'][0] == '_':
        value = 'dataclasses.field(default_factory=list)'
    field_desc = f'{field_desc} = {value}'
    field_desc = f"    {field_name}: {field_desc}"
    error = utils.check_attribute_name(field_name)
    if error:
        field_desc = f'# {field_desc} FIX ME! {error}'
    return field_desc

def _gen_dataclass(relation, fkeys):
    rel = relation()
    dc_name = relation._ho_dataclass_name()
    fields = []
    post_init = ['    def __post_init__(self):']
    for field_name, field in rel._ho_fields.items():
        fields.append(_get_field_desc(field_name, field))
        post_init.append(f'        self.{field_name}: Field = None')

    fkeys = {value:key for key, value in fkeys.items() if key != ''}
    for key, value in rel()._ho_fkeys.items():
        if key in fkeys:
            fkey_alias = fkeys[key]
            fdc_name = f'{value._FKey__relation._ho_dataclass_name()}'
            post_init.append(f"        self.{fkey_alias} = {fdc_name}")
    return '\n'.join([f'@dataclasses.dataclass\nclass {dc_name}(DC_Relation):'] + fields + post_init)

def _get_modules_list(dir, files_list, files):
    """
    Creates a list of Python modules to include in __all__ exports.
    
    Filters out system files and maintains clean module exports.
    Enhanced to work with the new test structure where tests are separate.
    """
    all_ = []
    for file_ in files:
        if re.findall(SKIP, file_):
            continue
        path_ = os.path.join(dir, file_)
        if path_ not in files_list and file_ not in DO_NOT_REMOVE:
            if path_.find('__pycache__') == -1:
                print(f"REMOVING: {path_}")
            os.remove(path_)
            continue
        # Include all Python files except __init__.py and __pycache__
        if (re.findall('.py$', file_) and
                file_ != INIT_PY and
                file_ != '__pycache__'):
            all_.append(file_.replace('.py', ''))
    all_.sort()
    return all_

def _update_init_files(package_dir, files_list, warning):
    """Update __all__ lists in __init__ files.
    """
    for dir, _, files in os.walk(package_dir):
        if dir == package_dir:
            continue
        reldir = dir.replace(package_dir, '')
        if re.findall(SKIP, reldir):
            continue
        all_ = _get_modules_list(dir, files_list, files)
        dirs = next(os.walk(dir))[1]

        if len(all_) == 0 and dirs == ['__pycache__']:
            shutil.rmtree(dir)
        else:
            with open(os.path.join(dir, INIT_PY), 'w', encoding='utf-8') as init_file:
                init_file.write(f'"""{warning}"""\n\n')
                all_ = ",\n    ".join([f"'{elt}'" for elt in all_])
                init_file.write(f'__all__ = [\n    {all_}\n]\n')

def _get_inheritance_info(rel, package_name):
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

def _get_fkeys(repo, class_name, module_path):
    try:
        mod_path = module_path.replace(repo.base_dir, '').replace(os.path.sep, '.')[1:-3]
        mod = importlib.import_module(mod_path)
        importlib.reload(mod)
        cls = mod.__dict__[class_name]
        fkeys = cls.__dict__.get('Fkeys', {})
        return fkeys
    except ModuleNotFoundError:
        pass
    return {}

def _assemble_module_template(module_path):
    """Construct the module after slicing it if it already exists.
    """
    ALT_BEGIN_CODE = "#>>> PLACE YOUR CODE BELLOW THIS LINE. DO NOT REMOVE THIS LINE!\n"
    user_s_code = ""
    global_user_s_code = "\n"
    module_template = MODULE_FORMAT
    user_s_class_attr = ''
    if os.path.exists(module_path):
        module_code = utils.read(module_path)
        if module_code.find(ALT_BEGIN_CODE) != -1:
            module_code = module_code.replace(ALT_BEGIN_CODE, utils.BEGIN_CODE)
        user_s_code = module_code.rsplit(utils.BEGIN_CODE, 1)[1]
        user_s_code = user_s_code.replace('{', '{{').replace('}', '}}')
        global_user_s_code = module_code.rsplit(utils.END_CODE)[0].split(utils.BEGIN_CODE)[1]
        global_user_s_code = global_user_s_code.replace('{', '{{').replace('}', '}}')
        user_s_class_attr = module_code.split(utils.BEGIN_CODE)[2].split(f'    {utils.END_CODE}')[0]
        user_s_class_attr = user_s_class_attr.replace('{', '{{').replace('}', '}}')
    return module_template.format(
        rt1=MODULE_TEMPLATE_1, rt2=MODULE_TEMPLATE_2, rt3=MODULE_TEMPLATE_3,
        bc_=utils.BEGIN_CODE, ec_=utils.END_CODE,
        global_user_s_code=global_user_s_code,
        user_s_class_attr=user_s_class_attr,
        user_s_code=user_s_code)

def _create_tests_directory(repo):
    """
    Creates the standard tests/ directory structure for Python projects.
    
    Creates:
    - tests/ root directory
    - tests/__init__.py for pytest discovery
    
    This follows Python testing best practices and enables automatic test discovery
    by pytest and other testing tools.
    
    Args:
        repo: Repository object containing project information
        
    Returns:
        str: Path to the created tests directory
    """
    tests_dir = os.path.join(repo.base_dir, 'tests')
    if not os.path.exists(tests_dir):
        os.makedirs(tests_dir)
        print(f"✅ Created tests directory: {tests_dir}")
    
    # Create __init__.py so pytest can discover tests
    init_file = os.path.join(tests_dir, '__init__.py')
    if not os.path.exists(init_file):
        with open(init_file, 'w', encoding='utf-8') as f:
            f.write('"""Tests for the halfORM project"""\n')
        print(f"✅ Created tests/__init__.py")
    
    return tests_dir

def _create_test_file(repo, module_name, class_name, fqtn, tests_dir):
    """
    Creates individual test files following Python testing conventions.
    
    Generates test files in a hierarchical structure:
    tests/database_name/schema_name/test_table_name.py
    
    This structure:
    - Prevents naming conflicts between tables in different schemas
    - Separates auto-generated tests from custom tests
    - Follows pytest discovery patterns
    - Maintains clear organization by database schema
    - Allows developers to add custom tests in tests/ root without conflicts
    
    Args:
        repo: Repository object containing project information
        module_name: Name of the database table/module
        class_name: Python class name for the table
        fqtn: Fully qualified table name (schema.table)
        tests_dir: Root tests directory path
        
    Returns:
        str: Path to the created test file
    """
    # Parse the fully qualified table name into components
    # Example: 'public.user_table' -> ['public', 'user_table']
    path_parts = fqtn.split('.')
    schema_name = path_parts[0]
    table_name = path_parts[1]
    
    # Create database-specific test directory: tests/database_name/
    # This isolates auto-generated tests from custom tests
    database_test_dir = os.path.join(tests_dir, repo.name)
    if not os.path.exists(database_test_dir):
        os.makedirs(database_test_dir)
        print(f"✅ Created database test directory: {database_test_dir}")
        
        # Create __init__.py for the database test package
        database_init_file = os.path.join(database_test_dir, '__init__.py')
        with open(database_init_file, 'w', encoding='utf-8') as f:
            f.write(f'"""Auto-generated tests for {repo.name} database"""\n')
    
    # Create schema-specific test directory: tests/database_name/schema_name/
    # This prevents conflicts between tables with same names in different schemas
    schema_test_dir = os.path.join(database_test_dir, schema_name)
    if not os.path.exists(schema_test_dir):
        os.makedirs(schema_test_dir)
        print(f"✅ Created schema test directory: {schema_test_dir}")
        
        # Create __init__.py for the schema test package
        schema_init_file = os.path.join(schema_test_dir, '__init__.py')
        with open(schema_init_file, 'w', encoding='utf-8') as f:
            f.write(f'"""Auto-generated tests for {repo.name}.{schema_name} schema"""\n')
    
    # Generate test file name following pytest conventions: test_*.py
    test_file_name = f'test_{table_name}.py'
    test_file_path = os.path.join(schema_test_dir, test_file_name)
    
    # Don't overwrite existing test files to preserve user customizations
    if os.path.exists(test_file_path):
        return test_file_path
    
    # Generate comprehensive test file template with user code sections
    test_content = f'''"""
Auto-generated tests for {repo.name}.{fqtn}

Generated automatically by halfORM.
These tests are regenerated on each 'half_orm dev apply'.
Place custom tests outside the {repo.name}/ directory.
"""
import pytest
from {repo.name}.{fqtn} import {class_name}

{utils.BEGIN_CODE}
# Place your additional imports here
{utils.END_CODE}

class Test{class_name}:
    """Auto-generated test class for {class_name}"""
    
    def test_instantiation(self):
        """Test basic instantiation"""
        obj = {class_name}()
        assert obj is not None
    
    def test_fields_access(self):
        """Test field access"""
        obj = {class_name}()
        # Add field-specific tests here
        pass
    
    {utils.BEGIN_CODE}
    # Place your additional test methods here
    def test_custom_behavior(self):
        """Add your custom tests here"""
        pass
    {utils.END_CODE}
'''
    
    # Write the test file
    with open(test_file_path, 'w', encoding='utf-8') as f:
        f.write(test_content)
    
    print(f"✅ Created test file: {test_file_path}")
    return test_file_path

def _update_this_module(repo, relation, package_dir, package_name):
    """
    Updates or creates a Python module for a database relation.
    
    Also generates corresponding test files in the standard test structure
    when in development mode.
    """
    _, fqtn = relation
    path = list(fqtn)
    if path[1].find('half_orm_meta') == 0:
        # hop internal. do nothing
        return None
    fqtn = '.'.join(path[1:])
    try:
        rel = repo.database.model.get_relation_class(fqtn)()
    except (TypeError, UnknownRelation) as err:
        sys.stderr.write(f"{err}\n{fqtn}\n")
        sys.stderr.flush()
        return None
    fields = []
    kwargs = []
    arg_names = []
    for key, value in rel._ho_fields.items():
        error = utils.check_attribute_name(key)
        if not error:
            fields.append(f"self.{key}: Field = None")
            kwarg_type = 'typing.Any'
            if hasattr(value.py_type, '__name__'):
                kwarg_type = str(value.py_type.__name__)
            kwargs.append(f"{key}: '{kwarg_type}'=None")
            arg_names.append(f'{key}={key}')
    fields = "\n        ".join(fields)
    kwargs.append('**kwargs')
    kwargs = ", ".join(kwargs)
    arg_names = ", ".join(arg_names)
    path[0] = package_dir
    path[1] = path[1].replace('.', os.sep)

    path = [iskeyword(elt) and f'{elt}_' or elt for elt in path]
    class_name = camel_case(path[-1])
    module_name = path[-1]  # Table name for test file generation
    module_path = f"{os.path.join(*path)}.py"
    path_1 = os.path.join(*path[:-1])
    if not os.path.exists(path_1):
        os.makedirs(path_1)
    module_template = _assemble_module_template(module_path)
    inheritance_import, inherited_classes = _get_inheritance_info(
        rel, package_name)
    with open(module_path, 'w', encoding='utf-8') as file_:
        documentation = "\n".join([line and f"    {line}" or "" for line in str(rel).split("\n")])
        file_.write(
            module_template.format(
                hop_release = hop_version(),
                module=f"{package_name}.{fqtn}",
                package_name=package_name,
                documentation=documentation,
                inheritance_import=inheritance_import,
                inherited_classes=inherited_classes,
                class_name=class_name,
                dc_name=rel._ho_dataclass_name(),
                fqtn=fqtn,
                kwargs=kwargs,
                arg_names=arg_names,
                warning=WARNING_TEMPLATE.format(package_name=package_name)))
    
    # Generate corresponding test file in development mode
    if repo.devel:
        tests_dir = _create_tests_directory(repo)
        test_file_path = _create_test_file(repo, module_name, class_name, fqtn, tests_dir)
    
    HO_DATACLASSES.append(_gen_dataclass(
        rel, _get_fkeys(repo, class_name, module_path)))
    return module_path

def _reset_dataclasses(repo, package_dir):
    with open(os.path.join(package_dir, "ho_dataclasses.py"), "w", encoding='utf-8') as file_:
        for relation in repo.database.model._relations():
            t_qrn = relation[1][1:]
            if t_qrn[0].find('half_orm') == 0:
                continue
            file_.write(f'class DC_{_get_full_class_name(*t_qrn)}: ...\n')

def _gen_dataclasses(package_dir, package_name):
    with open(os.path.join(package_dir, "ho_dataclasses.py"), "w", encoding='utf-8') as file_:
        file_.write(f"# dataclasses for {package_name}\n\n")
        hd_imports = list(HO_DATACLASSES_IMPORTS)
        hd_imports.sort()
        for to_import in hd_imports:
            file_.write(f"import {to_import}\n")
        file_.write("\n")
        for dc in HO_DATACLASSES:
            file_.write(f"\n{dc}\n")

def _create_pytest_config(repo):
    """
    Creates pytest configuration file with appropriate settings.
    
    Configures pytest to:
    - Discover tests recursively in tests/ directory
    - Follow Python testing conventions
    - Provide clear output formatting
    - Support both auto-generated and custom tests
    """
    pytest_ini_path = os.path.join(repo.base_dir, 'pytest.ini')
    if not os.path.exists(pytest_ini_path):
        pytest_config = f"""[tool:pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short
# Auto-generated tests are in tests/{repo.name}/
# Custom tests can be placed directly in tests/
collect_ignore = []
"""
        with open(pytest_ini_path, 'w', encoding='utf-8') as f:
            f.write(pytest_config)
        print(f"✅ Created pytest.ini configuration")

def _count_test_files_recursive(tests_dir):
    """
    Recursively counts all test files in the tests directory.
    
    Returns the total number of test_*.py files found at any depth
    in the tests directory structure.
    """
    count = 0
    for root, dirs, files in os.walk(tests_dir):
        for file in files:
            if file.startswith('test_') and file.endswith('.py'):
                count += 1
    return count

def generate(repo):
    """
    Synchronizes Python modules with PostgreSQL database structure.
    
    Enhanced to generate standard Python test structure alongside modules:
    - Creates tests/ directory following Python conventions
    - Generates test files with hierarchical organization
    - Separates auto-generated tests from custom tests
    - Configures pytest for automatic test discovery
    """
    package_name = repo.name
    package_dir = os.path.join(repo.base_dir, package_name)
    files_list = []
    try:
        sql_adapter_module = importlib.import_module('.sql_adapter', package_name)
        SQL_ADAPTER.update(sql_adapter_module.SQL_ADAPTER)
    except ModuleNotFoundError as exc:
        os.makedirs(package_dir, exist_ok=True)
        with open(os.path.join(package_dir, 'sql_adapter.py'), "w") as file_:
            file_.write(SQL_ADAPTER_TEMPLATE)
        sys.stderr.write(f"{exc}\n")
    except AttributeError as exc:
        sys.stderr.write(f"{exc}\n")
    repo.database.model._reload()
    if not os.path.exists(package_dir):
        os.mkdir(package_dir)

    _reset_dataclasses(repo, package_dir)

    with open(os.path.join(package_dir, INIT_PY), 'w', encoding='utf-8') as file_:
        file_.write(INIT_MODULE_TEMPLATE.format(package_name=package_name))

    if not os.path.exists(os.path.join(package_dir, BASE_TEST_PY)):
        with open(os.path.join(package_dir, BASE_TEST_PY), 'w', encoding='utf-8') as file_:
            file_.write(BASE_TEST.format(
                BEGIN_CODE=utils.BEGIN_CODE,
                END_CODE=utils.END_CODE,
                package_name=package_name))
    
    warning = WARNING_TEMPLATE.format(package_name=package_name)
    for relation in repo.database.model._relations():
        module_path = _update_this_module(repo, relation, package_dir, package_name)
        if module_path:
            files_list.append(module_path)

    _gen_dataclasses(package_dir, package_name)
    
    # Create pytest configuration in development mode
    if repo.devel:
        _create_pytest_config(repo)

    if len(NO_APAPTER):
        print("MISSING ADAPTER FOR SQL TYPE")
        print(f"Add the following items to __SQL_ADAPTER in {os.path.join(package_dir, 'sql_adapter.py')}")
        for key in NO_APAPTER.keys():
            print(f"  '{key}': typing.Any,")
    _update_init_files(package_dir, files_list, warning)
    
    # Display test generation summary in development mode
    if repo.devel:
        tests_dir = os.path.join(repo.base_dir, 'tests')
        if os.path.exists(tests_dir):
            test_count = _count_test_files_recursive(tests_dir)
            print(f"✅ Generated {test_count} auto-generated test files in tests/{repo.name}/ directory")
            print(f"💡 Custom tests can be placed directly in tests/ (outside {repo.name}/)")
            
            # Display test structure for verification
            print("Test structure:")
            for root, dirs, files in os.walk(tests_dir):
                level = root.replace(tests_dir, '').count(os.sep)
                indent = ' ' * 2 * level
                print(f"{indent}{os.path.basename(root) if root != tests_dir else 'tests'}/")
                sub_indent = ' ' * 2 * (level + 1)
                for file in files:
                    if file.startswith('test_') and file.endswith('.py'):
                        print(f"{sub_indent}{file}")
                    elif file == '__init__.py':
                        print(f"{sub_indent}{file}")