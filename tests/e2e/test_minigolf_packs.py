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
