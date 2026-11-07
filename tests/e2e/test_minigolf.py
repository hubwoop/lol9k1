"""The minigolf game and its leaderboard."""
from playwright.sync_api import Page, Route, expect

from conftest import login

COURSE_W, COURSE_H = 640, 400


# Exposes some internals of minigolf.js to the tests, by patching the script as it's served.
HOOK = """
    window.__mg = {
        finish: (scores) => {
            players.forEach((p, i) => { p.scores = scores[i].slice(); });
            holeIndex = HOLES.length - 1;
            finishRound();
        },
        place: (i, x, y, vx, vy) => {
            const b = players[i].ball;
            b.onCourse = true; b.x = x; b.y = y; b.vx = vx; b.vy = vy; b.moving = true;
            b.strokes = 1; state = 'rolling';
        },
        ball: (i) => { const b = players[i].ball; return {x: b.x, y: b.y, vx: b.vx, vy: b.vy, moving: b.moving}; },
    };
    // for the e2e tests and the curious"""


def hook_js(page: Page) -> None:
    def handle(route: Route):
        response = route.fetch()
        body = response.text()
        assert '    // for the e2e tests and the curious' in body
        route.fulfill(response=response, body=body.replace('    // for the e2e tests and the curious', HOOK, 1))
    page.route('**/static/js/minigolf.js', handle)


def putt(page: Page, from_x: float, from_y: float, pull_x: float, pull_y: float) -> None:
    """Drags on the canvas in course coordinates: pulling back by (pull_x, pull_y) shoots the other way."""
    box = page.locator('#minigolfCanvas').bounding_box()
    scale = box['width'] / COURSE_W

    def screen(x, y):
        return box['x'] + x * scale, box['y'] + y * scale

    page.mouse.move(*screen(from_x, from_y))
    page.mouse.down()
    page.mouse.move(*screen(from_x + pull_x, from_y + pull_y), steps=5)
    page.mouse.up()


def game_state(page: Page) -> dict:
    return page.evaluate('window.lol9k1Minigolf.state()')


def wait_for_turn(page: Page) -> None:
    page.wait_for_function("window.lol9k1Minigolf.state().state === 'aim'", timeout=20_000)


def test_minigolf_is_linked_from_the_navigation(page: Page, alice):
    login(page, alice)
    page.get_by_role('link', name='Minigolf').click()

    expect(page.get_by_role('heading', name="Who's playing?")).to_be_visible()
    expect(page.get_by_label('Player 1 name')).to_have_value('Alice')
    expect(page.get_by_text('No rounds played yet. Be the first!')).to_be_visible()


def test_hot_seat_players_take_turns(page: Page, alice):
    login(page, alice)
    page.goto('/minigolf/')
    page.get_by_role('button', name='+ Add player').click()
    page.get_by_label('Player 2 name').fill('Bob')
    page.get_by_role('button', name='Tee off!').click()

    wait_for_turn(page)
    expect(page.locator('#minigolfStatus')).to_contain_text("Alice, it's your turn!")
    # a gentle putt towards the cup, far too short to sink
    putt(page, 300, 300, -30, 0)
    wait_for_turn(page)

    state = game_state(page)
    assert state['turn'] == 1
    alice_state = state['players'][0]
    assert alice_state['strokes'] == 1
    assert alice_state['x'] > 110  # the ball rolled from the tee towards the cup
    expect(page.locator('#minigolfStatus')).to_contain_text("Bob, it's your turn!")
    expect(page.locator('#minigolfScorecard')).to_contain_text('Bob')


def test_hole_in_one(page: Page, alice):
    login(page, alice)
    page.goto('/minigolf/')
    page.get_by_role('button', name='Tee off!').click()
    wait_for_turn(page)

    # hole 1 is a straight lane, the cup is 420px to the right of the tee
    putt(page, 300, 200, -85, 0)

    page.wait_for_function('window.lol9k1Minigolf.state().hole === 1', timeout=20_000)
    assert game_state(page)['players'][0]['scores'] == [1]
    expect(page.locator('#minigolfScorecard tbody tr').nth(1).locator('td').first).to_have_text('1')


