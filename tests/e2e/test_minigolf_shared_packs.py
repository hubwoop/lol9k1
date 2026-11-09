"""Minigolf map packs shared by players: publish them from the editor, browse, test and play them."""
import json
from datetime import datetime, timedelta

from playwright.sync_api import Page, expect

from conftest import login
from test_minigolf import game, putt, wait_for_turn
from test_minigolf_network import game_id, holed, shot, status

MAX_PACKS = 10


def builtin_holes(page: Page, pack: str = 'classic') -> list:
    page.goto('/minigolf/')
    return page.evaluate(f'lol9k1MinigolfPacks[{json.dumps(pack)}].holes')


def publish(page: Page, name: str, holes: list, **extra):
    return page.request.post('/minigolf/api/packs', data={'name': name, 'hint': 'Fun for all', 'holes': holes, **extra})


def update(page: Page, pack_id: int, name: str, holes: list):
    return page.request.put(f'/minigolf/api/packs/{pack_id}', data={'name': name, 'hint': '', 'holes': holes})


def packs(page: Page) -> list:
    return page.request.get('/minigolf/api/packs').json()


def test_a_shared_pack_is_offered_to_everybody_and_has_a_hall_of_fame(page: Page, seed, alice, bob, new_user_page):
    login(page, alice)
    holes = builtin_holes(page)
    response = publish(page, '  Alice’s   Lanes ', holes)
    assert response.status == 201
    pack = response.json()
    assert (pack['name'], pack['author'], pack['course'], pack['version'], pack['holes'], pack['par']) == \
        ('Alice’s Lanes', 'Alice', 'pack:1', 1, 9, sum(h['par'] for h in holes))
    assert pack['mine'] and pack['can_withdraw']

    bob_page = new_user_page(bob)
    [listed] = packs(bob_page)
    assert listed['name'] == 'Alice’s Lanes' and not listed['mine'] and not listed['can_withdraw']
    course = bob_page.request.get('/minigolf/api/courses/pack:1').json()
    assert (course['name'], course['author'], course['playable']) == ('Alice’s Lanes', 'Alice', True)
    assert [h['name'] for h in course['holes']] == [h['name'] for h in holes]

    # rounds on it go to a Hall of Fame of its own
    assert bob_page.request.post('/minigolf/api/rounds', data={'course': 'pack:1', 'strokes': [2] * 9}).status == 201
    assert bob_page.request.post('/minigolf/api/rounds', data={'course': 'pack:1', 'strokes': [2] * 8}).status == 400
    board = bob_page.request.get('/minigolf/api/leaderboard?course=pack:1').json()
    assert board['best'] == [{'name': 'Bob', 'best': 18, 'rounds': 1}]
    assert bob_page.request.get('/minigolf/api/leaderboard').json()['best'] == []
    [listed] = packs(bob_page)
    assert (listed['rounds'], listed['players'], listed['best']) == (1, 1, {'total': 18, 'name': 'Bob'})

    # only shared packs are served, and only ones that exist
    for course in ('classic', 'pack:2', 'pack:x', 'pack:-1', 'pack:１'):
        assert bob_page.request.get(f'/minigolf/api/courses/{course}').status == 404


def test_packs_that_cant_be_played_are_refused(page: Page, seed, alice):
    login(page, alice)
    holes = builtin_holes(page)
    response = publish(page, 'Broken', [{**holes[0], 'cup': [5, 5]}])
    assert response.status == 400
    assert response.json() == 'hole 1: the cup is off the fairway or in the water'
    assert publish(page, ' ', holes).json() == 'the name of the pack is missing'
    assert publish(page, 'x' * 41, holes).status == 400
    assert publish(page, 'Too long', holes * 3).json() == 'a pack has 1 to 18 holes'
    assert publish(page, 'Huge', holes, padding='x' * 200_000).status == 413
    assert page.request.post('/minigolf/api/packs', data='[]', headers={'Content-Type': 'application/json'}).status == 400
    assert seed.query('select * from minigolf_packs') == []
    assert seed.query('select * from minigolf_pack_versions') == []


def test_every_player_shares_a_limited_number_of_packs(page: Page, seed, alice):
    login(page, alice)
    holes = builtin_holes(page)[:1]
    for i in range(MAX_PACKS):
        assert publish(page, f'Pack {i}', holes).status == 201
    response = publish(page, 'One too many', holes)
    assert response.status == 409
    assert 'withdraw one or publish an update' in response.json()

    # a withdrawn pack makes room
    assert page.request.delete('/minigolf/api/packs/1').status == 200
    assert publish(page, 'One more', holes).status == 201
    # names are their own, an update is the way to change a pack
    assert publish(page, 'pack 2', holes).status == 409
    assert len(seed.query("select * from minigolf_packs where status = 'listed'")) == MAX_PACKS


