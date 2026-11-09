"""Minigolf map packs shared by players: publish them from the editor, browse, test and play them."""
import json
from datetime import datetime, timedelta

from playwright.sync_api import Page, expect

from conftest import expect_flash, login
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
    response = page.request.post('/minigolf/api/games', data={'course': 'pack:1'})
    assert (response.status, response.json()) == \
        (409, 'that is an older version of the pack, pick its latest version to host a game')
    assert page.request.post('/minigolf/api/games', data={'course': 'pack:2'}).status == 201

    # the same holes under a new name aren't a new version
    response = update(page, 1, 'Lovely Lanes', holes[:3])
    assert (response.json()['name'], response.json()['version']) == ('Lovely Lanes', 2)

    # its rounds on earlier versions still count for "most played"
    [listed] = packs(page)
    assert (listed['rounds'], listed['rounds_all']) == (0, 1)
    page.goto('/minigolf/packs')
    expect(page.get_by_role('listitem', name='Lovely Lanes')).to_contain_text(
        'nobody played this version yet (1 round on earlier versions)')

    bob_page = new_user_page(bob)
    assert update(bob_page, 1, 'Mine now', holes).status == 403
    # whose pack it is comes first, whatever is wrong with the pack
    assert update(bob_page, 1, ' ', []).status == 403

    # versions nobody played go once they've been out of date for a while, which is days: a hot seat round
    # may still be played on one
    update(page, 1, 'Lovely Lanes', holes[:2])  # version 3, version 2 has a game on it
    update(page, 1, 'Lovely Lanes', holes[:1])  # version 4
    a_while_ago = (datetime.now() - timedelta(days=2)).isoformat(timespec='seconds')
    seed.query('update minigolf_pack_versions set published_at = ?', [a_while_ago])
    update(page, 1, 'Lovely Lanes', holes[:4])  # version 5
    assert [r['number'] for r in seed.query('select number from minigolf_pack_versions order by number')] == \
        [1, 2, 3, 4, 5]
    update(page, 1, 'Lovely Lanes', holes[:1])  # version 6
    a_while_ago = (datetime.now() - timedelta(days=4)).isoformat(timespec='seconds')
    seed.query('update minigolf_pack_versions set published_at = ?', [a_while_ago])
    update(page, 1, 'Lovely Lanes', holes[:4])  # version 7
    versions = [r['number'] for r in seed.query('select number from minigolf_pack_versions order by number')]
    assert versions == [1, 2, 6, 7]
    # a round on a version that's gone tells so, the game says it's gone
    response = page.request.post('/minigolf/api/rounds', data={'course': 'pack:3', 'strokes': [2] * 2})
    assert (response.status, response.json()) == (404, 'there is no such pack anymore, it may have been updated')
    assert page.request.post('/minigolf/api/rounds', data={'course': 'nope', 'strokes': [2]}).status == 400


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
    # Alice holed them all before publishing, they count until they're changed
    expect(bob_page.get_by_role('list', name='Before publishing').get_by_role('listitem')).to_have_count(0)
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


def test_the_packs_that_come_with_the_game_can_be_shared(page: Page, alice):
    """Whatever the editor can load, the server takes as it is."""
    login(page, alice)
    for pack in ('classic', 'brawl'):
        holes = builtin_holes(page, pack)
        response = publish(page, pack, holes)
        assert response.status == 201, response.json()
        shared = page.request.get(f"/minigolf/api/courses/{response.json()['course']}").json()['holes']
        assert shared == [{k: v for k, v in h.items() if v != [] and v is not False} for h in holes]


