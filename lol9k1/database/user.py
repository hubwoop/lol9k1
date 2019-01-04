from typing import NamedTuple

from lol9k1.auth.types import Token
from lol9k1.database import get_db


class User(NamedTuple):
    id: int
    name: str
    email: str
    password: str
    gender: str
    is_admin: bool
    token_used: Token


def get(user_id) -> User:
    db = get_db()
    user_row = db.execute('''
    select * from users where id = ?''', [user_id]).fetchone()
    user_row = [*user_row]
    user_row[5] = bool(user_row[5])
    return User(*user_row)
