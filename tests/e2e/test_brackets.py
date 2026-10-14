"""Built-in single elimination brackets: drawing them, entering results and who may do that."""
import sqlite3

import pytest
from playwright.sync_api import Page, expect

from conftest import expect_flash, login
from test_event_permissions import make_captains

JSON = {'Content-Type': 'application/json'}


@pytest.fixture
def worms(seed, alice):
    return seed.game('Worms', added_by=alice)


@pytest.fixture
def alices_event(seed, party, alice, worms) -> int:
    return seed.event(worms, creator=alice, start=party.at(0, 10), end=party.at(0, 12))


@pytest.fixture
def captains(seed, alices_event, bob):
    """Bob, Carol, Dave and Erin captain the teams of Alice's event."""
    users = [bob] + [seed.user(name) for name in ('Carol', 'Dave', 'Erin')]
    make_captains(seed, alices_event, *users)
    return {user.name: user for user in users}


def draw_bracket(page: Page, event_id: int) -> None:
    page.goto(f'/event/{event_id}')
    page.get_by_role('button', name='Draw bracket').click()
    expect_flash(page, 'Bracket drawn.')


def bracket(page: Page, event_id: int) -> dict:
    response = page.request.get(f'/event/{event_id}/bracket')
    assert response.ok
    return response.json()


def match_of(data: dict, team_name: str, round_name: str) -> dict:
    return next(m for m in data['matches'] if m['round'] == round_name
                and team_name in (m['team1'] and m['team1']['name'], m['team2'] and m['team2']['name']))


def post_score(page: Page, event_id: int, match_id: int, score1, score2):
    return page.request.post(f'/event/{event_id}/match/{match_id}/score',
                             data={'score1': score1, 'score2': score2}, headers=JSON)


def match_row(page: Page, match_id: int):
    return page.locator(f'#bracket-matches tr[data-match-id="{match_id}"]')


def final_row(page: Page):
    return page.locator('#bracket-matches tbody tr').filter(has=page.get_by_role('cell', name='Final', exact=True))


def enter_score(page: Page, match: dict, score1: int, score2: int) -> None:
    row = match_row(page, match['id'])
    row.get_by_label(f'Score of {match["team1"]["name"]}').fill(str(score1))
    row.get_by_label(f'Score of {match["team2"]["name"]}').fill(str(score2))
    row.get_by_role('button', name='Save').click()


def test_creator_draws_bracket(page: Page, alice, alices_event, captains):
    login(page, alice)

    draw_bracket(page, alices_event)

    # jquery.bracket renders two semifinals and the final, no third place match
    expect(page.locator('#bracket-container .round')).to_have_count(2)
    expect(page.locator('#bracket-container .team')).to_have_count(6)
    for name in captains:
        expect(page.locator('#bracket-container .label', has_text=f'Team {name}')).to_have_count(1)
    expect(page.locator('#bracket-matches tbody tr')).to_have_count(3)
    expect(final_row(page)).to_contain_text('TBD')
    data = bracket(page, alices_event)
    assert sorted(name for pairing in data['teams'] for name in pairing) == \
        ['Team Bob', 'Team Carol', 'Team Dave', 'Team Erin']
    assert data['champion'] is None


def test_captain_enters_result_and_bracket_updates_for_everyone(page: Page, alice, alices_event, captains,
                                                                  new_user_page):
    login(page, alice)
    draw_bracket(page, alices_event)
    bobs_match = match_of(bracket(page, alices_event), 'Team Bob', 'Semifinals')
    bob_page = new_user_page(captains['Bob'])
    bob_page.goto(f'/event/{alices_event}')

    bobs_side = 1 if bobs_match['team1']['name'] == 'Team Bob' else 2
    enter_score(bob_page, bobs_match, *((3, 1) if bobs_side == 1 else (1, 3)))

    final = final_row(bob_page)
    expect(final).to_contain_text('Team Bob')
    # Alice's page picks up the result without reloading
    expect(final_row(page)).to_contain_text('Team Bob')
    expect(page.locator('#bracket-container .label', has_text='Team Bob')).to_have_count(2)
    saved = next(m for m in bracket(page, alices_event)['matches'] if m['id'] == bobs_match['id'])
    assert saved['winner'] == saved[f'team{bobs_side}']['id']