def test_most_played_counts_every_version_and_newest_is_the_latest_version(page: Page, seed, alice):
    login(page, alice)
    holes = builtin_holes(page)
    publish(page, 'Old Favourite', holes[:1])
    publish(page, 'Newcomer', holes[:2])
    page.request.post('/minigolf/api/rounds', data={'course': 'pack:1', 'strokes': [2]})
    update(page, 1, 'Old Favourite', holes[:3])  # a fresh Hall of Fame, but still the most played
    assert [p['name'] for p in packs(page)] == ['Old Favourite', 'Newcomer']
    assert [p['name'] for p in page.request.get('/minigolf/api/packs?sort=new').json()] == ['Old Favourite', 'Newcomer']
    # a new name isn't a new pack
    a_while_ago = (datetime.now() - timedelta(hours=1)).isoformat(timespec='seconds')
    seed.query('update minigolf_pack_versions set published_at = ? where pack = 1', [a_while_ago])
    update(page, 1, 'Old Favourite Renamed', holes[:3])
    assert [p['name'] for p in page.request.get('/minigolf/api/packs?sort=new').json()] == \
        ['Newcomer', 'Old Favourite Renamed']
    assert page.request.get('/minigolf/api/packs?sort=nope').status == 400


def test_every_player_stores_a_limited_number_of_versions(page: Page, seed, alice):
    login(page, alice)
    holes = builtin_holes(page)
    publish(page, 'Busy', holes[:1])
    for i in range(2, 51):  # every one different from the one before
        assert update(page, 1, 'Busy', holes[:2 - i % 2]).status == 200, i
    response = update(page, 1, 'Busy', holes[:3])
    assert response.status == 409
    assert 'versions of your packs stored, 50 at most' in response.json()

    # versions nobody played go a while after they're replaced, then there's room again
    a_while_ago = (datetime.now() - timedelta(days=4)).isoformat(timespec='seconds')
    seed.query('update minigolf_pack_versions set published_at = ?', [a_while_ago])
    assert update(page, 1, 'Busy', holes[:3]).status == 200
    assert [r['number'] for r in seed.query('select number from minigolf_pack_versions')] == [50, 51]


def test_a_withdrawn_pack_nobody_played_goes_after_a_while(page: Page, seed, alice, bob, new_user_page):
    login(page, alice)
    holes = builtin_holes(page)
    publish(page, 'Gone', holes[:1])
    publish(page, 'Played', holes[:1])
    page.request.post('/minigolf/api/rounds', data={'course': 'pack:2', 'strokes': [2]})
    page.request.delete('/minigolf/api/packs/1')
    page.request.delete('/minigolf/api/packs/2')
    # a pack made from it still credits it while it's there
    bob_page = new_user_page(bob)
    assert publish(bob_page, 'Remix', holes[1:2], based_on=1).json()['based_on']['name'] == 'Gone'
    assert publish(bob_page, 'Remix of nothing', holes[:1], based_on=99).json()['based_on'] is None
    assert publish(bob_page, 'Bad credit', holes[:1], based_on='1').status == 400

    a_while_ago = (datetime.now() - timedelta(days=4)).isoformat(timespec='seconds')
    seed.query('update minigolf_packs set updated_at = ? where id in (1, 2)', [a_while_ago])
    publish(page, 'Next', holes[:1])
    # Bob's packs 3 and 4 and the new 5 stay, so does 2, which has been played
    assert [r['pack'] for r in seed.query('select pack from minigolf_pack_versions order by pack')] == [2, 3, 4, 5]
    assert page.request.get('/minigolf/api/packs/1').status == 404
    assert page.request.get('/minigolf/api/courses/pack:2').status == 200


def test_a_lobby_on_a_withdrawn_pack_can_still_be_played(page: Page, seed, alice, bob, new_user_page):
    login(page, alice)
    publish(page, 'Lanes', builtin_holes(page)[:1])
    gid = page.request.post('/minigolf/api/games', data={'course': 'pack:1'}).json()['id']
    page.request.delete('/minigolf/api/packs/1')
    bob_page = new_user_page(bob)
    assert bob_page.request.post(f'/minigolf/api/games/{gid}/join').status == 200
    assert page.request.post(f'/minigolf/api/games/{gid}/start').status == 200


def test_names_are_unique_per_player_whatever_their_case(page: Page, seed, alice, bob, new_user_page):
    login(page, alice)
    holes = builtin_holes(page)[:1]
    publish(page, 'Lanes', holes)
    publish(page, 'Other', holes)
    assert publish(page, 'LANES', holes).json() == 'you already share a pack called LANES, publish an update of it instead'
    assert update(page, 2, 'lanes', holes).status == 409
    # somebody else's, or a withdrawn one, doesn't count
    assert publish(new_user_page(bob), 'Lanes', holes).status == 201
    page.request.delete('/minigolf/api/packs/1')
    assert publish(page, 'Lanes', holes).status == 201


