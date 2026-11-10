"""What a shared minigolf map pack may hold, see lol9k1/minigolf_packs.py."""
import copy
import json
import math

import pytest

from lol9k1 import minigolf_packs
from lol9k1.minigolf_packs import (ITEM_NAMES, LIST_LIMITS, MAX_BYTES, MAX_HOLES, MAX_WALL_CORNERS, PackError,
                                   clean_text, validate_holes)

W, H, MAX_STROKES = 640, 400, 10


def rect(x, y, w, h):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def hole(**changes):
    h = {'name': 'Warm-up', 'par': 2, 'outline': rect(60, 140, 520, 120), 'start': [110, 200], 'cup': [530, 200]}
    h.update(changes)
    return h


def check(*holes):
    return validate_holes(list(holes), W, H, MAX_STROKES)


def refused(message, *holes):
    with pytest.raises(PackError, match=message):
        check(*holes)


def test_a_hole_comes_back_as_the_game_takes_it():
    assert check(hole()) == [hole()]


def test_everything_the_game_knows_is_kept_and_nothing_else():
    full = hole(
        blocks=[rect(300, 140, 20, 40)], sand=[[200, 150, 40, 40]], water=[[400, 220, 40, 30]],
        boosts=[[450, 150, 40, 40, 1, 0]], bumpers=[[250, 230, 12]],
        sliders=[{'x': 350, 'y': 150, 'w': 26, 'h': 60, 'ax': 0, 'ay': 40, 'speed': 1.5, 'phase': 0}],
        rotors=[{'cx': 310, 'cy': 160, 'len': 80, 'speed': 1.3, 'blades': 3, 'door': [290, 330]}],
        house=True, starts=[[110, 180], [110, 220]],
    )
    del full['start']
    sneaky = copy.deepcopy(full)
    sneaky.update(onload='alert(1)', __proto__={'polluted': True})
    sneaky['sliders'][0]['extra'] = 1
    assert check(sneaky) == [full]


def test_empty_lists_and_a_house_that_isnt_one_are_left_out():
    assert check(hole(blocks=[], water=[], house=False)) == [hole()]


def test_names_are_one_line_and_not_too_long():
    assert check(hole(name='  Up   the\nhill '))[0]['name'] == 'Up the hill'
    refused('hole 1: its name is missing', hole(name='   '))
    refused('hole 1: its name must be text', hole(name=None))
    refused('longer than 40', hole(name='x' * 41))
    assert clean_text(' My  pack ', 'the name', 40) == 'My pack'
    assert clean_text(None, 'the hint', 200, required=False) == ''
    with pytest.raises(PackError, match='the name is missing'):
        clean_text(' ', 'the name', 40)


@pytest.mark.parametrize('holes', [0, MAX_HOLES + 1])
def test_a_pack_has_a_sensible_number_of_holes(holes):
    refused(f'1 to {MAX_HOLES} holes', *[hole()] * holes)


def test_every_list_has_a_limit():
    refused('hole 1: it has 31 bumpers, 30 at most', hole(bumpers=[[200, 160, 5]] * (LIST_LIMITS['bumpers'] + 1)))
    refused('hole 1: the windmills must be a list', hole(rotors={'cx': 1}))
    refused('it has 31 sand areas, 30 at most', hole(sand=[[200, 150, 40, 40]] * (LIST_LIMITS['sand'] + 1)))


def test_things_are_called_what_the_editor_calls_them():
    """Every list has a name for its players, rotors are windmills."""
    assert set(ITEM_NAMES) == set(LIST_LIMITS)
    refused('the length of the blades of windmill 1', hole(rotors=[{'cx': 1, 'cy': 1, 'len': 0, 'speed': 1, 'blades': 3,
                                                                    'door': [0, 1]}]))
    refused('the x of sand area 2', hole(sand=[[200, 150, 40, 40], [1e9, 150, 40, 40]]))
    refused('the y of water 1', hole(water=[[200, 1e9, 40, 40]]))


