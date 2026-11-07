"""A small top down minigolf game to kill time between matches, with a shared leaderboard."""
import functools
from datetime import datetime

from flask import Blueprint, g, jsonify, render_template, request, session

from lol9k1.auth import auth
from lol9k1.database import get_db

bp = Blueprint('minigolf', __name__, url_prefix='/minigolf')

COURSE = 'classic'
HOLES = 9  # must match the number of holes in static/js/minigolf.js
MAX_STROKES = 10  # per hole, a ball that isn't holed by then scores this
LEADERBOARD_SIZE = 10


def api_login_required(view):
    """Like auth.login_required, but answers 401 JSON instead of redirecting to the login page.

    It also leaves the redirect target after login alone, so logging in again doesn't send the
    browser to a POST only API url.
    """
    @functools.wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.user is None:
            return jsonify(error='not logged in'), 401
        return view(*args, **kwargs)
    return wrapped_view


@bp.route('/')
@auth.login_required
def minigolf() -> str:
    return render_template('minigolf.html', page_title='Minigolf', max_strokes=MAX_STROKES, **leaderboard())


@bp.route('/api/rounds', methods=['POST'])
@api_login_required
def submit_round():
    payload = request.get_json(silent=True)
    strokes = payload.get('strokes') if isinstance(payload, dict) else None
    if (not isinstance(strokes, list) or len(strokes) != HOLES
            or not all(type(s) is int and 1 <= s <= MAX_STROKES for s in strokes)):
        return jsonify(error=f'strokes must be a list of {HOLES} integers between 1 and {MAX_STROKES}'), 400
    db = get_db()
    db.execute('insert into minigolf_rounds (user, course, strokes, total, played_at) values (?, ?, ?, ?, ?)',
               [session.get('user_id'), COURSE, ','.join(map(str, strokes)), sum(strokes),
                datetime.now().strftime('%Y-%m-%d %H:%M')])
    db.commit()
    return jsonify(leaderboard()), 201


@bp.route('/api/leaderboard')
@api_login_required
def get_leaderboard():
    return jsonify(leaderboard())


def leaderboard() -> dict:
    db = get_db()
    best = db.execute('''
select users.name, min(minigolf_rounds.total) as best, count(*) as rounds
from minigolf_rounds
  inner join users on minigolf_rounds.user = users.id
where minigolf_rounds.course = ?
group by users.id
order by best asc, rounds desc, users.name asc
limit ?''', [COURSE, LEADERBOARD_SIZE]).fetchall()
    recent = db.execute('''
select users.name, minigolf_rounds.total, minigolf_rounds.played_at
from minigolf_rounds
  inner join users on minigolf_rounds.user = users.id
where minigolf_rounds.course = ?
order by minigolf_rounds.id desc
limit ?''', [COURSE, LEADERBOARD_SIZE]).fetchall()
    return {
        'best': [{'name': r['name'], 'best': r['best'], 'rounds': r['rounds']} for r in best],
        'recent': [{'name': r['name'], 'total': r['total'], 'played_at': r['played_at']} for r in recent],
    }
