"""Minigolf map packs: every pack has holes and a leaderboard of its own."""
import json

from playwright.sync_api import Page, expect

from conftest import login
from test_minigolf import game, putt, wait_for_turn
from test_minigolf_network import game_id, holed, not_played, shot, status


def pick_pack(page: Page, name: str) -> None:
    page.get_by_label('Map pack').select_option(label=name)


def test_bumper_brawl_can_be_played_hot_seat(page: Page, seed, alice):
    login(page, alice)
    page.goto('/minigolf/')
    pick_pack(page, 'Bumper Brawl')
    expect(page.locator('#minigolfCourseHint')).to_contain_text('different side')
    page.get_by_role('button', name='Tee off!').click()
    wait_for_turn(page)

    # Crossroads: a bumper is in the way of the straight putt at the cup, so it can't be aced like that
    putt(page, 300, 300, -45, 0)

    expect(page.locator('#minigolfStatus')).to_contain_text("Alice, it's your turn! Stroke 2.", timeout=20_000)
    expect(game(page)).to_have_attribute('data-hole', '1')


def test_every_pack_has_a_leaderboard_of_its_own(page: Page, seed, alice):
    login(page, alice)
    response = page.request.post('/minigolf/api/rounds', data={'course': 'brawl', 'strokes': [2] * 9})
    assert response.status == 201
    assert response.json()['course'] == 'brawl'
    assert response.json()['best'] == [{'name': 'Alice', 'best': 18, 'rounds': 1}]
    # without a course it's a round of the classic course, as it's always been
    assert page.request.post('/minigolf/api/rounds', data={'strokes': [3] * 9}).status == 201
    assert page.request.get('/minigolf/api/leaderboard').json()['best'][0]['best'] == 27
    assert page.request.get('/minigolf/api/leaderboard?course=brawl').json()['best'][0]['best'] == 18

    page.goto('/minigolf/')
    expect(page.locator('#minigolfBoardCourse')).to_have_text('Classic')
    expect(page.locator('#minigolfBest tr').first).to_contain_text('27')
    pick_pack(page, 'Bumper Brawl')
    expect(page.locator('#minigolfBoardCourse')).to_have_text('Bumper Brawl')
    expect(page.locator('#minigolfBest tr').first).to_contain_text('18')
    expect(page.locator('#minigolfRecent tr').first).to_contain_text('18')

    rows = seed.query('select course, strokes from minigolf_rounds order by id')
    assert [(r['course'], json.loads(r['strokes'])) for r in rows] == [('brawl', [2] * 9), ('classic', [3] * 9)]


def test_unknown_packs_are_refused(page: Page, seed, alice):
    login(page, alice)
    assert page.request.post('/minigolf/api/rounds', data={'course': 'nope', 'strokes': [2] * 9}).status == 400
    assert page.request.get('/minigolf/api/leaderboard?course=nope').status == 400
    assert page.request.post('/minigolf/api/games', data={'course': 'nope'}).status == 400
    assert seed.query('select * from minigolf_rounds') == []
    assert seed.query('select * from minigolf_games') == []


def test_a_network_game_on_bumper_brawl(page: Page, seed, alice, bob, new_user_page):
    login(page, alice)
    page.goto('/minigolf/')
    pick_pack(page, 'Bumper Brawl')
    page.get_by_role('button', name='Host a network game').click()
    expect(page.locator('#minigolfLobbyTitle')).to_have_text("Alice's game: Bumper Brawl")

    bob_page = new_user_page(bob)
    bob_page.goto('/minigolf/')
    # Bob has the classic pack picked, the game is played on its own
    expect(bob_page.locator('#minigolfGames')).to_contain_text("Alice's game (Bumper Brawl): Alice")
    bob_page.get_by_role('button', name="Join Alice's game").click()
    expect(bob_page.locator('#minigolfLobbyTitle')).to_have_text("Alice's game: Bumper Brawl")
    page.get_by_role('button', name='Start the game').click()
    wait_for_turn(page)
    gid = game_id(seed)
    assert seed.query('select course from minigolf_games')[0]['course'] == 'brawl'

    # both putt up against the wall of their arm of the crossroads
    putt(page, 300, 300, 0, 30)
    expect(status(bob_page)).to_contain_text("Bob, it's your turn! Stroke 1.", timeout=20_000)
    putt(bob_page, 300, 300, 0, 30)
    expect(status(page)).to_contain_text("Alice, it's your turn! Stroke 2.", timeout=20_000)
    balls = [json.loads(m['data'])['balls'] for m in seed.query('select data from minigolf_moves order by seq')]
    # Alice tees off left of the cup in the middle, Bob on the other side
    assert balls[0][0]['x'] < 270
    assert balls[1][1]['x'] > 370

    # the rest of the game played by the API: both hole out in two on every hole, so Alice always goes first
    assert shot(page, gid, 2, 0, [holed(2), balls[1][1]]).status == 201
    assert shot(bob_page, gid, 3, 0, [holed(2), holed(2)]).status == 201
    seq = 4
    for hole in range(1, 9):
        assert shot(page, gid, seq, hole, [holed(2), not_played()]).status == 201
        assert shot(bob_page, gid, seq + 1, hole, [holed(2), holed(2)]).status == 201
        seq += 2

    expect(bob_page.locator('#minigolfResult')).to_be_visible(timeout=10_000)
    expect(bob_page.locator('#minigolfBoardCourse')).to_have_text('Bumper Brawl')
    rows = seed.query('select user, course, strokes from minigolf_rounds order by user')
    assert [(r['user'], r['course'], json.loads(r['strokes'])) for r in rows] == \
        [(alice.id, 'brawl', [2] * 9), (bob.id, 'brawl', [2] * 9)]


