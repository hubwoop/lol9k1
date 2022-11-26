from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField
from wtforms.fields import EmailField
from wtforms.validators import InputRequired, EqualTo, Email, Optional, Length

from lol9k1.auth.forms.fields import TokenField
from lol9k1.auth.forms.validators import ValidToken, UniqueUserEntry


class RegistrationForm(FlaskForm):

    token = TokenField(label='Token', description='Somebody sent you this!', validators=[InputRequired(), ValidToken()])

    name = StringField(
        label='Username',
        validators=[InputRequired(), UniqueUserEntry("name", "Username already registered."),
                    Length(min=3, message="Username must be at least 3 characters long"),
                    Length(max=30, message="A Username can have a maximum length of 30 characters.")],
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
        ('0', "Doesn't matter"), ('1', 'Male'), ('2', 'Female'), ('3', 'Boeing AH-64')])
