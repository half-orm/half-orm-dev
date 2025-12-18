"""
Main CLI module - Creates and configures the CLI group
"""

import click
import functools
import sys
from half_orm_dev.repo import Repo, OutdatedHalfORMDevError
from half_orm import utils
from .commands import ALL_COMMANDS


class Hop:
    """Sets the options available to the hop command"""

    def __init__(self):
        self.__repo: Repo = None
        self.__hop_upgrade_error: OutdatedHalfORMDevError = None

        # Try to initialize Repo, catch version errors
        try:
            self.__repo = Repo()  # Utilise le singleton
        except OutdatedHalfORMDevError as e:
            # Capture the error but don't raise it yet
            self.__hop_upgrade_error = e

        self.__available_cmds = self._determine_available_commands()

    def _determine_available_commands(self):
        """
        Determine which commands are available based on context.

        Returns different command sets based on:
        - Repository status (checked/unchecked)
        - Development mode (devel flag - metadata presence)
        - Environment (production flag)

        Note: When needs_hop_upgrade is true, commands will still be added
        but will be blocked by the decorator at execution time.
        """
        if self.needs_hop_upgrade:
            # Version downgrade detected - return a minimal set of commands
            # Commands will be blocked by decorator, but we need them in the list
            # so Click doesn't show "No such command" error
            return ['check', 'migrate']

        if not self.repo_checked:
            # Outside hop repository - commands for project initialization
            return ['init', 'clone']

        if self.__repo.needs_migration():
            return ['migrate']

        # Inside hop repository
        if not self.__repo.devel:
            # Sync-only mode (no metadata)
            return ['sync-package', 'check']

        # Development mode (metadata present)
        if self.__repo.database.production:
            # PRODUCTION ENVIRONMENT - Release deployment only
            return ['update', 'upgrade', 'check']
        else:
            # DEVELOPMENT ENVIRONMENT - Patch development
            return ['patch', 'release', 'check']

    @property
    def repo_checked(self):
        """Returns whether we are in a repo or not."""
        return self.__repo and self.__repo.checked

    @property
    def needs_hop_upgrade(self):
        """Returns whether half_orm_dev needs to be upgraded."""
        return self.__hop_upgrade_error is not None

    @property
    def hop_upgrade_error(self):
        """Returns the upgrade error if any."""
        return self.__hop_upgrade_error

    @property
    def state(self):
        """Returns the state of the repo."""
        return self.__repo.state if self.__repo else "Not in a repository"

    @property
    def available_commands(self):
        """Returns the list of available commands."""
        return self.__available_cmds


