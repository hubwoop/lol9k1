from typing import NamedTuple


class Token(NamedTuple):
    token: str
    used: bool
    added_by: int


class User(NamedTuple):
    id: int
    name: str
    email: str
    password: str
    gender: str
    is_admin: int
    token_used: str


class RegistrationError(Exception):
    pass
