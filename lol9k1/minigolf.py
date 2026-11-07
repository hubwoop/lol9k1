"""
A small top down minigolf game to kill time between matches, with a shared leaderboard.

It's played either hot seat on one computer, or across the network by registered players, each on
their own computer. A network game is a log of moves (minigolf_moves): every shot is simulated in the
shooter's browser, which reports how it was played and where all the balls ended up. The other
browsers poll the game, replay the shot from how it was played and then take the reported positions,
so tiny differences in their physics can't make them disagree. The server replays the log to know
whose turn it is and checks every move against it.
"""
import json
import math
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from flask import Blueprint, current_app, render_template, request, session

from lol9k1 import events
from lol9k1.auth import auth
from lol9k1.database import get_db

bp = Blueprint('minigolf', __name__, url_prefix='/minigolf')

# The map packs to choose from, by id: their name and number of holes. The holes themselves live in
# static/js/minigolf.js. The page hands the number of holes to the script, which refuses to play a pack
# that has a different number of holes, so a mismatch can't go unnoticed. Every pack has a leaderboard
# of its own, rounds and games remember the pack they were played on (their course).
COURSES = {
    'classic': {'name': 'Classic', 'holes': 9},
    # everybody tees off from a different side, aims at the same cup and gets in each other's way
    'brawl': {'name': 'Bumper Brawl', 'holes': 9},
}
COURSE = 'classic'  # the default
HOLES = COURSES[COURSE]['holes']
MAX_STROKES = 10  # per hole, a ball that isn't holed by then scores this
LEADERBOARD_SIZE = 10
# per game, hot seat and network alike. The tees are shared once there are more players than a hole has,
# and the script has a colour for up to 8 players.
MAX_PLAYERS = 4
MIN_NETWORK_PLAYERS = 2
# the others may skip a player who hasn't putted for this long, so a closed laptop can't stall a game
TURN_TIMEOUT = timedelta(seconds=90)
# lobbies nobody started for this long aren't offered for joining anymore
LOBBY_TTL = timedelta(hours=2)
MAX_PENALTIES = 20  # for the shooter's ball per shot, a sanity limit for splashes
# the course is as big as the canvas it's drawn on, balls can't be anywhere else
COURSE_WIDTH = 640
COURSE_HEIGHT = 400
MAX_SHOT_TIME = 24 * 60 * 60  # seconds on the course clock, which starts over on every hole

# Every finished round of the course with its total, the base of both leaderboards.
# A module constant that's put into the queries below as a CTE, never user input: their values
# go in as ? parameters.
ROUNDS = '''
      select r.id, r.user, u.name, r.played_at, (select sum(s.value) from json_each(r.strokes) s) as total
      from minigolf_rounds r
        join users u on r.user = u.id
      where r.course = ?
'''


@bp.route('/')
@auth.login_required
def minigolf() -> str:
    board = leaderboard(COURSE)
    return render_template('minigolf.html', page_title='Minigolf', courses=COURSES, course=COURSE,
                           max_strokes=MAX_STROKES,
                           max_players=MAX_PLAYERS, course_width=COURSE_WIDTH, course_height=COURSE_HEIGHT,
                           best=board['best'], recent=board['recent'])


@bp.route('/api/rounds', methods=['POST'])
@auth.login_required(api=True)
def submit_round_api():
    # Rounds are taken on trust: the game runs in the browser, so any logged-in player could post
    # a perfect round. That's fine among friends at a LAN party, the checks only keep out garbage.
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return json.dumps('expected a JSON object'), 400
    course = known_course(payload.get('course', COURSE))
    if course is None:
        return json.dumps(f'course must be one of {", ".join(COURSES)}'), 400
    holes = COURSES[course]['holes']
    strokes = payload.get('strokes')
    if (not isinstance(strokes, list) or len(strokes) != holes
            or not all(type(s) is int and 1 <= s <= MAX_STROKES for s in strokes)):
        return json.dumps(f'strokes must be a list of {holes} integers between 1 and {MAX_STROKES}'), 400
    db = get_db()
    save_round(db, session.get('user_id'), course, strokes)
    db.commit()
    return json.dumps(leaderboard(course)), 201