def test_walls_have_a_limit_of_corners_all_together():
    # each block is fine on its own, but every corner costs on every physics step
    corners = 30
    block = [[200 + 10 * math.cos(a * 2 * math.pi / corners), 160 + 10 * math.sin(a * 2 * math.pi / corners)]
             for a in range(corners)]
    refused(f'more than {MAX_WALL_CORNERS} corners', hole(blocks=[block] * 7))
    refused('3 to 32 corners', hole(blocks=[[[1, 1]] * 33]))


def test_a_pack_has_a_size_limit():
    big = hole(name='x' * 40, sand=[[200.123456789, 150.123456789, 40.123456789, 40.123456789]] * 30,
               water=[[60.123456789, 250.123456789, 1.123456789, 1.123456789]] * 30,
               boosts=[[60.123456789, 250.123456789, 1.123456789, 1.123456789, 0.123456789, 0.123456789]] * 30)
    refused(f'{MAX_BYTES // 1024} KB', *[big] * MAX_HOLES)


def test_the_size_is_measured_in_utf8_bytes_like_the_editor_does(monkeypatch):
    accented = hole(name='é' * 40)
    utf8 = len(json.dumps([accented], separators=(',', ':'), ensure_ascii=False).encode())
    # escaped, every é would take 6 characters rather than 2 bytes and the pack would be too big
    assert len(json.dumps([accented], separators=(',', ':'))) > utf8
    monkeypatch.setattr(minigolf_packs, 'MAX_BYTES', utf8)
    assert check(accented) == [accented]
    monkeypatch.setattr(minigolf_packs, 'MAX_BYTES', utf8 - 1)
    refused('too big', accented)


def test_a_huge_whole_number_is_refused_rather_than_crashing():
    refused('the x of the cup', hole(cup=[json.loads('1' + '0' * 400), 200]))


@pytest.mark.parametrize('changes, message', [
    ({'start': [600, 200]}, 'tee 1 is off the fairway'),
    ({'start': [110, 200], 'water': [[100, 190, 20, 20]]}, 'tee 1 is off the fairway or in the water'),
    ({'cup': [310, 160], 'blocks': [rect(300, 140, 20, 40)]}, 'the cup is off the fairway'),
    ({'start': [700, 200]}, 'the x of tee 1 must be a number from 0 to 640'),
    ({'starts': [[110, 200]] * 9}, '1 to 8 tees'),
    ({'start': None}, 'tee 1 must be a point'),
    ({'cup': [530, float('nan')]}, 'the y of the cup'),
    ({'cup': [530, True]}, 'the y of the cup'),
    ({'cup': [530, '200']}, 'the y of the cup'),
    ({'par': 0}, 'par must be a whole number from 1 to 10'),
    ({'par': 2.5}, 'par must be a whole number'),
    ({'outline': rect(-1e9, 0, 10, 10)}, 'the x of a corner of the outline'),
    ({'bumpers': [[200, 160, 500]]}, 'the radius of bumper 1'),
    ({'boosts': [[200, 160, 20, 20, 5, 0]]}, 'the dx of boost 1'),
    ({'rotors': [{'cx': 1, 'cy': 1, 'len': 10, 'speed': 1, 'blades': 99, 'door': [0, 1]}]}, '1 to 8 blades'),
    ({'rotors': [{'cx': 1, 'cy': 1, 'len': 10, 'speed': 1, 'blades': 3, 'door': [9, 1]}]}, 'from left to right'),
    ({'sliders': [{'x': 1, 'y': 1, 'w': 10, 'h': 10, 'ax': 0, 'ay': 0, 'speed': 1e6, 'phase': 0}]}, 'the speed of slider 1'),
])
def test_holes_that_cant_be_played_are_refused(changes, message):
    refused(message, hole(**changes))


def test_errors_name_the_hole():
    refused('hole 2: there is no tee', hole(), {k: v for k, v in hole().items() if k != 'start'})
    refused('hole 1: must be an object', 'hole')
