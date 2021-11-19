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
import time

import psycopg2
import pydash
from .hgit import HGit
from .update import update_modules

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
        self.__curr_release = None
        self.__curr_release_s = None
        self.__prev_release = None
        self.__next_release = None
        self.__update_release()

    def __update_release(self):
        self.__curr_release = self.__hop_cls.get_current_db_release()
        self.__curr_release_s = self.__hop_cls.get_release_s(self.__curr_release)
        self.__prev_release = self.__hop_cls.get_previous_release()
        self.__prev_release_s = self.__hop_cls.get_release_s(self.__prev_release)
        self.__next_release = self.__hop_cls.get_next_release()
        self.__next_release_s = self.__next_release and self.__hop_cls.get_release_s(self.__next_release)
        # print('XXX update release', self.__prev_release_s, self.__curr_release_s, self.__next_release_s)


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
        return f'{self.__hop_cls.project_path}/Patches/{self.__hop_cls.release_path}/'

    def __get_backup_file_name(self, release):
        release_s = self.__hop_cls.get_release_s(release)
        return f'{self.__hop_cls.project_path}/Backups/{self.dbname}-{release_s}.sql'

    @property
    def changelog(self):
        with open(os.path.join(self.__patch_path, 'CHANGELOG.md'), encoding='utf-8') as changelog:
            return changelog.read()

    def is_first_release(self):
        return self.__curr_release_s == '0.0.0'

    def revert(self):
        """Revert to the previous release

        Needs the backup
        """
        self.__update_release()
        if self.is_first_release():
            sys.stderr.write('Current release is 0.0.0. There is no previous release to revert to!\n')
            sys.exit(1)
        backup_file = self.__get_backup_file_name(self.__prev_release)
        if os.path.exists(backup_file):
            self.__hop_cls.model.disconnect()
            print("Restoring previous DB release...")
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
                major=self.__curr_release['major'],
                minor=self.__curr_release['minor'],
                patch=self.__curr_release['patch']
                ).delete()
            self.__update_release()
            print(f'Reverted to {self.__curr_release_s}')
            self.__hop_cls.what_next()
            # self.__hgit.set_branch(self.__curr_release_s)
        else:
            print(f'Revert failed! No backup file for {prev_release_s}.')

    def patch(self, force=False, revert=False):
        """Patches the repo

        Gets the current patch release
        Gets the next release to apply.
        If the branch is hop_main applies the next patch available (Patches/X/Y/Z)
        If the method is invoked and the last applied patch correspond to the git branch, reverts and applie the patch.

        Args:
            force (bool, optional): [description]. Defaults to False.
            revert (bool, optional): [description]. Defaults to False.

        Returns:
            [type]: [description]
        """
        self.__update_release()
        if self.__hop_cls.production:
            # we ensure that we are on the hop_main branch in prod
            # we set force and revert to False
            # we pull to sync the git repo
            self.__hgit.repo.git.checkout('hop_main')
            force = False
            revert = False
            self.__hgit.repo.git.pull()

        if self.__create_mode or self.__init_mode:
            self.__hop_cls.last_release_s = 'pre-patch'
            self.save_database()
            return self._init()

        if revert:
            self.revert()
        else:
            branch_name = str(self.__hgit.repo.active_branch)
            if branch_name == f'hop_{self.__curr_release_s}':
                revert_i = input(f'Replay patch {self.__curr_release_s} [Y/n]? ') or 'Y'
                if revert_i.upper() == 'Y':
                    self.revert()
                    force = True
                else:
                    sys.exit()
            self.__patch(force=force)
        self.__hop_cls.what_next()
        return self.__curr_release_s

    def __register(self):
        "Mise à jour de la table half_orm_meta.hop_release"
        new_release = self.model.get_relation_class('half_orm_meta.hop_release')(
            major=self.__hop_cls.release['major'],
            minor=self.__hop_cls.release['minor'],
            patch=int(self.__hop_cls.release['patch'])
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

    def save_database(self, force=False):
        """Dumps the database 
        """
        if not os.path.isdir('./Backups'):
            os.mkdir('./Backups')
        svg_file = self.__backup_path(self.__hop_cls.last_release_s)
        if os.path.isfile(svg_file) and not force:
            sys.stderr.write(
                f"Oops! there is already a dump for the {self.__hop_cls.last_release_s} release.\n")
            sys.stderr.write(f"Please use the --force option if you realy want to proceed.\n")
            sys.exit(1)
        subprocess.run(['pg_dump', self.dbname, '-f', svg_file], check=True)

    def __patch(self, commit=None, force=False):
        "Applies the patch and insert the information in the half_orm_meta.hop_release table"
        #TODO: simplify
        if self.__next_release is None:
            return
        # we've got a patch we switch to a new branch
        if not self.__hop_cls.model.production:
            self.__hgit.set_branch(self.__hop_cls.release_s)
        self.save_database(force)
        if not os.path.exists(self.__patch_path):
            sys.stderr.write(f'The directory {self.__patch_path} does not exists!\n')
            sys.exit(1)

        changelog_file = os.path.join(self.__patch_path, 'CHANGELOG.md')
        # bundle_file = os.path.join(patch_path, 'BUNDLE')

        if not os.path.exists(changelog_file):
            sys.stderr.write(f"ERROR! {changelog_file} is missing!\n")
            sys.exit(1)

        if commit is None:
            commit = self.__hgit.commit.hexsha
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

        update_modules(self.model, self.package_name)
        self.__register()

    # def apply_issue(self, issue, commit=None, bundled_issue=None):
    #     "Applique un issue"
    #     self.__patch('devel/issues/{}'.format(issue), commit, bundled_issue)

    def prep_next_release(self, release_level):
        """Returns the next (major, minor, patch) tuple according to the release_level

        Args:
            release_level (str): one of ['patch', 'minor', 'major']
        """
        current = self.__hop_cls.get_current_db_release()
        next = {}
        next['major'] = current['major']
        next['minor'] = current['minor']
        next['patch'] = current['patch']
        next[release_level] = next[release_level] + 1
        if release_level == 'major':
            next['minor'] = next['patch'] = 0
        if release_level == 'minor':
            next['patch'] = 0
        new_release_s = '{major}.{minor}.{patch}'.format(**next)
        print(f'PREPARING: {new_release_s}')
        patch_path = 'Patches/{major}/{minor}/{patch}'.format(**next)
        if not os.path.exists(patch_path):
            changelog_msg = input('CHANGELOG message (leave empty to abort): ')
            if not changelog_msg:
                print('Aborting')
                return
            os.makedirs(patch_path)
            with open(f'{patch_path}/CHANGELOG.md', 'w', encoding='utf-8') as changelog:
                changelog.write(changelog_msg)
        self.__hgit.set_branch(new_release_s)
        print(f'You can now add your patch scripts (*.py, *.sql) in {patch_path}. See Patches/README.')

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
            release = self.__hop_cls.get_release_s(self.__hop_cls.get_current_db_release())
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
        return "0.0.0"
