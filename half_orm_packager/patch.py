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

from datetime import date
import os
import shutil
import sys
import subprocess

import psycopg2
import pydash


class Patch:
    #TODO: docstring
    "class Patch"
    def __init__(self, model, create_mode=False, init_mode=False):
        self.model = model
        self.__package_name = None
        self.__dbname = self.model._dbname
        self.__create_mode = create_mode
        self.__init_mode = init_mode
        self.__orig_dir = os.path.abspath('.')
        self.__module_dir = os.path.dirname(__file__)
        self.__last_release_s = None
        self.__release = None
        self.__release_s = ''
        self.__release_path = None

    def patch(self, package_name, force=False):
        #TODO: docstring
        "method patch"

        self.__package_name = package_name
        if self.__create_mode or self.__init_mode:
            self.__last_release_s = 'pre-patch'
            self.save_database()
            return self._init()
        self._patch(force=force)
        os.chdir(self.__orig_dir)
        return self.__release_s

    def update_release(self, changelog, commit, issue):
        "Mise à jour de la table half_orm_meta.hop_release"
        new_release = self.model.get_relation_class('half_orm_meta.hop_release')(
            major=self.__release['major'],
            minor=self.__release['minor'],
            patch=int(self.__release['patch']),
            commit=commit
        )
        if new_release.is_empty():
            new_release.changelog = changelog
            new_release.insert()
        new_release = new_release.get()
        if issue:
            num, issue_release = str(issue).split('.')
            self.model.get_relation_class('half_orm_meta.hop_release_issue')(
                num=num, issue_release=issue_release,
                release_major=new_release['major'],
                release_minor=new_release['minor'],
                release_patch=new_release['patch'],
                release_pre_release=new_release['pre_release'],
                release_pre_release_num=new_release['pre_release_num'],
                changelog=changelog
            ).insert()

    @classmethod
    def get_sha1_commit(cls, patch_script):
        "Returns the sha1 of the last commmit"
        commit = subprocess.Popen(
            "git log --oneline --abbrev=-1 --max-count=1 {}".format(
            os.path.dirname(patch_script)
        ), shell=True, stdout=subprocess.PIPE)
        commit = commit.stdout.read().decode()
        if commit.strip():
            commit = commit.split()[0] # commit is the commit sha1
        else:
            sys.stderr.write("WARNING! Running in test mode (logging the date as commit).\n")
            commit = "{}".format(date.today())
        return commit

    def save_database(self):
        """Dumps the database"""
        if not os.path.isdir('./Backups'):
            os.mkdir('./Backups')
        svg_file = f'./Backups/{self.__dbname}-{self.__last_release_s}.sql'
        if os.path.isfile(svg_file):
            sys.stderr.write(
                f"Oops! there is already a dump for the {self.__last_release_s} release.\n")
            sys.stderr.write(f"Please remove {svg_file} if you realy want to proceed.\n")
            sys.exit(1)
        subprocess.run(['pg_dump', self.__dbname, '-f', svg_file], check=True)

    def _patch(self, commit=None, issue=None, force=False):
        "Applies the patch and insert the information in the half_orm_meta.hop_release table"
        #TODO: simplify
        last_release = self.get_current_release()
        self.get_next_release(last_release)
        if self.__release_s == '':
            return
        self.save_database()
        patch_path = f'Patches/{self.__release_path}/'
        if not os.path.exists(patch_path):
            sys.stderr.write(f'The directory {patch_path} does not exists!\n')
            sys.exit(1)

        changelog_file = os.path.join(patch_path, 'CHANGELOG.md')
        # bundle_file = os.path.join(patch_path, 'BUNDLE')

        if not os.path.exists(changelog_file):
            sys.stderr.write("ERROR! {} is missing!\n".format(changelog_file))
            self.exit_(1)

        if commit is None:
            commit = self.get_sha1_commit(changelog_file)
            if not force:
                repo_is_clean = subprocess.Popen(
                    "git status --porcelain", shell=True, stdout=subprocess.PIPE)
                repo_is_clean = repo_is_clean.stdout.read().decode().strip().split('\n')
                repo_is_clean = [line for line in repo_is_clean if line != '']
                if repo_is_clean:
                    print("WARNING! Repo is not clean:\n\n{}".format('\n'.join(repo_is_clean)))
                    cont = input("\nApply [y/N]?")
                    if cont.upper() != 'Y':
                        print("Aborting")
                        self.exit_(1)

        changelog = open(changelog_file, encoding='utf-8').read()

        print(changelog)
        # try:
        #     with open(bundle_file) as bundle_file_:
        #         bundle_issues = [ issue.strip() for issue in bundle_file_.readlines() ]
        #         self.update_release(changelog, commit, None)
        #         _ = [
        #             self.apply_issue(issue, commit, issue)
        #             for issue in bundle_issues
        #         ]
        # except FileNotFoundError:
        #     pass

        files = []
        for file_ in os.scandir(patch_path):
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

        self.update_release(changelog, commit, issue)

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
            next_release_s = '{major}.{minor}.{patch}'.format(**next_release)
            tried.append(next_release_s)
            if os.path.exists('Patches/{}'.format(next_release_path)):
                print("NEXT RELEASE: {major}.{minor}.{patch}".format(**next_release))
                self.__release = next_release
                self.__release_s = next_release_s
                self.__release_path = next_release_path
                return next_release
        print(f"No new release to apply after {self.__last_release_s}.")
        print(f"Next possible releases: {', '.join(tried)}.")
        return None

    def exit_(self, retval=0):
        "Exit after restoring orig dir"
        os.chdir(self.__orig_dir)
        sys.exit(retval)

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
                    f"The package {self.__package_name} will not containt any business code!\n")
            return None
        print(f"Initializing the patch system for the '{self.__dbname}' database.")
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
