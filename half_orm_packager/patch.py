"The patch module"

import json
import os
import sys

from half_orm_packager import utils

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
        next = dict(current)
        next[release_level] = next[release_level] + 1
        if release_level == 'major':
            next['minor'] = next['patch'] = 0
        if release_level == 'minor':
            next['patch'] = 0
        new_release_s = '{major}.{minor}.{patch}'.format(**next)
        print(f'PREPARING: {new_release_s}')
        patch_path = 'Patches/{major}/{minor}/{patch}'.format(**next)
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
        print(f'You can now add your patch scripts (*.py, *.sql) in {patch_path}. See Patches/README.')
