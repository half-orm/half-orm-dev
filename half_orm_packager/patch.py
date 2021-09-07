#!/usr/bin/env python3
#-*- coding: utf-8 -*-

"""Patche la base de donnée

Détermine le patch suivant et l'applique. Les patchs sont appliqués un
par un.

Si l'option -i <no de patch> est utilisée, le patch sera pris dans
Patches/devel/issues/<no de patch>.
Le numéro de patch dans la table half_orm_meta.hop_release sera 9999.9999.<no de patch>
L'option -i n'est pas utilisable si patch.yml positionne PRODUCTION à True.
"""

from datetime import date, datetime
import os
import shutil
import sys
import subprocess

import psycopg2
import pydash
from .hgit import HGit

class Patch:
    #TODO: docstring
    "class Patch"
    def __init__(self, hop_cls, create_mode=False, init_mode=False):
        self.__hop_cls = hop_cls
        self.__hgit = HGit(hop_cls)
        self.__create_mode = create_mode
        self.__init_mode = init_mode
        # self.__orig_dir = os.path.abspath('.')
        self.__module_dir = os.path.dirname(__file__)
        self.__last_release_s = None
        self.__release = None
        self.__release_s = ''
        self.__release_path = None

    @property
    def model(self):
        "halfORM model property"
        return self.__hop_cls.model

    @property
    def dbname(self):
        "database name property"
        return self.model._dbname

    @property
    def package_name(self):
        "package name property"
        return self.__hop_cls.package_name

    @property
    def __patch_path(self):
        return f'{self.__hop_cls.project_path}/Patches/{self.__release_path}/'

    def __get_backup_file_name(self, release):
        release_s = self.get_release_s(release)
        return f'{self.__hop_cls.project_path}/Backups/{self.dbname}-{release_s}.sql'

    @property
    def changelog(self):
        with open(os.path.join(self.__patch_path, 'CHANGELOG.md'), encoding='utf-8') as changelog:
            return changelog.read()

    def __get_previous_release(self):
        "Returns the penultimate release"
        #pylint: disable=invalid-name
        Previous = self.__hop_cls.model.get_relation_class(
            'half_orm_meta.view.hop_penultimate_release')
        return next(Previous().select())

    def _revert(self):
        """Revert to the previous release

        Needs the backup
        """
        prev_release = self.__get_previous_release()
        curr_release = self.get_current_release()
        backup_file = self.__get_backup_file_name(prev_release)
        if os.path.exists(backup_file):
            self.__hop_cls.model.disconnect()
            print("Restoring previous release...")
            try:
                subprocess.run(['dropdb', self.dbname], check=True)
            except subprocess.CalledProcessError:
                print("Aborting")
                sys.exit(1)
            subprocess.run(['createdb', self.dbname], check=True)
            subprocess.run(
                ['psql', self.dbname, '-f', backup_file],
                check=True,
                stdout=subprocess.DEVNULL)
            os.remove(backup_file)
            self.__hop_cls.model.ping()
            #pylint: disable=invalid-name
            Release = self.__hop_cls.model.get_relation_class('half_orm_meta.hop_release')
            Release(
                major=curr_release['major'],
                minor=curr_release['minor'],
                patch=curr_release['patch']
                ).delete()
            print(f'Reverted to {self.get_release_s(prev_release)}')
        else:
            print(f'Revert failed! No backup file for {prev_release}.')

    def patch(self, force=False, revert=False):
        #TODO: docstring
        "patch method"

        if self.__create_mode or self.__init_mode:
            self.__last_release_s = 'pre-patch'
            self.save_database()
            return self._init()
        if revert:
            return self._revert()
        branch_name = str(self.__hgit.repo.active_branch)
        curr_release = self.get_release_s(self.get_current_release())
        if branch_name == f'hop_{curr_release}':
            revert_i = input(f'Replay patch {curr_release} [Y/n]? ') or 'Y'
            if revert_i.upper() == 'Y':
                self._revert()
                force = True
            else:
                sys.exit()
        self._patch(force=force)
        return self.__release_s

    def __register(self):
        "Mise à jour de la table half_orm_meta.hop_release"
        new_release = self.model.get_relation_class('half_orm_meta.hop_release')(
            major=self.__release['major'],
            minor=self.__release['minor'],
            patch=int(self.__release['patch'])
        )
        #FIXME
        commit = str(datetime.now())
        if new_release.is_empty():
            new_release.changelog = self.changelog
            new_release.commit = commit
            new_release.insert()
        else:
            new_release.update(changelog=self.changelog, commit=commit)
        new_release = new_release.get()

    def __backup_path(self, release_s: str) -> str:
        "Returns the absolute path of the backup file"
        return f'{self.__hop_cls.project_path}/Backups/{self.dbname}-{release_s}.sql'

    def save_database(self):
        """Dumps the database"""
        if not os.path.isdir('./Backups'):
            os.mkdir('./Backups')
        svg_file = self.__backup_path(self.__last_release_s)
        if os.path.isfile(svg_file):
            sys.stderr.write(
                f"Oops! there is already a dump for the {self.__last_release_s} release.\n")
            sys.stderr.write(f"Please remove {svg_file} if you realy want to proceed.\n")
            sys.exit(1)
        subprocess.run(['pg_dump', self.dbname, '-f', svg_file], check=True)

    def _patch(self, commit=None, force=False):
        "Applies the patch and insert the information in the half_orm_meta.hop_release table"
        #TODO: simplify
        last_release = self.get_current_release()
        self.get_next_release(last_release)
        if self.__release_s == '':
            return
        self.__hgit.set_branch(self.__release_s)
        # we got a patch we switch to a new branch
        self.save_database()
        if not os.path.exists(self.__patch_path):
            sys.stderr.write(f'The directory {self.__patch_path} does not exists!\n')
            sys.exit(1)

        changelog_file = os.path.join(self.__patch_path, 'CHANGELOG.md')
        # bundle_file = os.path.join(patch_path, 'BUNDLE')

        if not os.path.exists(changelog_file):
            sys.stderr.write(f"ERROR! {changelog_file} is missing!\n")
            sys.exit(1)

        if commit is None:
            commit = self.__hgit.get_sha1_commit(changelog_file)
            if not force:
                self.__hgit.exit_if_repo_is_not_clean()

        changelog = open(changelog_file, encoding='utf-8').read()

        print(changelog)
        # try:
        #     with open(bundle_file) as bundle_file_:
        #         bundle_issues = [ issue.strip() for issue in bundle_file_.readlines() ]
        #         self.__register(changelog         _ = [
        #             self.apply_issue(issue, commit, issue)
        #             for issue in bundle_issues
        #         ]
        # except FileNotFoundError:
        #     pas
        files = []
        for file_ in os.scandir(self.__patch_path):
            files.append({'name': file_.name, 'file': file_})
        for elt in pydash.order_by(files, ['name']):
            file_ = elt['file']
            extension = file_.name.split('.').pop()
            if (not file_.is_file() or not (extension in ['sql', 'py'])):
                continue
            print(f'+ {file_.name}')

            if extension == 'sql':
                query = open(file_.path, 'r', encoding='utf-8').read().replace('%', '%%')
                if len(query) <= 0:
                    continue

                try:
                    self.model.execute_query(query)
                except psycopg2.Error as err:
                    sys.stderr.write(
                        f"""WARNING! SQL error in :{file_.path}\n
                            QUERY : {query}\n
                            {err}\n""")
                    continue
                except (psycopg2.OperationalError, psycopg2.InterfaceError) as err:
                    raise Exception(f'Problem with query in {file_.name}') from err
            if extension == 'py':
                # exécuter le script
                with subprocess.Popen(file_.path, shell=True) as sub:
                    sub.wait()

        subprocess.run(['hop', 'update', '-f'], check=True)
        self.__register()

    # def apply_issue(self, issue, commit=None, bundled_issue=None):
    #     "Applique un issue"
    #     self._patch('devel/issues/{}'.format(issue), commit, bundled_issue)

    def get_current_release(self):
        """Returns the current release (dict)
        """
        return next(self.model.get_relation_class('half_orm_meta.view.hop_last_release')().select())

    @classmethod
    def get_release_s(cls, release):
        """Returns the current release (str)
        """
        return '{major}.{minor}.{patch}'.format(**release)

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

    def __add_relation(self, sql_dir, fqtn):
        with open(f'{sql_dir}/{fqtn}.sql', encoding='utf-8') as cmd:
            self.model.execute_query(cmd.read())

    def _init(self):
        "Initialises the patch system"

        sql_dir = f"{self.__module_dir}/db_patch_system"
        release = True
        last_release = True
        penultimate_release = True
        release_issue = True
        release = self.model.has_relation('half_orm_meta.hop_release')
        last_release = self.model.has_relation('half_orm_meta.view.hop_last_release')
        penultimate_release = self.model.has_relation('half_orm_meta.penultimate_release')
        release_issue = self.model.has_relation('half_orm_meta.hop_release_issue')
        patch_confict = release or last_release or release_issue or penultimate_release
        if patch_confict:
            release = self.get_release_s(self.get_current_release())
            if release != '0.0.0':
                sys.stderr.write('WARNING!\n')
                sys.stderr.write(f'The hop patch system is already present at {release}!\n')
                sys.stderr.write(
                    f"The package {self.package_name} will not containt any business code!\n")
            return None
        print(f"Initializing the patch system for the '{self.dbname}' database.")
        if not os.path.exists('./Patches'):
            os.mkdir('./Patches')
            shutil.copy(f'{sql_dir}/README', './Patches/README')
        self.__add_relation(sql_dir, 'half_orm_meta.hop_release')
        self.__add_relation(sql_dir, 'half_orm_meta.view.hop_last_release')
        self.__add_relation(sql_dir, 'half_orm_meta.view.hop_penultimate_release')
        self.__add_relation(sql_dir, 'half_orm_meta.hop_release_issue')
        self.model.execute_query(
            "insert into half_orm_meta.hop_release values " +
            "(0,0,0, '', 0, now(), now(),'[0.0.0] First release', " +
            f'{date.today()})')

        print("Patch system initialized at release '0.0.0'.")
        return "0.0.0"
