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

import importlib
import inspect
import os
import re
import shutil
import sys
import time
import re as _re
from keyword import iskeyword
from pathlib import Path
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
HO_DATACLASSES = []
HO_DATACLASSES_IMPORTS = set()
HO_TYPEDICTS: list = []
HO_TYPEDICTS_IMPORTS: set = set()
INIT_MODULE_TEMPLATE = read_template('init_module_template')
MODULE_TEMPLATE_1 = read_template('module_template_1')
MODULE_TEMPLATE_2 = read_template('module_template_2')
MODULE_TEMPLATE_3 = read_template('module_template_3')
WARNING_TEMPLATE = read_template('warning')
CONFTEST = read_template('conftest_template')
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
CONFTEST_PY = 'conftest.py'
DO_NOT_REMOVE = [INIT_PY]
TEST_PREFIX = 'test_'
TEST_SUFFIX = '.py'

MODEL = None


def _to_valid_identifier(name: str) -> str:
    """Return a valid Python identifier from a PostgreSQL relation/schema name.

    Rules applied in order:
    - Non-alphanumeric characters (except '_') → replaced by '_'
    - Starts with a digit → prefixed with '_'
    - Python keyword → suffixed with '_'
    """
    sanitized = _re.sub(r'[^a-zA-Z0-9_]', '_', name)
    if sanitized and sanitized[0].isdigit():
        sanitized = f'_{sanitized}'
    if iskeyword(sanitized):
        sanitized = f'{sanitized}_'
    return sanitized


def __get_test_directory_path(schema_name, table_name, base_dir):
    """
    Calculate the test directory path for a given schema and table.

    Args:
        schema_name: PostgreSQL schema name (e.g., 'public')
        table_name: PostgreSQL table name (e.g., 'user_profiles')
        base_dir: Project base directory path

    Returns:
        Path: tests/schema_name/table_name/

    Example:
        __get_test_directory_path('public', 'user_profiles', '/path/to/project')
        # Returns: Path('/path/to/project/tests/public/user_profiles')
    """
    base_path = Path(base_dir)
    tests_dir = base_path / 'tests'

    # Convert schema name: dots to underscores, keep original underscores
    schema_dir_name = schema_name.replace('.', '_')

    # Table name: keep underscores as-is
    table_dir_name = table_name

    return tests_dir / schema_dir_name / table_dir_name


def __get_test_file_path(schema_name, table_name, base_dir, package_name):
    """
    Calculate the complete test file path for a given schema and table.

    Args:
        schema_name: PostgreSQL schema name (e.g., 'public')
        table_name: PostgreSQL table name (e.g., 'user_profiles')
        base_dir: Project base directory path
        package_name: Python package name

    Returns:
        Path: Complete path to test file

    Example:
        __get_test_file_path('public', 'user_profiles', '/path', 'mydb')
        # Returns: Path('/path/tests/public/user_profiles/test_public_user_profiles.py')
    """
    test_dir = __get_test_directory_path(schema_name, table_name, base_dir)

    # Convert schema and table names for filename
    schema_file_name = schema_name.replace('.', '_')
    table_file_name = table_name

    # Construct filename: test_<schema>_<table>.py
    test_filename = f"{TEST_PREFIX}{schema_file_name}_{table_file_name}{TEST_SUFFIX}"

    return test_dir / test_filename


def __get_full_class_name(schemaname, relationname):
    schemaname = ''.join([elt.capitalize() for elt in schemaname.split('.')])
    relationname = ''.join([elt.capitalize() for elt in relationname.split('_')])
    return f'{schemaname}{relationname}'


def __get_field_desc(field_name, field):
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


def __gen_dataclass(relation, fkeys):
    rel = relation()
    dc_name = relation._ho_dataclass_name()
    fields = []
    post_init = ['    def __post_init__(self):']
    for field_name, field in rel._ho_fields.items():
        fields.append(__get_field_desc(field_name, field))
        post_init.append(f'        self.{field_name}: Field = None')

    # Invert user-defined aliases: constraint_name → alias
    aliases = {constraint: alias for alias, constraint in fkeys.items() if alias != ''}
    for constraint_name, fkey in rel._ho_fkeys.items():
        if constraint_name in aliases:
            attr_name = aliases[constraint_name]
        elif constraint_name.startswith('_reverse_fkey_'):
            attr_name = 'rfk_' + constraint_name[len('_reverse_fkey_'):]
        else:
            attr_name = 'fk_' + constraint_name
        try:
            fk_fqrn = list(fkey()._t_fqrn)
            fdc_name = f'DC_{__get_full_class_name(fk_fqrn[1], fk_fqrn[2])}'
        except Exception:
            fdc_name = dc_name  # fallback: host class
        post_init.append(f"        self.{attr_name} = {fdc_name}")
    return '\n'.join([f'@dataclasses.dataclass\nclass {dc_name}(DC_Relation):'] + fields + post_init)


