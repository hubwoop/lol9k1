import typing

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, Field
from wtforms.fields.html5 import EmailField
from wtforms.validators import InputRequired, EqualTo, Email, Optional, Length, ValidationError
from wtforms.widgets import TextInput

from lol9k1 import database
from lol9k1.auth.types import Token


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


class ValidToken(object):

    """ A validator for tokens """

    def __init__(self, message_invalid=None):
        self.message_invalid = message_invalid if message_invalid else "Invalid or used invite token"

    def __call__(self, form, field):
        maybe_matched_token = field.data
        print(f"ValidToken {field.data}")
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


class RegistrationForm(FlaskForm):

    token = TokenField(label='Token', description='Somebody sent you this!', validators=[InputRequired(), ValidToken()])

    name = StringField(
        label='Username',
        validators=[InputRequired(), UniqueUserEntry("name", "Username already registered."),
                    Length(min=3, message="Usernames must be at least 3 characters long"),
                    Length(max=30, message="Usernames have a maximum length of 30 characters.")],
        description='Please choose a name that everyone knows!',
        render_kw={"placeholder": "Your Fancy Name", "maxlength": 30, "minlength": 3})

    password = PasswordField(
        label='New Password',
        validators=[InputRequired(),
                    Length(min=8, message='Password must be at least 8 characters long.'),
                    Length(max=300, message='Password may not be longer than 300 characters.'),
                    EqualTo('confirm', message='Passwords must match')],
        description='Example of secure password:'
                    ' b̶̢̯̞̫͔͉̱̳̹̝̳̻͓̙̗̣͞ͅ(̴̙̗̙͉̞͚̯̩͞"͟͠҉̻̼̝̗̺̜̟͈̞͖͓̫̺̭̥j'
                    '̢̛̟̩͚̯͡s̷̶͏̼͇̮̺̼̰͉̘͔̩͎̹͘B̷̵̕͢͟'
                    '̰̝̟̖͉ͅŞ҉̖̯͇̬̳̮̟͕̲͙̘͡ͅo̵̴̧͔̯̖̙̗͉͚̕l͇̣͍̻̗̦͎͇͓̗̲̟̙͍͇̣̩͢͝j̴͡'
                    '҉̦̱̤̬̱̣͍͙̯͕̖̯̳̕͢k̵̹̻̘̘̦̭͓̭̱̜̩͇̜͜͠d̴͖̜̙͇͙͓͉̞͈͓̳̤͔̗͟ ',
        render_kw={"minlength": 8, "maxlength": 300})

    confirm = PasswordField(label='Repeat Password', render_kw={"minlength": 8, "maxlength": 300})

    email = EmailField(label='E-Mail',
                       validators=[Optional(), Email(), UniqueUserEntry("email", "E-Mail already registered.")],
                       description='If you should ever forget your '
                                   'password we can use your mail '
                                   'to reset it.',
                       render_kw={"placeholder": "1337-h4X0r@russia.gov"})

    gender = SelectField(label='Gender', choices=[
        ('optional', "Doesn't matter"), ('male', 'Male'), ('female', 'Female'), ('apache', 'Boeing AH-64')])


