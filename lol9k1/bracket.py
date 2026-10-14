"""
Built-in single elimination brackets.

The matches of a bracket are stored in the ``matches`` table. Only the first
round stores its teams (``null`` is a bye), every later match is played by the
winners of the two matches before it. That way correcting a result can never
leave a later round with stale teams.
"""
import json
import random
from typing import List, NamedTuple, Optional

from flask import Blueprint, abort, current_app, flash, redirect, request, session, url_for, Response

import lol9k1.utilities as utilities
from lol9k1.auth import auth
from lol9k1.database import get_db
from lol9k1.events import get_creator_or_404, get_details, user_may_manage
from lol9k1.utilities import STYLE

MAX_SCORE = 9999
SINGLE_ELIMINATION = 1

bp = Blueprint('bracket', __name__, url_prefix='/event')


class BracketTeam(NamedTuple):
    id: int
    name: str
    captain: int


class Match(NamedTuple):
    id: int
    round: int
    position: int
    team1: Optional[BracketTeam]
    team2: Optional[BracketTeam]
    score1: Optional[int]
    score2: Optional[int]
    # a first round match against nobody, its team advances without playing
    bye: bool

    @property
    def winner(self) -> Optional[BracketTeam]:
        if self.bye:
            return self.team1 or self.team2
        if self.team1 is None or self.team2 is None or self.score1 is None or self.score2 is None:
            return None
        return self.team1 if self.score1 > self.score2 else self.team2


class BracketError(Exception):
    """A score can't be entered right now, the message says why."""


def enabled() -> bool:
    return current_app.config['ENABLE_BRACKETS']


def seed_order(size: int) -> List[int]:
    """
    The seeds (1-based) in bracket order, e.g. [1, 4, 2, 3] for 4 slots. Seed 1
    meets the last seed, so as long as there are more teams than half the slots,
    the byes (the seeds above the number of teams) never meet each other.
    """
    order = [1]
    while len(order) < size:
        order = [seed for s in order for seed in (s, 2 * len(order) + 1 - s)]
    return order


def round_name(round_index: int, rounds: int) -> str:
    remaining = rounds - round_index
    if remaining == 1:
        return 'Final'
    if remaining == 2:
        return 'Semifinals'
    if remaining == 3:
        return 'Quarterfinals'
    return f'Round {round_index + 1}'


def exists(event_id: int) -> bool:
    return get_db().execute('select 1 from matches where event = ? limit 1', [event_id]).fetchone() is not None


def get_teams(event_id: int) -> dict:
    rows = get_db().execute('''
      select t.id, t.name, t.captain, u.name from teams t
        join tournament_participants tp on tp.team = t.id and tp.is_team_captain = 1
        join users u on t.captain = u.id
      where tp.tournament = ?
    ''', [event_id]).fetchall()
    return {row[0]: BracketTeam(row[0], row[1] or f'Team {row[3]}', row[2]) for row in rows}


