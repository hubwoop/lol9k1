import random
import sqlite3
import uuid
from typing import Optional

import click
from flask import current_app, g
from flask.cli import with_appcontext
from werkzeug.security import generate_password_hash

from lol9k1 import migrate
from lol9k1.auth.types import Token
from lol9k1.utilities import generate_name, generate_token


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config['DATABASE'],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row

    return g.db


def close_db(e=None):
    db = g.pop('db', None)

    if db is not None:
        db.close()


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(db_command)
    app.cli.add_command(init_db_command)
    app.cli.add_command(create_admin_command)
    app.cli.add_command(create_dummy_users)


def get_config(key: str) -> str:
    row = get_db().execute('select value from config where key = ?', [key]).fetchone()
    return row[0] if row else ''


def get_party_start_date() -> str:
    return get_config('date_start')


def get_party_end_date() -> str:
    return get_config('date_end')


@click.group('db')
def db_command() -> None:
    """
    Manages the schema of the SQLite database.

    The path to the database can be specified via current_app.config['DATABASE']
    or the LOL9K1_DB_PATH environment variable.
    """


@db_command.command('upgrade')
@with_appcontext
def db_upgrade_command() -> None:
    """Creates the database or migrates it to the latest version."""
    try:
        result = migrate.upgrade(current_app.config['DATABASE'], log=click.echo)
    except (migrate.MigrationError, sqlite3.Error) as e:
        raise click.ClickException(str(e))
    if not result.ahead:
        click.echo(f'Database is at version {result.to_version}'
                   f'{"" if result.applied else " (up to date)"}.')


@db_command.command('status')
@with_appcontext
def db_status_command() -> None:
    """Shows the database version and pending migrations."""
    version, pending = migrate.status(current_app.config['DATABASE'])
    click.echo(f'Database is at version {version}.')
    for migration in pending:
        click.echo(f'Pending: {migration.path.name}')


@click.command('init-db')
@with_appcontext
@click.pass_context
def init_db_command(ctx: click.Context) -> None:
    """Alias for `flask db upgrade`, safe to run on an existing database."""
    ctx.invoke(db_upgrade_command)


@click.command('create-admin-token')
@with_appcontext
def create_admin_command() -> None:
    """Create an admin user."""
    token = generate_token()
    add_token(added_by=0, admin=True, token=token)
    click.echo(f'Your invite token is:\n{token}')


@click.command('create-dummy-users')
@click.option('-n', '--number', default=9, type=int)
@click.option('-p', '--password', default='password', type=str)
@with_appcontext
def create_dummy_users(number: int, password: str) -> None:
    """Create dummy users."""
    for _ in range(number):
        token = generate_token()
        name = generate_name()
        try:
            add_token(token=token, added_by=0, admin=False)
            add_user(
                name=name, password=password, email=f'{uuid.uuid4()}@example.com',
                gender=random.choice((0, 1, 2)), token=token, is_admin=False)
            click.echo(f"Created '{name}' with token '{token}'")
        except sqlite3.IntegrityError:
            click.echo(f"Failed to create '{name}' with token '{token}'", err=True)
    click.echo(click.style(f"Done creating users. All passwords are set to '{password}'", fg='green'))


def get_unused_token(provided_token) -> Optional[Token]:
    db = get_db()
    row = db.execute('select * from invites where token = ? and used = 0', [provided_token]).fetchone()
    return Token(*row) if row else None


def add_user(name: str, password: str, email: str, gender: str, token: str, is_admin: bool) -> None:
    db = get_db()
    db.execute('insert into users (name, password, email, gender, is_admin, token_used) '
               'values (?, ?, ?, ?, ?, ?)',
               [name, generate_password_hash(password), email, gender, is_admin, token])
    db.execute('update invites set used = 1 where token = ?', [token])
    db.commit()


def add_token(token: str, added_by: int, admin: bool) -> None:
    db = get_db()
    db.execute('insert into invites (token, used, added_by, admin) values (?, ?, ?, ?)',
               [token, 0, added_by, admin])
    db.commit()
