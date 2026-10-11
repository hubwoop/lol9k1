from flask import Blueprint, render_template, abort

from lol9k1 import events
from lol9k1.auth import auth
from lol9k1.database import get_db

bp = Blueprint('game', __name__, url_prefix='/game')


@bp.route('/<game>')
@auth.login_required
def game_detail(game) -> str:
    db = get_db()
    game_row = db.execute('select * from games where slug = ?', [game]).fetchone()
    if not game_row:
        abort(404)
    return render_template('game.html', game_row=game_row, events=events.get_all_by_game(game_row['id']))


def get_all():
    db = get_db()
    return db.execute('select * from games').fetchall()