def __get_type_annotation(field) -> tuple:
    """Return (type_str, extra_imports) for a TypedDict field annotation.

    Array types (SQL prefix '_') map to List[T].
    """
    sql_type = field._metadata['fieldtype']
    is_array = sql_type.startswith('_')
    base_sql_type = sql_type[1:] if is_array else sql_type

    py_type = SQL_ADAPTER.get(base_sql_type)
    imports: set = set()

    if py_type is None or py_type is Any:
        type_str = 'Any'
    elif py_type.__module__ != 'builtins':
        imports.add(py_type.__module__)
        name = py_type.__name__ if hasattr(py_type, '__name__') else 'Any'
        type_str = f'{py_type.__module__}.{name}'
    else:
        type_str = py_type.__name__

    if is_array:
        return f'List[{type_str}]', imports
    return type_str, imports


def __json_scalar_type(sql_type_name: str) -> str:
    """Map a JSON schema scalar type name to a Python type string.

    Updates HO_TYPEDICTS_IMPORTS as needed.
    """
    py_type = SQL_ADAPTER.get(sql_type_name.lower())
    if py_type is None or py_type is Any:
        return 'Any'
    if py_type.__module__ != 'builtins':
        HO_TYPEDICTS_IMPORTS.add(py_type.__module__)
        name = py_type.__name__ if hasattr(py_type, '__name__') else 'Any'
        return f'{py_type.__module__}.{name}'
    return py_type.__name__


def __gen_json_typedicts(name_prefix: str, schema) -> tuple:
    """Recursively generate TypedDict classes from a Field.json_schema structure.

    Returns (class_strings, top_class_name).
    class_strings are in dependency order (nested classes before the class using them).

    YAML value conventions:
        scalar string  → SQL type name  (e.g. 'text', 'integer', 'uuid')
        [scalar]       → List[T]
        [dict]         → List[NestedDict]
        dict           → NestedDict
    """
    if not isinstance(schema, dict):
        return [], 'Any'

    classes = []
    fields = []

    for key, val in schema.items():
        if isinstance(val, str):
            type_str = __json_scalar_type(val)
            fields.append(f"    {key}: Optional[{type_str}]")
        elif isinstance(val, list) and len(val) == 1:
            item = val[0]
            if isinstance(item, str):
                inner = __json_scalar_type(item)
                fields.append(f"    {key}: Optional[List[{inner}]]")
            elif isinstance(item, dict):
                child_prefix = name_prefix + ''.join(w.capitalize() for w in key.split('_'))
                nested, child_name = __gen_json_typedicts(child_prefix, item)
                classes.extend(nested)
                fields.append(f"    {key}: Optional[List['{child_name}']]")
            else:
                fields.append(f"    {key}: Optional[Any]")
        elif isinstance(val, dict):
            child_prefix = name_prefix + ''.join(w.capitalize() for w in key.split('_'))
            nested, child_name = __gen_json_typedicts(child_prefix, val)
            classes.extend(nested)
            fields.append(f"    {key}: Optional['{child_name}']")
        else:
            fields.append(f"    {key}: Optional[Any]")

    class_name = f'{name_prefix}Dict'
    body = '\n'.join(fields) if fields else '    pass'
    classes.append(f'class {class_name}(TypedDict, total=False):\n{body}')
    return classes, class_name


def __gen_typedict(relation, fkeys) -> list:
    """Generate TypedDict class(es) for a relation.

    Returns a list of class strings: nested JSON TypedDicts first, then the main class.
    Only database columns are included — FK accessor attributes are not part of a row dict.
    json/jsonb fields with a json_schema generate nested TypedDict classes.
    """
    rel = relation()
    t_qrn = list(rel._t_fqrn)[1:]
    dict_class_name = f'{__get_full_class_name(*t_qrn)}Dict'

    extra_classes = []
    fields = []
    for field_name, field in rel._ho_fields.items():
        json_schema = getattr(field, 'json_schema', None)
        if json_schema is not None and isinstance(json_schema, dict):
            field_cc = ''.join(w.capitalize() for w in field_name.split('_'))
            json_classes, top_name = __gen_json_typedicts(
                f'{dict_class_name[:-4]}{field_cc}', json_schema
            )
            extra_classes.extend(json_classes)
            type_str = top_name
        else:
            type_str, imports = __get_type_annotation(field)
            HO_TYPEDICTS_IMPORTS.update(imports)
        line = f"    {field_name}: Optional[{type_str}]"
        error = utils.check_attribute_name(field_name)
        if error:
            line = f"# {line}  # FIX ME! {error}"
        fields.append(line)

    body = '\n'.join(fields) if fields else '    pass'
    main_class = f'class {dict_class_name}(TypedDict, total=False):\n{body}'
    return extra_classes + [main_class]