# ---------------------------------------------------------------- the holes themselves
#
# Checked on the hole data the game plays with, see lol9k1MinigolfPacks in static/js/minigolf.js.

CENTRE_X, CENTRE_Y = 320, 200  # of the course
BALL_R, WALL_R = 6, 10

# the mirrors and rotations of the course that keep it on the canvas, by name
TRANSFORMS = {
    'mirrored left to right': lambda x, y: (2 * CENTRE_X - x, y),
    'mirrored top to bottom': lambda x, y: (x, 2 * CENTRE_Y - y),
    'turned half way round': lambda x, y: (2 * CENTRE_X - x, 2 * CENTRE_Y - y),
    'turned a quarter clockwise': lambda x, y: (CENTRE_X - (y - CENTRE_Y), CENTRE_Y + (x - CENTRE_X)),
    'turned a quarter anticlockwise': lambda x, y: (CENTRE_X + (y - CENTRE_Y), CENTRE_Y - (x - CENTRE_X)),
}


def packs(page: Page) -> dict:
    page.goto('/minigolf/')
    return page.evaluate('lol9k1MinigolfPacks')


def starts(hole) -> list:
    return hole.get('starts') or [hole['start']]


def _point(p):
    return round(p[0], 3), round(p[1], 3)


def _polygon(points, t):
    """A polygon as the set of its walls, whichever way round it's listed."""
    moved = [_point(t(*p)) for p in points]
    return frozenset(frozenset((moved[i], moved[(i + 1) % len(moved)])) for i in range(len(moved)))


def _rect(r, t):
    xs, ys = zip(*(t(x, y) for x, y in ((r[0], r[1]), (r[0] + r[2], r[1] + r[3]))))
    return round(min(xs), 3), round(min(ys), 3), round(max(xs), 3), round(max(ys), 3)


def _shape(hole, t) -> dict:
    """Everything on a hole that makes a difference to a ball, moved by t."""
    def sliders_at(time):
        import math
        rects = set()
        for s in hole.get('sliders', []):
            k = math.sin(time * s['speed'] + s['phase']) * 0.5 + 0.5
            rects.add(_rect([s['x'] + s['ax'] * k, s['y'] + s['ay'] * k, s['w'], s['h']], t))
        return frozenset(rects)

    def boost(b):
        cx, cy = b[0] + b[2] / 2, b[1] + b[3] / 2
        (mx, my), (dx, dy) = t(cx, cy), t(cx + b[4], cy + b[5])
        return _rect(b, t), _point((dx - mx, dy - my))

    return {
        'cup': _point(t(*hole['cup'])),
        'outline': _polygon(hole['outline'], t),
        'blocks': frozenset(_polygon(b, t) for b in hole.get('blocks', [])),
        'water': frozenset(_rect(r, t) for r in hole.get('water', [])),
        'sand': frozenset(_rect(r, t) for r in hole.get('sand', [])),
        'boosts': frozenset(boost(b) for b in hole.get('boosts', [])),
        'bumpers': frozenset((*_point(t(b[0], b[1])), b[2]) for b in hole.get('bumpers', [])),
        'sliders': tuple(sliders_at(time / 10) for time in range(50)),
    }


def test_every_tee_of_a_hole_is_as_good_as_the_others(page: Page, alice):
    """A mirror or a rotation that leaves the hole as it is takes the first tee to every other one."""
    login(page, alice)
    unfair = []
    for pack_id, pack in packs(page).items():
        for number, hole in enumerate(pack['holes'], 1):
            tees = starts(hole)
            if len(tees) == 1:
                continue
            assert not hole.get('rotors'), 'checking windmills is not supported'
            same = _shape(hole, lambda x, y: (x, y))
            keeping = [t for t in TRANSFORMS.values() if _shape(hole, t) == same]
            for tee in tees[1:]:
                if not any(_point(t(*tees[0])) == _point(tee) for t in keeping):
                    unfair.append(f'{pack_id} {number} {hole["name"]}: tee {tee}')
            assert len(set(map(_point, tees))) == len(tees), f'{hole["name"]} has a tee twice'
    assert unfair == []


def _clear_line(hole, tee) -> bool:
    """Whether a ball could roll straight from the tee into the cup, without anything in the way."""
    import math

    def wall_distance(x, y, a, b):
        abx, aby = b[0] - a[0], b[1] - a[1]
        k = max(0, min(1, ((x - a[0]) * abx + (y - a[1]) * aby) / (abx * abx + aby * aby)))
        return math.hypot(x - a[0] - abx * k, y - a[1] - aby * k)

    walls = [(poly[i], poly[(i + 1) % len(poly)]) for poly in [hole['outline'], *hole.get('blocks', [])]
             for i in range(len(poly))]
    (x0, y0), (x1, y1) = tee, hole['cup']
    for step in range(401):
        x, y = x0 + (x1 - x0) * step / 400, y0 + (y1 - y0) * step / 400
        if math.hypot(x - x1, y - y1) < 8:
            return True
        if (any(r[0] <= x <= r[0] + r[2] and r[1] <= y <= r[1] + r[3] for r in hole.get('water', []))
                or any(wall_distance(x, y, a, b) < WALL_R for a, b in walls)
                or any(math.hypot(x - b[0], y - b[1]) < b[2] + BALL_R for b in hole.get('bumpers', []))):
            return False
    return True


def test_bumper_brawl_cant_be_aced_with_a_straight_putt(page: Page, alice):
    login(page, alice)
    clear = [f'{hole["name"]}: tee {tee}' for hole in packs(page)['brawl']['holes']
             for tee in starts(hole) if _clear_line(hole, tee)]
    assert clear == []
