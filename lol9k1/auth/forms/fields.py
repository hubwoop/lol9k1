from wtforms import Field
from wtforms.widgets import TextInput

from lol9k1 import database


class TokenField(Field):
    """ Wraps text input to return TokenInfo """

    widget = TextInput()

    def _value(self) -> str:
        if self.data:
            return self.value
        else:
            return ""

    def process_formdata(self, token):
        if token:
            print(f"ProvidedTOken {token[0]}")
            self.value = token[0]
            self.data = database.get_unused_token(token[0])  # type: Token
