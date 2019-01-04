from typing import NamedTuple

from lol9k1.database import get_db
from lol9k1.database.user import User


class Game(NamedTuple):
    id: int
    name: str
    slug: str
    max_players: int
    description: str
    no_drm: bool
    available: bool
    low_spec: bool
    added_by: User
    igdb_id: int


def get(game_id) -> Game:
    db = get_db()
    game_row = db.execute('''
    select g.id, g.name, g.slug, g.max_players, g.description,
    g.no_drm, g.available, g.low_spec, u.id, g.igdb_id from games g 
        join users u on u.id = g.added_by
    where g.id = ?''', [game_id]).fetchone()
    game_row = [*game_row]
    game_row[5] = bool(game_row[5])
    game_row[6] = bool(game_row[6])
    game_row[7] = bool(game_row[7])
    return Game(*game_row)