def test_testing_a_shared_pack_keeps_your_work(page: Page, seed, alice):
    login(page, alice)
    publish(page, 'Lanes', builtin_holes(page)[:2])
    page.goto('/minigolf/editor')
    page.get_by_label('Pack to load').select_option(label='A new pack')
    page.get_by_role('button', name='Load').click()
    page.get_by_label('Name', exact=True).first.fill('My Masterpiece')
    page.get_by_label('Name', exact=True).first.press('Tab')
    expect(page.locator('#mgeRestore')).to_be_hidden()

    page.goto('/minigolf/editor?pack=1')
    expect(page.locator('#mgePublishMessage')).to_have_text('Loaded your pack Lanes.')
    # even after a reload, the work is a click away
    page.reload()
    expect(page.get_by_label('Name', exact=True).first).to_have_value('Lanes')
    page.get_by_role('button', name='↩ Back to My Masterpiece').click()
    expect(page.get_by_label('Name', exact=True).first).to_have_value('My Masterpiece')
    # Lanes was loaded as it is, so there's nothing to bring back
    expect(page.locator('#mgeRestore')).to_be_hidden()

    # loading a pack over it keeps it too
    page.get_by_label('Pack to load').select_option(label='Classic')
    page.get_by_role('button', name='Load').click()
    expect(page.get_by_role('button', name='↩ Back to My Masterpiece')).to_be_visible()


def test_publishing_is_remembered_whatever_is_undone(page: Page, seed, alice):
    login(page, alice)
    publish(page, 'Lanes', builtin_holes(page)[:1])
    page.goto('/minigolf/editor?pack=1')
    expect(page.locator('#mgeShareStatus')).to_have_text('This is your shared pack Lanes, version 1.')
    hole_name = page.get_by_label('Name', exact=True).nth(1)
    hole_name.fill('Renamed')
    hole_name.press('Tab')
    expect(page.locator('#mgeShareStatus')).to_contain_text("with changes that aren't published yet")
    page.get_by_role('button', name='↶ Undo').click()
    page.get_by_role('button', name='↶ Undo').click()  # back to before Lanes was loaded
    page.get_by_role('button', name='↷ Redo').click()
    page.get_by_role('button', name='↷ Redo').click()
    expect(page.locator('#mgeShareStatus')).to_contain_text('This is your shared pack Lanes, version 1')


def test_what_the_server_would_refuse_is_pointed_out_before_publishing(page: Page, alice):
    login(page, alice)
    page.goto('/minigolf/editor')
    page.get_by_label('Pack to load').select_option(label='A new pack')
    page.get_by_role('button', name='Load').click()
    blockers = page.get_by_role('list', name='Before publishing')
    hole_name = page.get_by_label('Name', exact=True).nth(1)
    hole_name.fill('   ')
    hole_name.press('Tab')
    expect(blockers).to_contain_text('Hole 1 (   ): it has no name.')
    hole_name.fill('x' * 40)
    hole_name.press('Tab')
    expect(blockers).not_to_contain_text('longer than')
    # measured like the server does: collapsed whitespace, characters rather than UTF-16 units
    hint = page.get_by_label('Hint')
    hint.fill('🏌' * 200)
    hint.press('Tab')
    expect(blockers).not_to_contain_text('The hint')
    hint.fill('🏌' * 201)
    hint.press('Tab')
    expect(blockers).to_contain_text('The hint is longer than 200 characters.')
    hint.fill('a' + ' ' * 300 + 'b')
    hint.press('Tab')
    expect(blockers).not_to_contain_text('The hint')


