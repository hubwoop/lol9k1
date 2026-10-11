import os
import random
import sqlite3

from flask import (
    Blueprint, flash, redirect, render_template, request, session, url_for, Response, abort
)
from markupsafe import Markup
from slugify import slugify

from lol9k1 import utilities
from lol9k1.auth import auth
from lol9k1.database import get_db
from lol9k1.utilities import STYLE

bp = Blueprint('landing', __name__)


@bp.route('/', methods=['GET'])
def landing() -> str:
    if session.get('logged_in'):
        db = get_db()
        if request.args.get('not_voted', default='False') == 'True':
            cursor = db.execute(select_start_page(without_users_vote=True), [session.get('user_id')])
        elif request.args.get('order_by_score', default='False') == 'True':
            cursor = db.execute(select_start_page(order_by_score=True), [session.get('user_id')])
        else:
            cursor = db.execute(select_start_page(), [session.get('user_id')])
        game_rows = cursor.fetchall()
        return render_template('landing/start.html', game_rows=game_rows)
    else:
        this_dir = os.path.dirname(os.path.realpath(__file__))
        video_dir = os.path.join(this_dir, 'static', 'vid')
        random_video = random.choice(os.listdir(video_dir))
        return render_template('auth/login.html',
                               video_uri=url_for('static', filename=f'vid/{random_video}'))


def select_start_page(without_users_vote=False, order_by_score=False) -> str:
    return f'''
select
  games.id,
  games.name,
  games.slug,
  games.max_players,
  games.description,
  games.no_drm,
  games.low_spec,
  games.available,
  users.name as added_by_user,
  sum(votes.vote) as score,
  voted.vote as this_sessions_user_vote
from games
  inner join votes on games.id = votes.game
  inner join users on games.added_by = users.id
  left join votes voted on games.id = voted.game and voted.user = ? {'where voted.vote isnull' if without_users_vote else ''}
group by games.id
order by {'score desc' if order_by_score else 'games.name asc'}
'''


@bp.route('/add', methods=['POST'])
@auth.login_required
def add_game() -> Response:
    title = request.form['title']
    games_row = get_db().execute('select id from games where slug = ?', [slugify(title)]).fetchone()
    if games_row:
        flash(Markup('Game <a href="#gameRow-{}">{}</a> has already been added!').format(games_row[0], title),
              STYLE.error)
    else:
        game_id = add_game_to_db(title)
        flash(Markup('You added game (<a href="#gameRow-{}">{}</a>).').format(game_id, title), STYLE.success)
    return redirect(url_for('landing.landing'))


@bp.route('/api/vote/<game>/<vote>', methods=['POST'])
@auth.login_required
def game_vote(game, vote) -> Response:
    vote = int(vote)
    game = int(game)
    db = get_db()
    if abs(vote) != 1 or not db.execute('select id from games where id = ?', [game]).fetchone():
        flash(utilities.DEFAULT_REFUSAL_MESSAGE, STYLE.warning)
        return redirect(url_for('landing.landing'))
    user = session.get('user_id')
    cursor = db.execute('select vote from votes where user = ? and game = ?', [user, game])
    result = cursor.fetchone()
    if result:
        if result[0] == vote:
            flash("You already voted for that!", STYLE.error)
            return redirect(url_for('landing.landing'))
        else:
            db.execute('update votes set vote = ? where user = ? and game = ?', [vote, user, game])
            db.commit()
            flash("Your vote has been changed :)!", STYLE.success)
            return redirect(url_for('landing.landing', _anchor=f"gameRow-{game}"))
    else:
        db.execute('insert into votes (user, game, vote) values (?, ?, ?)', [user, game, vote])
        db.commit()
        flash("Thanks for voting :)", STYLE.success)
        return redirect(url_for('landing.landing', _anchor=f"gameRow-{game}"))


@bp.route('/delete/game/<int:game_id>')
@auth.login_required
@auth.admin_required
def delete_game(game_id: int) -> Response:
    db = get_db()
    row = db.execute('select name from games where id = ?', [game_id]).fetchone()
    if not row:
        abort(404)
    game = row[0]
    try:
        db.execute('delete from votes where game = ?', [game_id])
        db.execute('delete from events where game = ?', [game_id])
        db.execute('delete from games where id = ?', [game_id])
        db.commit()
    except sqlite3.Error as e:
        db.rollback()
        flash(f'Something went wrong during deletion of game "{game}": {e}', STYLE.error)
    else:
        flash(f"Game {game} deleted.", STYLE.message)
    return redirect(url_for('landing.landing'))


def add_game_to_db(title: str) -> int:
    """Adds the game from the form. The user who adds it votes for it."""
    form = request.form
    try:
        max_players = int(form['max_players'])
    except (KeyError, ValueError):
        max_players = None
    description = form.get('description') or None
    no_drm = 1 if 'no_drm' in form else None
    available = 1 if 'available' in form else None
    low_spec = 1 if 'low_spec' in form else None
    user_id = session.get('user_id')
    db = get_db()
    game_id = db.execute(
        'insert into games (name, slug, max_players, description, no_drm, available, low_spec, added_by) '
        'values (?, ?, ?, ?, ?, ?, ?, ?)',
        [title, slugify(title), max_players, description, no_drm, available, low_spec, user_id]
    ).lastrowid
    db.execute('insert into votes (user, game, vote) values (?, ?, 1)', [user_id, game_id])
    db.commit()
    return game_id