def create(event_id: int) -> None:
    """Draws a new bracket from the teams of the event, replacing an existing one."""
    team_ids = list(get_teams(event_id))
    if len(team_ids) < 2:
        raise BracketError('A bracket needs at least two teams. Assign team captains first.')
    random.shuffle(team_ids)
    size = 2
    while size < len(team_ids):
        size *= 2
    slots = [team_ids[seed - 1] if seed <= len(team_ids) else None for seed in seed_order(size)]
    db = get_db()
    db.execute('delete from matches where event = ?', [event_id])
    for position in range(size // 2):
        db.execute('insert into matches (event, round, position, team1, team2) values (?, 0, ?, ?, ?)',
                   (event_id, position, slots[2 * position], slots[2 * position + 1]))
    round_index, matches_in_round = 1, size // 4
    while matches_in_round:
        for position in range(matches_in_round):
            db.execute('insert into matches (event, round, position) values (?, ?, ?)',
                       (event_id, round_index, position))
        round_index, matches_in_round = round_index + 1, matches_in_round // 2
    db.commit()


def delete(event_id: int) -> None:
    db = get_db()
    db.execute('delete from matches where event = ?', [event_id])
    db.commit()


def load(event_id: int) -> List[List[Match]]:
    """The rounds of the bracket of an event, each a list of its matches in bracket order."""
    teams = get_teams(event_id)
    rows = get_db().execute('''
      select id, round, position, team1, team2, score1, score2 from matches
      where event = ? order by round, position
    ''', [event_id]).fetchall()
    rounds: List[List[Match]] = []
    for row in rows:
        match_id, round_index, position, team1_id, team2_id, score1, score2 = row
        if round_index == 0:
            team1, team2 = teams.get(team1_id), teams.get(team2_id)
            bye = team1 is None or team2 is None
        else:
            previous = rounds[round_index - 1]
            team1, team2 = previous[2 * position].winner, previous[2 * position + 1].winner
            bye = False
        if round_index == len(rounds):
            rounds.append([])
        rounds[round_index].append(Match(match_id, round_index, position, team1, team2, score1, score2, bye))
    return rounds


def next_match(rounds: List[List[Match]], match: Match) -> Optional[Match]:
    if match.round + 1 == len(rounds):
        return None
    return rounds[match.round + 1][match.position // 2]


def find(rounds: List[List[Match]], match_id: int) -> Optional[Match]:
    for matches in rounds:
        for match in matches:
            if match.id == match_id:
                return match
    return None


def may_enter_score(match: Match, may_manage: bool) -> bool:
    if may_manage:
        return True
    user_id = session.get('user_id')
    return any(team is not None and team.captain == user_id for team in (match.team1, match.team2))


def check_score_can_change(rounds: List[List[Match]], match: Match) -> None:
    if match.bye:
        raise BracketError('This team advances without playing.')
    if match.team1 is None or match.team2 is None:
        raise BracketError('The teams of this match are not decided yet.')
    following = next_match(rounds, match)
    if following is not None and following.score1 is not None:
        raise BracketError('The next match of the winner already has a result. Clear that one first.')


def set_score(event_id: int, match_id: int, scores: Optional[tuple]) -> None:
    db = get_db()
    score1, score2 = scores if scores else (None, None)
    db.execute('update matches set score1 = ?, score2 = ? where id = ? and event = ?',
               (score1, score2, match_id, event_id))
    db.commit()


def parse_scores(body) -> Optional[tuple]:
    """
    Parses ``{"score1": 2, "score2": 1}``, or ``{"score1": null, "score2": null}`` to clear a result.
    Raises ValueError if the body is malformed and BracketError if the scores make no winner.
    """
    if not isinstance(body, dict) or 'score1' not in body or 'score2' not in body:
        raise ValueError
    score1, score2 = body['score1'], body['score2']
    if score1 is None and score2 is None:
        return None
    for score in (score1, score2):
        if isinstance(score, bool) or not isinstance(score, int):
            raise ValueError
        if not 0 <= score <= MAX_SCORE:
            raise BracketError(f'Scores must be between 0 and {MAX_SCORE}.')
    if score1 == score2:
        raise BracketError('A match needs a winner, the scores must not be equal.')
    return score1, score2


def to_json(event_id: int, may_manage: bool) -> dict:
    """The bracket in the format of jquery.bracket plus a flat list of its matches for entering scores."""
    rounds = load(event_id)
    if not rounds:
        return {'exists': False, 'may_manage': may_manage}

    def team_json(team: Optional[BracketTeam]) -> Optional[dict]:
        return {'id': team.id, 'name': team.name} if team else None

    matches = []
    for matches_in_round in rounds:
        for match in matches_in_round:
            if match.bye:
                continue
            editable = may_enter_score(match, may_manage)
            if editable:
                try:
                    check_score_can_change(rounds, match)
                except BracketError:
                    editable = False
            matches.append({
                'id': match.id,
                'round': round_name(match.round, len(rounds)),
                'team1': team_json(match.team1),
                'team2': team_json(match.team2),
                'score1': match.score1,
                'score2': match.score2,
                'winner': match.winner.id if match.winner else None,
                'editable': editable,
            })
    champion = rounds[-1][0].winner
    return {
        'exists': True,
        'may_manage': may_manage,
        'champion': champion.name if champion else None,
        # jquery.bracket: the first round's pairings and per bracket, round and match a [score1, score2] pair
        'teams': [[match.team1.name if match.team1 else None, match.team2.name if match.team2 else None]
                  for match in rounds[0]],
        'results': [[[[match.score1, match.score2] for match in matches_in_round] for matches_in_round in rounds]],
        'matches': matches,
    }


def require_enabled_event(event_id: int) -> int:
    if not enabled():
        abort(404)
    return get_creator_or_404(event_id)


@bp.route('/<int:event_id>/bracket')
@auth.login_required
def bracket_api(event_id):
    creator = require_enabled_event(event_id)
    return json.dumps(to_json(event_id, user_may_manage(creator)))


@bp.route('/<int:event_id>/bracket', methods=['POST'])
@auth.login_required
def manage_bracket(event_id) -> Response:
    creator = require_enabled_event(event_id)
    if not user_may_manage(creator):
        flash(utilities.DFAULT_REFUSAL_MESSAGE, STYLE.warning)
        return redirect(url_for('event.event', event_id=event_id))
    action = request.form.get('action')
    if action == 'create':
        details = get_details(event_id)
        if details.state:
            flash('Finish the pick phase before drawing the bracket.', STYLE.warning)
        elif details.tournament_mode is not None and str(details.tournament_mode) != str(SINGLE_ELIMINATION):
            flash('Built-in brackets only support single elimination so far. '
                  'Link a bracket on an external website instead.', STYLE.warning)
        else:
            try:
                create(event_id)
                flash('Bracket drawn. Captains can now enter the results of their matches.', STYLE.success)
            except BracketError as e:
                flash(str(e), STYLE.warning)
    elif action == 'delete':
        delete(event_id)
        flash('Bracket deleted.', STYLE.message)
    else:
        abort(400)
    return redirect(url_for('event.event', event_id=event_id, _anchor='bracket'))


@bp.route('/<int:event_id>/match/<int:match_id>/score', methods=['POST'])
@auth.login_required
def score_api(event_id, match_id):
    creator = require_enabled_event(event_id)
    rounds = load(event_id)
    match = find(rounds, match_id)
    if match is None:
        abort(404)
    may_manage = user_may_manage(creator)
    if not may_enter_score(match, may_manage):
        return Response(json.dumps({'error': utilities.DFAULT_REFUSAL_MESSAGE}), 403, mimetype='application/json')
    try:
        scores = parse_scores(request.get_json(silent=True))
        check_score_can_change(rounds, match)
    except ValueError:
        abort(400)
    except BracketError as e:
        return Response(json.dumps({'error': str(e)}), 409, mimetype='application/json')
    set_score(event_id, match_id, scores)
    return json.dumps(to_json(event_id, may_manage))
