import os

import dateutil
from flask import Flask
from flaskext.markdown import Markdown
from slugify import slugify

from lol9k1 import utilities


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        DATABASE=os.path.join(app.root_path, 'lol9k1.db'),
        SECRET_KEY=os.urandom(24),
        IGDB_API_KEY=os.environ.get('IGDB_API_KEY'),
        MAX_INVITE_TOKENS=3,
    )
    if os.environ.get('DEBUGGING', default="False").capitalize() == 'True':
        app.config['SECRET_KEY'] = 'wat'

    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile('config.py', silent=True)
    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)

    app.config.from_envvar('LOL9K1_SETTINGS', silent=True)

    Markdown(app)

    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    @app.template_filter('strftime')
    def format_date_time_string(date: str, fmt=None) -> str:
        date = dateutil.parser.parse(date)
        native = date.replace(tzinfo=None)
        the_format = '%d.%m.%y <strong>%H:%M</strong>'
        return native.strftime(the_format)

    @app.template_filter('gender')
    def translate_gender(gender: int, fmt=None) -> str:
        gender = utilities.GENDER_INT_TO_STRING[int(gender)]
        return gender

    @app.template_filter('slugify')
    def translate_gender(string: str, fmt=None) -> str:
        return slugify(string)

    from . import database
    database.init_app(app)

    from lol9k1.auth import auth
    app.register_blueprint(auth.bp)

    from . import invite
    app.register_blueprint(invite.bp)

    from . import landing
    app.register_blueprint(landing.bp)

    from . import schedule
    app.register_blueprint(schedule.bp)

    from . import admin
    app.register_blueprint(admin.bp)

    from . import game
    app.register_blueprint(game.bp)

    from . import events
    app.register_blueprint(events.bp)

    from . import tournament
    app.register_blueprint(tournament.bp)

    return app
