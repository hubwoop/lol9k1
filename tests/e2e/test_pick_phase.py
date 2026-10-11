"""
The live team pick phase: captains take turns picking players for their teams
while every participant's browser updates in real time.
"""
import sqlite3
import time

import pytest
from playwright.sync_api import Page, Route, expect

from conftest import expect_flash, login


@pytest.fixture
def pick_phase(page: Page, seed, party, alice, new_user_page):
    """
    Alice creates an event with Bob and Carol as captains and starts the pick phase.
    Returns a helper describing the setup; ``page`` is Alice's (the event creator's) browser.
    """
    bob = seed.user('Bob')
    carol = seed.user('Carol')
    dave = seed.user('Dave')
    erin = seed.user('Erin')
    game_id = seed.game('Worms', added_by=alice)
    event_id = seed.event(game_id, creator=alice, start=party.at(0, 10), end=party.at(0, 12))

    login(page, alice)
    page.goto(f'/event/{event_id}')
    page.get_by_label('Bob').check()
    page.get_by_label('Carol').check()
    page.get_by_role('button', name='Set captains').click()
    expect(page.locator('dl dd')).to_have_text(['Bob 👑', 'Carol 👑'])
    page.get_by_role('button', name='Start picking teams').click()
    expect(page.get_by_role('heading', name='Tourney owner options:')).to_be_visible()

    class PickPhase:
        pass

    setup = PickPhase()
    setup.event_id = event_id
    setup.users = {u.name: u for u in (alice, bob, carol, dave, erin)}
    setup.creator_page = page
    setup.pages = {'Bob': new_user_page(bob), 'Carol': new_user_page(carol)}
    for captain_page in setup.pages.values():
        captain_page.goto(f'/event/{event_id}')

    def state():
        return page.request.get(f'/event/{event_id}/state').json()

    def team_of(captain: str) -> int:
        return next(t['team_id'] for t in state()['teams'] if t['captain'] == captain)

    def picking_captain() -> str:
        current = state()
        return next(t['captain'] for t in current['teams']
                    if t['team_id'] == current['pick_details']['currently_picking'])

    setup.state = state
    setup.state_of_team = lambda team_id: next(t for t in state()['teams'] if t['team_id'] == team_id)
    setup.team_of = team_of
    setup.picking_captain = picking_captain
    return setup


def wait_until(condition, timeout: float = 10):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, 'condition not met in time'
        time.sleep(0.2)


def other(captain: str) -> str:
    return 'Carol' if captain == 'Bob' else 'Bob'


@pytest.fixture
def pick_page(pick_phase, new_user_page):
    """
    Opens the pick page in a fresh browser session of ``captain`` whose captain-of requests go
    through ``on_captain_of``. The page's uncaught errors are collected in ``page.errors``.
    """

    def _open(captain: str, on_captain_of) -> Page:
        page = new_user_page(pick_phase.users[captain])
        page.errors = []
        page.on('pageerror', lambda error: page.errors.append(str(error)))
        page.route(f'**/event/{pick_phase.event_id}/captain-of', on_captain_of)
        page.goto(f'/event/{pick_phase.event_id}')
        return page

    return _open


def expect_picking_enabled(page: Page, enabled: bool, available_players: int = 3):
    pick_buttons = page.locator('#possible-teammates button')
    expect(pick_buttons).to_have_count(available_players)
    for button in [*pick_buttons.all(), page.get_by_role('button', name='Skip', exact=True)]:
        if enabled:
            expect(button).to_be_enabled()
        else:
            expect(button).to_be_disabled()


def test_pick_page_shows_teams_and_available_players(pick_phase):
    for page in [pick_phase.creator_page, *pick_phase.pages.values()]:
        teams = page.locator('#state')
        expect(teams.locator(f'#team-{pick_phase.team_of("Bob")}')).to_contain_text('Bob 👑')
        expect(teams.locator(f'#team-{pick_phase.team_of("Carol")}')).to_contain_text('Carol 👑')
        expect(teams.locator('li.isPicking')).to_have_count(1)
        available = page.locator('#possible-teammates > li')
        expect(available).to_have_count(3)
        for name in ('Alice', 'Dave', 'Erin'):
            expect(available.filter(has_text=name)).to_have_count(1)
    # only the event owner gets owner options
    expect(pick_phase.pages['Bob'].get_by_role('heading', name='Tourney owner options:')).to_have_count(0)


