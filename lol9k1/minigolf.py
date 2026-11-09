"""
A small top down minigolf game to kill time between matches, with a shared leaderboard.

It's played either hot seat on one computer, or across the network by registered players, each on
their own computer. A network game is a log of moves (minigolf_moves): every shot is simulated in the
shooter's browser, which reports how it was played and where all the balls ended up. The other
browsers poll the game, replay the shot from how it was played and then take the reported positions,
so tiny differences in their physics can't make them disagree. The server replays the log to know
whose turn it is and checks every move against it.

Players share map packs of their own, built in the map editor (see lol9k1/minigolf_packs.py for what a pack
may hold). A shared pack's holes never change: an update is a new version, and a version is a course like any
other, 'pack:<version id>', with a Hall of Fame of its own. So rounds and running games always keep the holes
they're played on.
"""
import json
import math
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from flask import Blueprint, current_app, flash, g, render_template, request, session

from lol9k1 import events, minigolf_packs
from lol9k1.auth import auth
from lol9k1.database import get_db
from lol9k1.utilities import STYLE

bp = Blueprint('minigolf', __name__, url_prefix='/minigolf')

# The map packs that come with the game, by id: their name and number of holes. The holes themselves live in
# static/js/minigolf.js. The page hands the number of holes to the script, which refuses to play a pack
# that has a different number of holes, so a mismatch can't go unnoticed. Every pack has a leaderboard
# of its own, rounds and games remember the pack they were played on (their course).
# Packs shared by players are in the database, see course_info.
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
# Shared map packs: every player may have this many on offer at once. Withdrawn ones don't count,
# and neither do the versions an update replaces.
MAX_PACKS_PER_USER = 10
SHARED_PREFIX = 'pack:'  # a shared pack's course is 'pack:<version id>'
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
    # ?course= picks a pack, e.g. a shared one from the browser (/minigolf/packs)
    course = known_course(request.args.get('course', COURSE))
    if course is None:
        # an old link, or a version nobody played that's gone since
        flash(f"That map pack doesn't exist anymore, here's {COURSES[COURSE]['name']}.", STYLE.warning)
        course = COURSE
    courses = playable_courses()
    if course not in courses:
        # an older version or a withdrawn pack can still be played, it's just not offered
        courses[course] = course_info(course)
    board = leaderboard(course)
    return render_template('minigolf.html', page_title='Minigolf', courses=courses, course=course,
                           max_strokes=MAX_STROKES,
                           max_players=MAX_PLAYERS, course_width=COURSE_WIDTH, course_height=COURSE_HEIGHT,
                           best=board['best'], recent=board['recent'])


@bp.route('/editor')
@auth.login_required
def editor() -> str:
    """The map editor: build holes, test play them, and publish them as a shared pack or export them for
    static/js/minigolf.js. Until a pack is published it all happens in the browser."""
    return render_template('minigolf_editor.html', page_title='Minigolf map editor', courses=COURSES, course=COURSE,
                           shared=list_packs(), max_strokes=MAX_STROKES, max_players=MAX_PLAYERS,
                           course_width=COURSE_WIDTH, course_height=COURSE_HEIGHT, limits=pack_limits())


@bp.route('/api/rounds', methods=['POST'])
@auth.login_required(api=True)
def submit_round_api():
    # Rounds are taken on trust: the game runs in the browser, so any logged-in player could post
    # a perfect round. That's fine among friends at a LAN party, the checks only keep out garbage.
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return json.dumps('expected a JSON object'), 400
    course = known_course(payload.get('course', COURSE))
    if course is None and _shared_version(payload.get('course')) is not None:
        # a version nobody played that's gone since the round started, the game tells the player so
        return json.dumps(GONE_PACK), 404
    if course is None:
        return json.dumps(UNKNOWN_COURSE), 400
    holes = course_info(course)['holes']
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


UNKNOWN_COURSE = f'course must be one of {", ".join(COURSES)} or a shared pack ({SHARED_PREFIX}<version>)'
GONE_PACK = 'there is no such pack anymore, it may have been updated'


