#-*- coding: utf-8 -*-

import os
import codecs
from setuptools import setup

def read(name):
    return codecs.open(
        os.path.join(os.path.dirname(__file__), name), "r", "utf-8").read()

setup(
    name='half_orm_packager',
    version=read('half_orm_packager/version.txt').strip(),
    description="half_orm packager.",
    long_description=read('README.md'),
    keywords='postgres, relation-object mapping',
    author='Joël Maïzi',
    author_email='joel.maizi@collorg.org',
    url='https://github.com/collorg/halfORM_packager',
    license='GNU General Public License v3 (GPLv3)',
    packages=['half_orm_packager'],
    package_data={'half_orm_packager': [
        'templates/*', 'templates/.gitignore', 'db_patch_system/*', 'version.txt']},
    install_requires=[
        'GitPython',
        'click',
        'pydash',
        'half_orm>=0.7.4'
    ],
    entry_points={
        'console_scripts': [
            'hop=half_orm_packager.hop:main',
        ],
    },
    classifiers=[
        # How mature is this project? Common values are
        #   3 - Alpha
        #   4 - Beta
        #   5 - Production/Stable
        'Development Status :: 3 - Alpha',

        # Indicate who your project is intended for
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',

        # Pick your license as you wish (should match "license" above)
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',

        # Specify the Python versions you support here. In particular, ensure
        # that you indicate whether you support Python 2, Python 3 or both.
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
    ],
    long_description_content_type = "text/markdown"
)