def test_captains_pick_players_in_turns(pick_phase):
    first = pick_phase.picking_captain()
    second = other(first)
    dave, erin = pick_phase.users['Dave'], pick_phase.users['Erin']

    # the first captain picks Dave ...
    pick_phase.pages[first].locator(f'#possible-teammate-{dave.id}').get_by_role('button').click()
    for page in [pick_phase.creator_page, *pick_phase.pages.values()]:
        expect(page.locator(f'#team-{pick_phase.team_of(first)}')).to_contain_text('Dave')
        expect(page.locator(f'#possible-teammate-{dave.id}')).to_have_count(0)
        expect(page.locator(f'#team-{pick_phase.team_of(second)}')).to_have_class('isPicking')
    assert pick_phase.picking_captain() == second

    # ... it's not their turn anymore, the server refuses another pick
    refused = pick_phase.pages[first].request.post(
        f'/event/{pick_phase.event_id}/team/{pick_phase.team_of(first)}/add-mate', data=erin.id)
    assert refused.json() == 'no.'

    # ... then the second captain picks Erin
    pick_phase.pages[second].locator(f'#possible-teammate-{erin.id}').get_by_role('button').click()
    for page in pick_phase.pages.values():
        expect(page.locator(f'#team-{pick_phase.team_of(second)}')).to_contain_text('Erin')
    assert pick_phase.picking_captain() == first


def test_non_captain_cannot_pick(pick_phase, new_user_page):
    dave = new_user_page(pick_phase.users['Dave'])
    picking_team = pick_phase.state()['pick_details']['currently_picking']

    refused = dave.request.post(f'/event/{pick_phase.event_id}/team/{picking_team}/add-mate',
                                data=pick_phase.users['Dave'].id)

    assert refused.json() == 'no.'
    assert all(len(team['players']) == 1 for team in pick_phase.state()['teams'])


def test_captain_renames_team(pick_phase):
    captain = pick_phase.picking_captain()
    page = pick_phase.pages[captain]
    team_name = page.locator(f'#team-{pick_phase.team_of(captain)} > h5')

    # the name becomes editable on click, the second click focuses it
    team_name.dblclick()
    page.keyboard.press('ControlOrMeta+A')
    page.keyboard.type('Rocket Squad')
    # leaving the field saves the new name
    page.locator('body').click(position={'x': 1, 'y': 1})

    expect(team_name).to_have_text('Team Rocket Squad')
    team = pick_phase.team_of(captain)
    wait_until(lambda: pick_phase.state_of_team(team)['name'] == 'Rocket Squad')


def test_everyone_skipping_ends_pick_phase(pick_phase, base_url):
    first = pick_phase.picking_captain()
    second = other(first)

    pick_phase.pages[first].get_by_role('button', name='Skip', exact=True).click()
    expect(pick_phase.pages[first].locator(f'#team-{pick_phase.team_of(second)}')).to_have_class('isPicking')
    pick_phase.pages[second].get_by_role('button', name='Skip', exact=True).click()

    # all pages leave the pick phase and show the event page again
    event_url = f'{base_url}/event/{pick_phase.event_id}'
    for page in [pick_phase.creator_page, *pick_phase.pages.values()]:
        expect(page).to_have_url(event_url)
        expect(page.get_by_role('heading', name='Teams')).to_be_visible()
    assert pick_phase.state()['state'] is None


def test_owner_ends_pick_phase_and_teams_are_kept(pick_phase, base_url):
    first = pick_phase.picking_captain()
    dave = pick_phase.users['Dave']
    pick_phase.pages[first].locator(f'#possible-teammate-{dave.id}').get_by_role('button').click()
    expect(pick_phase.creator_page.locator(f'#team-{pick_phase.team_of(first)}')).to_contain_text('Dave')

    pick_phase.creator_page.get_by_role('link', name='End pick phase').click()

    page = pick_phase.creator_page
    expect(page).to_have_url(f'{base_url}/event/{pick_phase.event_id}')
    expect(page.get_by_role('heading', name='Edit event details')).to_be_visible()
    team = page.locator('dl dt').filter(has_text=f'Team #{pick_phase.team_of(first)}')
    expect(team).to_be_visible()
    expect(page.locator('dl dd').filter(has_text='Dave')).to_be_visible()
    # captains' pages follow automatically
    expect(pick_phase.pages[first]).to_have_url(f'{base_url}/event/{pick_phase.event_id}')


