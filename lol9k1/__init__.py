import os
from flask import Flask
from flaskext.markdown import Markdown


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
