# Usage

Notes for halfORM packager usage

## Initialization

```
pipenv install half-orm-packager
pipenv install half-orm
pipenv shell
export HALFORM_CONF_DIR=/path/to/half_orm/private/dir 
hop new my_hop_project
```

## Create the first patch

```
cd my_hop_project
hop patch -p
# Enter the commit message

# Add a file with the base model in Patches/0/0/1/model.sql

# Apply the patch
hop patch

# Commit the changes
git add Patches/0/0/1 my_hop_project
git commit -F Patches/0/0/1/CHANGELOG.md

# Merge to hop_main

git checkout hop_main
git merge hop_0.0.1
```

## Create the second patch (without sql modifications)

```
# Initiate a new patch
hop patch -p

# Enter the commit message

# Add a file with the base model in Patches/0/0/1/model.sql

# Make a modification in my_hop_project/schema/table.py

# Commit the changes
git add Patches/0/0/1 my_hop_project
git commit -F Patches/0/0/1/CHANGELOG.md

# Apply the patch, the only modification is that it update the version number

hop patch

# Merge to hop_main
```