def test_owner_can_force_skip(pick_phase):
    first = pick_phase.picking_captain()
    second = other(first)

    pick_phase.creator_page.get_by_role('button', name='Force skip').click()

    expect(pick_phase.pages[second].locator(f'#team-{pick_phase.team_of(second)}')).to_have_class('isPicking')
    assert pick_phase.picking_captain() == second


def test_captain_cannot_end_pick_phase(pick_phase):
    captain_page = pick_phase.pages['Bob']

    captain_page.goto(f'/event/{pick_phase.event_id}/stop-pick-phase')

    assert pick_phase.state()['state'] == 'pickphase'


def test_only_picking_captain_can_pick_even_if_captain_of_answers_late(pick_phase, pick_page):
    """The view must not decide whose turn it is before it knows which teams the user leads."""
    def answer_late(route: Route):
        time.sleep(1.5)  # meanwhile the page would already poll and render the state
        route.continue_()

    first = pick_phase.picking_captain()
    second = other(first)
    pages = {captain: pick_page(captain, answer_late) for captain in (first, second)}

    expect_picking_enabled(pages[first], True)
    expect_picking_enabled(pages[second], False)

    # after a pick the turn moves on to the other captain
    pages[first].locator(f'#possible-teammate-{pick_phase.users["Dave"].id}').get_by_role('button').click()
    for page in pages.values():
        expect(page.locator(f'#team-{pick_phase.team_of(second)}')).to_have_class('isPicking')
        expect(page.locator(f'#team-{pick_phase.team_of(first)}')).not_to_have_class('isPicking')
    expect_picking_enabled(pages[second], True, available_players=2)
    expect_picking_enabled(pages[first], False, available_players=2)
    assert pages[first].errors == pages[second].errors == []


CAPTAIN_OF_FAILURES = {
    'network error': lambda route: route.abort(),
    'server error': lambda route: route.fulfill(status=500, content_type='text/html',
                                                 body='<h1>Internal Server Error</h1>'),
    # e.g. an expired session: the request is redirected to the landing page
    'html instead of json': lambda route: route.fulfill(status=200, content_type='text/html',
                                                         body='<!doctype html><html><body>Login</body></html>'),
}


@pytest.mark.parametrize('failure', CAPTAIN_OF_FAILURES.keys())
def test_pick_page_survives_failing_captain_of(pick_phase, pick_page, failure):
    captain_of_fails = True

    def flaky_captain_of(route: Route):
        if captain_of_fails:
            CAPTAIN_OF_FAILURES[failure](route)
        else:
            route.continue_()

    captain = pick_phase.picking_captain()
    page = pick_page(captain, flaky_captain_of)

    # the state is shown, but as long as it's unknown whose turn it is nobody can pick
    expect(page.locator('#state > li')).to_have_count(2)
    expect(page.locator(f'#team-{pick_phase.team_of(captain)}')).to_have_class('isPicking')
    expect_picking_enabled(page, False)

    # the page keeps asking and recovers once the server answers again
    captain_of_fails = False
    expect_picking_enabled(page, True)
    page.locator(f'#possible-teammate-{pick_phase.users["Dave"].id}').get_by_role('button').click()
    expect(page.locator(f'#team-{pick_phase.team_of(captain)}')).to_contain_text('Dave')
    expect(page.locator(f'#team-{pick_phase.team_of(other(captain))}')).to_have_class('isPicking')
    expect_picking_enabled(page, False, available_players=2)
    assert page.errors == []


def delete_event(seed, event_id: int):
    with sqlite3.connect(seed.path) as db:
        db.execute('delete from tournament_participants where tournament = ?', [event_id])
        db.execute('delete from events where id = ?', [event_id])


def test_pick_page_leaves_when_event_is_deleted(pick_phase, seed, base_url):
    page = pick_phase.creator_page
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    expect(page.locator('#state > li')).to_have_count(2)

    delete_event(seed, pick_phase.event_id)

    expect_flash(page, 'does not exist')
    expect(page).to_have_url(f'{base_url}/')
    expect(page.locator('#state')).to_have_count(0)
    assert errors == []
