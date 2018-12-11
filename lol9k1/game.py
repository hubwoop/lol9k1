from flask import (Blueprint, render_template)

from lol9k1 import events, auth
from lol9k1.database import get_db

bp = Blueprint('game', __name__, url_prefix='/game')


@auth.login_required
@bp.route('/<game>')
def game_detail(game):
    db = get_db()
    game_row = db.execute('select * from games where slug = ?', [game]).fetchone()
    games_events = events.get_all_by_game(game_row[0])
    return render_template('game.html', game_row=game_row, page_title=game_row[1], events=games_events)
