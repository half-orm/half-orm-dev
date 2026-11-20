"""
Unit tests for the deletion of modules that match no relation.

generate() drops any module in the package whose relation is absent from
the database. The database is not always a superset of the package: a
patch creating a table may not be applied on the current branch, or not
applied yet during `patch apply`. Deleting the module then also deletes
the business logic the developer wrote in it - so generate() stops,
before modifying anything, unless nothing can be lost.
"""
from pathlib import Path

import pytest
from unittest.mock import Mock

from half_orm import utils

import half_orm_dev.modules as _mod


def _generated_module(global_code='', class_attr='', body=''):
    """A module in the shape MODULE_FORMAT produces: three editable zones."""
    return (
        "import typing\n"
        + utils.BEGIN_CODE + global_code + utils.END_CODE
        + "\n\nclass Author:\n"
        + "    " + utils.BEGIN_CODE + class_attr + "    " + utils.END_CODE
        + "    def __init__(self):\n        super().__init__()\n        "
        + utils.BEGIN_CODE + body
    )


def _repo(tmp_path, package_dir, committed):
    repo = Mock()
    repo.base_dir = str(tmp_path)
    repo.hgit.file_is_committed.return_value = committed
    return repo


class TestModuleIsPristine:
    def test_generated_only_is_pristine(self, tmp_path):
        path = tmp_path / 'author.py'
        path.write_text(_generated_module())
        assert _mod._module_is_pristine(str(path)) is True

    def test_code_in_class_body_is_not_pristine(self, tmp_path):
        path = tmp_path / 'author.py'
        path.write_text(_generated_module(body="\n        def full_name(self): ...\n"))
        assert _mod._module_is_pristine(str(path)) is False

    def test_code_at_module_level_is_not_pristine(self, tmp_path):
        path = tmp_path / 'author.py'
        path.write_text(_generated_module(global_code="\nimport datetime\n"))
        assert _mod._module_is_pristine(str(path)) is False

    def test_class_attribute_is_not_pristine(self, tmp_path):
        path = tmp_path / 'author.py'
        path.write_text(_generated_module(class_attr="\n    Fkeys = {'a': 'b'}\n"))
        assert _mod._module_is_pristine(str(path)) is False

    def test_file_without_markers_is_not_pristine(self, tmp_path):
        """Nothing is known about it, so it is not ours to throw away."""
        path = tmp_path / 'helpers.py'
        path.write_text("def helper():\n    return 42\n")
        assert _mod._module_is_pristine(str(path)) is False


def _package(tmp_path):
    """A package with a schema directory, as generate() lays it out."""
    package_dir = tmp_path / 'mydb'
    (package_dir / 'public').mkdir(parents=True)
    (package_dir / '__init__.py').write_text('')
    (package_dir / 'public' / '__init__.py').write_text('')
    return package_dir


class TestObsoleteFiles:
    def test_modules_matching_no_relation(self, tmp_path):
        package_dir = _package(tmp_path)
        kept = package_dir / 'public' / 'post.py'
        gone = package_dir / 'public' / 'author.py'
        kept.write_text(_generated_module())
        gone.write_text(_generated_module())

        obsolete = _mod._obsolete_files(str(package_dir), {str(kept)})

        assert obsolete == [str(gone)]

    def test_init_files_byte_code_and_root_are_left_alone(self, tmp_path):
        package_dir = _package(tmp_path)
        (package_dir / 'public' / '__pycache__').mkdir()
        (package_dir / 'public' / '__pycache__' / 'author.cpython-314.pyc').write_text('')
        (package_dir / 'sql_adapter.py').write_text('')

        assert _mod._obsolete_files(str(package_dir), set()) == []


class TestCheckObsoleteModules:
    def _obsolete(self, tmp_path, content):
        package_dir = _package(tmp_path)
        path = package_dir / 'public' / 'author.py'
        path.write_text(content)
        return package_dir, path

    def test_pristine_module_can_be_deleted(self, tmp_path):
        package_dir, _ = self._obsolete(tmp_path, _generated_module())
        _mod._check_obsolete_modules(
            _repo(tmp_path, package_dir, committed=False), str(package_dir), set())

    def test_committed_developer_code_can_be_deleted(self, tmp_path):
        """git still has it, so deleting loses nothing."""
        package_dir, _ = self._obsolete(
            tmp_path, _generated_module(body="\n        def x(self): ...\n"))
        _mod._check_obsolete_modules(
            _repo(tmp_path, package_dir, committed=True), str(package_dir), set())

    def test_uncommitted_developer_code_stops_and_is_listed(self, tmp_path):
        package_dir, path = self._obsolete(
            tmp_path, _generated_module(body="\n        def full_name(self): ...\n"))

        with pytest.raises(_mod.UncommittedModulesError) as error:
            _mod._check_obsolete_modules(
                _repo(tmp_path, package_dir, committed=False), str(package_dir), set())

        assert error.value.modules == ['mydb/public/author.py']
        assert 'mydb/public/author.py' in str(error.value)
        assert 'commit the work' in str(error.value)
        assert path.exists(), "the check must not touch the file"

    def test_a_module_the_database_accounts_for_is_not_checked(self, tmp_path):
        package_dir, path = self._obsolete(
            tmp_path, _generated_module(body="\n        x = 1\n"))
        _mod._check_obsolete_modules(
            _repo(tmp_path, package_dir, committed=False), str(package_dir), {str(path)})

    def test_without_git_uncommitted_code_stops(self, tmp_path):
        """Unanswerable means keep: no repository is not a licence to delete."""
        package_dir, _ = self._obsolete(
            tmp_path, _generated_module(body="\n        x = 1\n"))
        repo = Mock()
        repo.base_dir = str(tmp_path)
        repo.hgit = None

        with pytest.raises(_mod.UncommittedModulesError):
            _mod._check_obsolete_modules(repo, str(package_dir), set())

    def test_git_failure_stops_rather_than_deletes(self, tmp_path):
        package_dir, _ = self._obsolete(
            tmp_path, _generated_module(body="\n        x = 1\n"))
        repo = Mock()
        repo.base_dir = str(tmp_path)
        repo.hgit.file_is_committed.side_effect = RuntimeError('git exploded')

        with pytest.raises(_mod.UncommittedModulesError):
            _mod._check_obsolete_modules(repo, str(package_dir), set())

    def test_a_hand_written_file_without_markers_stops(self, tmp_path):
        """Nothing is known about it, so it is not ours to throw away."""
        package_dir = _package(tmp_path)
        (package_dir / 'public' / 'helpers.py').write_text("def helper():\n    return 42\n")

        with pytest.raises(_mod.UncommittedModulesError) as error:
            _mod._check_obsolete_modules(
                _repo(tmp_path, package_dir, committed=False), str(package_dir), set())

        assert error.value.modules == ['mydb/public/helpers.py']
