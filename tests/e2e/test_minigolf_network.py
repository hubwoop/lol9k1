"""Minigolf across the network: registered players, each in their own browser."""
import json
from datetime import datetime, timedelta

from playwright.sync_api import Page, expect

from conftest import login
from test_minigolf import game, putt, wait_for_turn

HOLES = 9


def status(page: Page):
    return page.locator('#minigolfStatus')


def host_game(page: Page) -> None:
    page.goto('/minigolf/')
    page.get_by_role('button', name='Host a network game').click()
    expect(page.locator('#minigolfLobby')).to_be_visible()


def join_game(page: Page, host: str) -> None:
    page.goto('/minigolf/')
    page.get_by_role('button', name=f"Join {host}'s game").click()
    expect(page.locator('#minigolfLobbyPlayers')).to_contain_text(page.evaluate(
        "document.getElementById('minigolf').dataset.player"))


def start_game(page: Page) -> None:
    page.get_by_role('button', name='Start the game').click()
    wait_for_turn(page)


def game_id(seed) -> int:
    return seed.query('select id from minigolf_games order by id desc limit 1')[0]['id']


def shot(page: Page, gid: int, seq: int, hole: int, balls: list, **params):
    return page.request.post(f'/minigolf/api/games/{gid}/moves', data={
        'seq': seq, 'hole': hole, 'shot': {'power': 0.5, 'dx': 1, 'dy': 0, 'time': 1.5, **params}, 'balls': balls})


def holed(strokes):
    return {'x': 530, 'y': 200, 'strokes': strokes, 'sunk': True}


def not_played():
    return {'x': 0, 'y': 0, 'strokes': 0, 'sunk': False}


def test_two_players_take_turns_on_their_own_computers(page: Page, alice, bob, new_user_page):
    login(page, alice)
    host_game(page)
    expect(page.get_by_role('button', name='Start the game')).to_be_disabled()

    bob_page = new_user_page(bob)
    join_game(bob_page, 'Alice')
    expect(bob_page.locator('#minigolfLobbyHint')).to_contain_text('Waiting for Alice to start the game')
    expect(page.locator('#minigolfLobbyPlayers')).to_contain_text('Bob')
    start_game(page)

    expect(status(page)).to_contain_text("Alice, it's your turn! Stroke 1.")
    expect(status(bob_page)).to_contain_text('Waiting for Alice to putt', timeout=10_000)
    expect(bob_page.locator('#minigolfScorecard')).to_contain_text('Alice')

    # Bob can't putt for Alice
    putt(bob_page, 300, 200, -30, 0)
    expect(game(bob_page)).not_to_have_attribute('data-state', 'rolling')

    putt(page, 300, 300, -30, 0)
    expect(status(page)).to_contain_text('Waiting for Bob to putt', timeout=20_000)
    expect(status(bob_page)).to_contain_text("Bob, it's your turn! Stroke 1.", timeout=20_000)
    # Bob saw Alice's stroke
    expect(bob_page.locator('#minigolfScorecard tbody tr').nth(1).locator('td').first).to_have_text('1')

    putt(bob_page, 300, 300, -30, 0)
    expect(status(page)).to_contain_text("Alice, it's your turn! Stroke 2.", timeout=20_000)
    expect(status(bob_page)).to_contain_text('Waiting for Alice to putt', timeout=20_000)


def test_a_hole_in_one_shows_up_on_the_other_computer(page: Page, alice, bob, new_user_page):
    login(page, alice)
    host_game(page)
    bob_page = new_user_page(bob)
    join_game(bob_page, 'Alice')
    start_game(page)
    wait_for_turn(bob_page)

    putt(page, 300, 200, -85, 0)

    expect(status(bob_page)).to_contain_text("Bob, it's your turn! Stroke 1.", timeout=20_000)
    expect(bob_page.locator('#minigolfScorecard tbody tr').nth(1).locator('td').first).to_have_text('1')
    expect(game(bob_page)).to_have_attribute('data-hole', '1')


