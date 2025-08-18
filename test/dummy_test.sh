#!/usr/bin/env bash

set -vex

if [ -n "$GITHUB_ENV" ]
then
   git config --global user.email "half_orm_ci@collorg.org"
   git config --global user.name "HalfORM CI"
fi

cd -- "$( dirname -- "${BASH_SOURCE[0]}" )"
export HALFORM_CONF_DIR=$PWD/.config

cat $HALFORM_CONF_DIR/hop_test
# switch to development mode
perl -spi -e 's=True=False=' $HALFORM_CONF_DIR/hop_test

clean_db() {
    rm -rf hop_test
    set +e
    dropdb hop_test
    set -e
}

pwd
clean_db
createdb hop_test
yes | half_orm dev new hop_test --devel
clean_db
# it should be able to create a repo not in devel mode
yes | half_orm dev new hop_test
cd hop_test

half_orm dev sync-package
set +e
# it should FAIL: prepare is only available in devel mode
half_orm dev prepare
if [ $? = 0 ]; then exit 1; fi
set -e

cd ..
pwd
clean_db
# it should be able to create a repo in devel mode
yes | half_orm dev new hop_test --devel
cd hop_test

tree .

rm -rf /tmp/hop_test.git

# We need a central repo to release and simulate a production environment
git init --bare /tmp/hop_test.git

# 0.0.1
half_orm dev prepare -m "First patch release" << EOF
patch
EOF

if [ `git branch --show-current` != 'hop_0.0.1' ] ; then echo "It should be on branch hop_0.0.1" ; exit 1 ; fi

echo 'create table first ( a text primary key )' > Patches/0/0/1/a.sql
half_orm dev apply
git add .
git commit -m "First table"
set +e
which pytest
if [ $? = 0 ]; then pip uninstall -y pytest ; fi

# It should FAIL: pytest must be install to commit release
half_orm dev release
if [ $? = 0 ]; then exit 1; fi
set -e
pip install pytest
half_orm dev release

# 0.0.2
half_orm dev prepare -l patch -m "Second patch release"
if [ `git branch --show-current` != 'hop_0.0.2' ] ; then echo "It should be on branch hop_0.0.2" ; exit 1 ; fi

echo 'create table a ( a text primary key, class int, "class + 1" int )' > Patches/0/0/2/00_a.sql
cat > Patches/0/0/2/a.py << EOF
from hop_test.public.first import First
list(First())
EOF

# It should be able to apply multiple times
sync; sync
half_orm dev apply

tree .

set +e
half_orm dev
set -e

yes | half_orm dev apply

half_orm dev apply

git add .
git commit -m "(wip) First"
git status

# Change of the model + the patches must be executed in order
echo 'create table a ( a text primary key, bla text )' > Patches/0/0/2/00_a.sql
echo 'alter table a add column b text' > Patches/0/0/2/01_a.sql
echo 'alter table a alter column b set not null' > Patches/0/0/2/02_a.sql
echo 'alter table a add constraint b_uniq unique(b)' > Patches/0/0/2/03_a.sql

# half_orm dev undo

half_orm dev apply
# git diff hop_test/public/a.py

git status

set +e
# should commit before release
half_orm dev release -m "First release"
if [ $? = 0 ]; then exit 1; fi
set -e

git add .
git commit -m "(wip) ajout de a.bla"

touch dirty
set +e
# git repo must be clean
half_orm dev release
if [ $? = 0 ]; then exit 1; fi
set -e
rm dirty

echo '        verybad' >> hop_test/public/a.py
git add .
git commit -m "(bad)"
set +e
# test must pass
half_orm dev release # 0.0.2
if [ $? = 0 ]; then exit 1; fi
set -e
git branch
git reset HEAD~ --hard

set +e
# git repo must have an origin to push
half_orm dev release --push
if [ $? = 0 ]; then exit 1; fi
set -e

git remote add origin /tmp/hop_test.git
git status

sync; sync
half_orm dev release --push # 0.0.2

git status

set +e
half_orm dev
set -e

half_orm dev prepare -l minor -m "First minor patch" # 0.1.0
if [ `git branch --show-current` != 'hop_0.1.0' ] ; then echo "It should be on branch hop_0.1.0" ; exit 1 ; fi

echo 'create table b ( b text primary key, a text references a )' > Patches/0/1/0/b.sql

half_orm dev apply

tree

# git diff
git status

git add .
git commit -m "(wip) Second"

echo add a_fk in B.Fkeys
cat > hop_test/public/b.py << EOF
from half_orm.field import Field
from half_orm.fkey import FKey
from hop_test import MODEL, ho_dataclasses

