"""Ranking and badges, see lol9k1/leaderboard.py."""
from datetime import datetime

import pytest

from lol9k1.leaderboard import (Appearance, MOST_VOTES, NIGHT_OWL, PICKED_LAST_BUT_WON, build, played_at_night,
                                undefeated_in)

NOON = datetime(2026, 10, 10, 12), datetime(2026, 10, 10, 14)


def appearance(user_id, event_id, placement, teams=2, game='CS', when=NOON, pick_number=None, last_pick=None):
    return Appearance(user_id=user_id, user_name=f'user{user_id}', event_id=event_id, start=when[0], end=when[1],
                      game_name=game, teams=teams, placement=placement, pick_number=pick_number,
                      last_pick=last_pick)


def standings(board):
    return [(s.name, s.rank, s.points, s.wins, s.played) for s in board.standings]


def badges_of(board, user_id):
    return next(s.badges for s in board.standings if s.user_id == user_id)


def test_points_are_teams_finished_ahead_of():
    board = build([appearance(1, 1, 1, teams=4), appearance(2, 1, 2, teams=4), appearance(3, 1, None, teams=4),
                   appearance(2, 2, 1)], [])

    # on equal points and wins, fewer events played ranks higher
    assert standings(board) == [('user1', 1, 3, 1, 1), ('user2', 2, 3, 1, 2), ('user3', 3, 0, 0, 1)]


def test_equal_records_share_a_rank():
    board = build([appearance(1, 1, 1), appearance(2, 2, 1), appearance(3, 2, 2)], [])

    assert [(s.name, s.rank) for s in board.standings] == [('user1', 1), ('user2', 1), ('user3', 3)]


def test_most_upvotes_badge_goes_to_everyone_tied_for_most():
    board = build([appearance(1, 1, 1)], [(1, 'user1', 3), (2, 'user2', 3), (3, 'user3', 1)])

    assert badges_of(board, 1) == [MOST_VOTES]
    voters = next(a for a in board.achievements if a.badge == MOST_VOTES)
    assert voters.holders == ['user1', 'user2']


def test_last_pick_that_won():
    board = build([appearance(1, 1, 1, pick_number=4, last_pick=4),
                   appearance(2, 1, 2, pick_number=3, last_pick=4),
                   appearance(3, 2, 2, pick_number=2, last_pick=2)], [])

    assert badges_of(board, 1) == [PICKED_LAST_BUT_WON]
    assert badges_of(board, 2) == []
    assert badges_of(board, 3) == []


def test_undefeated_needs_every_event_of_a_game_won():
    board = build([appearance(1, 1, 1), appearance(1, 2, 1), appearance(1, 3, 1, game='Worms'),
                   appearance(2, 1, 1), appearance(2, 2, 1), appearance(2, 4, 2)], [])

    assert badges_of(board, 1) == [undefeated_in('CS')]
    assert badges_of(board, 2) == []


def test_night_owl():
    late = datetime(2026, 10, 11, 2, 30), datetime(2026, 10, 11, 3, 30)
    board = build([appearance(1, 1, 2, when=late), appearance(2, 2, 2)], [])

    assert badges_of(board, 1) == [NIGHT_OWL]
    assert badges_of(board, 2) == []


@pytest.mark.parametrize('start, end, expected', [
    ('2026-10-11 03:00', '2026-10-11 04:00', True),
    ('2026-10-11 05:59', '2026-10-11 07:00', True),
    ('2026-10-10 22:00', '2026-10-11 03:01', True),
    ('2026-10-10 20:00', '2026-10-12 01:00', True),
    ('2026-10-10 22:00', '2026-10-11 03:00', False),
    ('2026-10-11 06:00', '2026-10-11 09:00', False),
    ('2026-10-11 12:00', '2026-10-11 11:00', False),
])
def test_played_at_night(start, end, expected):
    assert played_at_night(datetime.fromisoformat(start), datetime.fromisoformat(end)) is expected
