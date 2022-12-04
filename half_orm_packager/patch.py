"The patch module"

import json
import os
import sys

import pydash
import psycopg2

from half_orm_packager import utils
from half_orm_packager import modules

class Patch:
    "The Patch class..."
    def __init__(self, repo):
        self.__repo = repo

    def prep_next_release(self, release_level, message=None):
        """Returns the next (major, minor, patch) tuple according to the release_level

        Args:
            release_level (str): one of ['patch', 'minor', 'major']
        """
        if str(self.__repo.hgit.branch) != 'hop_main':
            sys.stderr.write('ERROR! Wrong branch. Please, switch to the hop_main branch before.\n')
            sys.exit(1)
        current = self.__repo.database.last_release
        next_release = dict(current)
        next_release[release_level] = next_release[release_level] + 1
        if release_level == 'major':
            next_release['minor'] = next_release['patch'] = 0
        if release_level == 'minor':
            next_release['patch'] = 0
        # pylint: disable=consider-using-f-string
        new_release_s = '{major}.{minor}.{patch}'.format(**next_release)
        print(f'PREPARING: {new_release_s}')
        # pylint: disable=consider-using-f-string
        patch_path = 'Patches/{major}/{minor}/{patch}'.format(**next_release)
        if not os.path.exists(patch_path):
            changelog_msg = message or input('CHANGELOG message - (leave empty to abort): ')
            if not changelog_msg:
                print('Aborting')
                return
            os.makedirs(patch_path)
            with open(f'{patch_path}/MANIFEST.json', 'w', encoding='utf-8') as manifest:
                manifest.write(json.dumps({
                    'hop_version': utils.hop_version(),
                    'changelog_msg': changelog_msg,
                }))
        self.__repo.hgit.set_branch(new_release_s)
        print('You can now add your patch scripts (*.py, *.sql)'
            f'in {patch_path}. See Patches/README.')
        modules.generate(self.__repo)

    def apply(self, path):
        "Apply the patch in 'path'"
        print(f'Applying patch at {path}')
        files = []
        for file_ in os.scandir(path):
            files.append({'name': file_.name, 'file': file_})
        for elt in pydash.order_by(files, ['name']):
            file_ = elt['file']
            extension = file_.name.split('.').pop()
            if file_.name == 'MANIFEST.py':
                continue
            if (not file_.is_file() or not (extension in ['sql', 'py'])):
                continue
            print(f'+ {file_.name}')

            if extension == 'sql':
                query = open(file_.path, 'r', encoding='utf-8').read().replace('%', '%%')
                if len(query) <= 0:
                    continue

                try:
                    self.__repo.model.execute_query(query)
                except psycopg2.Error as err:
                    sys.stderr.write(
                        f"""WARNING! SQL error in :{file_.path}\n
                            QUERY : {query}\n
                            {err}\n""")
                    self.__repo.abort()
                except (psycopg2.OperationalError, psycopg2.InterfaceError) as err:
                    raise Exception(f'Problem with query in {file_.name}') from err
            elif extension == 'py':
                try:
                    subprocess.check_call(file_.path, shell=True)
                except subprocess.CalledProcessError:
                    self.__repo.abort()
        modules.generate(self.__repo)
        
    @property
    def status(self):
        "The status of a patch"
        return '[Patch]'