def __gen_typedicts(package_dir: str, package_name: str) -> None:
    with open(os.path.join(package_dir, "ho_typeddicts.py"), "w", encoding='utf-8') as file_:
        file_.write(f"# TypedDicts for {package_name}\n\n")
        file_.write("from __future__ import annotations\n")
        file_.write("from typing import TypedDict, Optional, List, Any\n")
        td_imports = sorted(HO_TYPEDICTS_IMPORTS)
        for mod in td_imports:
            file_.write(f"import {mod}\n")
        file_.write("\n")
        for td in HO_TYPEDICTS:
            file_.write(f"\n{td}\n")


def __get_modules_list(dir, files_list, files):
    all_ = []
    for file_ in files:
        if re.findall(SKIP, file_):
            continue
        path_ = os.path.join(dir, file_)
        if path_ not in files_list and file_ not in DO_NOT_REMOVE:
            if path_.find('__pycache__') == -1:
                # Warn user - file does not correspond to a relation in the database
                sys.stderr.write(f"WARNING: '{path_}' does not correspond to a relation. Removing.\n")
            os.remove(path_)
            continue
        if (re.findall('.py$', file_) and
                file_ != INIT_PY and
                file_ != '__pycache__'):
            all_.append(file_.replace('.py', ''))
    all_.sort()
    return all_


def __update_init_files(package_dir, files_list, warning):
    """Update __all__ lists in __init__ files.
    """
    for dir, _, files in os.walk(package_dir):
        if dir == package_dir:
            continue
        reldir = dir.replace(package_dir, '')
        if re.findall(SKIP, reldir):
            continue
        all_ = __get_modules_list(dir, files_list, files)
        dirs = next(os.walk(dir))[1]

        if len(all_) == 0 and dirs == ['__pycache__']:
            shutil.rmtree(dir)
        else:
            with open(os.path.join(dir, INIT_PY), 'w', encoding='utf-8') as init_file:
                init_file.write(f'"""{warning}"""\n\n')
                all_ = ",\n    ".join([f"'{elt}'" for elt in all_])
                init_file.write(f'__all__ = [\n    {all_}\n]\n')


def __get_inheritance_info(rel, package_name):
    """Returns inheritance informations for the rel relation.
    """
    inheritance_import_list = []
    inherited_classes_aliases_list = []
    for base in rel.__class__.__bases__:
        if base.__name__ != 'Relation' and hasattr(base, '_t_fqrn'):
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


def __get_fkeys(repo, class_name, module_path):
    """Read the Fkeys dict from the module file using AST, without importing.

    Importing via importlib requires the project package to be on sys.path,
    which is not guaranteed during `hop migrate`.  Parsing with ast reads
    directly from the file on disk regardless of installation state.
    """
    if not os.path.exists(module_path):
        return {}
    try:
        import ast
        source = utils.read(module_path)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for stmt in node.body:
                    if (isinstance(stmt, ast.Assign)
                            and len(stmt.targets) == 1
                            and isinstance(stmt.targets[0], ast.Name)
                            and stmt.targets[0].id == 'Fkeys'):
                        return ast.literal_eval(stmt.value)
    except Exception:
        pass
    return {}


