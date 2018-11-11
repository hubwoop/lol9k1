from utilities import get_db
from slugify import slugify
from flask import Request


class GameAdder:
    def __init__(self, request: Request, session):
        self.request = request  # type: Request
        self.session = session

    def add_game_to_db(self):
        description, max_players, low_spec, available, no_drm = self.__validate_input()
        self.__add_games_row(available, description, low_spec, max_players, no_drm, self.request.form['title'])
        game = self.__add_games_vote_row()
        return game

    def __add_games_row(self, available, description, low_spec, max_players, no_drm, title):
        db = get_db()
        db.execute(
            'insert into games (name, slug, max_players, description, no_drm, available, low_spec, added_by) '
            'values (?, ?, ?, ?, ?, ?, ?, ?)',
            [title, slugify(title), max_players, description, no_drm, available, low_spec, self.session.get('user_id')]
        )
        db.commit()

    def __add_games_vote_row(self):
        db = get_db()
        game = db.execute('select id from games where name = ?', [self.request.form['title']]).fetchone()[0]
        db.execute('insert into votes (user, game, vote) values (?, ?, ?)', [self.session.get('user_id'), game, 1])
        db.commit()
        return game

    def __validate_input(self):
        max_players = None
        if 'max_players' in self.request.form:
            try:
                max_players = int(self.request.form['max_players'])
            except ValueError:
                pass
        if 'description' in self.request.form and not self.request.form['description']:
            description = None
        else:
            description = self.request.form['description']
        if 'low_spec' in self.request.form:
            low_spec = 1
        else:
            low_spec = None
        if 'available' in self.request.form:
            available = 1
        else:
            available = None
        if 'no_drm' in self.request.form:
            no_drm = 1
        else:
            no_drm = None
        return description, max_players, low_spec, available, no_drm
