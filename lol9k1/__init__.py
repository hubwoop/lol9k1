import os
from flask import Flask
from flaskext.markdown import Markdown


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    configure(app, test_config)

    Markdown(app)

    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    from . import template_filters
    template_filters.register_on(app)

    from . import database
    database.init_app(app)

    from .auth import auth
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


def configure(app, test_config):
    db_path = os.environ.get(
        'LOL9K1_DB_PATH',
        os.path.join(app.root_path, 'lol9k1.db')
    )
    if bool(os.environ.get('FLASK_DEBUG', default=False)):
        secret = 'debugging'
    else:
        secret = os.environ.get('LOL9K1_SECRET_KEY', default=os.urandom(24))
    app.config.from_mapping(
        DATABASE=db_path,
        IGDB_API_KEY=os.environ.get('LOL9K1_IGDB_API_KEY', default=None),
        MAX_INVITE_TOKENS=3,
        SECRET_KEY=secret
    )
    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile('config.py', silent=True)
    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)
        app.config.from_prefixed_env()
    app.config.from_envvar('LOL9K1_SETTINGS', silent=True)