def test_a_pack_that_cant_be_loaded_can_be_tried_again(page: Page, seed, alice, bob, new_user_page):
    login(page, alice)
    publish(page, 'Lanes', builtin_holes(page)[:1])
    bob_page = new_user_page(bob)
    failing = {'on': True}

    def flaky(route):
        if failing['on']:
            route.fulfill(status=503, content_type='application/json', body='"down for a moment"')
        else:
            route.continue_()
    bob_page.route('**/minigolf/api/courses/**', flaky)
    bob_page.goto('/minigolf/')
    bob_page.get_by_label('Map pack').select_option(label='Lanes by Alice')
    # it's said next to the picker, with a button to try again
    notice = bob_page.locator('#minigolfCourseNotice')
    expect(notice).to_have_text("Couldn't load Lanes. Check your connection and try again. Retry")
    expect(status(bob_page)).to_have_text("Couldn't load Lanes. Check your connection and try again.")
    bob_page.get_by_role('button', name='Retry').click()
    expect(notice).to_contain_text("Couldn't load Lanes")
    # so does teeing off
    bob_page.get_by_role('button', name='Tee off!').click()
    expect(notice).to_contain_text("Couldn't load Lanes")
    failing['on'] = False
    bob_page.get_by_role('button', name='Retry').click()
    expect(status(bob_page)).to_have_text('Ready.')
    expect(notice).to_be_hidden()
    bob_page.get_by_role('button', name='Tee off!').click()
    wait_for_turn(bob_page)
    expect(game(bob_page)).to_have_attribute('data-hole', '1')


def test_a_pack_without_a_length_is_refused(page: Page, alice, live_server):
    """Its size is checked before it's read, so a request has to say how long it is."""
    import http.client
    from urllib.parse import urlparse
    login(page, alice)
    cookie = '; '.join(f"{c['name']}={c['value']}" for c in page.context.cookies())
    url = urlparse(live_server)
    connection = http.client.HTTPConnection(url.hostname, url.port, timeout=10)
    connection.request('POST', '/minigolf/api/packs', body=iter([b'{"name": "Chunked", "holes": []}']),
                       headers={'Cookie': cookie, 'Content-Type': 'application/json'}, encode_chunked=True)
    response = connection.getresponse()
    assert (response.status, json.loads(response.read())) == (411, 'the request has no Content-Length')


def test_a_copy_of_a_shared_pack_isnt_a_pack_of_your_own(page: Page, seed, alice, bob, new_user_page):
    login(page, alice)
    holes = builtin_holes(page)[:2]
    publish(page, 'Lanes', holes)
    bob_page = new_user_page(bob)
    response = publish(bob_page, 'My Lanes', holes, based_on=1)
    assert (response.status, response.json()) == (409, "change something first, it's the same as Lanes by Alice")
    assert publish(bob_page, 'My Lanes', holes[:1], based_on=1).status == 201


def test_an_old_link_to_a_pack_says_what_can_be_played(page: Page, seed, alice):
    login(page, alice)
    holes = builtin_holes(page)
    publish(page, 'Lanes', holes[:1])
    page.request.post('/minigolf/api/rounds', data={'course': 'pack:1', 'strokes': [2]})  # so version 1 is kept
    update(page, 1, 'Lanes', holes[:2])
    notice = page.locator('#minigolfCourseNotice')
    host = page.get_by_role('button', name='Host a network game')

    # an older version can still be played hot seat, the latest one is a click away
    page.goto('/minigolf/?course=pack:1')
    expect(page.get_by_label('Map pack')).to_have_value('pack:1')
    expect(notice).to_contain_text('This is an older version of the pack: hot seat only')
    expect(host).to_be_disabled()
    page.get_by_role('link', name='Play Lanes, its latest version').click()
    expect(page.get_by_label('Map pack')).to_have_value('pack:2')
    expect(notice).to_be_hidden()
    expect(host).to_be_enabled()

    # so can a withdrawn pack
    page.request.delete('/minigolf/api/packs/1')
    page.goto('/minigolf/?course=pack:2')
    expect(notice).to_have_text("This pack was withdrawn: hot seat only, it can't be hosted over the network.")
    expect(host).to_be_disabled()
    response = page.request.post('/minigolf/api/games', data={'course': 'pack:2'})
    assert (response.status, response.json()) == (409, 'that pack has been withdrawn, it can only be played hot seat now')
    page.get_by_label('Map pack').select_option('classic')
    expect(host).to_be_enabled()

    # and one that isn't there at all falls back to the classic pack, saying so
    page.goto('/minigolf/?course=pack:99')
    expect_flash(page, "That map pack doesn't exist anymore, here's Classic.")
    expect(page.get_by_label('Map pack')).to_have_value('classic')
    page.goto('/minigolf/')
    expect(page.get_by_role('alert')).to_have_count(0)