def test_captain_cannot_enter_result_of_other_match(page: Page, alice, alices_event, captains, new_user_page):
    login(page, alice)
    draw_bracket(page, alices_event)
    data = bracket(page, alices_event)
    other_match = next(m for m in data['matches']
                       if m['round'] == 'Semifinals' and 'Team Bob' not in (m['team1']['name'], m['team2']['name']))
    bob_page = new_user_page(captains['Bob'])
    bob_page.goto(f'/event/{alices_event}')

    expect(match_row(bob_page, other_match['id'])).to_be_visible()
    expect(match_row(bob_page, other_match['id']).locator('input')).to_have_count(0)
    response = post_score(bob_page, alices_event, other_match['id'], 2, 0)

    assert response.status == 403
    assert bracket(page, alices_event)['matches'] == data['matches']


def test_spectator_sees_bracket_but_cannot_manage_it(page: Page, seed, alice, alices_event, captains,
                                                     new_user_page):
    login(page, alice)
    draw_bracket(page, alices_event)
    mallory = new_user_page(seed.user('Mallory'))

    mallory.goto(f'/event/{alices_event}')

    expect(mallory.locator('#bracket-container .team')).to_have_count(6)
    expect(mallory.locator('#bracket-matches input')).to_have_count(0)
    expect(mallory.get_by_role('button', name='Delete bracket')).to_have_count(0)
    response = mallory.request.post(f'/event/{alices_event}/bracket', form={'action': 'delete'})
    assert 'no.' in response.text()
    assert seed.query('select count(*) from matches')[0][0] == 3


def test_tournament_is_played_to_the_end(page: Page, alice, alices_event, captains):
    login(page, alice)
    draw_bracket(page, alices_event)
    semifinals = [m for m in bracket(page, alices_event)['matches'] if m['round'] == 'Semifinals']

    for semifinal in semifinals:
        enter_score(page, semifinal, 2, 0)
        expect(match_row(page, semifinal['id'])).to_contain_text('Clear')
    final = match_of(bracket(page, alices_event), semifinals[0]['team1']['name'], 'Final')
    enter_score(page, final, 1, 5)

    champion = semifinals[1]['team1']['name']
    expect(page.locator('#bracket-champion')).to_have_text(f'🏆 {champion} won the tournament!')
    # results before the final can only change once the final is cleared
    expect(match_row(page, semifinals[0]['id']).locator('input')).to_have_count(0)
    refused = post_score(page, alices_event, semifinals[0]['id'], 0, 2)
    assert refused.status == 409
    assert 'Clear that one first' in refused.json()['error']

    match_row(page, final['id']).get_by_role('button', name='Clear').click()
    expect(page.locator('#bracket-champion')).to_be_hidden()
    enter_score(page, semifinals[0], 0, 2)
    expect(final_row(page)).to_contain_text(
        semifinals[0]['team2']['name'])


def test_three_teams_get_a_bye(page: Page, seed, alice, bob, alices_event):
    make_captains(seed, alices_event, bob, seed.user('Carol'), seed.user('Dave'))
    login(page, alice)

    draw_bracket(page, alices_event)

    data = bracket(page, alices_event)
    # the bye isn't a match anybody plays, its team is already in the final
    assert [m['round'] for m in data['matches']] == ['Semifinals', 'Final']
    final = data['matches'][1]
    assert (final['team1'] is None) != (final['team2'] is None)
    assert final['editable'] is False
    expect(page.locator('#bracket-container .label', has_text='BYE')).to_have_count(1)
    assert post_score(page, alices_event, final['id'], 1, 0).status == 409


