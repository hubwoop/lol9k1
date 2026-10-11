"""Only the creator or an admin may manage an event; broken or unknown requests fail cleanly."""
import sqlite3

import pytest
from playwright.sync_api import Page

from conftest import login
from test_pick_phase import pick_phase, other  # noqa: F401


@pytest.fixture
def alices_event(seed, party, alice) -> int:
    game_id = seed.game('Worms', added_by=alice)
    return seed.event(game_id, creator=alice, start=party.at(0, 10), end=party.at(0, 12))


def make_captains(seed, event_id: int, *users) -> None:
    with sqlite3.connect(seed.path) as db:
        for user in users:
            team_id = db.execute('insert into teams (captain) values (?)', [user.id]).lastrowid
            db.execute('insert into tournament_participants (user, tournament, team, is_team_captain) '
                       'values (?, ?, ?, 1)', [user.id, event_id, team_id])


def event_row(seed, event_id: int):
    return seed.query('select description, external_url, state, pick_order from events where id = ?', [event_id])[0]


def captain_ids(seed, event_id: int) -> list:
    rows = seed.query('select user from tournament_participants where tournament = ? and is_team_captain = 1',
                      [event_id])
    return sorted(r['user'] for r in rows)


@pytest.mark.parametrize('form', [
    {'description': 'pwned'},
    {'external_url': 'https://evil.example/'},
    {'checked-captains': 'MALLORY', 'check-captains': 'True'},
    {'initiate-picking': 'True'},
], ids=['description', 'external_url', 'captains', 'initiate-picking'])
def test_non_owner_cannot_change_event(page: Page, seed, alice, bob, alices_event, form):
    mallory = seed.user('Mallory')
    make_captains(seed, alices_event, alice, bob)
    form = {k: str(mallory.id) if v == 'MALLORY' else v for k, v in form.items()}
    before = (event_row(seed, alices_event), captain_ids(seed, alices_event))
    login(page, mallory)

    response = page.request.post(f'/event/{alices_event}', form=form)

    assert response.ok
    assert 'no.' in response.text()
    assert (event_row(seed, alices_event), captain_ids(seed, alices_event)) == before


@pytest.mark.parametrize('url', ['javascript:alert(document.domain)', ' JavaScript:alert(1)', 'data:text/html,x'])
def test_bracket_url_must_be_http(page: Page, seed, alice, alices_event, url):
    login(page, alice)

    response = page.request.post(f'/event/{alices_event}', form={'external_url': url})

    assert 'must start with http:// or https://' in response.text()
    assert event_row(seed, alices_event)['external_url'] is None


@pytest.mark.parametrize('as_admin', [False, True], ids=['user', 'admin'])
@pytest.mark.parametrize('method, path', [
    ('get', '/event/999/state'),
    ('post', '/event/999/team/1/skip'),
    ('post', '/event/999/team/1/add-mate'),
    ('get', '/event/999/stop-pick-phase'),
    ('get', '/event/delete/999'),
])
def test_nonexistent_event_is_404(page: Page, seed, alice, admin, as_admin, method, path):
    login(page, admin if as_admin else alice)

    if method == 'post':
        response = page.request.post(path, data='1', headers={'Content-Type': 'application/json'})
    else:
        response = page.request.get(path, max_redirects=0)

    assert response.status == 404


def test_state_of_event_without_pick_phase(page: Page, alice, alices_event):
    login(page, alice)

    response = page.request.get(f'/event/{alices_event}/state')

    assert response.status == 200
    assert response.json() == {'teams': [], 'pick_details': {'pick_order': [], 'currently_picking': None},
                               'state': None}


def test_unknown_team_and_malformed_pick_are_rejected(pick_phase):
    request = pick_phase.creator_page.request
    base = f'/event/{pick_phase.event_id}'
    team = pick_phase.state()['pick_details']['currently_picking']
    json_header = {'Content-Type': 'application/json'}

    assert request.post(f'{base}/team/9999/skip').status == 404
    assert request.post(f'{base}/team/9999/add-mate', data='1', headers=json_header).status == 404
    assert request.post(f'{base}/team/{team}/add-mate', data='"dave"', headers=json_header).status == 400
    assert request.post(f'{base}/team/{team}/add-mate', data='not json', headers=json_header).status == 400
    assert pick_phase.state()['pick_details']['currently_picking'] == team


def test_non_captain_cannot_rename_other_team(pick_phase):
    bobs_team = pick_phase.team_of('Bob')
    carol = pick_phase.pages['Carol']

    refused = carol.request.post(f'/event/team/{bobs_team}/name', data='"Carol rules"',
                                 headers={'Content-Type': 'application/json'})

    assert refused.json() == 'no.'
    assert pick_phase.state_of_team(bobs_team)['name'] is None


def test_rename_unknown_team_is_404(pick_phase):
    response = pick_phase.pages['Bob'].request.post('/event/team/9999/name', data='"x"',
                                                    headers={'Content-Type': 'application/json'})

    assert response.status == 404


@pytest.mark.parametrize('name', ['"' + 'A' * 51 + '"', '"   "'], ids=['too-long', 'blank'])
def test_invalid_team_name_is_refused(pick_phase, name):
    bobs_team = pick_phase.team_of('Bob')

    refused = pick_phase.pages['Bob'].request.post(f'/event/team/{bobs_team}/name', data=name,
                                                   headers={'Content-Type': 'application/json'})

    assert refused.json() == 'no.'
    assert pick_phase.state_of_team(bobs_team)['name'] is None


def test_team_name_is_stripped(pick_phase):
    bobs_team = pick_phase.team_of('Bob')

    pick_phase.pages['Bob'].request.post(f'/event/team/{bobs_team}/name', data='"  Rocket Squad  "',
                                         headers={'Content-Type': 'application/json'})

    assert pick_phase.state_of_team(bobs_team)['name'] == 'Rocket Squad'


def test_non_captain_non_creator_cannot_skip(pick_phase, new_user_page):
    dave = new_user_page(pick_phase.users['Dave'])
    team = pick_phase.state()['pick_details']['currently_picking']

    refused = dave.request.post(f'/event/{pick_phase.event_id}/team/{team}/skip')

    assert refused.json() == 'no.'
    assert pick_phase.state()['pick_details']['currently_picking'] == team


def test_admin_ends_someone_elses_pick_phase(pick_phase, admin, new_user_page):
    admin_page = new_user_page(admin)

    admin_page.goto(f'/event/{pick_phase.event_id}/stop-pick-phase')

    assert pick_phase.state()['state'] is None
