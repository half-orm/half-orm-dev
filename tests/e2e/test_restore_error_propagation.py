"""
Regression test: database restoration must fail loudly, not silently.

Bug scenario:
  All `psql -f <file>` restoration calls (schema.sql, data-X.Y.Z.sql,
  release-X.Y.Z.sql, dump files) were invoked without `-v ON_ERROR_STOP=1`.

  Without that flag, psql does NOT stop on a SQL error and, crucially,
  still exits with status 0 - the failure is only visible as text on
  stderr, interleaved with normal NOTICE output. Since
  Database._execute_native_pg_command() only raises on a non-zero exit
  code (`subprocess.run(..., check=True)`), a broken/truncated/corrupted
  schema or data file was silently treated as a successful restore.

  Concretely: `restore_database_from_schema()` first DROP SCHEMA CASCADEs
  everything, then loads schema.sql. If schema.sql fails to load (e.g. it
  isn't valid SQL - which happens for real when git checks it out as a
  plain text file instead of following the schema.sql -> schema-X.Y.Z.sql
  symlink, e.g. under `core.symlinks=false`), the command "succeeds" with
  exit 0, and the caller proceeds as if nothing happened - `patch apply`
  reports success with an empty database and no error at all.

  Fix: every restoration psql invocation now passes `-v ON_ERROR_STOP=1`,
  so a failed load raises RepoError instead of leaving a silently empty
  database.
"""
import pytest


@pytest.mark.e2e
class TestRestoreDatabaseErrorPropagation:
    """A broken schema/data file must fail the restore, not empty it out."""

    def test_broken_release_schema_fails_patch_apply_instead_of_emptying_db(
        self, project_with_release
    ):
        """
        Corrupt model/release-X.Y.Z.sql - the file `patch apply` actually
        restores from once a release exists (restore_database_from_release_schema,
        the everyday path for any patch after the first in a release) - with
        invalid SQL, and verify `patch apply` fails loudly instead of
        silently succeeding with an empty database.
        """
        env = project_with_release
        run = env['run']
        project_dir = env['project_dir']
        release_version = env['release_version']

        patch_id = '1-should-not-apply'
        run(['half_orm', 'dev', 'patch', 'create', patch_id])

        patch_dir = project_dir / 'Patches' / patch_id
        (patch_dir / '01_create_table.sql').write_text(
            "CREATE TABLE public.canary (id SERIAL PRIMARY KEY);\n"
        )

        # Corrupt the release schema file that
        # restore_database_from_release_schema() loads - this is the file
        # `patch apply` actually restores from once a release schema
        # exists (i.e. every normal development patch, not just legacy
        # backward-compat).
        release_schema = (
            project_dir / '.hop' / 'model' / f'release-{release_version}.sql'
        )
        original_content = release_schema.read_text()
        release_schema.write_text("this is not valid SQL at all;\n")

        try:
            result = run(['half_orm', 'dev', 'patch', 'apply'], check=False)

            assert result.returncode != 0, (
                "patch apply must fail when the schema file is broken, "
                "not silently succeed with an empty database.\n"
                f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
            )

            # And the database must not have been left silently empty:
            # the pre-existing failure must be visible in the output.
            combined = (result.stdout + result.stderr).lower()
            assert 'error' in combined or 'erreur' in combined or 'échec' in combined, (
                f"Expected a visible error in output.\n"
                f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
            )
        finally:
            # Restore the release schema file so DB state doesn't leak into
            # other tests / manual inspection.
            release_schema.write_text(original_content)