def __apply_fkey_aliases_to_doc(documentation: str, rel, existing_fkeys: dict) -> str:
    """Replace the Fkeys block in the docstring using the developer's aliases.

    For each constraint already aliased in existing_fkeys the alias is preserved.
    New constraints (not yet aliased) fall back to the default rfk_/fk_ name.
    This prevents spurious diffs when generate() runs automatically on branches
    where the developer has already defined aliases.
    """
    import re
    if not rel._ho_fkeys:
        return documentation

    # Invert existing_fkeys: constraint_name → alias (skip empty aliases)
    aliases = {constraint: alias for alias, constraint in existing_fkeys.items() if alias}

    # documentation adds 4 spaces to each line from str(rel), so Fkeys = { is at 4 spaces
    lines = ["    Fkeys = {"]
    for constraint_name in rel._ho_fkeys:
        if constraint_name in aliases:
            key = aliases[constraint_name]
        elif constraint_name.startswith('_reverse_fkey_'):
            key = 'rfk_' + constraint_name[len('_reverse_fkey_'):]
        else:
            key = 'fk_' + constraint_name
        lines.append(f"        '{key}': '{constraint_name}',")
    lines.append("    }")
    new_block = '\n'.join(lines)

    return re.sub(
        r'    Fkeys = \{[^}]*\}',
        new_block,
        documentation,
        flags=re.DOTALL,
    )


def __assemble_module_template(module_path):
    """Construct the module after slicing it if it already exists."""
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


def __update_this_module(
        repo, relation, package_dir, package_name):
    """Updates the module and generates corresponding test file."""
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

    path = [_to_valid_identifier(elt).lower() if i >= 2 else elt for i, elt in enumerate(path)]
    class_name = camel_case(path[-1])
    if class_name and class_name[0].isdigit():
        class_name = f'_{class_name}'
    module_path = f"{os.path.join(*path)}.py"
    path_1 = os.path.join(*path[:-1])
    if not os.path.exists(path_1):
        os.makedirs(path_1)

    # Read user-defined Fkeys aliases (for docstring and dataclass generation).
    existing_fkeys = __get_fkeys(repo, class_name, module_path)

    module_template = __assemble_module_template(module_path)
    inheritance_import, inherited_classes = __get_inheritance_info(
        rel, package_name)

    t_qrn = list(rel._t_fqrn)[1:]
    dict_class_name = f'{__get_full_class_name(*t_qrn)}Dict'

    # Generate Python module
    with open(module_path, 'w', encoding='utf-8') as file_:
        documentation = "\n".join([line and f"    {line}" or "" for line in str(rel).split("\n")[1:]])
        documentation = __apply_fkey_aliases_to_doc(documentation, rel, existing_fkeys)
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
                dict_class_name=dict_class_name,
                fqtn=fqtn,
                kwargs=kwargs,
                arg_names=arg_names,
                warning=WARNING_TEMPLATE.format(package_name=package_name)))

    # Generate test file in tests/ directory structure
    schema_name = path[1].replace(os.sep, '.')  # Convert back to schema.name format
    table_name = path[-1]
    test_file_path = __get_test_file_path(schema_name, table_name, repo.base_dir, package_name)

    if not test_file_path.exists():
        # Create test directory structure
        test_file_path.parent.mkdir(parents=True, exist_ok=True)

        # Generate test file
        # Build module path from the transformed path (lowercased, valid identifiers)
        module_dotpath = '.'.join([package_name] + path[1].replace(os.sep, '.').split('.') + [path[-1]])
        with open(test_file_path, 'w', encoding='utf-8') as file_:
            file_.write(TEST.format(
                package_name=package_name,
                module=module_dotpath,
                class_name=class_name))

    HO_DATACLASSES.append(__gen_dataclass(rel, existing_fkeys))
    HO_TYPEDICTS.extend(__gen_typedict(rel, existing_fkeys))

    return module_path


def __reset_dataclasses(repo, package_dir):
    with open(os.path.join(package_dir, "ho_dataclasses.py"), "w", encoding='utf-8') as file_:
        for relation in repo.database.model._relations():
            t_qrn = relation[1][1:]
            if t_qrn[0].find('half_orm') == 0:
                continue
            file_.write(f'class DC_{__get_full_class_name(*t_qrn)}: ...\n')


_TYPING_NAMES = frozenset(('Any', 'Dict', 'Iterator', 'List', 'Optional', 'Tuple', 'Union'))