def create_cli_group():
    """
    Creates and returns the CLI group with appropriate commands.

    Returns:
        click.Group: Configured CLI group
    """
    hop = Hop()

    def check_version_before_invoke(f, allow_on_downgrade=False):
        """Decorator to check version before invoking any command.

        Args:
            f: Function to wrap
            allow_on_downgrade: If True, allow this command even when version is outdated
        """
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            if hop.needs_hop_upgrade and not allow_on_downgrade:
                # Display formatted error message for version downgrade
                error = hop.hop_upgrade_error
                click.echo("=" * 70, err=True)
                click.echo(f"{utils.Color.red('❌ OUTDATED half_orm_dev VERSION')}", err=True)
                click.echo("=" * 70, err=True)
                click.echo(f"\n  Repository requires: {utils.Color.bold(error.required_version)}", err=True)
                click.echo(f"  Installed version:   {utils.Color.bold(error.installed_version)}", err=True)
                click.echo(f"\n  Your installed version is OLDER than the repository requirement.", err=True)
                click.echo(f"  All commands are blocked for safety.", err=True)
                click.echo(f"\n  Please upgrade half_orm_dev:", err=True)
                click.echo(f"    {utils.Color.bold(f'pip install --upgrade half_orm_dev=={error.required_version}')}", err=True)
                click.echo("\n" + "=" * 70 + "\n", err=True)
                sys.exit(1)
                raise click.Abort()
            return f(*args, **kwargs)
        return wrapper

    # Create custom Group that auto-decorates commands
    class VersionCheckGroup(click.Group):
        def add_command(self, cmd, name=None):
            """Override to decorate all commands with version check."""
            if isinstance(cmd, click.Command) and cmd.callback:
                cmd.callback = check_version_before_invoke(cmd.callback)
            super().add_command(cmd, name)

    @click.group(cls=VersionCheckGroup, invoke_without_command=True)
    @click.pass_context
    @check_version_before_invoke
    def dev(ctx):
        """halfORM development tools - Git-centric patch management and database synchronization"""
        if ctx.invoked_subcommand is None:
            # Show repo state when no subcommand is provided
            if hop.repo_checked:
                # Check if migration is needed
                if hop._Hop__repo.needs_migration():
                    # Propose automatic migration
                    from half_orm_dev.utils import hop_version
                    from half_orm_dev.repo import RepoError
                    installed_version = hop_version()
                    config_version = hop._Hop__repo._Repo__config.hop_version
                    current_branch = hop._Hop__repo.hgit.branch if hop._Hop__repo.hgit else 'unknown'

                    click.echo(f"\n{'='*70}")
                    click.echo(f"✨ {utils.Color.bold('Repository Migration Available')} ✨")
                    click.echo(f"{'='*70}")
                    click.echo(f"\n  Repository version: {config_version}")
                    click.echo(f"  Installed version:  {installed_version}")
                    click.echo(f"  Current branch:     {current_branch}")
                    click.echo(f"\n  A migration is needed to update the repository structure.")
                    click.echo(f"  This will:")
                    click.echo(f"    • Switch to ho-prod branch (if not already there)")
                    click.echo(f"    • Update repository configuration")
                    click.echo(f"    • Sync changes to all active branches")
                    click.echo(f"\n  💡 You can interrupt (Ctrl+C) to backup .git/ if needed.")
                    click.echo(f"\n{'='*70}\n")

                    # Ask for confirmation
                    if click.confirm("Apply migration now?", default=True):
                        click.echo()

                        # Switch to ho-prod if needed
                        if current_branch != 'ho-prod':
                            try:
                                click.echo(f"  Switching to ho-prod...")
                                hop._Hop__repo.hgit.checkout('ho-prod')
                                click.echo(f"  ✓ Now on ho-prod")
                                click.echo()
                            except Exception as e:
                                click.echo(utils.Color.red(f"  ❌ Failed to switch to ho-prod: {e}"), err=True)
                                click.echo(f"\n  Please switch manually: git checkout ho-prod", err=True)
                                click.echo(f"  Then run: half_orm dev migrate\n", err=True)
                                raise click.Abort()

                        # Run migration
                        try:
                            click.echo(f"  Running migrations...")
                            result = hop._Hop__repo.run_migrations_if_needed(silent=False)

                            if result['migration_run']:
                                click.echo(f"\n✓ {utils.Color.green('Migration completed successfully')}")
                                click.echo(f"  Updated .hop/config: hop_version = {installed_version}")
                                click.echo(f"  Synced .hop/ to active branches")
                                click.echo()

                                # Return to original branch if we switched
                                if current_branch != 'ho-prod':
                                    try:
                                        click.echo(f"  Returning to {current_branch}...")
                                        hop._Hop__repo.hgit.checkout(current_branch)
                                        click.echo(f"  ✓ Back on {current_branch}\n")
                                    except Exception:
                                        click.echo(f"  ⚠️  Could not return to {current_branch}", err=True)
                                        click.echo(f"  You are now on ho-prod\n", err=True)
                            else:
                                click.echo(f"✓ {utils.Color.green('Repository is up to date')}\n")

                        except RepoError as e:
                            click.echo(utils.Color.red(f"\n❌ Migration failed: {e}\n"), err=True)
                            raise click.Abort()
                    else:
                        # User declined migration
                        click.echo(f"\n  Migration declined.")
                        click.echo(f"  All commands are blocked until migration is complete.")
                        click.echo(f"\n  To apply migration later, run:")
                        click.echo(f"    {utils.Color.bold('half_orm dev migrate')}")
                        click.echo(f"\n{'='*70}\n")
                else:
                    # Normal display
                    click.echo(hop.state)
                    click.echo(f"\n{utils.Color.bold('Available commands:')}")

                    # Adapt displayed commands based on environment
                    if hop._Hop__repo.database.production:
                        # Production commands
                        click.echo(f"  • {utils.Color.bold('update')} - Fetch and list available releases")
                        click.echo(f"  • {utils.Color.bold('upgrade [--to-release=X.Y.Z]')} - Apply releases to production")
                    else:
                        # Development commands
                        click.echo(f"  • {utils.Color.bold('patch')}")
                        click.echo(f"  • {utils.Color.bold('prepare-release <level>')} - Prepare next release stage file (patch/minor/major)")
                        click.echo(f"  • {utils.Color.bold('promote-to <target>')} - Promote stage to rc or prod")

                    click.echo(f"\nTry {utils.Color.bold('half_orm dev <command> --help')} for more information.\n")
            else:
                click.echo(hop.state)
                click.echo("\nNot in a hop repository.")
                click.echo(f"\n{utils.Color.bold('Available commands:')}")
                click.echo(f"\n  • {utils.Color.bold('init <package_name>')} - Create new halfORM project.")
                click.echo(f"\n  • {utils.Color.bold('clone <git origin>')} - Clone an existing halfORM project.\n")

    # Add only available commands to the group
    for cmd_name in hop.available_commands:
        if cmd_name in ALL_COMMANDS:
            dev.add_command(ALL_COMMANDS[cmd_name])

    return dev