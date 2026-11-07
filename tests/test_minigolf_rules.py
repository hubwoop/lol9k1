"""Whose turn it is in a network minigolf game, see lol9k1/minigolf.py (GameState)."""
import pytest

from lol9k1.minigolf import HOLES, MAX_STROKES, GameState, MoveError


def ball(strokes, sunk=False, x=100.0, y=200.0):
    return {'x': x, 'y': y, 'strokes': strokes, 'sunk': sunk}


def untouched(state, seat):
    """A ball as the shooter's browser reports it when the shot didn't move it."""
    b = state.balls[seat]
    return {'x': b['x'] if b['x'] is not None else 0, 'y': b['y'] if b['y'] is not None else 0,
            'strokes': b['strokes'], 'sunk': b['sunk']}


def shoot(state, seat, strokes, sunk=False):
    balls = [untouched(state, i) for i in range(state.players)]
    balls[seat] = ball(strokes, sunk)
    return state.shot(seat, state.hole, balls)


def test_players_take_turns_in_seat_order_on_the_first_hole():
    state = GameState.new(3)
    assert state.turn == 0
    shoot(state, 0, 1)
    assert state.turn == 1
    shoot(state, 1, 1)
    assert state.turn == 2
    shoot(state, 2, 1)
    assert state.turn == 0


def test_holed_players_are_skipped_and_the_best_tees_off_first_on_the_next_hole():
    state = GameState.new(3)
    shoot(state, 0, 1)
    shoot(state, 1, 1, sunk=True)
    shoot(state, 2, 1, sunk=True)
    assert state.turn == 0
    shoot(state, 0, 2)
    assert state.turn == 0
    shoot(state, 0, 3, sunk=True)

    assert state.hole == 1
    assert state.scores == [[3], [1], [1]]
    assert state.order == [1, 2, 0]
    assert state.turn == 1
    assert all(not b['on'] for b in state.balls)


def test_a_ball_is_picked_up_after_the_maximum_number_of_strokes():
    state = GameState.new(2)
    shoot(state, 0, 1, sunk=True)
    shoot(state, 1, MAX_STROKES + 1)  # e.g. a splash on the last stroke

    assert state.hole == 1
    assert state.scores == [[1], [MAX_STROKES]]


def test_only_the_player_whose_turn_it_is_can_shoot():
    state = GameState.new(2)
    with pytest.raises(MoveError):
        shoot(state, 1, 1)
    with pytest.raises(MoveError):
        state.shot(0, 1, [ball(1), ball(0)])


@pytest.mark.parametrize('balls', [
    [ball(0), ball(0)],                     # the shooter didn't take a stroke
    [ball(1)],                              # a ball missing
    [ball(1, x=float('nan')), ball(0)],
    [ball(1, x='1'), ball(0)],
    [{**ball(1), 'strokes': 1.0}, ball(0)],
    [{**ball(1), 'sunk': 1}, ball(0)],
    [ball(30), ball(0)],
    [ball(1, x=-1), ball(0)],               # off the course
    [ball(1, y=9e9), ball(0)],
    'nope',
])
def test_impossible_balls_are_refused(balls):
    state = GameState.new(2)
    with pytest.raises(ValueError):
        state.shot(0, 0, balls)
    assert state.turn == 0


def test_balls_that_are_not_in_play_cant_be_moved():
    state = GameState.new(2)
    # player 1 hasn't teed off yet, so the shot can't have touched their ball
    kept = state.shot(0, 0, [ball(1), ball(5, sunk=True)])
    assert kept[1] == {'x': None, 'y': None, 'strokes': 0, 'sunk': False, 'out': False, 'on': False}


def test_others_can_be_knocked_into_the_water():
    state = GameState.new(2)
    shoot(state, 0, 1)
    shoot(state, 1, 1)
    kept = state.shot(0, 0, [ball(2), ball(2)])
    assert kept[1]['strokes'] == 2
    assert state.turn == 1


def test_leaving_on_your_turn_passes_it_on():
    state = GameState.new(3)
    state.leave(0)
    assert state.turn == 1
    state.leave(2)
    shoot(state, 1, 1, sunk=True)

    assert state.hole == 1
    assert state.turn == 1
    with pytest.raises(MoveError):
        state.leave(2)


def test_the_game_ends_when_everybody_left():
    state = GameState.new(2)
    state.leave(1)
    state.leave(0)
    assert state.finished
    assert state.turn is None


def test_the_game_ends_after_the_last_hole():
    state = GameState.new(2)
    for _ in range(HOLES):
        shoot(state, state.turn, 1, sunk=True)
        shoot(state, state.turn, 2, sunk=True)
    assert state.finished
    assert state.scores == [[1, 1, 1, 1, 1, 1, 1, 1, 1], [2, 2, 2, 2, 2, 2, 2, 2, 2]]
    with pytest.raises(MoveError):
        shoot(state, 0, 1)


def test_somebody_elses_ball_cant_be_holed_or_given_more_than_one_penalty():
    state = GameState.new(2)
    shoot(state, 0, 1)
    shoot(state, 1, 1)
    for rival in (ball(1, sunk=True), ball(3), ball(1, x=-9e9)):
        with pytest.raises(ValueError):
            state.shot(0, 0, [ball(2), rival])
    assert state.turn == 0


def test_a_game_lasts_as_many_holes_as_its_course_has():
    state = GameState.new(1, holes=2)
    shoot(state, 0, 1, sunk=True)
    assert not state.finished
    shoot(state, 0, 1, sunk=True)
    assert state.finished
    assert state.scores == [[1, 1]]


def test_every_course_has_holes():
    from lol9k1.minigolf import COURSE, COURSES
    assert COURSE in COURSES
    assert all(c['holes'] > 0 and c['name'] for c in COURSES.values())
