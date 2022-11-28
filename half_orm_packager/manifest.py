"""Manages the MANIFEST.json
"""

import json
import os

class Manifest:
    def __init__(self, hop_cls):
        self.__hop_release = hop_cls.version
        self.__changelog_msg = None
        self.__new_release_s = hop_cls.release_path.replace('/', '.')
        self.__file = f'{hop_cls.patch_path}/MANIFEST.json'
        self.__read()

    def __read(self):
        if os.path.exists(self.__file):
            with open(self.__file) as manifest:
                data = json.loads(manifest)
                print(data)
                sys.exit(1)

    def write(self, changelog_msg):
        with open(self.__file, 'w', encoding='utf-8') as manifest:
            manifest.write(json.dumps({
                'hop_version': self.__hop_release,
                'changelog_msg': self.__changelog_msg,
                'new_release': self.__new_release_s
            })) 