def test_finished_game_puts_every_players_round_into_the_hall_of_fame(page: Page, seed, alice, bob, new_user_page):
    login(page, alice)
    host_game(page)
    bob_page = new_user_page(bob)
    join_game(bob_page, 'Alice')
    start_game(page)
    gid = game_id(seed)

    # Alice holes every hole in one and keeps the honour, Bob takes two
    seq = 0
    for hole in range(HOLES):
        assert shot(page, gid, seq, hole, [holed(1), not_played()]).status == 201
        assert shot(bob_page, gid, seq + 1, hole, [holed(1), holed(2)]).status == 201
        seq += 2

    for p in (page, bob_page):
        expect(p.locator('#minigolfResult')).to_be_visible(timeout=10_000)
        expect(p.locator('#minigolfResultRows tr').first).to_contain_text('Alice')
        expect(p.locator('#minigolfResultRows tr').first).to_contain_text('9')
        expect(p.locator('#minigolfSaved')).to_contain_text("Everybody's rounds went into the Hall of Fame.")
    expect(page.locator('#minigolfBest tr').first).to_contain_text('Alice')
    expect(page.locator('#minigolfBest tr').nth(1)).to_contain_text('Bob')

    rows = seed.query('select user, strokes from minigolf_rounds order by user')
    assert [(r['user'], json.loads(r['strokes'])) for r in rows] == [(alice.id, [1] * HOLES), (bob.id, [2] * HOLES)]
    assert seed.query('select status from minigolf_games')[0]['status'] == 'finished'

    page.get_by_role('button', name='Play again').click()
    expect(page.get_by_role('heading', name="Who's playing?")).to_be_visible()


def test_a_reloaded_page_resumes_the_game(page: Page, seed, alice, bob, new_user_page):
    login(page, alice)
    host_game(page)
    bob_page = new_user_page(bob)
    join_game(bob_page, 'Alice')
    start_game(page)
    gid = game_id(seed)
    assert shot(page, gid, 0, 0, [holed(1), not_played()]).status == 201
    assert shot(bob_page, gid, 1, 0, [holed(1), holed(3)]).status == 201

    page.reload()
    page.get_by_role('button', name="Resume Alice's game").click()

    wait_for_turn(page)
    expect(game(page)).to_have_attribute('data-hole', '2')
    expect(status(page)).to_contain_text("Alice, it's your turn! Stroke 1.")


def test_an_idle_player_can_be_skipped(page: Page, seed, alice, bob, new_user_page):
    login(page, alice)
    host_game(page)
    bob_page = new_user_page(bob)
    join_game(bob_page, 'Alice')
    start_game(page)
    expect(status(bob_page)).to_contain_text('Waiting for Alice to putt')
    expect(bob_page.get_by_role('button', name='Skip Alice')).to_be_hidden()

    # Alice went to get a pizza a while ago
    long_ago = (datetime.now() - timedelta(minutes=3)).isoformat(timespec='seconds')
    seed.query('update minigolf_games set started_at = ?', [long_ago])

    bob_page.get_by_role('button', name='Skip Alice').click()

    expect(status(bob_page)).to_contain_text("Bob, it's your turn! Stroke 1.")
    expect(bob_page.locator('#minigolfScorecard')).to_contain_text('Alice (left)')
    expect(status(page)).to_contain_text('You were skipped', timeout=10_000)


def test_leaving_a_running_game_passes_the_turn_on(page: Page, alice, bob, new_user_page):
    login(page, alice)
    host_game(page)
    bob_page = new_user_page(bob)
    join_game(bob_page, 'Alice')
    start_game(page)

    page.once('dialog', lambda dialog: dialog.accept())
    page.get_by_role('button', name='Leave game').click()

    expect(page.get_by_role('heading', name="Who's playing?")).to_be_visible()
    expect(status(page)).to_contain_text('You left the game.')
    expect(status(bob_page)).to_contain_text("Bob, it's your turn! Stroke 1.", timeout=10_000)
    expect(bob_page.locator('#minigolfScorecard')).to_contain_text('Alice (left)')