#>>> PLACE YOUR CODE BELOW THIS LINE. DO NOT REMOVE THIS LINE!
import datetime
#<<< PLACE YOUR CODE ABOVE THIS LINE. DO NOT REMOVE THIS LINE!

class B(MODEL.get_relation_class('public.b'), ho_dataclasses.DC_PublicB):
    #>>> PLACE YOUR CODE BELOW THIS LINE. DO NOT REMOVE THIS LINE!
    Fkeys = {
        'a_fk': 'b_a_fkey',
    }
    #<<< PLACE YOUR CODE ABOVE THIS LINE. DO NOT REMOVE THIS LINE!
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        #>>> PLACE YOUR CODE BELOW THIS LINE. DO NOT REMOVE THIS LINE!
EOF

half_orm dev apply

git add .
git commit -m "(b) with Fkeys"

mkdir hop_test/Api
touch hop_test/Api/__init__.py
mkdir hop_test/Api/coucou
echo 'print ("coucou")' > hop_test/Api/coucou/__init__.py

git add .
git commit -m "Add API"

half_orm dev release
if [ `git branch --show-current` != 'hop_main' ] ; then echo "It should be on branch hop_main" ; exit 1 ; fi

git status
git push
git tag

# It should be able to prepare a major, a minor and a patch simultaneously.
half_orm dev prepare -l major -m major # 1.0.0
if [ `git branch --show-current` != 'hop_1.0.0' ] ; then echo "It should be on branch hop_1.0.0" ; exit 1 ; fi

half_orm dev prepare -l minor -m minor # 0.2.0
if [ `git branch --show-current` != 'hop_0.2.0' ] ; then echo "It should be on branch hop_0.2.0" ; exit 1 ; fi

touch Patches/0/2/0/coucou
git add .
git commit -m "[WIP] 0.2.0 test"
half_orm dev apply

echo toto > toto
git status
set +e
# It should FAIL: the git repo is not clean
half_orm dev prepare -l patch -m patch
if [ $? = 0 ]; then echo "It should FAIL: the git repo is not clean"; exit 1; fi
set -e


git add toto
git commit -m "toto"

# Check rebase fails

git checkout hop_main
echo tata > toto
git add .
git commit -m "toto on hop_main"

set +e
# It should FAIL: hop_0.2.0 can't be rebased on hop_main
half_orm dev
if [ $? = 0 ]; then exit 1; fi
set -e
git branch
git reset HEAD~ --hard

git checkout hop_0.2.0

# half_orm dev undo
# git checkout hop_main
#  (half_orm dev prepare should undo the changes and switch to hop_main branch)
half_orm dev prepare -l patch -m patch # 0.1.1
git branch

set +e
# It should FAIL: there is already on minor version in preparation.
half_orm dev prepare -l minor -m coucou
if [ $? = 0 ]; then exit 1; fi
half_orm dev
set -e

git checkout hop_0.2.0
set +e
# It should FAIL: the patch in preparation must be released first.
half_orm dev release
if [ $? = 0 ]; then exit 1; fi
set -e
if [ ! -f Backups/hop_test-0.1.0.sql ]; then exit 1; fi
rm Backups/hop_test-0.1.0.sql
git checkout hop_0.1.1
half_orm dev apply
touch Patches/0/1/1/coucou
git add .
git commit -m "[WIP] 0.1.1 test"
half_orm dev apply
half_orm dev release

cat > TODO << EOF
something
EOF
git add TODO
git commit -m "Add todo to check rebase on apply"

git checkout hop_0.2.0
# It should rebase hop_0.2.0 on hop_main (hop_0.1.1 has been released)
half_orm dev apply
half_orm dev release

half_orm dev prepare -l patch -m "0.2.1..." # 0.2.1
half_orm dev apply
touch Patches/0/2/1/coucou
git add .
git commit -m "[0.2.1] coucou"
half_orm dev release

git checkout hop_1.0.0
half_orm dev apply
touch Patches/1/0/0/coucou
git add .
git commit -m "[WIP] 1.0.0 test"
half_orm dev apply
half_orm dev release

git push

echo 'APPLY PATCH IN PRODUCTION'
perl -spi -e 's=False=True=' $HALFORM_CONF_DIR/hop_test
set +e
half_orm dev
set -e
half_orm dev --help
half_orm dev restore 0.0.1
set +e
half_orm dev
set -e
# It should upgrade to the latest version released (1.0.0)
half_orm dev upgrade
perl -spi -e 's=True=False=' $HALFORM_CONF_DIR/hop_test
