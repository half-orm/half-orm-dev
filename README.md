# halfORM packager (early alpha stage)

> **📢 Project Evolution Notice**
>
> **halfORM_dev is being redesigned to integrate with halfORM 0.16's new extension system.**
>
> This project will be refactored as `half-orm-dev` to provide development tools through the unified `half_orm` CLI interface. The core functionality (project management, database patches, code generation) will remain the same, but the integration and command structure will be modernized.
>
> **Current Status:**
> - halfORM core 0.16 with extension is about to be released
> - halfORM_dev refactoring will start soon
> - New `half-orm-dev` extension planned for Q3 2025
>
> **What's Changing:**
> - Commands will integrate with `half_orm dev` instead of standalone `hop`
> - Extension auto-discovery and security model
> - Simplified installation and configuration
> - Consistent CLI experience across all halfORM tools
>
> **For Current Users:**
> The existing halfORM_dev will continue to work as-is. The new extension will provide a migration path when ready.
>
> **Stay Updated:**
> Follow progress in [halfORM Discussions](https://github.com/collorg/halfORM/discussions) and [halfORM Issues](https://github.com/collorg/halfORM/issues).

---

THIS DOC IS A WORK IN PROGRESS...

This package allows you to patch/test a PostgreSQL model and its associated
Python code using the `hop` command.

It is based on the [half_orm](https://github.com/collorg/halfORM)
PostgreSQL &#8594; Python relation object mapper.


## Installation

Run `pip install half_orm_dev`.

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
The table `half_orm_meta.release` will containt the patch history
of your model (see `hop patch` bellow).


```
$ hop new pagila
HALFORM_CONF_DIR: /home/joel/.halform
Using '/home/joel/.halform/pagila' file for connexion.
Initializing git with a 'main' branch.
Initializing the patch system for the 'pagila' database.
Patch system initialized at release '0.0.0'.

The hop project 'pagila' has been created.
```

The tree command shows you the repartition of the modules in your package.

```
$ tree pagila
pagila
├── Backups
│   └── pagila-pre-patch.sql
├── pagila
│   ├── base_test.py
│   ├── db_connector.py
│   ├── __init__.py
│   └── public
│       ├── actor_info.py
│       ├── actor_info_test.py
│       ├── actor.py
│       ├── actor_test.py
│       ├── address.py
│       ├── address_test.py
│       ├── category.py
│       ├── category_test.py
│       ├── city.py
│       ├── city_test.py
│       ├── country.py
│       ├── country_test.py
│       ├── customer_list.py
│       ├── customer_list_test.py
│       ├── customer.py
│       ├── customer_test.py
│       ├── film_actor.py
│       ├── film_actor_test.py
│       ├── film_category.py
│       ├── film_category_test.py
│       ├── film_list.py
│       ├── film_list_test.py
│       ├── film.py
│       ├── film_test.py
│       ├── __init__.py
│       ├── inventory.py
│       ├── inventory_test.py
│       ├── language.py
│       ├── language_test.py
│       ├── nicer_but_slower_film_list.py
│       ├── nicer_but_slower_film_list_test.py
│       ├── payment_p2020_01.py
│       ├── payment_p2020_01_test.py
│       ├── payment_p2020_02.py
│       ├── payment_p2020_02_test.py
│       ├── payment_p2020_03.py
│       ├── payment_p2020_03_test.py
│       ├── payment_p2020_04.py
│       ├── payment_p2020_04_test.py
│       ├── payment_p2020_05.py
│       ├── payment_p2020_05_test.py
│       ├── payment_p2020_06.py
│       ├── payment_p2020_06_test.py
│       ├── payment.py
│       ├── payment_test.py
│       ├── rental.py
│       ├── rental_test.py
│       ├── sales_by_film_category.py
│       ├── sales_by_film_category_test.py
│       ├── sales_by_store.py
│       ├── sales_by_store_test.py
│       ├── staff_list.py
│       ├── staff_list_test.py
│       ├── staff.py
│       ├── staff_test.py
│       ├── store.py
│       └── store_test.py
├── Patches
│   └── README
├── Pipfile
├── README.md
└── setup.py
```

Once created, go to the newly created directory

```
cd pagila
```

## The organisation

```
$ tree -d
.
├── Backups
├── pagila
│   └── public
└── Patches
```

You will now be able to manage your package with the `hop` command.

## Get the status of your package: *`hop`*

```
$ hop 
STATUS

        connection_file_name: pagila
        package_name: pagila
        
CURRENT RELEASE: 0.0.0: 2021-09-03 at 11:54:22+02:00
No new release to apply after 0.0.0.
Next possible releases: 0.0.1, 0.1.0, 1.0.0.
hop --help to get help.
```

## Patch your model: *`hop patch`*

```
$ hop patch
No new release to apply after 0.0.0.
Next possible releases: 0.0.1, 0.1.0, 1.0.0.
```

The patch system will try to find a next suitable patch to apply from the
last release number. If the last patch is X.Y.Z, `hop patch` will try in order
X.Y.<Z+1>, X.<Y+1>.Z, <X+1>.Y.Z.


To prepare a new patch, run `hop patch -p <patch_level>` where patch_level is one
of ['patch', 'minor', 'major']. The command will create a directory in 
`Patches/X/Y/Z` with a CHANGELOG.md description file. You can add in this
directory a series of patches scripts.
The scripts are applied in alphabetical order and can only be of two types:


* SQL with .sql extension
* Python with .py extension

If there is a suitable patch to apply, hop will create a branch `hop_<release>`,
backup the database in `Backups/<dbname>-<release>.sql`, apply the patch and
update the Python code.

In development, you will frequently need to adjust a patch.
To replay a patch, simply run `hop patch` again.

To revert to the previous patch run `hop patch -r`.
If your git repo is not clean, `hop patch` will complain. You can use `hop patch -f`
to avoid the warning.

You can use git as you wish during this phase.
## Generate a release (CI): *`hop release`* NotImplented

* `hop release -a` for alpha
* `hop release -c` for release candidate
* `hop release -p` for production

## Test your code

Each `hop patch` should test and report any error.

The package is test ready. For each module there is a test

```
$ pytest pagila/
================= test session starts =================
platform linux -- Python 3.8.5, pytest-6.2.5, py-1.10.0, pluggy-1.0.0
rootdir: /home/joel/Dev/halfORM_packager/tmp/pagila
collected 28 items                                    

pagila/public/actor_info_test.py .              [  3%]
pagila/public/actor_test.py .                   [  7%]
pagila/public/address_test.py .                 [ 10%]
pagila/public/category_test.py .                [ 14%]
pagila/public/city_test.py .                    [ 17%]
pagila/public/country_test.py .                 [ 21%]
pagila/public/customer_list_test.py .           [ 25%]
pagila/public/customer_test.py .                [ 28%]
pagila/public/film_actor_test.py .              [ 32%]
pagila/public/film_category_test.py .           [ 35%]
pagila/public/film_list_test.py .               [ 39%]
pagila/public/film_test.py .                    [ 42%]
pagila/public/inventory_test.py .               [ 46%]
pagila/public/language_test.py .                [ 50%]
pagila/public/nicer_but_slower_film_list_test.py . [ 53%]
                                                [ 53%]
pagila/public/payment_p2020_01_test.py .        [ 57%]
pagila/public/payment_p2020_02_test.py .        [ 60%]
pagila/public/payment_p2020_03_test.py .        [ 64%]
pagila/public/payment_p2020_04_test.py .        [ 67%]
pagila/public/payment_p2020_05_test.py .        [ 71%]
pagila/public/payment_p2020_06_test.py .        [ 75%]
pagila/public/payment_test.py .                 [ 78%]
pagila/public/rental_test.py .                  [ 82%]
pagila/public/sales_by_film_category_test.py .  [ 85%]
pagila/public/sales_by_store_test.py .          [ 89%]
pagila/public/staff_list_test.py .              [ 92%]
pagila/public/staff_test.py .                   [ 96%]
pagila/public/store_test.py .                   [100%]

================= 28 passed in 0.18s ==================
```