def test_finished_round_goes_to_the_leaderboard(page: Page, seed, alice, bob):
    login(page, alice)
    page.goto('/minigolf/')

    response = page.request.post('/minigolf/api/rounds', data={'strokes': [2, 3, 3, 3, 3, 3, 3, 3, 4]})
    assert response.status == 201
    assert response.json()['best'] == [{'name': 'Alice', 'best': 27, 'rounds': 1}]
    page.request.post('/minigolf/api/rounds', data={'strokes': [1, 2, 3, 3, 3, 3, 3, 3, 4]})

    page.reload()
    best = page.locator('#minigolfBest tr')
    expect(best).to_have_count(1)
    expect(best.first).to_contain_text('Alice')
    expect(best.first).to_contain_text('25')
    expect(page.locator('#minigolfRecent tr')).to_have_count(2)
    rows = seed.query('select user, course, strokes, total from minigolf_rounds order by id')
    assert [tuple(r) for r in rows] == [(alice.id, 'classic', '2,3,3,3,3,3,3,3,4', 27),
                                        (alice.id, 'classic', '1,2,3,3,3,3,3,3,4', 25)]


def test_invalid_rounds_are_rejected(page: Page, seed, alice):
    login(page, alice)
    for payload in ({'strokes': [1] * 8}, {'strokes': [0] + [1] * 8}, {'strokes': [11] + [1] * 8},
                    {'strokes': ['1'] * 9}, {'strokes': [1.5] * 9}, {'strokes': [True] * 9}, [1] * 9, {}):
        response = page.request.post('/minigolf/api/rounds', data=payload)
        assert response.status == 400, payload
    assert seed.query('select * from minigolf_rounds') == []


def test_minigolf_requires_login(page: Page):
    page.goto('/minigolf/')

    expect(page.locator('input[name=username]')).to_be_visible()


def test_round_submitted_after_logout_is_refused_without_breaking_the_next_login(page: Page, seed, alice):
    login(page, alice)
    page.goto('/minigolf/')
    page.request.get('/auth/logout')  # e.g. logged out in another tab while playing

    status = page.evaluate("""() => fetch('/minigolf/api/rounds', {method: 'POST', credentials: 'include',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify({strokes: [3,3,3,3,3,3,3,3,3]})})
        .then(r => r.status)""")
    assert status == 401
    assert seed.query('select * from minigolf_rounds') == []

    login(page, alice)
    assert '/api/' not in page.url


def test_tied_players_share_a_place(page: Page, alice):
    hook_js(page)
    login(page, alice)
    page.goto('/minigolf/')
    page.get_by_role('button', name='+ Add player').click()
    page.get_by_label('Player 2 name').fill('Bob')
    page.get_by_role('button', name='+ Add player').click()
    page.get_by_label('Player 3 name').fill('Carol')
    page.get_by_role('button', name='Tee off!').click()
    wait_for_turn(page)

    page.evaluate('window.__mg.finish([[3,3,3,3,3,3,3,3,3],[3,3,3,3,3,3,3,3,3],[4,4,4,4,4,4,4,4,4]])')

    places = page.locator('#minigolfResultRows tr td:first-child').all_inner_texts()
    assert places == ['🥇', '🥇', '🥉']
    expect(page.locator('#minigolfStatus')).to_contain_text("It's a tie! Alice & Bob share the win.")


def test_ball_dead_centre_in_the_cup_does_not_freeze_the_game(page: Page, alice):
    hook_js(page)
    login(page, alice)
    page.goto('/minigolf/')
    page.get_by_role('button', name='Tee off!').click()
    wait_for_turn(page)

    # the hole 1 cup is at (530, 200): 480 px/s for one 1/240 s step lands exactly on its centre, too fast to sink
    page.evaluate('window.__mg.place(0, 528, 200, 480, 0)')
    page.wait_for_function("window.lol9k1Minigolf.state().state !== 'rolling'", timeout=20_000)
    ball = page.evaluate('window.__mg.ball(0)')
    assert ball['x'] == ball['x'] and ball['y'] == ball['y'], f'ball position became NaN: {ball}'