def test_an_update_is_a_new_version_and_played_versions_are_kept(page: Page, seed, alice, bob, new_user_page):
    login(page, alice)
    holes = builtin_holes(page)
    publish(page, 'Lanes', holes)
    assert page.request.post('/minigolf/api/rounds', data={'course': 'pack:1', 'strokes': [3] * 9}).status == 201

    response = update(page, 1, 'Lanes', holes[:3])
    assert response.status == 200
    assert (response.json()['course'], response.json()['version'], response.json()['holes']) == ('pack:2', 2, 3)
    # the first version was played, so it stays with its Hall of Fame, but new games are on the new one
    assert page.request.get('/minigolf/api/leaderboard?course=pack:1').json()['best'][0]['best'] == 27
    assert page.request.get('/minigolf/api/courses/pack:1').json()['name'] == 'Lanes (v1)'
    assert page.request.post('/minigolf/api/games', data={'course': 'pack:1'}).status == 409
    assert page.request.post('/minigolf/api/games', data={'course': 'pack:2'}).status == 201

    # the same holes under a new name aren't a new version
    response = update(page, 1, 'Lovely Lanes', holes[:3])
    assert (response.json()['name'], response.json()['version']) == ('Lovely Lanes', 2)

    bob_page = new_user_page(bob)
    assert update(bob_page, 1, 'Mine now', holes).status == 403

    # versions nobody played go once they've been out of date for a while
    update(page, 1, 'Lovely Lanes', holes[:2])  # version 3, version 2 has a game on it
    update(page, 1, 'Lovely Lanes', holes[:1])  # version 4
    a_while_ago = (datetime.now() - timedelta(hours=3)).isoformat(timespec='seconds')
    seed.query('update minigolf_pack_versions set published_at = ?', [a_while_ago])
    update(page, 1, 'Lovely Lanes', holes[:4])  # version 5
    versions = [r['number'] for r in seed.query('select number from minigolf_pack_versions order by number')]
    assert versions == [1, 2, 4, 5]


def test_a_pack_is_withdrawn_by_its_author_or_an_admin(page: Page, seed, alice, bob, admin, new_user_page):
    login(page, alice)
    publish(page, 'Lanes', builtin_holes(page)[:1])
    publish(page, 'More Lanes', builtin_holes(page)[:2])
    bob_page = new_user_page(bob)
    assert bob_page.request.delete('/minigolf/api/packs/1').status == 403
    page.goto('/minigolf/packs?mine=1')
    page.once('dialog', lambda dialog: dialog.accept())
    page.get_by_role('button', name='Withdraw Lanes').click()
    expect(page.get_by_role('listitem', name='Lanes', exact=True)).to_have_count(0)
    assert seed.query('select status from minigolf_packs where id = 1')[0]['status'] == 'withdrawn'
    assert page.request.delete('/minigolf/api/packs/1').status == 409
    admin_page = new_user_page(admin)
    assert [p['can_withdraw'] for p in packs(admin_page)] == [True]
    assert admin_page.request.delete('/minigolf/api/packs/2').status == 200

    assert packs(bob_page) == []
    # games and rounds on it can still be finished, but nobody can host a new one
    course = bob_page.request.get('/minigolf/api/courses/pack:1').json()
    assert course['playable'] is False
    assert bob_page.request.post('/minigolf/api/games', data={'course': 'pack:1'}).status == 409
    assert update(page, 1, 'Lanes', builtin_holes(page)[:1]).status == 409
    # it can still be played hot seat by its link, and a link to no pack is the classic one
    bob_page.goto('/minigolf/?course=pack:1')
    expect(bob_page.get_by_label('Map pack')).to_have_value('pack:1')
    expect(status(bob_page)).to_have_text('Ready.')
    bob_page.goto('/minigolf/?course=pack:99')
    expect(bob_page.get_by_label('Map pack')).to_have_value('classic')


def test_build_a_pack_test_every_hole_and_publish_it(page: Page, seed, alice):
    login(page, alice)
    page.goto('/minigolf/editor')
    page.get_by_label('Pack to load').select_option(label='A new pack')
    page.get_by_role('button', name='Load').click()
    page.get_by_label('Name', exact=True).first.fill('My First Pack')
    page.get_by_label('Name', exact=True).first.press('Tab')

    blockers = page.get_by_role('list', name='Before publishing')
    expect(blockers).to_have_text("Hole 1 (New hole) hasn't been holed in a test run yet.")
    expect(page.get_by_role('button', name='Publish', exact=True)).to_be_disabled()

    # the new hole is a straight lane, the cup is 420px to the right of the tee
    page.get_by_role('button', name='▶ Test').click()
    wait_for_turn(page)
    putt(page, 300, 200, -85, 0)
    expect(page.locator('#minigolfResult')).to_be_visible(timeout=20_000)
    page.get_by_role('button', name='■ Stop test').click()
    expect(page.locator('#mgeHoles button').first).to_have_attribute('data-tested', 'true')
    expect(blockers.get_by_role('listitem')).to_have_count(0)

    page.get_by_role('button', name='Publish', exact=True).click()
    expect(page.locator('#mgePublishMessage')).to_contain_text('Published My First Pack, version 1.')
    [row] = seed.query('select p.name, v.holes from minigolf_packs p join minigolf_pack_versions v on p.version = v.id')
    assert row['name'] == 'My First Pack'
    assert [h['name'] for h in json.loads(row['holes'])] == ['New hole']

    # it's an update from now on, and a changed hole has to be holed again
    expect(page.get_by_role('button', name='Publish update (version 2)')).to_be_enabled()
    page.get_by_label('Par', exact=True).fill('4')
    page.get_by_label('Par', exact=True).press('Tab')
    expect(blockers).to_have_text("Hole 1 (New hole) hasn't been holed in a test run yet.")
    expect(page.get_by_role('button', name='Publish as a new pack')).to_be_visible()


