import json
import random
import sqlite3
import uuid
from typing import Optional

import click
from flask import current_app, g
from flask.cli import with_appcontext
from slugify import slugify
from igdb_api_python.igdb import igdb
from werkzeug.security import generate_password_hash

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


def init_db():
    db = get_db()
    with current_app.open_resource('schema.sql', mode='r') as f:
        db.executescript(f.read())
    db.commit()


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(create_admin_command)
    app.cli.add_command(create_dummy_users)


def get_party_start_date() -> str:
    db = get_db()
    start_date_row = db.execute("select value from config where key = 'date_start'").fetchone()
    try:
        return start_date_row[0]
    except TypeError:
        return ""


def get_party_end_date() -> str:
    db = get_db()
    end_date_row = db.execute("select value from config where key = 'date_end'").fetchone()
    try:
        return end_date_row[0]
    except TypeError:
        return ""


@click.command('init-db')
@with_appcontext
def init_db_command() -> None:
    """Apply the db schema to a (new) sqlite DB @ LOL9K1_DB_PATH."""
    init_db()
    click.echo('Initialized the database.')


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
    while number > 0:
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
        number -= 1
    click.echo(click.style(f"Done creating users. All passwords are set to '{password}'", fg='green'))


@click.command('add-missing-slugs')
@with_appcontext
def add_slugs_if_missing() -> str:
    db = get_db()
    cursor = db.execute('select id, name, slug from games')
    game_names = cursor.fetchall()
    for game_name in game_names:
        if not game_name[2]:
            db.execute('update games set slug = ? where id = ?', [slugify(game_name[1]), game_name[0]])
    db.commit()
    return "done :)"


@click.command('update-igdb-ids')
@with_appcontext
def add_igdb_ids_if_missing() -> str:
    igdb_connection = get_igdb()
    db = get_db()
    cursor = db.execute('select id, name, igdb_id from games')
    game_names = cursor.fetchall()
    for game_name in game_names:
        if not game_name[2]:
            result = igdb_connection.games({
                'search': game_name[1],
                'fields': 'name'
            })
            print(json.dumps(result.json(), indent=2, sort_keys=True))
            igdb_id = input(f"ID of game: {game_name[1]}?")
            if igdb_id:
                db.execute('update games set igdb_id = ? where id = ?', [int(igdb_id), game_name[0]])
    db.commit()
    return "done :)"


def get_igdb() -> igdb:
    if not hasattr(g, 'igdb'):
        g.igdb = igdb(current_app.config['IGDB_API_KEY'])
    return g.igdb


def get_game_slug_by_id(game_id: int) -> str:
    db = get_db()
    slug_row = db.execute('select slug from games where id = ?', [game_id]).fetchone()
    return slug_row[0]


def get_game_id_by_slug(slug: str) -> int:
    db = get_db()
    slug_row = db.execute('select id from games where slug = ?', [slug]).fetchone()
    return int(slug_row[0])


def get_unused_token(provided_token) -> Optional[Token]:
    db = get_db()
    cursor = db.execute('select * from invites where token = ? and used = 0', [provided_token])
    try:
        return Token(*cursor.fetchone())
    except TypeError:
        return None


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
