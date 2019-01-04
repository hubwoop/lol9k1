import json
import sqlite3
import uuid
from typing import Optional, NamedTuple

import click
from flask import current_app, g
from flask.cli import with_appcontext
from slugify import slugify
from igdb_api_python.igdb import igdb
from lol9k1 import utilities
from lol9k1.auth.types import Token


class TokenRow(NamedTuple):
    token: str
    used: bool
    added_by: int


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
def init_db_command():
    """Clear the existing data and create new tables."""
    init_db()
    click.echo('Initialized the database.')


@click.command('create-admin')
@with_appcontext
def create_admin_command():
    db = get_db()
    token = uuid.uuid4().hex[:12]
    db.execute('insert into invites (token, added_by) values (?, ?)', [token, 0])
    db.commit()
    click.echo(f'Your invite token is:\n{token}')


@click.command('add-missing-slugs')
@with_appcontext
def add_slugs_if_missing():
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
def add_igdb_ids_if_missing():
    igdb_connection = utilities.get_igdb()
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
