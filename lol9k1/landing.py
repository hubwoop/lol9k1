import os
import random
import sqlite3

from flask import (
    Blueprint, flash, redirect, render_template, request, session, url_for
)
from markupsafe import Markup
from slugify import slugify

from lol9k1 import utilities
from lol9k1.auth import auth
from lol9k1.database import get_db
from lol9k1.utilities import STYLE

bp = Blueprint('landing', __name__)


@bp.route('/', methods=['GET'])
def landing():
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
        return render_template('authentication/login.html',
                               video_uri=url_for('static', filename=f'vid/{random_video}'))


def select_start_page(without_users_vote=False, order_by_score=False):
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


@auth.login_required
@bp.route('/add', methods=['POST'])
def add_game():
    db = get_db()
    title = request.form['title']
    cursor = db.execute('select id from games where slug = ?', [slugify(request.form['title'])])
    games_row = cursor.fetchone()
    if games_row:
        game_id = games_row[0]
        flash(
            Markup(f'Game <a href="#gameRow-{game_id}">{title}</a> has already been added!'),
            STYLE.error
        )
    else:
        game_id = add_game_to_db()
        flash(Markup(f'You added game (<a href="#gameRow-{game_id}">{title}</a>).'), STYLE.success)
    return redirect(url_for('landing.landing'))


@auth.login_required
@bp.route('/api/vote/<game>/<vote>', methods=['POST'])
def game_vote(game, vote):
    vote = int(vote)
    game = int(game)
    db = get_db()
    if abs(vote) != 1 or not db.execute('select id from games where id = ?', [game]).fetchone():
        flash(utilities.NAVY_SEAL, STYLE.warning)
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


@auth.login_required
@bp.route('/delete/game/<int:game_id>')
def delete_game(game_id: int):
    db = get_db()
    game = db.execute('select name from games where id = ?', [game_id]).fetchone()[0]
    try:
        db.execute('delete from votes where game = ?', [game_id])
        db.execute('delete from events where game = ?', [game_id])
        db.execute('delete from games where id = ?', [game_id])
        db.commit()
    except sqlite3.Error as e:
        flash(f'Something went wrong during deletion of game "{game}": {e}', STYLE.error)
    flash(f"Game {game} deleted.", STYLE.message)
    return redirect(url_for('landing.landing'))


def add_game_to_db():
    description, max_players, low_spec, available, no_drm = __validate_input()
    __add_games_row(available, description, low_spec, max_players, no_drm, request.form['title'])
    game = __add_games_vote_row()
    return game


def __add_games_row(available, description, low_spec, max_players, no_drm, title):
    db = get_db()
    db.execute(
        'insert into games (name, slug, max_players, description, no_drm, available, low_spec, added_by) '
        'values (?, ?, ?, ?, ?, ?, ?, ?)',
        [title, slugify(title), max_players, description, no_drm, available, low_spec, session.get('user_id')]
    )
    db.commit()


def __add_games_vote_row():
    db = get_db()
    game = db.execute('select id from games where name = ?', [request.form['title']]).fetchone()[0]
    db.execute('insert into votes (user, game, vote) values (?, ?, ?)', [session.get('user_id'), game, 1])
    db.commit()
    return game


def __validate_input():
    max_players = None
    if 'max_players' in request.form:
        try:
            max_players = int(request.form['max_players'])
        except ValueError:
            pass
    if 'description' in request.form and not request.form['description']:
        description = None
    else:
        description = request.form['description']
    if 'low_spec' in request.form:
        low_spec = 1
    else:
        low_spec = None
    if 'available' in request.form:
        available = 1
    else:
        available = None
    if 'no_drm' in request.form:
        no_drm = 1
    else:
        no_drm = None
    return description, max_players, low_spec, available, no_drm
