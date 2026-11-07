"""
Ranks players across the whole party by their recorded match results and hands out badges.

An event counts as played once results are recorded for it. Then every participant
of it has played it. A player scores one point for every team their team beat,
i.e. every team placed lower than theirs.
"""
from collections import defaultdict
from datetime import datetime, time, timedelta
from typing import Dict, Iterable, List, NamedTuple, Optional

from flask import Blueprint, render_template

from lol9k1 import events
from lol9k1.auth import auth
from lol9k1.database import get_db

bp = Blueprint('leaderboard', __name__, url_prefix='/leaderboard')

NIGHT_OWL_FROM = time(3)
NIGHT_OWL_UNTIL = time(6)
UNDEFEATED_MIN_EVENTS = 2


class Appearance(NamedTuple):
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
        """One point per team beaten. Placement 1 of 4 beats 3 teams, placement 4 of 4 beats none."""
        if self.placement is None:
            return 0
        return max(self.teams - self.placement, 0)


class Upvotes(NamedTuple):
    user_id: int
    user_name: str
    count: int


class Badge(NamedTuple):
    icon: str
    title: str
    description: str


class Standing(NamedTuple):
    user_id: int
    name: str
    points: int
    wins: int
    played: int
    rank: int
    badges: List[Badge]


class Achievement(NamedTuple):
    badge: Badge
    holders: List[str]


class Leaderboard(NamedTuple):
    standings: List[Standing]
    achievements: List[Achievement]


MOST_VOTES = Badge('🗳️', 'Most games voted for', 'Upvoted more games than any other player.')
PICKED_LAST_BUT_WON = Badge('🐢', 'Picked last but won', 'Was the last pick of an event and won it anyway.')
NIGHT_OWL = Badge('🦉', 'Night owl', f'Played an event between {NIGHT_OWL_FROM:%H:%M} and {NIGHT_OWL_UNTIL:%H:%M}.')


def undefeated_in(game_name: str) -> Badge:
    return Badge('🛡️', f'Undefeated in {game_name}',
                 f'Won every {game_name} event they played, at least {UNDEFEATED_MIN_EVENTS}.')


@bp.route('/')
@auth.login_required
def leaderboard() -> str:
    board = rank_players(load_appearances(), load_upvotes())
    return render_template('leaderboard.html', page_title='Leaderboard', leaderboard=board)


def rank_players(appearances: Iterable[Appearance], upvotes: Iterable[Upvotes]) -> Leaderboard:
    """Ranks everybody who played an event with results. Only players can earn badges."""
    by_user = _by_user(appearances)
    badges = award_badges(by_user, upvotes)
    totals = []
    for user_id, user_appearances in by_user.items():
        totals.append((user_id, user_appearances[0].user_name,
                       sum(a.points for a in user_appearances),
                       sum(a.won for a in user_appearances),
                       len(user_appearances)))
    totals.sort(key=lambda t: (-t[2], -t[3], t[4], t[1].casefold()))

    standings = []
    for position, (user_id, name, points, wins, played) in enumerate(totals, start=1):
        previous = standings[-1] if standings else None
        if previous and (previous.points, previous.wins, previous.played) == (points, wins, played):
            rank = previous.rank
        else:
            rank = position
        standings.append(Standing(user_id, name, points, wins, played, rank, badges.get(user_id, [])))

    holders = defaultdict(list)
    for standing in standings:
        for badge in standing.badges:
            holders[badge].append(standing.name)
    achievements = [Achievement(badge, sorted(names, key=str.casefold)) for badge, names in holders.items()]
    achievements.sort(key=lambda a: a.badge.title.casefold())
    return Leaderboard(standings, achievements)


def award_badges(by_user: Dict[int, List[Appearance]], upvotes: Iterable[Upvotes]) -> Dict[int, List[Badge]]:
    """Maps the ids of players (users in ``by_user``) to the badges they earned."""
    badges = defaultdict(list)

    player_upvotes = [u for u in upvotes if u.user_id in by_user]
    most_upvotes = max((u.count for u in player_upvotes), default=0)
    if most_upvotes > 0:
        for upvote in player_upvotes:
            if upvote.count == most_upvotes:
                badges[upvote.user_id].append(MOST_VOTES)

    for user_id, user_appearances in by_user.items():
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


def _by_user(appearances: Iterable[Appearance]) -> Dict[int, List[Appearance]]:
    by_user = defaultdict(list)
    for appearance in appearances:
        by_user[appearance.user_id].append(appearance)
    return dict(by_user)


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
                       start=events.parse_stored_datetime(row['start_datetime']),
                       end=events.parse_stored_datetime(row['end_datetime']),
                       game_name=row['game_name'], teams=row['teams'], placement=row['placement'],
                       pick_number=row['pick_number'], last_pick=row['last_pick'])
            for row in rows]


def load_upvotes() -> List[Upvotes]:
    rows = get_db().execute('''
      select u.id, u.name, count(*) from votes v join users u on v.user = u.id where v.vote = 1 group by u.id
    ''').fetchall()
    return [Upvotes(*row) for row in rows]
