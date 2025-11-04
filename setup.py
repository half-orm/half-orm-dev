#-*- coding: utf-8 -*-

import os
import codecs
import re
from setuptools import setup, find_packages

def read(name):
    return codecs.open(
        os.path.join(os.path.dirname(__file__), name), "r", "utf-8").read()

def get_half_orm_version_constraint():
    """
    Calculate half_orm version constraint from half_orm_dev version.

    For version X.Y.Z[-xxx], returns: half_orm>=X.Y.0,<X.(Y+1).0
    """
    version_text = read('half_orm_dev/version.txt').strip()

    # Parse version with regex to handle X.Y.Z[-suffix]
    match = re.match(r'^(\d+)\.(\d+)\.(\d+)(?:-.*)?$', version_text)

    if not match:
        raise ValueError(f"Invalid version format in version.txt: {version_text}")

    major, minor, patch = match.groups()
    major, minor = int(major), int(minor)

    # Generate constraint: half_orm>=X.Y.0,<X.(Y+1).0
    min_version = f"{major}.{minor}.0"
    max_version = f"{major}.{minor + 1}.0"

    return f"half_orm>={min_version},<{max_version}"

setup(
    name='half_orm_dev',
    version=read('half_orm_dev/version.txt').strip(),
    description="half_orm development Framework.",
    long_description=read('README.md'),
    keywords='postgres, relation-object mapping',
    author='Joël Maïzi',
    author_email='joel.maizi@collorg.org',
    url='https://github.com/collorg/halfORM_dev',
    license='GNU General Public License v3 (GPLv3)',
    packages=find_packages(),
    package_data={'half_orm_dev': [
        'templates/*', 'templates/.gitignore', 'db_patch_system/*', 'patches/**/*', 'version.txt']},
    install_requires=[
        'GitPython',
        'click',
        'pydash',
        get_half_orm_version_constraint(),
        'pytest'
    ],
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
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Programming Language :: Python :: 3.14',
    ],
    long_description_content_type = "text/markdown"
)