def __gen_dc_relation() -> tuple:
    """Introspect Relation to generate DC_Relation with signatures and docstrings.

    Returns (class_str, frozenset of typing names needed).
    """
    from half_orm.relation import Relation

    def _fmt_doc(doc: str) -> str:
        lines = doc.splitlines()
        if len(lines) == 1:
            return f'        """{doc}"""'
        parts = [f'        """{lines[0]}']
        for line in lines[1:]:
            parts.append(f'        {line}' if line.strip() else '')
        parts.append('        """')
        return '\n'.join(parts)

    method_blocks = []
    for name in sorted(dir(Relation)):
        if not name.startswith('ho_'):
            continue
        raw = inspect.getattr_static(Relation, name)
        is_classmethod = isinstance(raw, classmethod)
        underlying = raw.__func__ if isinstance(raw, (classmethod, staticmethod)) else raw
        if not callable(underlying):
            continue
        is_async = inspect.iscoroutinefunction(underlying)
        try:
            sig_str = str(inspect.signature(underlying))
        except (ValueError, TypeError):
            continue
        doc = inspect.getdoc(underlying)
        block = []
        if is_classmethod:
            block.append('    @classmethod')
        prefix = '    async def' if is_async else '    def'
        block.append(f'{prefix} {name}{sig_str}:')
        if doc:
            block.append(_fmt_doc(doc))
        block.append('        ...')
        method_blocks.append('\n'.join(block))

    full_body = '\n\n'.join(method_blocks)
    needed_typing = frozenset(t for t in _TYPING_NAMES if t in full_body)
    class_str = (
        'class DC_Relation:\n'
        '    # auto-generated by half-orm-dev — do not edit\n\n'
        + full_body + '\n'
    )
    return class_str, needed_typing


def __gen_dataclasses(package_dir, package_name):
    dc_relation_str, dc_typing = __gen_dc_relation()
    with open(os.path.join(package_dir, "ho_dataclasses.py"), "w", encoding='utf-8') as file_:
        file_.write(f"# DO NOT EDIT — auto-generated by half-orm-dev\n\n")
        file_.write("import dataclasses\n")
        file_.write("from half_orm.field import Field\n")
        if dc_typing:
            file_.write(f"from typing import {', '.join(sorted(dc_typing))}\n")
        for mod in sorted(HO_DATACLASSES_IMPORTS):
            file_.write(f"import {mod}\n")
        file_.write("\n\n")
        file_.write(dc_relation_str)
        for dc in HO_DATACLASSES:
            file_.write(f"\n\n{dc}\n")


def generate(repo):
    """Synchronize the modules with the structure of the relation in PG."""
    # Reset accumulators — allows safe repeated calls in the same process
    HO_DATACLASSES.clear()
    HO_DATACLASSES_IMPORTS.clear()
    HO_TYPEDICTS.clear()
    HO_TYPEDICTS_IMPORTS.clear()
    NO_APAPTER.clear()

    package_name = repo.name
    base_dir = Path(repo.base_dir)
    package_dir = base_dir / package_name
    files_list = []

    try:
        sql_adapter_module = importlib.import_module('.sql_adapter', package_name)
        SQL_ADAPTER.update(sql_adapter_module.SQL_ADAPTER)
    except ModuleNotFoundError as exc:
        package_dir.mkdir(parents=True, exist_ok=True)
        with open(package_dir / 'sql_adapter.py', "w", encoding='utf-8') as file_:
            file_.write(SQL_ADAPTER_TEMPLATE)
        sys.stderr.write(f"{exc}\n")
    except AttributeError as exc:
        sys.stderr.write(f"{exc}\n")

    repo.database.model.reconnect(reload=True)

    if not package_dir.exists():
        package_dir.mkdir(parents=True)

    __reset_dataclasses(repo, str(package_dir))

    # Generate package __init__.py
    with open(package_dir / INIT_PY, 'w', encoding='utf-8') as file_:
        file_.write(INIT_MODULE_TEMPLATE.format(package_name=package_name))

    # Generate tests/conftest.py instead of package/base_test.py
    tests_dir = base_dir / 'tests'
    tests_dir.mkdir(exist_ok=True)

    conftest_path = tests_dir / CONFTEST_PY
    if not conftest_path.exists():
        with open(conftest_path, 'w', encoding='utf-8') as file_:
            file_.write(CONFTEST.format(
                package_name=package_name,
                hop_release=hop_version()))

    warning = WARNING_TEMPLATE.format(package_name=package_name)

    # Generate modules for each relation
    for relation in repo.database.model._relations():
        module_path = __update_this_module(repo, relation, str(package_dir), package_name)
        if module_path:
            files_list.append(module_path)
            # Tests are no longer added to files_list (they live in tests/ directory)

    __gen_dataclasses(str(package_dir), package_name)
    __gen_typedicts(str(package_dir), package_name)

    if len(NO_APAPTER):
        print("MISSING ADAPTER FOR SQL TYPE")
        print(f"Add the following items to __SQL_ADAPTER in {package_dir / 'sql_adapter.py'}")
        for key in NO_APAPTER.keys():
            print(f"  '{key}': typing.Any,")

    __update_init_files(str(package_dir), files_list, warning)