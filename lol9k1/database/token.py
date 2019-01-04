from typing import NamedTuple

from lol9k1.database.user import User
from lol9k1.database import get_db


class Token(NamedTuple):
    token: str
    used: bool
    added_by: User


def get(invite_token) -> Token:
    db = get_db()
    token_row = db.execute('''
    select invites.token, invites.used, users.name from invites
        join users on invites.added_by = users.id
    where invites.token = ?''', [invite_token]).fetchone()
    token_row = [*token_row]
    token_row[1] = bool(token_row[1])
    return Token(*token_row)