def test_the_editor_knows_every_limit(page: Page, alice):
    login(page, alice)
    page.goto('/minigolf/editor')
    limits = json.loads(page.locator('#minigolfEditor').get_attribute('data-limits'))
    assert (limits['bumper'], limits['speed'], limits['blades']) == (80, 10, 8)


def test_withdrawing_on_the_browse_page_says_what_happened(page: Page, seed, alice):
    login(page, alice)
    publish(page, 'Lanes', builtin_holes(page)[:1])
    publish(page, 'More Lanes', builtin_holes(page)[:1])
    page.goto('/minigolf/packs?mine=1')
    empty = page.locator('.mgpEmpty')
    expect(empty).to_be_hidden()
    dialogs = []
    page.on('dialog', lambda dialog: (dialogs.append(dialog.message), dialog.accept()))

    # what the server says goes to the player, not an HTTP status
    page.route('**/minigolf/api/packs/1', lambda route: route.fulfill(
        status=403, content_type='application/json', body='"only its author or an admin can withdraw a pack"'))
    with page.expect_event('dialog', lambda dialog: dialog.type == 'alert'):
        page.get_by_role('button', name='Withdraw Lanes').click()
    assert dialogs[-1] == "Couldn't withdraw Lanes: only its author or an admin can withdraw a pack"
    expect(page.get_by_role('listitem', name='Lanes', exact=True)).to_have_count(1)
    page.unroute('**/minigolf/api/packs/1')
    page.get_by_role('button', name='Withdraw Lanes').click()
    expect(page.get_by_role('listitem', name='Lanes', exact=True)).to_have_count(0)
    expect(empty).to_be_hidden()

    # one withdrawn in another tab is just taken off the list, and the last one gone leaves the empty list's words
    assert page.request.delete('/minigolf/api/packs/2').status == 200
    page.get_by_role('button', name='Withdraw More Lanes').click()
    expect(page.get_by_role('listitem', name='More Lanes')).to_have_count(0)
    expect(page.get_by_role('status')).to_have_text('More Lanes had been withdrawn already.')
    expect(empty).to_be_visible()
    expect(empty).to_contain_text("You don't share any packs yet.")
    assert len([d for d in dialogs if d.startswith("Couldn't")]) == 1


def test_the_holes_of_a_pack_that_couldnt_be_loaded_can_be_tried_again(page: Page, seed, alice):
    login(page, alice)
    publish(page, 'Lanes', builtin_holes(page)[:2])
    failing = {'on': True}

    def flaky(route):
        if failing['on']:
            route.fulfill(status=503, content_type='application/json', body='"down for a moment"')
        else:
            route.continue_()
    page.route('**/minigolf/api/courses/**', flaky)
    page.goto('/minigolf/packs')
    holes = page.get_by_role('list', name='Holes of Lanes')
    expect(holes).to_have_text("Couldn't load the holes of Lanes. Check your connection and try again. Retry")
    failing['on'] = False
    holes.get_by_role('button', name='Retry').click()
    expect(holes.get_by_role('link')).to_have_count(2)
    expect(holes.get_by_role('button', name='Retry')).to_have_count(0)
    # the pictures are decoration, the links say which hole they are
    expect(holes.locator('canvas[aria-hidden="true"]')).to_have_count(2)


def test_when_a_pack_was_published_reads_easily(page: Page, seed, alice):
    login(page, alice)
    publish(page, 'Lanes', builtin_holes(page)[:1])
    published = seed.query('select published_at from minigolf_pack_versions')[0]['published_at']
    page.goto('/minigolf/packs')
    when = page.get_by_role('listitem', name='Lanes').locator('time')
    expect(when).to_have_text(f'today {published[11:16]}')
    expect(when).to_have_attribute('title', published.replace('T', ' '))
    expect(when).to_have_attribute('datetime', published)