def save_round(db: sqlite3.Connection, user: int, course: str, strokes: list[int]) -> None:
    db.execute('''insert into minigolf_rounds (user, course, strokes, played_at) values (?, ?, ?, ?)''',
               [user, course, json.dumps(strokes), datetime.now().strftime(events.EVENT_DATETIME_FORMAT)])


def known_course(value) -> Optional[str]:
    """The id of the course a request names, None if there's no such course (or it isn't even a string).
    It's the server's own id that's returned, so nothing a client sent gets echoed back."""
    return next((course for course in COURSES if course == value), None)


def _course_arg() -> str:
    course = known_course(request.args.get('course', COURSE))
    if course is None:
        raise _ApiError(f'course must be one of {", ".join(COURSES)}', 400)
    return course


@bp.route('/api/leaderboard')
@auth.login_required(api=True)
def leaderboard_api():
    return json.dumps(leaderboard(_course_arg()))


def leaderboard(course: str) -> dict:
    """On this course, the best round of every player, and the latest round of every player, most recent first."""
    db = get_db()
    best = db.execute(f'''
      with rounds as ({ROUNDS})
      select name, min(total) as best, count(*) as rounds from rounds
      group by user
      order by best asc, rounds desc, name asc
      limit ?
    ''', [course, LEADERBOARD_SIZE]).fetchall()
    recent = db.execute(f'''
      with rounds as ({ROUNDS})
      select name, total, played_at from rounds
      where id in (select max(id) from rounds group by user)
      order by id desc
      limit ?
    ''', [course, LEADERBOARD_SIZE]).fetchall()
    return {
        'course': course,
        'best': [{'name': r['name'], 'best': r['best'], 'rounds': r['rounds']} for r in best],
        'recent': [{'name': r['name'], 'total': r['total'], 'played_at': r['played_at']} for r in recent],
    }


# ---------------------------------------------------------------- network games
#
# The rules below mirror the ones in static/js/minigolf.js (endOfShot, startHole, finishHole),
# both sides have to agree on whose turn it is.

class MoveError(Exception):
    """A move that doesn't fit the game, answered with 409."""


def fresh_ball() -> dict:
    return {'x': None, 'y': None, 'strokes': 0, 'sunk': False, 'out': False, 'on': False}