@pytest.mark.parametrize('body, status', [
    ({'score1': 2, 'score2': 2}, 409),
    ({'score1': -1, 'score2': 2}, 409),
    ({'score1': 2, 'score2': None}, 400),
    ({'score1': '2', 'score2': 1}, 400),
    ({'score1': True, 'score2': 1}, 400),
    ({'score1': 2}, 400),
    ([2, 1], 400),
])
def test_invalid_scores_are_refused(page: Page, seed, alice, alices_event, captains, body, status):
    login(page, alice)
    draw_bracket(page, alices_event)
    match = bracket(page, alices_event)['matches'][0]

    response = page.request.post(f'/event/{alices_event}/match/{match["id"]}/score', data=body, headers=JSON)

    assert response.status == status
    assert seed.query('select count(*) from matches where score1 is not null')[0][0] == 0


def test_tie_shows_error_in_page(page: Page, alice, alices_event, captains):
    login(page, alice)
    draw_bracket(page, alices_event)
    match = bracket(page, alices_event)['matches'][0]

    enter_score(page, match, 1, 1)

    expect(page.locator('#bracket-error')).to_have_text('A match needs a winner, the scores must not be equal.')


def test_unknown_match_or_event_is_404(page: Page, seed, alice, bob, party, worms, alices_event, captains):
    other_event = seed.event(worms, creator=alice, start=party.at(0, 14), end=party.at(0, 16))
    login(page, alice)
    draw_bracket(page, alices_event)
    match = bracket(page, alices_event)['matches'][0]

    assert post_score(page, other_event, match['id'], 1, 0).status == 404
    assert post_score(page, alices_event, 9999, 1, 0).status == 404
    assert page.request.get('/event/9999/bracket').status == 404
    assert bracket(page, other_event) == {'exists': False, 'may_manage': True}


def test_changing_captains_deletes_bracket(page: Page, seed, alice, alices_event, captains):
    login(page, alice)
    draw_bracket(page, alices_event)
    expect(page.get_by_text('Changing team captains deletes the bracket.')).to_be_visible()

    page.locator(f'#possible-captain-{captains["Erin"].id}').uncheck()
    page.get_by_role('button', name='Set captains').click()

    expect(page.get_by_role('button', name='Draw bracket')).to_be_visible()
    assert seed.query('select count(*) from matches')[0][0] == 0


def test_creator_deletes_and_redraws_bracket(page: Page, seed, alice, alices_event, captains):
    login(page, alice)
    draw_bracket(page, alices_event)
    page.on('dialog', lambda dialog: dialog.accept())

    page.get_by_role('button', name='Delete bracket').click()
    expect_flash(page, 'Bracket deleted.')
    assert seed.query('select count(*) from matches')[0][0] == 0

    draw_bracket(page, alices_event)
    page.get_by_role('button', name='Redraw bracket').click()
    expect_flash(page, 'Bracket drawn.')
    assert seed.query('select count(*) from matches')[0][0] == 3


def test_deleting_event_deletes_its_bracket(page: Page, seed, alice, alices_event, captains):
    login(page, alice)
    draw_bracket(page, alices_event)

    page.goto(f'/event/delete/{alices_event}')

    expect_flash(page, f'Deleted event {alices_event}.')
    assert seed.query('select count(*) from matches')[0][0] == 0


def test_bracket_needs_single_elimination_event(page: Page, seed, alice, party, worms, captains):
    double = seed.event(worms, creator=alice, start=party.at(0, 14), end=party.at(0, 16), mode=2)
    make_captains(seed, double, captains['Bob'], captains['Carol'])
    login(page, alice)

    page.goto(f'/event/{double}')
    expect(page.get_by_text('Built-in brackets only support single elimination so far.')).to_be_visible()
    page.request.post(f'/event/{double}/bracket', form={'action': 'create'})

    assert seed.query('select count(*) from matches')[0][0] == 0


def test_team_names_are_rendered_as_text(page: Page, seed, alice, alices_event, captains):
    with sqlite3.connect(seed.path) as db:
        db.execute("update teams set name = '<img src=x onerror=window.pwned=1>' where captain = ?",
                   [captains['Bob'].id])
    login(page, alice)

    draw_bracket(page, alices_event)

    expect(page.locator('#bracket-container .label', has_text='<img src=x')).to_have_count(1)
    expect(page.locator('#bracket-matches td', has_text='<img src=x')).to_have_count(1)
    assert page.evaluate('window.pwned') is None