def test_a_game_everybody_left_ends_without_a_winner(page: Page, seed, alice, bob, new_user_page):
    login(page, alice)
    host_game(page)
    bob_page = new_user_page(bob)
    join_game(bob_page, 'Alice')
    start_game(page)
    long_ago = (datetime.now() - timedelta(minutes=3)).isoformat(timespec='seconds')
    seed.query('update minigolf_games set started_at = ?', [long_ago])
    bob_page.get_by_role('button', name='Skip Alice').click()
    expect(status(page)).to_contain_text('You were skipped', timeout=10_000)

    bob_page.once('dialog', lambda dialog: dialog.accept())
    bob_page.get_by_role('button', name='Leave game').click()

    # Alice kept watching
    expect(page.locator('#minigolfResult')).to_be_visible(timeout=10_000)
    expect(status(page)).to_contain_text('Everybody left, so nobody wins.')
    expect(page.locator('#minigolfSaved')).to_contain_text('no rounds were saved')
    assert seed.query('select * from minigolf_rounds') == []


def test_the_host_leaving_the_lobby_calls_the_game_off(page: Page, seed, alice, bob, new_user_page):
    login(page, alice)
    host_game(page)
    bob_page = new_user_page(bob)
    join_game(bob_page, 'Alice')

    page.locator('#minigolfLobby').get_by_role('button', name='Leave').click()

    expect(status(bob_page)).to_contain_text('The game was called off.', timeout=10_000)
    expect(bob_page.get_by_role('heading', name="Who's playing?")).to_be_visible()
    assert seed.query('select * from minigolf_games') == []


def test_moves_that_dont_fit_the_game_are_refused(page: Page, seed, alice, bob, new_user_page, admin):
    login(page, alice)
    created = page.request.post('/minigolf/api/games')
    assert created.status == 201
    gid = created.json()['id']
    assert page.request.post(f'/minigolf/api/games/{gid}/start').status == 409  # alone
    bob_page = new_user_page(bob)
    assert bob_page.request.post(f'/minigolf/api/games/{gid}/join').status == 200
    assert bob_page.request.post(f'/minigolf/api/games/{gid}/start').status == 403  # not the host
    assert page.request.post(f'/minigolf/api/games/{gid}/start').status == 200
    admin_page = new_user_page(admin)
    assert admin_page.request.post(f'/minigolf/api/games/{gid}/join').status == 409  # already started

    assert shot(bob_page, gid, 0, 0, [not_played(), holed(1)]).status == 409       # Alice's turn
    assert shot(admin_page, gid, 0, 0, [holed(1), not_played()]).status == 403     # not playing
    assert shot(page, gid, 1, 0, [holed(1), not_played()]).status == 409           # wrong seq
    assert shot(page, gid, 0, 1, [holed(1), not_played()]).status == 409           # wrong hole
    assert shot(page, gid, 0, 0, [not_played(), not_played()]).status == 400       # no stroke taken
    assert shot(page, gid, 0, 0, [holed(1)]).status == 400                         # a ball missing
    assert shot(page, gid, 0, 0, [holed(1), not_played()], dx=1e9).status == 400  # not a direction
    assert shot(page, gid, 0, 0, [holed(1), not_played()], time=-1).status == 400
    assert seed.query('select * from minigolf_moves') == []

    assert shot(page, gid, 0, 0, [holed(1), not_played()]).status == 201
    assert shot(page, gid, 1, 0, [holed(2), not_played()]).status == 409           # Bob's turn now
    assert page.request.post(f'/minigolf/api/games/{gid}/skip', data={'seat': 1, 'seq': 1}).status == 409  # not idle


def test_a_full_game_cant_be_joined(page: Page, seed, alice, bob, new_user_page):
    login(page, alice)
    gid = page.request.post('/minigolf/api/games').json()['id']
    for name in ('Bob', 'Carol', 'Dave'):
        other = bob if name == 'Bob' else seed.user(name)
        assert new_user_page(other).request.post(f'/minigolf/api/games/{gid}/join').status == 200
    eve_page = new_user_page(seed.user('Eve'))

    assert eve_page.request.post(f'/minigolf/api/games/{gid}/join').status == 409
    eve_page.goto('/minigolf/')
    listed = eve_page.locator('#minigolfGames li')
    expect(listed).to_contain_text("Alice's game (Classic): Alice, Bob, Carol, Dave")
    expect(listed).to_contain_text('(full)')
    expect(eve_page.get_by_role('button', name="Join Alice's game")).to_have_count(0)