def known_course(value) -> Optional[str]:
    """The id of the course a request names, None if there's no such course (or it isn't even a string).
    It's the server's own id that's returned, so nothing a client sent gets echoed back."""
    builtin = next((course for course in COURSES if course == value), None)
    if builtin is not None:
        return builtin
    version = _shared_version(value)
    return f'{SHARED_PREFIX}{version}' if version is not None and course_info(f'{SHARED_PREFIX}{version}') else None


def _shared_version(course) -> Optional[int]:
    """The version id in a shared pack's course, None if it isn't one."""
    if not isinstance(course, str) or not course.startswith(SHARED_PREFIX):
        return None
    number = course[len(SHARED_PREFIX):]
    return int(number) if number.isascii() and number.isdigit() and len(number) < 10 else None


def course_info(course: str) -> Optional[dict]:
    """A course by its id: its name and number of holes, and for a shared pack who made it, whether new games
    can be hosted on it (playable: it's the pack's current version and it isn't withdrawn), whether the pack is
    withdrawn and the course of its current version (latest). None if there's no such course."""
    if course in COURSES:
        return {**COURSES[course], 'shared': False, 'playable': True}
    version = _shared_version(course)
    if version is None:
        return None
    cache = g.setdefault('minigolf_courses', {})
    if course not in cache:
        row = get_db().execute('''
          select p.id, p.name, p.status, p.version, v.number, v.hole_count, u.name as author
          from minigolf_pack_versions v
            join minigolf_packs p on v.pack = p.id
            join users u on p.author = u.id
          where v.id = ?
        ''', [version]).fetchone()
        cache[course] = None if row is None else _shared_course(
            row['name'] if row['version'] == version else f"{row['name']} (v{row['number']})",
            row['hole_count'], row['id'], row['author'], row['status'], row['version'], version)
    return cache[course]


def _shared_course(name: str, holes: int, pack: int, author: str, status: str, latest: int, version: int) -> dict:
    """A shared pack's version as course_info has it, from the pack and its current version (latest)."""
    return {'name': name, 'holes': holes, 'shared': True, 'pack': pack, 'author': author,
            'playable': status == 'listed' and latest == version, 'withdrawn': status != 'listed',
            'latest': f'{SHARED_PREFIX}{latest}'}


def course_name(course: str) -> str:
    info = course_info(course)
    return info['name'] if info else course


def playable_courses() -> dict:
    """The packs to pick from: the ones that come with the game, then the shared ones, newest first."""
    courses = {course: course_info(course) for course in COURSES}
    cache = g.setdefault('minigolf_courses', {})
    for pack in list_packs():
        # list_packs has all course_info needs, so it doesn't look up every pack again
        course = pack['course']
        cache[course] = _shared_course(pack['name'], pack['holes'], pack['id'], pack['author'], pack['status'],
                                       _shared_version(course), _shared_version(course))
        courses[course] = cache[course]
    return courses


def _course_arg() -> str:
    course = known_course(request.args.get('course', COURSE))
    if course is None:
        raise _ApiError(UNKNOWN_COURSE, 400)
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
            if not (minigolf_packs.is_number(x) and 0 <= x <= COURSE_WIDTH and minigolf_packs.is_number(y) and 0 <= y <= COURSE_HEIGHT):
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


