"""
Ranks players across the whole party by their recorded match results and hands out badges.

An event counts as played once results are recorded for it. Then every participant
of it has played it, teams without a placement finished behind all placed teams.
A player scores one point for every team their team finished ahead of.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Iterable, List, Optional

import dateutil.parser
from flask import Blueprint, render_template

from lol9k1.auth import auth
from lol9k1.database import get_db

bp = Blueprint('leaderboard', __name__, url_prefix='/leaderboard')

NIGHT_OWL_FROM = time(3)
NIGHT_OWL_UNTIL = time(6)
UNDEFEATED_MIN_EVENTS = 2


@dataclass(frozen=True)
class Appearance:
    """A player taking part in an event that has results."""
    user_id: int
    user_name: str
    event_id: int
    start: Optional[datetime]
    end: Optional[datetime]
    game_name: str
    teams: int
    placement: Optional[int]
    pick_number: Optional[int]
    last_pick: Optional[int]

    @property
    def won(self) -> bool:
        return self.placement == 1

    @property
    def points(self) -> int:
        # teams finished ahead of, unplaced teams finished behind everybody placed
        if self.placement is None:
            return 0
        return max(self.teams - self.placement, 0)


@dataclass(frozen=True)
class Badge:
    icon: str
    title: str
    description: str


@dataclass
class Standing:
    user_id: int
    name: str
    points: int = 0
    wins: int = 0
    played: int = 0
    rank: int = 0
    badges: List[Badge] = field(default_factory=list)


@dataclass(frozen=True)
class Achievement:
    badge: Badge
    holders: List[str]


@dataclass(frozen=True)
class Leaderboard:
    standings: List[Standing]
    achievements: List[Achievement]


MOST_VOTES = Badge('🗳️', 'Most games voted for', 'Upvoted more games than anybody else.')
PICKED_LAST_BUT_WON = Badge('🐢', 'Picked last but won', 'Was the last pick of an event and won it anyway.')
NIGHT_OWL = Badge('🦉', 'Night owl', f'Played an event between {NIGHT_OWL_FROM:%H:%M} and {NIGHT_OWL_UNTIL:%H:%M}.')


def undefeated_in(game_name: str) -> Badge:
    return Badge('🛡️', f'Undefeated in {game_name}',
                 f'Won every {game_name} event they played, at least {UNDEFEATED_MIN_EVENTS}.')


@bp.route('/')
@auth.login_required
def leaderboard() -> str:
    board = build(load_appearances(), load_upvotes())
    return render_template('leaderboard.html', page_title='Leaderboard', leaderboard=board)


def build(appearances: Iterable[Appearance], upvotes: Iterable[tuple]) -> Leaderboard:
    """Ranks the players of ``appearances``. ``upvotes`` are (user id, user name, number of upvotes)."""
    appearances = list(appearances)
    upvotes = list(upvotes)
    standings = {}
    for appearance in appearances:
        standing = standings.setdefault(appearance.user_id, Standing(appearance.user_id, appearance.user_name))
        standing.played += 1
        standing.wins += appearance.won
        standing.points += appearance.points
    ranked = sorted(standings.values(), key=lambda s: (-s.points, -s.wins, s.played, s.name.casefold()))
    for position, standing in enumerate(ranked, start=1):
        previous = ranked[position - 2] if position > 1 else None
        if previous and (previous.points, previous.wins, previous.played) == (standing.points, standing.wins,
                                                                                standing.played):
            standing.rank = previous.rank
        else:
            standing.rank = position

    names = {user_id: name for user_id, name, _ in upvotes}
    names.update({a.user_id: a.user_name for a in appearances})
    awarded = award_badges(appearances, upvotes)
    for user_id, badges in awarded.items():
        if user_id in standings:
            standings[user_id].badges = badges
    holders = defaultdict(list)
    for user_id, badges in awarded.items():
        for badge in badges:
            holders[badge].append(names[user_id])
    achievements = [Achievement(badge, sorted(names_, key=str.casefold)) for badge, names_ in holders.items()]
    achievements.sort(key=lambda a: a.badge.title.casefold())
    return Leaderboard(ranked, achievements)


def award_badges(appearances: List[Appearance], upvotes: List[tuple]) -> dict:
    """Maps user ids to the badges they earned."""
    badges = defaultdict(list)

    most_upvotes = max((count for _, _, count in upvotes), default=0)
    if most_upvotes > 0:
        for user_id, _, count in upvotes:
            if count == most_upvotes:
                badges[user_id].append(MOST_VOTES)

    for user_id, user_appearances in _by_user(appearances).items():
        if any(a.won and a.pick_number is not None and a.pick_number == a.last_pick for a in user_appearances):
            badges[user_id].append(PICKED_LAST_BUT_WON)
        if any(played_at_night(a.start, a.end) for a in user_appearances):
            badges[user_id].append(NIGHT_OWL)
        per_game = defaultdict(list)
        for appearance in user_appearances:
            per_game[appearance.game_name].append(appearance)
        for game_name in sorted(per_game, key=str.casefold):
            games = per_game[game_name]
            if len(games) >= UNDEFEATED_MIN_EVENTS and all(a.won for a in games):
                badges[user_id].append(undefeated_in(game_name))
    return dict(badges)


def _by_user(appearances: List[Appearance]) -> dict:
    by_user = defaultdict(list)
    for appearance in appearances:
        by_user[appearance.user_id].append(appearance)
    return by_user


def played_at_night(start: Optional[datetime], end: Optional[datetime]) -> bool:
    """Whether the time between ``start`` and ``end`` overlaps the night owl hours of any day."""
    if not start or not end or end <= start:
        return False
    day = start.date() - timedelta(days=1)
    while day <= end.date():
        night_start = datetime.combine(day, NIGHT_OWL_FROM)
        night_end = datetime.combine(day, NIGHT_OWL_UNTIL)
        if start < night_end and end > night_start:
            return True
        day += timedelta(days=1)
    return False


def _parse(value) -> Optional[datetime]:
    try:
        return dateutil.parser.parse(str(value)).replace(tzinfo=None)
    except (ValueError, OverflowError):
        return None


def load_appearances() -> List[Appearance]:
    rows = get_db().execute('''
      select tp.user, u.name as user_name, e.id as event, e.start_datetime, e.end_datetime, g.name as game_name,
        (select count(*) from tournament_participants c
          where c.tournament = e.id and c.is_team_captain = 1) as teams,
        r.placement, tp.pick_number,
        (select max(l.pick_number) from tournament_participants l where l.tournament = e.id) as last_pick
      from tournament_participants tp
        join users u on tp.user = u.id
        join events e on tp.tournament = e.id
        join games g on e.game = g.id
        left join event_results r on r.event = tp.tournament and r.team = tp.team
      where exists (select 1 from event_results x where x.event = tp.tournament)
    ''').fetchall()
    return [Appearance(user_id=row['user'], user_name=row['user_name'], event_id=row['event'],
                       start=_parse(row['start_datetime']), end=_parse(row['end_datetime']),
                       game_name=row['game_name'], teams=row['teams'], placement=row['placement'],
                       pick_number=row['pick_number'], last_pick=row['last_pick'])
            for row in rows]


def load_upvotes() -> List[tuple]:
    rows = get_db().execute('''
      select u.id, u.name, count(*) from votes v join users u on v.user = u.id where v.vote = 1 group by u.id
    ''').fetchall()
    return [tuple(row) for row in rows]