@dataclass
class GameState:
    """Where a running game is at, replayed from its moves. Players are referred to by seat."""
    players: int
    holes: int = HOLES
    hole: int = 0
    balls: list = field(default_factory=list)
    scores: list = field(default_factory=list)  # per seat, the strokes on each finished hole
    left: list = field(default_factory=list)
    order: list = field(default_factory=list)  # tee order on the current hole
    turn: Optional[int] = None
    finished: bool = False

    @classmethod
    def new(cls, players: int, holes: int = HOLES) -> 'GameState':
        state = cls(players, holes, scores=[[] for _ in range(players)], left=[False] * players)
        state._start_hole()
        return state

    def done(self, seat: int) -> bool:
        ball = self.balls[seat]
        return self.left[seat] or ball['sunk'] or ball['out']

    def _start_hole(self) -> None:
        self.balls = [fresh_ball() for _ in range(self.players)]
        # honours: best score on the previous hole tees off first
        previous = self.hole - 1
        self.order = sorted(range(self.players), key=lambda s: (self.scores[s][previous] if self.hole else 0, s))
        playing = [s for s in self.order if not self.left[s]]
        if playing:
            self.turn = playing[0]
        else:
            self.turn = None
            self.finished = True

    def _finish_hole(self) -> None:
        for seat, ball in enumerate(self.balls):
            self.scores[seat].append(min(ball['strokes'], MAX_STROKES))
        self.hole += 1
        if self.hole == self.holes:
            self.turn = None
            self.finished = True
        else:
            self._start_hole()

    def _next_turn(self, after: int) -> None:
        """The next player in honour order who still has to play, or on to the next hole."""
        at = self.order.index(after)
        for i in range(1, self.players + 1):
            candidate = self.order[(at + i) % self.players]
            if not self.done(candidate):
                self.turn = candidate
                return
        self._finish_hole()

    def shot(self, seat: int, hole: int, balls: list) -> list:
        """Plays a shot of the player in this seat that left the balls like this, returns them as kept."""
        if self.finished:
            raise MoveError('the game is over')
        if hole != self.hole:
            raise MoveError(f'the game is on hole {self.hole + 1}')
        if seat != self.turn:
            raise MoveError("it's not your turn")
        if not isinstance(balls, list) or len(balls) != self.players:
            raise ValueError(f'balls must be a list of {self.players} balls')
        kept = []
        for i, (old, new) in enumerate(zip(self.balls, balls)):
            shooter = i == seat
            # a ball that isn't in play can't be touched: not teed off yet, holed, picked up or its player left
            if not shooter and (not old['on'] or self.done(i)):
                kept.append(old)
                continue
            if not isinstance(new, dict):
                raise ValueError('a ball must be an object')
            x, y, strokes, sunk = new.get('x'), new.get('y'), new.get('strokes'), new.get('sunk')
            if not (_is_number(x) and 0 <= x <= COURSE_WIDTH and _is_number(y) and 0 <= y <= COURSE_HEIGHT):
                raise ValueError('a ball must be on the course')
            if type(strokes) is not int or type(sunk) is not bool:
                raise ValueError('strokes must be an integer and sunk a boolean')
            # the shooter takes a stroke and maybe penalties. Somebody else's ball can only be
            # knocked into the water, once, and can't be holed for them.
            least, most = (old['strokes'] + 1, old['strokes'] + 1 + MAX_PENALTIES) if shooter \
                else (old['strokes'], old['strokes'] + 1)
            if not least <= strokes <= most:
                raise ValueError(f'ball {i} can\'t have taken {strokes} strokes')
            if sunk and not shooter:
                raise ValueError("only the shooter's ball can be holed")
            out = shooter and not sunk and strokes >= MAX_STROKES
            kept.append({'x': x, 'y': y, 'strokes': min(strokes, MAX_STROKES) if out else strokes,
                         'sunk': sunk, 'out': out, 'on': True})
        self.balls = kept
        self._next_turn(seat)
        return kept

    def leave(self, seat: int) -> None:
        if self.finished:
            raise MoveError('the game is over')
        if self.left[seat]:
            raise MoveError('already left the game')
        self.left[seat] = True
        if not any(not left for left in self.left):
            self.turn = None
            self.finished = True
        elif self.turn == seat:
            self._next_turn(seat)