def test_browse_test_and_play_somebody_elses_pack(page: Page, seed, alice, bob, new_user_page):
    login(page, alice)
    warm_up = builtin_holes(page)[0]
    publish(page, 'Warm Ups', [warm_up, {**warm_up, 'name': 'Again'}])

    bob_page = new_user_page(bob)
    bob_page.goto('/minigolf/')
    bob_page.get_by_role('link', name='🗺 Map packs').click()
    pack = bob_page.get_by_role('listitem', name='Warm Ups')
    expect(pack).to_contain_text('by Alice')
    expect(pack).to_contain_text('2 holes, par 4')
    expect(pack).to_contain_text('nobody played it yet')
    expect(pack.get_by_role('button', name='Withdraw Warm Ups')).to_have_count(0)

    # test a hole in the editor, it's a pack of Bob's own from there on
    pack.get_by_role('link', name='Test hole 2, Again, par 2').click()
    expect(bob_page.locator('#mgePublishMessage')).to_have_text(
        'Loaded Warm Ups by Alice. Test it, change it, publish it as a pack of your own.')
    expect(bob_page.locator('#mgeHoles button[aria-current="true"]')).to_have_text('Again (par 2)')
    expect(bob_page.locator('#mgeShareStatus')).to_contain_text('Made from Warm Ups by Alice')
    assert bob_page.url.endswith('/minigolf/editor')
    # Undo takes back what was in the editor before
    bob_page.get_by_role('button', name='↶ Undo').click()
    expect(bob_page.get_by_role('list', name='Holes').get_by_role('button').first).to_have_text('Warm-up (par 2)')

    bob_page.goto('/minigolf/packs')
    bob_page.get_by_role('link', name='Play Warm Ups').click()
    expect(bob_page.get_by_label('Map pack')).to_have_value('pack:1')
    expect(bob_page.locator('#minigolfBoardCourse')).to_have_text('Warm Ups')
    expect(bob_page.locator('#minigolfCourseHint')).to_have_text('Fun for all (by Alice)')
    expect(status(bob_page)).to_have_text('Ready.')
    bob_page.get_by_role('button', name='Tee off!').click()
    wait_for_turn(bob_page)
    putt(bob_page, 300, 200, -85, 0)
    expect(game(bob_page)).to_have_attribute('data-hole', '2', timeout=20_000)
    wait_for_turn(bob_page)
    putt(bob_page, 300, 200, -85, 0)
    expect(bob_page.locator('#minigolfSaved')).to_contain_text('went into the Hall of Fame', timeout=20_000)
    rows = seed.query('select course, strokes from minigolf_rounds')
    assert [(r['course'], json.loads(r['strokes'])) for r in rows] == [('pack:1', [1, 1])]

    # and it's picked like any other pack
    page.goto('/minigolf/packs?sort=new')
    expect(page.get_by_role('listitem', name='Warm Ups')).to_contain_text('1 round by 1 player, best 2 by Bob')


def test_a_network_game_on_a_shared_pack(page: Page, seed, alice, bob, new_user_page):
    login(page, alice)
    warm_up = builtin_holes(page)[0]
    publish(page, 'Quickie', [warm_up])
    page.goto('/minigolf/')
    page.get_by_label('Map pack').select_option(label='Quickie by Alice')
    expect(status(page)).to_have_text('Ready.')
    page.get_by_role('button', name='Host a network game').click()
    expect(page.locator('#minigolfLobbyTitle')).to_have_text("Alice's game: Quickie")

    # Bob has the classic pack picked, the game loads the shared one
    bob_page = new_user_page(bob)
    bob_page.goto('/minigolf/')
    expect(bob_page.locator('#minigolfGames')).to_contain_text("Alice's game (Quickie): Alice")
    bob_page.get_by_role('button', name="Join Alice's game").click()
    expect(bob_page.locator('#minigolfLobbyTitle')).to_have_text("Alice's game: Quickie")
    page.get_by_role('button', name='Start the game').click()
    wait_for_turn(page)
    putt(page, 300, 200, -85, 0)
    expect(status(bob_page)).to_contain_text("Bob, it's your turn! Stroke 1.", timeout=20_000)
    assert shot(bob_page, game_id(seed), 1, 0, [holed(1), holed(2)]).status == 201

    expect(page.locator('#minigolfResult')).to_be_visible(timeout=10_000)
    rows = seed.query('select user, course, strokes from minigolf_rounds order by user')
    assert [(r['user'], r['course'], json.loads(r['strokes'])) for r in rows] == \
        [(alice.id, 'pack:1', [1]), (bob.id, 'pack:1', [2])]
