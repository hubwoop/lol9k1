"""A small top down minigolf game to kill time between matches, with a shared leaderboard."""
import json
from datetime import datetime

from flask import Blueprint, render_template, request, session

from lol9k1 import events
from lol9k1.auth import auth
from lol9k1.database import get_db

bp = Blueprint('minigolf', __name__, url_prefix='/minigolf')

COURSE = 'classic'
# The course itself lives in static/js/minigolf.js. The page hands HOLES to the script, which refuses
# to start if its course has a different number of holes, so a mismatch can't go unnoticed.
HOLES = 9
MAX_STROKES = 10  # per hole, a ball that isn't holed by then scores this
LEADERBOARD_SIZE = 10

# Every finished round of the course with its total, the base of both leaderboards.
ROUNDS = '''
      select r.id, r.user, u.name, r.played_at, (select sum(s.value) from json_each(r.strokes) s) as total
      from minigolf_rounds r
        join users u on r.user = u.id
      where r.course = ?
'''


@bp.route('/')
@auth.login_required
def minigolf() -> str:
    board = leaderboard()
    return render_template('minigolf.html', page_title='Minigolf', holes=HOLES, max_strokes=MAX_STROKES,
                           best=board['best'], recent=board['recent'])


@bp.route('/api/rounds', methods=['POST'])
@auth.login_required(api=True)
def submit_round_api():
    # Rounds are taken on trust: the game runs in the browser, so any logged-in player could post
    # a perfect round. That's fine among friends at a LAN party, the checks only keep out garbage.
    payload = request.get_json(silent=True)
    strokes = payload.get('strokes') if isinstance(payload, dict) else None
    if (not isinstance(strokes, list) or len(strokes) != HOLES
            or not all(type(s) is int and 1 <= s <= MAX_STROKES for s in strokes)):
        return json.dumps(f'strokes must be a list of {HOLES} integers between 1 and {MAX_STROKES}'), 400
    db = get_db()
    db.execute('''insert into minigolf_rounds (user, course, strokes, played_at) values (?, ?, ?, ?)''',
               [session.get('user_id'), COURSE, json.dumps(strokes),
                datetime.now().strftime(events.EVENT_DATETIME_FORMAT)])
    db.commit()
    return json.dumps(leaderboard()), 201


@bp.route('/api/leaderboard')
@auth.login_required(api=True)
def leaderboard_api():
    return json.dumps(leaderboard())


def leaderboard() -> dict:
    """The best round of every player, and the latest round of every player, most recent first."""
    db = get_db()
    best = db.execute(f'''
      with rounds as ({ROUNDS})
      select name, min(total) as best, count(*) as rounds from rounds
      group by user
      order by best asc, rounds desc, name asc
      limit ?
    ''', [COURSE, LEADERBOARD_SIZE]).fetchall()
    recent = db.execute(f'''
      with rounds as ({ROUNDS})
      select name, total, played_at from rounds
      where id in (select max(id) from rounds group by user)
      order by id desc
      limit ?
    ''', [COURSE, LEADERBOARD_SIZE]).fetchall()
    return {
        'best': [{'name': r['name'], 'best': r['best'], 'rounds': r['rounds']} for r in best],
        'recent': [{'name': r['name'], 'total': r['total'], 'played_at': r['played_at']} for r in recent],
    }