def _is_number(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _shot_params(shot) -> dict:
    if not isinstance(shot, dict):
        raise ValueError('shot must be an object')
    params = {k: shot.get(k) for k in ('power', 'dx', 'dy', 'time')}
    if (not all(_is_number(v) for v in params.values()) or not 0 <= params['power'] <= 1
            or abs(math.hypot(params['dx'], params['dy']) - 1) > 1e-6 or not 0 <= params['time'] <= MAX_SHOT_TIME):
        raise ValueError('shot must have a power between 0 and 1, a direction dx, dy of length 1 '
                         f'and a time between 0 and {MAX_SHOT_TIME}')
    return params


def _now() -> datetime:
    return datetime.now()


def _timestamp(moment: datetime) -> str:
    return moment.isoformat(timespec='seconds')


@dataclass
class Game:
    id: int
    course: str
    status: str
    host: int
    created_at: str
    started_at: Optional[str]
    players: list  # sqlite3.Row of user, name, in seat order
    moves: list    # dicts of seq, user, seat, kind, data, played_at
    state: Optional[GameState]  # None in the lobby

    def seat_of(self, user: int) -> Optional[int]:
        return next((i for i, p in enumerate(self.players) if p['user'] == user), None)

    def last_activity(self) -> datetime:
        return datetime.fromisoformat(self.moves[-1]['played_at'] if self.moves else self.started_at)

    def can_skip(self, user: int) -> bool:
        """Whether this player may skip whoever's turn it is, because they've been idle for too long."""
        seat = self.seat_of(user)
        return (self.status == 'playing' and self.state.turn is not None and seat is not None
                and not self.state.left[seat] and seat != self.state.turn
                and _now() - self.last_activity() >= TURN_TIMEOUT)


def load_game(game_id: int) -> Optional[Game]:
    """The game, None if there's no such game or it's on a course this server doesn't have (anymore)."""
    db = get_db()
    row = db.execute('select * from minigolf_games where id = ?', [game_id]).fetchone()
    if row is None:
        return None
    if row['course'] not in COURSES:
        # a pack that was renamed or retired: without its holes the game can't be replayed
        current_app.logger.warning('minigolf game %s is on the unknown course %r', game_id, row['course'])
        return None
    players = db.execute('''
      select p.user, u.name from minigolf_game_players p
        join users u on p.user = u.id
      where p.game = ?
      order by p.id
    ''', [game_id]).fetchall()
    seats = {p['user']: i for i, p in enumerate(players)}
    moves = [{'seq': m['seq'], 'user': m['user'], 'seat': seats[m['user']], 'kind': m['kind'],
              'data': json.loads(m['data']) if m['data'] else None, 'played_at': m['played_at']}
             for m in db.execute('select * from minigolf_moves where game = ? order by seq', [game_id])]
    state = None
    if row['status'] != 'lobby':
        state = GameState.new(len(players), COURSES[row['course']]['holes'])
        for move in moves:
            if move['kind'] == 'shot':
                state.shot(move['seat'], move['data']['hole'], move['data']['balls'])
            else:
                state.leave(move['seat'])
    return Game(row['id'], row['course'], row['status'], row['host'], row['created_at'], row['started_at'],
                players, moves, state)


def game_view(game: Game, since: int = 0) -> dict:
    """A game as the browsers see it, with the moves from seq ``since`` on."""
    user = session.get('user_id')
    state = game.state
    view = {
        'id': game.id,
        'course': game.course,
        'status': game.status,
        'host': next((p['name'] for p in game.players if p['user'] == game.host), None),
        'is_host': game.host == user,
        'me': game.seat_of(user),
        'players': [{'seat': i, 'name': p['name'], 'left': bool(state and state.left[i]),
                     'scores': state.scores[i] if state else []}
                    for i, p in enumerate(game.players)],
        'seq': len(game.moves),
    }
    if state:
        view.update({
            'hole': state.hole,
            'turn': state.turn,
            'balls': state.balls,
            'can_skip': game.can_skip(user),
            'moves': [{'seq': m['seq'], 'kind': m['kind'], 'seat': m['seat'], **(m['data'] or {})}
                      for m in game.moves[since:]],
        })
    return view


class _ApiError(Exception):
    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.status = status


def _game_or_404(game_id: int) -> Game:
    game = load_game(game_id)
    if game is None:
        raise _ApiError('no such game', 404)
    return game


@bp.errorhandler(_ApiError)
def _api_error(error: _ApiError):
    return json.dumps(str(error)), error.status


@bp.errorhandler(MoveError)
def _move_error(error: MoveError):
    return json.dumps(str(error)), 409


def _json_body() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise _ApiError('expected a JSON object', 400)
    return payload


@bp.route('/api/games')
@auth.login_required(api=True)
def games_api():
    """The lobbies that can be joined, and the games the player is in."""
    user = session.get('user_id')
    rows = get_db().execute('''
      select g.id, g.course, g.status, g.created_at, h.name as host,
             (select json_group_array(name) from (
               select u.name from minigolf_game_players p join users u on p.user = u.id
               where p.game = g.id order by p.id)) as players,
             exists(select 1 from minigolf_game_players p where p.game = g.id and p.user = ?) as joined,
             exists(select 1 from minigolf_moves m where m.game = g.id and m.user = ? and m.kind = 'leave') as left_game
      from minigolf_games g
        join users h on g.host = h.id
      where g.status = 'lobby' and g.created_at >= ?
         or g.status = 'playing' and exists(select 1 from minigolf_game_players p where p.game = g.id and p.user = ?)
      order by g.id desc
    ''', [user, user, _timestamp(_now() - LOBBY_TTL), user]).fetchall()
    return json.dumps([{'id': r['id'], 'course': r['course'], 'status': r['status'], 'host': r['host'], 'players': json.loads(r['players']),
                        'joined': bool(r['joined'])}
                       for r in rows if not r['left_game'] and r['course'] in COURSES])


@bp.route('/api/games', methods=['POST'])
@auth.login_required(api=True)
def create_game_api():
    payload = request.get_json(silent=True)
    # without a body it's a game on the default course
    course = known_course(payload.get('course', COURSE) if isinstance(payload, dict) else COURSE)
    if course is None:
        raise _ApiError(f'course must be one of {", ".join(COURSES)}', 400)
    db = get_db()
    # lobbies nobody started in time aren't offered anymore, so they can go. Played games are kept
    # with their moves, it's one row per putt and a LAN party doesn't putt that much.
    stale = _timestamp(_now() - LOBBY_TTL)
    db.execute('''delete from minigolf_game_players where game in (
                    select id from minigolf_games where status = 'lobby' and created_at < ?)''', [stale])
    db.execute("delete from minigolf_games where status = 'lobby' and created_at < ?", [stale])
    cursor = db.execute('insert into minigolf_games (course, host, status, created_at) values (?, ?, ?, ?)',
                        [course, session.get('user_id'), 'lobby', _timestamp(_now())])
    db.execute('insert into minigolf_game_players (game, user) values (?, ?)', [cursor.lastrowid, session.get('user_id')])
    db.commit()
    return json.dumps(game_view(load_game(cursor.lastrowid))), 201


@bp.route('/api/games/<int:game_id>')
@auth.login_required(api=True)
def game_api(game_id: int):
    since = request.args.get('since', default=0, type=int)
    return json.dumps(game_view(_game_or_404(game_id), max(0, since)))


@bp.route('/api/games/<int:game_id>/join', methods=['POST'])
@auth.login_required(api=True)
def join_game_api(game_id: int):
    user = session.get('user_id')
    game = _game_or_404(game_id)
    if game.seat_of(user) is not None:
        return json.dumps(game_view(game))
    db = get_db()
    try:
        db.execute('insert into minigolf_game_players (game, user) values (?, ?)', [game_id, user])
    except sqlite3.IntegrityError:
        db.rollback()
        raise MoveError('already joined')
    # checked after the insert, which holds the write lock, so two joins at once can't both get the last seat
    status = db.execute('select status from minigolf_games where id = ?', [game_id]).fetchone()
    count = db.execute('select count(*) from minigolf_game_players where game = ?', [game_id]).fetchone()[0]
    if status is None or status['status'] != 'lobby':
        db.rollback()
        raise MoveError('the game has already started')
    if count > MAX_PLAYERS:
        db.rollback()
        raise MoveError(f'the game is full, {MAX_PLAYERS} players at most')
    db.commit()
    return json.dumps(game_view(load_game(game_id)))


@bp.route('/api/games/<int:game_id>/start', methods=['POST'])
@auth.login_required(api=True)
def start_game_api(game_id: int):
    game = _game_or_404(game_id)
    if game.host != session.get('user_id'):
        raise _ApiError('only the host can start the game', 403)
    db = get_db()
    updated = db.execute('''update minigolf_games set status = 'playing', started_at = ? where id = ? and status = 'lobby' ''',
                         [_timestamp(_now()), game_id]).rowcount
    count = db.execute('select count(*) from minigolf_game_players where game = ?', [game_id]).fetchone()[0]
    if not updated:
        db.rollback()
        raise MoveError('the game has already started')
    if count < MIN_NETWORK_PLAYERS:
        db.rollback()
        raise MoveError(f'waiting for players, it takes {MIN_NETWORK_PLAYERS} to play over the network')
    db.commit()
    return json.dumps(game_view(load_game(game_id)))


@bp.route('/api/games/<int:game_id>/leave', methods=['POST'])
@auth.login_required(api=True)
def leave_game_api(game_id: int):
    user = session.get('user_id')
    game = _game_or_404(game_id)
    seat = game.seat_of(user)
    if seat is None:
        raise _ApiError("you're not playing in this game", 403)
    db = get_db()
    if game.status == 'lobby':
        if game.host == user:
            # the host leaving calls the game off
            db.execute('delete from minigolf_game_players where game = ?', [game_id])
            db.execute("delete from minigolf_games where id = ? and status = 'lobby'", [game_id])
        else:
            db.execute('delete from minigolf_game_players where game = ? and user = ?', [game_id, user])
        status = db.execute('select status from minigolf_games where id = ?', [game_id]).fetchone()
        if status is not None and status['status'] != 'lobby':
            db.rollback()
            raise MoveError('the game has just started, try again')
        db.commit()
        return json.dumps('left'), 200
    _add_move(game, user, seat, 'leave', None)
    return json.dumps(game_view(load_game(game_id)))


@bp.route('/api/games/<int:game_id>/skip', methods=['POST'])
@auth.login_required(api=True)
def skip_player_api(game_id: int):
    """Takes the player whose turn it is out of the game, once they've been idle for TURN_TIMEOUT."""
    payload = _json_body()
    game = _game_or_404(game_id)
    if game.status != 'playing':
        raise MoveError('the game is not running')
    if payload.get('seat') != game.state.turn or payload.get('seq') != len(game.moves):
        raise MoveError("that player's turn is over")
    if not game.can_skip(session.get('user_id')):
        raise MoveError(f"you can skip a player who hasn't played for {TURN_TIMEOUT.seconds} seconds")
    seat = game.state.turn
    _add_move(game, game.players[seat]['user'], seat, 'leave', {'skipped_by': session.get('user_id')})
    return json.dumps(game_view(load_game(game_id)))


@bp.route('/api/games/<int:game_id>/moves', methods=['POST'])
@auth.login_required(api=True)
def shot_api(game_id: int):
    """A shot of the player whose turn it is: how it was played and where all the balls ended up."""
    payload = _json_body()
    user = session.get('user_id')
    game = _game_or_404(game_id)
    seat = game.seat_of(user)
    if seat is None:
        raise _ApiError("you're not playing in this game", 403)
    if game.status != 'playing':
        raise MoveError('the game is not running')
    if payload.get('seq') != len(game.moves):
        raise MoveError('something happened in the meantime')
    hole = payload.get('hole')
    if type(hole) is not int:
        raise _ApiError('hole must be an integer', 400)
    try:
        shot = _shot_params(payload.get('shot'))
        balls = game.state.shot(seat, hole, payload.get('balls'))
    except ValueError as e:
        raise _ApiError(str(e), 400)
    _add_move(game, user, seat, 'shot', {'hole': hole, 'shot': shot, 'balls': balls})
    return json.dumps(game_view(load_game(game_id), since=payload['seq'])), 201


def _add_move(game: Game, user: int, seat: int, kind: str, data: Optional[dict]) -> None:
    """Appends a move to the game, and saves everyone's rounds if it ended it. A shot is applied already."""
    if kind == 'leave':
        game.state.leave(seat)
    db = get_db()
    try:
        db.execute('insert into minigolf_moves (game, seq, user, kind, data, played_at) values (?, ?, ?, ?, ?, ?)',
                   [game.id, len(game.moves), user, kind, json.dumps(data) if data is not None else None,
                    _timestamp(_now())])
    except sqlite3.IntegrityError:
        # somebody else's move got in first
        db.rollback()
        raise MoveError('something happened in the meantime')
    if game.state.finished:
        db.execute("update minigolf_games set status = 'finished' where id = ?", [game.id])
        for i, player in enumerate(game.players):
            if not game.state.left[i]:
                save_round(db, player['user'], game.course, game.state.scores[i])
    db.commit()
