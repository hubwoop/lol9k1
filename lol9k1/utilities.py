import sqlite3
from collections import namedtuple

from igdb_api_python.igdb import igdb

NAVY_SEAL = "no."
g = None
app = None
MODE_INT_TO_STRING = {
    1: 'Single Elimination',
    2: 'Double Elimination'
}
GENDER_INT_TO_STRING = {
    0: "😐",
    1: "🚹",
    2: "🚺",
    3: "🚁"
}

flash_categories = namedtuple('flash_type', ['message', 'error', 'warning', 'success'])
STYLE = flash_categories('primary', 'danger', 'warning', 'success')


def connect_db():
    rv = sqlite3.connect(app.config['DATABASE'])
    rv.row_factory = sqlite3.Row
    return rv


def get_db() -> sqlite3.Connection:
    if not hasattr(g, 'sqlite_db'):
        g.sqlite_db = connect_db()
    return g.sqlite_db


def get_igdb() -> igdb:
    if not hasattr(g, 'igdb'):
        g.igdb = igdb(app.config['IGDB_API_KEY'])
    return g.igdb


def user_logged_in(session) -> bool:
    db = get_db()
    if not session.get('logged_in'):
        return False
    user_entry = db.execute('select * from users where id = ?', [session.get('user_id')]).fetchone()
    if not user_entry:
        return False
    return True


def get_game_slug_by_id(game_id: int) -> str:
    db = get_db()
    slug_row = db.execute('select slug from games where id = ?', [game_id]).fetchone()
    return slug_row[0]


def get_game_id_by_slug(slug: str) -> int:
    db = get_db()
    slug_row = db.execute('select id from games where slug = ?', [slug]).fetchone()
    return int(slug_row[0])



