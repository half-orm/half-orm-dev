# halfORM packager (early alpha stage)

This package allows you to patch/test a PostgreSQL model and its associated
Python code using the `hop` command.

It is based on the [half_orm](https://github.com/collorg/halfORM) Python library.

To install it, run `pip install half_orm_packager`.

## help

```
$ hop --help
Usage: hop [OPTIONS] COMMAND [ARGS]...

  Generates/Synchronises/Patches a python package from a PostgreSQL database

Options:
  -v, --version
  --help         Show this message and exit.

Commands:
  new     Creates a new hop project named <package_name>.
  patch   Applies the next patch
  test    Tests some common pitfalls.
  update  Updates the Python code with the changes made to the model.
  ```

## Create a new package for your database: *`hop new`*

```
hop new <package name>
```

**WARNING!** The `hop new` command will add to your database
two new schemas: `half_orm_meta` and "`half_orm_meta.view`".
The table `half_orm_meta.hop_release` will containt the patch history
of your model (see `hop patch` bellow).


```
$ hop new my_database
Database (my_database): 
Input the connection parameters to the my_database database.
User (joel): 
Password: 
Is it an ident login with a local account? [Y/n] 
Production (False): 
The my_database database does not exist.
Do you want to create it (Y/n): 
Initializing git with a 'main' branch.
Initialising the patch system for the 'my_database' database.
Patch system initialized at release '0.0.0'.
Switching to the 'devel' branch.
```

Once created, go to the newly created directory

```
cd my_database
```

## Get the status of your hop repo: *`hop`*

```
$ hop 
STATUS
CURRENT RELEASE: 0.0.0: 2021-09-02 at 10:23:09+02:00
No new release to apply after 0.0.0.
hop --help to get help.
```

## Patch your model: *`hop patch`*

```
$ hop patch
No new release to apply after 0.0.0.
Was expecting one of: 0.0.1, 0.1.0, 1.0.0.
```

The patch system will try to find a next suitable patch to apply from the
last release number. If the last patch is X.Y.Z, `hop -p` will try
X.Y.<Z+1>, X.<Y+1>.Z, <X+1>.Y.Z in order.


To create a X.Y.Z patch, just create a directory Patches/X/Y/Z. In it you'll
have to add a CHANGELOG.md description file with a series of patches scripts.
The scripts are applied in alphabetical order and can only be of two types:

* SQL with .sql extension
* Python with .py extension

## Update the Python code: *`hop update`*

The hop update command synchronizes the Python code to reflect
the changes made to the model by a patch.

**WARNING!** If the update complains about missing modules, you must use the `-f`.
