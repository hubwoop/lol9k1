from wtforms import Field
from wtforms.widgets import TextInput

from lol9k1 import database
from lol9k1.auth.types import Token


class TokenField(Field):
    """ Wraps text input to return TokenInfo """

    widget = TextInput()

    def _value(self) -> str:
        # only return the token value if it exists internally and is not used
        if self.data:
            return self.value
        else:
            return ""

    def process_formdata(self, value_list):
        if value_list:
            self.value = value_list[0]
            self.data = database.get_unused_token(value_list[0])  # type: Token
