import typing

from wtforms import ValidationError

from lol9k1 import database


class ValidToken(object):
    """ A validator for tokens """

    def __init__(self, message_invalid=None):
        self.message_invalid = message_invalid if message_invalid else "Invalid or used invite token"

    def __call__(self, form, field):
        maybe_matched_token = field.data
        if not maybe_matched_token:
            raise ValidationError(self.message_invalid)


class UniqueUserEntry(object):

    def __init__(self, column: str, message: typing.Optional[str] = None):
        self.column = column
        self.message = message if message else f"{column} already reserved."

    def __call__(self, form, field):
        possible_match = database.get_db().execute(f'select id from users where {self.column} = ?', [field.data])

        if possible_match.fetchone():
            raise ValidationError(self.message)
