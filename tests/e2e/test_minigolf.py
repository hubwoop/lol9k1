"""The minigolf game and its leaderboard."""
import json

from playwright.sync_api import Page, expect

from conftest import login


def putt(page: Page, from_x: float, from_y: float, pull_x: float, pull_y: float) -> None:
    """Drags on the canvas in course coordinates: pulling back by (pull_x, pull_y) shoots the other way."""
    canvas = page.locator('#minigolfCanvas')
    box = canvas.bounding_box()
    # the course is as big as the canvas, which is scaled up by the device pixel ratio
    course_width = canvas.evaluate('c => c.width / Math.min(window.devicePixelRatio || 1, 2)')
    scale = box['width'] / course_width

    def screen(x, y):
        return box['x'] + x * scale, box['y'] + y * scale

    page.mouse.move(*screen(from_x, from_y))
    page.mouse.down()
    page.mouse.move(*screen(from_x + pull_x, from_y + pull_y), steps=5)
    page.mouse.up()


def game(page: Page):
    return page.locator('#minigolf')


def wait_for_turn(page: Page) -> None:
    expect(game(page)).to_have_attribute('data-state', 'aim', timeout=20_000)


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
    expect(page.locator('#minigolfStatus')).to_contain_text("Alice, it's your turn! Stroke 1.")
    # a gentle putt towards the cup, far too short to sink
    putt(page, 300, 300, -30, 0)

    expect(page.locator('#minigolfStatus')).to_contain_text("Bob, it's your turn! Stroke 1.", timeout=20_000)
    expect(game(page)).to_have_attribute('data-hole', '1')
    expect(page.locator('#minigolfScorecard')).to_contain_text('Bob')


def test_hole_in_one(page: Page, alice):
    login(page, alice)
    page.goto('/minigolf/')
    page.get_by_role('button', name='Tee off!').click()
    wait_for_turn(page)

    # hole 1 is a straight lane, the cup is 420px to the right of the tee
    putt(page, 300, 200, -85, 0)

    expect(game(page)).to_have_attribute('data-hole', '2', timeout=20_000)
    expect(page.locator('#minigolfScorecard tbody tr').nth(1).locator('td').first).to_have_text('1')


def test_page_tells_the_script_how_many_holes_the_server_expects(page: Page, alice):
    login(page, alice)

    def with_holes(route):
        response = route.fetch()
        route.fulfill(response=response, body=response.text().replace('data-holes="9"', 'data-holes="18"'))
    page.route('**/minigolf/', with_holes)
    page.goto('/minigolf/')

    expect(page.locator('#minigolfStatus')).to_contain_text('the server expects 18')
    page.get_by_role('button', name='Tee off!').click()
    expect(game(page)).not_to_have_attribute('data-state', 'aim')


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
    # only the latest round of every player
    expect(page.locator('#minigolfRecent tr')).to_have_count(1)
    expect(page.locator('#minigolfRecent tr').first).to_contain_text('25')
    rows = seed.query('select user, course, strokes from minigolf_rounds order by id')
    assert [(r['user'], r['course'], json.loads(r['strokes'])) for r in rows] == \
        [(alice.id, 'classic', [2, 3, 3, 3, 3, 3, 3, 3, 4]), (alice.id, 'classic', [1, 2, 3, 3, 3, 3, 3, 3, 4])]


def test_latest_rounds_show_every_player(page: Page, alice, new_user_page, bob):
    bob_page = new_user_page(bob)
    for _ in range(12):
        bob_page.request.post('/minigolf/api/rounds', data={'strokes': [4] * 9})
    login(page, alice)
    page.request.post('/minigolf/api/rounds', data={'strokes': [3] * 9})
    bob_page.request.post('/minigolf/api/rounds', data={'strokes': [5] * 9})

    page.goto('/minigolf/')

    recent = page.locator('#minigolfRecent tr')
    expect(recent).to_have_count(2)
    expect(recent.nth(0)).to_contain_text('Bob')
    expect(recent.nth(0)).to_contain_text('45')
    expect(recent.nth(1)).to_contain_text('Alice')


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
    login(page, alice)
    page.goto('/minigolf/')

    places = page.evaluate('lol9k1MinigolfRules.places([27, 27, 36, 30])')

    assert places == [0, 0, 3, 2]


def test_ball_dead_centre_in_the_cup_is_not_pulled_anywhere(page: Page, alice):
    login(page, alice)
    page.goto('/minigolf/')

    # dividing by the distance to the centre used to turn the ball into NaN and freeze the game
    assert page.evaluate('lol9k1MinigolfRules.cupPull(0, 0, 1 / 240)') == {'vx': 0, 'vy': 0}
    pull = page.evaluate('lol9k1MinigolfRules.cupPull(3, 4, 1)')
    assert (round(pull['vx']), round(pull['vy'])) == (1560, 2080)
