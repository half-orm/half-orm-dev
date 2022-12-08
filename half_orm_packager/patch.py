"The patch module"

import json
import os
import subprocess
import sys

import pydash
import psycopg2

from half_orm_packager import utils
from half_orm_packager import modules

class Patch:
    "The Patch class..."
    __levels = ['patch', 'minor', 'major']

    def __init__(self, repo):
        self.__repo = repo
        self.__patches_base_dir = os.path.join(repo.base_dir, 'Patches')
        self.__changelog_file = os.path.join(self.__repo.base_dir, '.hop', 'CHANGELOG')
        if not os.path.exists(self.__patches_base_dir):
            os.makedirs(self.__patches_base_dir)
        if not os.path.exists(self.__changelog_file):
            utils.write(self.__changelog_file, f'{self.__repo.database.last_release_s}\n')
        self.__sequence = self.__get_sequence()

    @classmethod
    @property
    def levels(cls):
        "Returns the levels"
        return cls.__levels

    def __get_sequence(self):
        """Get the sequence of patches in .hop/CHANGLOG"""
        return [elt.split()[0] for elt in utils.readlines(self.__changelog_file)]

    def __append_to_changelog(self, release_level):
        """Update with the release the .hop/CHANGELOG file"""
        utils.write(self.__changelog_file, f'{release_level}\n', mode='a+')

    def __update_changelog(self, release_level):
        "Add the commit sha1 to the release in the .hop/CHANGELOG file"
        out = []
        for line in utils.readlines(self.__changelog_file):
            line = line.strip()
            if line and line.split()[0] != release_level:
                out.append(line)
            else:
                out.append(f'{release_level}\t{self.__repo.hgit.last_commit()}\n')
        utils.write(self.__changelog_file, '\n'.join(out))

    @property
    def previous(self):
        "Return .hop/CHANGELOG second to last line."
        return self.__sequence[-2]

    @property
    def last(self):
        "Return .hop/CHANGELOG last line"
        return self.__sequence[-1]

    def __repr(self, release):
        # pylint: disable=consider-using-f-string
        return '{major}.{minor}.{patch}'.format(**release)

    @property
    def __next_possible_releases(self):
        current = dict(self.__repo.database.last_release)
        next_releases = {}
        for level in self.__levels:
            next_releases[level] = dict(current)
            next_releases[level][level] = current[level] + 1
        return next_releases

    def prep_next_release(self, release_level, message=None):
        """Returns the next (major, minor, patch) tuple according to the release_level

        Args:
            release_level (str): one of ['patch', 'minor', 'major']
        """
        if release_level is None:
            next_levels = '\n'.join(
                [f"- {level}: {self.__repr(self.__next_possible_releases[level])}"
                for level in self.__levels])
            print(f'Next possible releases:\n{next_levels}')
            release_level = input(f"Release level {self.__levels}? ")
            if not release_level in self.__levels:
                utils.error(f"Wrong release level ({release_level}).\n", exit_code=1)
        if str(self.__repo.hgit.branch) != 'hop_main':
            utils.error(
                'ERROR! Wrong branch. Please, switch to the hop_main branch before.\n', exit_code=1)
        next_release = dict(self.__repo.database.last_release)
        next_release[release_level] = next_release[release_level] + 1
        if release_level == 'major':
            next_release['minor'] = next_release['patch'] = 0
        if release_level == 'minor':
            next_release['patch'] = 0
        # pylint: disable=consider-using-f-string
        new_release_s = '{major}.{minor}.{patch}'.format(**next_release)
        print(f'PREPARING: {new_release_s}')
        patch_path = os.path.join(
            'Patches',
            str(next_release['major']),
            str(next_release['minor']),
            str(next_release['patch']))
        if not os.path.exists(patch_path):
            changelog_msg = message or input('Message - (leave empty to abort): ')
            if not changelog_msg:
                print('Aborting')
                return
            os.makedirs(patch_path)
            with open(os.path.join(patch_path, 'MANIFEST.json'), 'w', encoding='utf-8') as manifest:
                manifest.write(json.dumps({
                    'hop_version': utils.hop_version(),
                    'changelog_msg': changelog_msg,
                }))
        self.__repo.hgit.set_branch(new_release_s)
        print('You can now add your patch scripts (*.py, *.sql)'
            f'in {patch_path}. See Patches/README.')
        modules.generate(self.__repo)
        self.__append_to_changelog(new_release_s)

    def __check_apply_or_re_apply(self):
        """Return True if it's the first time.
        False otherwise.
        """
        if self.__repo.database.last_release_s == self.__repo.hgit.current_release:
            return 're-apply'
        return 'apply'

    def __backup_file(self, release):
        backup_dir = os.path.join(self.__repo.base_dir, 'Backups')
        if not os.path.isdir(backup_dir):
            os.mkdir(backup_dir)
        file_name = f'{self.__repo.name}-{release}.sql'
        return os.path.join(backup_dir, file_name)

    def __save_db(self):
        """Save the database
        """
        svg_file = self.__backup_file(self.previous)
        print(f'Saving the database into {svg_file}')
        if os.path.isfile(svg_file):
            utils.error(
                f"Oops! there is already a dump for the {self.previous} release.\n")
            utils.error("Please remove it if you really want to proceed.\n", exit_code=1)
        self.__repo.database.execute_pg_command('pg_dump', '-f', svg_file, stderr=subprocess.PIPE)

    def __restore_previous_db(self):
        """Restore the database to the release_s version.
        """
        print(f'Restoring the database to {self.previous}')
        self.__repo.model.disconnect()
        self.__repo.database.execute_pg_command('dropdb')
        self.__repo.database.execute_pg_command('createdb')
        self.__repo.database.execute_pg_command(
            'psql', '-f', self.__backup_file(self.previous), stdout=subprocess.DEVNULL)
        self.__repo.model.ping()

    def __execute_sql(self, file_):
        "Execute sql query contained in sql file_"
        query = utils.read(file_.path).replace('%', '%%')
        if len(query) == 0:
            return
        try:
            self.__repo.model.execute_query(query)
        except (psycopg2.Error, psycopg2.OperationalError, psycopg2.InterfaceError) as err:
            utils.error(f'Problem with query in {file_.name}\n{err}\n')
            self.__restore_previous_db()
            os.remove(self.__backup_file(self.previous))
            sys.exit(1)

    def __execute_script(self, file_):
        try:
            subprocess.run(
                ['python', file_.path],
                env=os.environ.update({'PYTHONPATH': self.__repo.base_dir}),
                shell=False, check=True)
        except subprocess.CalledProcessError as err:
            utils.error(f'Problem with script {file_}\n{err}\n')
            self.__restore_previous_db()
            os.remove(self.__backup_file(self.previous))
            sys.exit(1)

    def apply(self, release, force=False):
        "Apply the patch in 'path'"
        changelog_msg = ''
        if self.__check_apply_or_re_apply() == 'apply':
            self.__save_db()
        else:
            if not force:
                okay = input('Do you want to re-apply the patch [y/N]?') or 'y'
                if okay.upper() != 'Y':
                    sys.exit()
            self.__restore_previous_db()
        print(f'Applying patch {release}')
        files = []
        major, minor, patch = release.split('.')
        path = os.path.join(self.__patches_base_dir, major, minor, patch)
        for file_ in os.scandir(path):
            files.append({'name': file_.name, 'file': file_})
        for elt in pydash.order_by(files, ['name']):
            file_ = elt['file']
            extension = file_.name.split('.').pop()
            if file_.name == 'MANIFEST.py':
                changelog_msg = json.loads(utils.read(file_))['changelog_msg']
            if (not file_.is_file() or not (extension in ['sql', 'py'])):
                continue
            print(f'+ {file_.name}')

            if extension == 'sql':
                self.__execute_sql(file_)
            elif extension == 'py':
                self.__execute_script(file_)
        modules.generate(self.__repo)
        self.__repo.database.register_release(major, minor, patch, changelog_msg)

    @property
    def state(self):
        "The state of a patch"
        return '[Patch]'

    def undo(self, database_only=False):
        "Undo a patch."
        self.__restore_previous_db()
        if not database_only:
            modules.generate(self.__repo)
        os.remove(self.__backup_file(self.previous))

    def release(self, push):
        "Release a patch"
        # Git repo must be clean
        if not self.__repo.hgit.repos_is_clean():
            utils.error(
                'Please `git commit` your changes before releasing the patch.\n', exit_code=1)
        # The patch must be applied and the last to apply
        if not self.__repo.database.last_release_s == self.last:
            utils.error('Please `hop apply-patch` before releasing the patch.\n', exit_code=1)
        # If we undo the patch (db only) and re-apply it the repo must still be clear.
        self.undo(database_only=True)
        self.apply(self.last, force=True)
        if not self.__repo.hgit.repos_is_clean():
            utils.error(
                'Something has changed when re-applying the patch. This should not happen.\n',
                exit_code=1)
        # the tests must pass
        try:
            subprocess.run(['pytest', self.__repo.name], check=True)
        except subprocess.CalledProcessError:
            utils.error('Tests must pass in order to release the patch.\n', exit_code=1)
        # So far, so good
        self.__repo.hgit.rebase_to_hop_main(push)
        self.__update_changelog(self.__repo.database.last_release_s)