def _shot_params(shot) -> dict:
    if not isinstance(shot, dict):
        raise ValueError('shot must be an object')
    params = {k: shot.get(k) for k in ('power', 'dx', 'dy', 'time')}
    if (not all(minigolf_packs.is_number(v) for v in params.values()) or not 0 <= params['power'] <= 1
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
    info = course_info(row['course'])
    if info is None:
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
        state = GameState.new(len(players), info['holes'])
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
        'course_name': course_name(game.course),
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
    return json.dumps([{'id': r['id'], 'course': r['course'], 'course_name': course_name(r['course']),
                        'status': r['status'], 'host': r['host'], 'players': json.loads(r['players']),
                        'joined': bool(r['joined'])}
                       for r in rows if not r['left_game'] and course_info(r['course'])])


@bp.route('/api/games', methods=['POST'])
@auth.login_required(api=True)
def create_game_api():
    payload = request.get_json(silent=True)
    # without a body it's a game on the default course
    course = known_course(payload.get('course', COURSE) if isinstance(payload, dict) else COURSE)
    if course is None:
        raise _ApiError(UNKNOWN_COURSE, 400)
    info = course_info(course)
    if not info['playable']:
        # a new game is on what's on offer, lobbies that are open already can still be played
        if info['withdrawn']:
            raise MoveError('that pack has been withdrawn, it can only be played hot seat now')
        raise MoveError('that is an older version of the pack, pick its latest version to host a game')
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


# ---------------------------------------------------------------- shared map packs
#
# Published from the map editor, browsed on /minigolf/packs. A pack's holes are validated and rebuilt by
# minigolf_packs.validate_holes and are never changed: an update adds a version. Versions nobody has played
# are thrown away a while after they're out of date (see _prune_versions), the others are kept for their
# rounds and games.

PACK_SORTS = {
    # most rounds on any of its versions first, packs nobody played yet newest first
    'popular': 'rounds_all desc, v.published_at desc, v.id desc',
    # the latest version first, a new name or hint doesn't make a pack new
    'new': 'v.published_at desc, v.id desc',
}
TOTAL = '(select sum(s.value) from json_each(r.strokes) s)'  # of a round r, for the queries below
# the request a pack comes in, holes and all: a bit more than the holes may take, for the JSON around them
MAX_PACK_REQUEST = minigolf_packs.MAX_BYTES * 2
# Versions every player may have stored, of all their packs, withdrawn or not. Played versions are kept
# for good, so this keeps a busy author from filling the disk: 50 versions are 3.2 MB at most.
MAX_VERSIONS_PER_USER = 50
# An unplayed version that's out of date, or of a withdrawn pack, goes after this long. Somebody may still be
# playing a hot seat round on it, which the server doesn't know about until it's saved, so it's kept for days
# rather than hours: a version takes MAX_BYTES at most and there are MAX_VERSIONS_PER_USER of them at most.
VERSION_TTL = timedelta(days=3)


class _Conflict(_ApiError):
    """A request that doesn't fit the shared packs as they are, answered with 409."""

    def __init__(self, message: str):
        super().__init__(message, 409)


def pack_limits() -> dict:
    """The limits of shared packs, for the editor to check a pack before publishing it."""
    return {'holes': minigolf_packs.MAX_HOLES, 'name': minigolf_packs.MAX_NAME, 'hint': minigolf_packs.MAX_HINT,
            'packs': MAX_PACKS_PER_USER, 'bytes': minigolf_packs.MAX_BYTES, 'tees': minigolf_packs.MAX_TEES,
            'corners': minigolf_packs.MAX_CORNERS, 'wall_corners': minigolf_packs.MAX_WALL_CORNERS,
            'lists': minigolf_packs.LIST_LIMITS, 'par': MAX_STROKES, 'bumper': minigolf_packs.MAX_BUMPER,
            'speed': minigolf_packs.MAX_SPEED, 'blades': minigolf_packs.MAX_BLADES}


def list_packs(sort: str = 'popular', pack_id: Optional[int] = None, author: Optional[int] = None) -> list[dict]:
    """The shared packs on offer, or the one with this id even if it's withdrawn. With how often and by how many
    the current version has been played, its best round, and how often any version has been played."""
    where, params = ["p.status = 'listed'"], []
    if pack_id is not None:
        where, params = ['p.id = ?'], [pack_id]
    if author is not None:
        where.append('p.author = ?')
        params.append(author)
    rows = get_db().execute(f"""
      with packs as (
        -- the course of the current version, rounds are kept by it
        select p.*, '{SHARED_PREFIX}' || p.version as course from minigolf_packs p
      )
      select p.id, p.name, p.hint, p.author, u.name as author_name, p.status, p.course, p.created_at, p.updated_at,
             v.number, v.hole_count, v.par, v.published_at,
             b.id as based_on, b.name as based_on_name, bu.name as based_on_author,
             (select count(*) from minigolf_rounds r where r.course = p.course) as rounds,
             (select count(*) from minigolf_rounds r
               where r.course in (select '{SHARED_PREFIX}' || o.id from minigolf_pack_versions o where o.pack = p.id)
             ) as rounds_all,
             (select count(distinct r.user) from minigolf_rounds r where r.course = p.course) as players,
             (select json_array({TOTAL}, ru.name) from minigolf_rounds r join users ru on r.user = ru.id
              where r.course = p.course order by {TOTAL}, r.id limit 1) as best
      from packs p
        join users u on p.author = u.id
        -- a withdrawn pack nobody played has no version left once it's pruned, but it's still the pack it was
        left join minigolf_pack_versions v on v.id = p.version
        left join minigolf_packs b on b.id = p.based_on
        left join users bu on bu.id = b.author
      where {' and '.join(where)}
      order by {PACK_SORTS.get(sort, PACK_SORTS['popular'])}
    """, params).fetchall()
    user = session.get('user_id')
    admin = bool(auth.current_user_is_admin())
    packs = []
    for r in rows:
        best = json.loads(r['best']) if r['best'] else None
        packs.append({
            'id': r['id'], 'course': r['course'], 'name': r['name'], 'hint': r['hint'],
            'author': r['author_name'], 'mine': r['author'] == user,
            'can_withdraw': r['status'] == 'listed' and (r['author'] == user or admin),
            'status': r['status'], 'version': r['number'], 'holes': r['hole_count'], 'par': r['par'],
            'based_on': {'id': r['based_on'], 'name': r['based_on_name'], 'author': r['based_on_author']}
            if r['based_on'] else None,
            'rounds': r['rounds'], 'rounds_all': r['rounds_all'], 'players': r['players'],
            'best': {'total': best[0], 'name': best[1]} if best else None,
            'created_at': r['created_at'], 'updated_at': r['updated_at'], 'published_at': r['published_at'],
        })
    return packs


def _pack_or_404(pack_id: int) -> dict:
    packs = list_packs(pack_id=pack_id)
    if not packs:
        raise _ApiError('no such pack', 404)
    return packs[0]


def _holes_of(course: str) -> list:
    version = _shared_version(course)
    row = get_db().execute('select holes from minigolf_pack_versions where id = ?', [version]).fetchone()
    return json.loads(row['holes'])


@bp.route('/packs')
@auth.login_required
def packs_page() -> str:
    """Browse the packs players share: play them, test them in the editor, withdraw your own."""
    sort = request.args.get('sort') if request.args.get('sort') in PACK_SORTS else 'popular'
    mine = request.args.get('mine') == '1'
    packs = list_packs(sort, author=session.get('user_id') if mine else None)
    return render_template('minigolf_packs.html', page_title='Minigolf map packs', packs=packs, sort=sort,
                           mine=mine, max_packs=MAX_PACKS_PER_USER, course_width=COURSE_WIDTH,
                           course_height=COURSE_HEIGHT)


@bp.route('/api/packs')
@auth.login_required(api=True)
def packs_api():
    sort = request.args.get('sort', 'popular')
    if sort not in PACK_SORTS:
        raise _ApiError(f'sort must be one of {", ".join(PACK_SORTS)}', 400)
    return json.dumps(list_packs(sort))


@bp.route('/api/packs/<int:pack_id>')
@auth.login_required(api=True)
def pack_api(pack_id: int):
    """A shared pack with the holes of its current version, withdrawn or not: for testing it in the editor."""
    pack = _pack_or_404(pack_id)
    if pack['version'] is None:
        raise _ApiError(GONE_PACK, 404)
    return json.dumps({**pack, 'holes_data': _holes_of(pack['course'])})


@bp.route('/api/courses/<course>')
@auth.login_required(api=True)
def course_api(course: str):
    """The holes of a shared pack's version, for the game to play it. The packs that come with the game
    are in static/js/minigolf.js."""
    known = known_course(course)
    info = known and course_info(known)
    if not info or not info['shared']:
        raise _ApiError(GONE_PACK, 404)
    hint = get_db().execute('select hint from minigolf_packs where id = ?', [info['pack']]).fetchone()['hint']
    return json.dumps({'course': known, 'name': info['name'], 'author': info['author'], 'hint': hint,
                       'playable': info['playable'], 'withdrawn': info['withdrawn'], 'latest': info['latest'],
                       'holes': _holes_of(known)})


def _check_pack_size() -> None:
    """Refuses the request of a pack that's too big before its body is read. Raises _ApiError."""
    if request.content_length is None:
        raise _ApiError('the request has no Content-Length', 411)
    if request.content_length > MAX_PACK_REQUEST:
        raise _ApiError(f'a pack may take {minigolf_packs.MAX_BYTES // 1024} KB at most', 413)


def _pack_payload() -> tuple[dict, str, str, list]:
    """The request of a pack that's published, and its name, hint and holes, checked. Raises _ApiError."""
    _check_pack_size()
    payload = _json_body()
    try:
        name = minigolf_packs.clean_text(payload.get('name'), 'the name of the pack', minigolf_packs.MAX_NAME)
        hint = minigolf_packs.clean_text(payload.get('hint'), 'the hint', minigolf_packs.MAX_HINT, required=False)
        holes = minigolf_packs.validate_holes(payload.get('holes'), COURSE_WIDTH, COURSE_HEIGHT, MAX_STROKES)
    except minigolf_packs.PackError as e:
        raise _ApiError(str(e), 400)
    return payload, name, hint, holes


def _prune_versions(db: sqlite3.Connection) -> None:
    """Throws away the versions nobody played or plays: out of date, or of a withdrawn pack, for a while."""
    db.execute(f"""
      delete from minigolf_pack_versions
      where not exists(select 1 from minigolf_rounds where course = '{SHARED_PREFIX}' || minigolf_pack_versions.id)
        and not exists(select 1 from minigolf_games where course = '{SHARED_PREFIX}' || minigolf_pack_versions.id)
        and (
          (select n.published_at from minigolf_pack_versions n
           where n.pack = minigolf_pack_versions.pack and n.number > minigolf_pack_versions.number
           order by n.number limit 1) < :stale
          or exists(select 1 from minigolf_packs p
                    where p.id = minigolf_pack_versions.pack and p.status = 'withdrawn' and p.updated_at < :stale)
        )
    """, {'stale': _timestamp(_now() - VERSION_TTL)})


def _add_version(db: sqlite3.Connection, user: int, pack_id: int, holes: list, moment: str) -> int:
    _prune_versions(db)
    stored = db.execute("""select count(*) from minigolf_pack_versions v join minigolf_packs p on v.pack = p.id
                           where p.author = ?""", [user]).fetchone()[0]
    if stored >= MAX_VERSIONS_PER_USER:
        db.rollback()
        raise _Conflict(f'you have {stored} versions of your packs stored, {MAX_VERSIONS_PER_USER} at most. '
                        f'Versions nobody played go {VERSION_TTL.days} days after they are replaced or withdrawn')
    number = db.execute('select coalesce(max(number), 0) + 1 from minigolf_pack_versions where pack = ?',
                        [pack_id]).fetchone()[0]
    version = db.execute("""insert into minigolf_pack_versions (pack, number, holes, hole_count, par, published_at)
                            values (?, ?, ?, ?, ?, ?)""",
                         [pack_id, number, json.dumps(holes, separators=(',', ':')), len(holes),
                          sum(h['par'] for h in holes), moment]).lastrowid
    db.execute('update minigolf_packs set version = ? where id = ?', [version, pack_id])
    return version


@bp.route('/api/packs', methods=['POST'])
@auth.login_required(api=True)
def publish_pack_api():
    """Shares a pack: {name, hint, holes, based_on}, based_on the shared pack it was made from, if any."""
    payload, name, hint, holes = _pack_payload()
    based_on = payload.get('based_on')
    user = session.get('user_id')
    db = get_db()
    if based_on is not None:
        if type(based_on) is not int:
            raise _ApiError('based_on must be the id of a shared pack', 400)
        # a pack it was made from that's gone just isn't credited
        row = db.execute('''select p.id, p.name, u.name as author, v.holes from minigolf_packs p
                              join users u on p.author = u.id
                              left join minigolf_pack_versions v on v.id = p.version
                            where p.id = ?''', [based_on]).fetchone()
        based_on = row['id'] if row else None
        # loading a shared pack in the editor counts its holes as tested, but a copy isn't a pack of your own
        if row and row['holes'] and json.loads(row['holes']) == holes:
            raise _Conflict(f"change something first, it's the same as {row['name']} by {row['author']}")
    moment = _timestamp(_now())
    try:
        # the names of a player's listed packs are unique (minigolf_packs_listed_name_unique)
        pack_id = db.execute("""insert into minigolf_packs (author, name, hint, based_on, created_at, updated_at)
                                values (?, ?, ?, ?, ?, ?)""", [user, name, hint, based_on, moment, moment]).lastrowid
    except sqlite3.IntegrityError:
        db.rollback()
        raise _Conflict(f'you already share a pack called {name}, publish an update of it instead')
    # counted after the insert, which holds the write lock, so two at once can't both get the last one
    count = db.execute("select count(*) from minigolf_packs where author = ? and status = 'listed'", [user]).fetchone()[0]
    if count > MAX_PACKS_PER_USER:
        db.rollback()
        raise _Conflict(f'you share {MAX_PACKS_PER_USER} packs already, withdraw one or publish an update instead')
    _add_version(db, user, pack_id, holes, moment)
    db.commit()
    return json.dumps(_pack_or_404(pack_id)), 201


@bp.route('/api/packs/<int:pack_id>', methods=['PUT'])
@auth.login_required(api=True)
def update_pack_api(pack_id: int):
    """A new version of a pack, by its author. With the same holes it's a new name or hint, no new version.
    Admins can withdraw a pack, but only its author can change it."""
    # who may change the pack is checked before the pack itself, only its size before that
    _check_pack_size()
    user = session.get('user_id')
    pack = _pack_or_404(pack_id)
    if not pack['mine']:
        raise _ApiError("it's not your pack, publish it as a pack of your own", 403)
    if pack['status'] != 'listed':
        raise _Conflict('the pack has been withdrawn, publish it as a new pack')
    _, name, hint, holes = _pack_payload()
    db = get_db()
    moment = _timestamp(_now())
    try:
        db.execute('update minigolf_packs set name = ?, hint = ?, updated_at = ? where id = ?',
                   [name, hint, moment, pack_id])
    except sqlite3.IntegrityError:
        db.rollback()
        raise _Conflict(f'you already share another pack called {name}')
    if holes != _holes_of(pack['course']):
        _add_version(db, user, pack_id, holes, moment)
    db.commit()
    g.pop('minigolf_courses', None)
    return json.dumps(_pack_or_404(pack_id))


@bp.route('/api/packs/<int:pack_id>', methods=['DELETE'])
@auth.login_required(api=True)
def withdraw_pack_api(pack_id: int):
    """Takes a pack off offer, by its author or an admin. Games on it, open lobbies included, can still be
    played and rounds on it still count: it's just not offered anymore."""
    pack = _pack_or_404(pack_id)
    if not pack['can_withdraw']:
        if pack['status'] != 'listed':
            raise _Conflict('the pack has been withdrawn already')
        raise _ApiError('only its author or an admin can withdraw a pack', 403)
    db = get_db()
    db.execute("update minigolf_packs set status = 'withdrawn', updated_at = ? where id = ?",
               [_timestamp(_now()), pack_id])
    _prune_versions(db)
    db.commit()
    return json.dumps('withdrawn')
