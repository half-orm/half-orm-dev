"""
CLI Command: init-database - Configure database connection and metadata
"""

import click
from half_orm import utils
from half_orm_dev.database import Database


class DatabaseSetupError(Exception):
    """Raised when database setup fails"""
    pass


@click.command('init-database')
@click.argument('database_name')
@click.option('--host', default='localhost', help='PostgreSQL host (default: localhost)')
@click.option('--port', default=5432, type=int, help='PostgreSQL port (default: 5432)')
@click.option('--user', default=None, help='Database user (default: $USER)')
@click.option('--password', default=None, help='Database password (prompts if missing)')
@click.option('--create-db', is_flag=True, help='Create database if it doesn\'t exist')
@click.option('--add-metadata', is_flag=True, help='Add half_orm_meta schemas to existing database')
@click.option('--production', is_flag=True, help='Mark as production environment (default: False)')
def init_database(database_name, host, port, user, password, create_db, add_metadata, production):
    """
    Configure database connection and half-orm metadata.

    ARGUMENTS:
        database_name: PostgreSQL database name

    Configure database connection parameters and install half-orm-dev metadata schemas.
    Handles both new database creation and adding metadata to existing databases.

    Examples:
        # Interactive setup for new database
        half_orm dev init-database my_blog_db --create-db

        # Non-interactive with all parameters
        half_orm dev init-database blog_prod --host=db.company.com --user=app_user --password=secret123 --add-metadata --production

        # Add metadata to existing database
        half_orm dev init-database legacy_db --add-metadata
    """
    try:
        # Collect connection parameters from CLI options
        connection_options = {
            'host': host,
            'port': port,
            'user': user,
            'password': password,
            'production': production
        }

        # Setup database connection and metadata
        # Note: For init-database we don't need a full repo, just database setup
        # We'll call the new setup_database class method (to be implemented)
        Database.setup_database(
            database_name=database_name,
            connection_options=connection_options,
            create_db=create_db,
            add_metadata=add_metadata
        )

        click.echo(f"✅ Database '{database_name}' initialized successfully.")
        click.echo(f"📁 Configuration saved to {database_name} configuration file")

    except DatabaseSetupError as e:
        utils.error(f"Database setup failed: {e}", exit_code=1)
