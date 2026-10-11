"""Managing a tournament: details, team captains, permissions and deletion."""
import pytest
from playwright.sync_api import Page, expect

from conftest import expect_flash, login


@pytest.fixture
def worms(seed, alice):
    return seed.game('Worms', added_by=alice)


@pytest.fixture
def alices_event(seed, party, alice, worms) -> int:
    return seed.event(worms, creator=alice, start=party.at(0, 10), end=party.at(0, 12))


def test_event_page_shows_details(page: Page, alice, alices_event):
    login(page, alice)

    page.goto(f'/event/{alices_event}')

    expect(page.get_by_role('heading', name=f'Worms - Tourney by Alice (Event #{alices_event})')).to_be_visible()
    expect(page.get_by_text('No description yet.')).to_be_visible()
    expect(page.get_by_text('None so far.')).to_be_visible()
    page.get_by_role('link', name='Worms', exact=True).click()
    expect(page.get_by_role('heading', name='Worms')).to_be_visible()


def test_event_page_loads_no_bracket_scripts_while_brackets_are_disabled(page: Page, alice, alices_event, base_url):
    requested = []
    page.on('request', lambda request: requested.append(request.url))
    login(page, alice)

    page.goto(f'/event/{alices_event}')

    expect(page.get_by_role('heading', name='Edit event details')).to_be_visible()
    assert not [url for url in requested if 'bracket' in url or not url.startswith(base_url)]


def test_game_page_lists_its_events(page: Page, alice, alices_event):
    login(page, alice)

    page.goto('/game/worms')
    page.get_by_role('link', name=f'Event #{alices_event}').click()

    expect(page.get_by_role('heading', name=f'Worms - Tourney by Alice (Event #{alices_event})')).to_be_visible()


def test_nonexistent_event(page: Page, alice):
    login(page, alice)

    page.goto('/event/999')

    expect_flash(page, 'The selected event does not exist (anymore).')


def test_creator_edits_description_and_bracket_url(page: Page, seed, alice, alices_event):
    login(page, alice)
    page.goto(f'/event/{alices_event}')

    page.get_by_label('Tournament bracket URL on external website').fill('https://challonge.com/lol9k1')
    page.get_by_label('Description').fill('## House rules\n\nNo **ninja ropes** allowed.')
    page.get_by_role('button', name='Submit').click()

    # description is rendered as markdown
    expect(page.get_by_role('heading', name='House rules')).to_be_visible()
    expect(page.locator('strong', has_text='ninja ropes')).to_be_visible()
    expect(page.get_by_role('link', name='Bracket', exact=True)).to_have_attribute('href', 'https://challonge.com/lol9k1')
    row = seed.query('select description, external_url from events where id = ?', [alices_event])[0]
    assert row['external_url'] == 'https://challonge.com/lol9k1'
    assert 'No **ninja ropes** allowed.' in row['description']


def test_creator_sets_team_captains(page: Page, seed, alice, bob, alices_event):
    carol = seed.user('Carol')
    login(page, alice)
    page.goto(f'/event/{alices_event}')

    page.get_by_label('Bob').check()
    page.get_by_label('Carol').check()
    page.get_by_role('button', name='Set captains').click()

    teams = page.locator('dl')
    expect(teams.locator('dd')).to_have_text(['Bob 👑', 'Carol 👑'])
    expect(teams.locator('dt')).to_have_count(2)
    expect(page.get_by_label('Bob')).to_be_checked()
    expect(page.get_by_label('Carol')).to_be_checked()
    expect(page.get_by_label('Alice')).not_to_be_checked()
    expect(page.get_by_role('button', name='Start picking teams')).to_be_visible()

    # replacing captains rebuilds the teams
    page.get_by_label('Bob').uncheck()
    page.get_by_role('button', name='Set captains').click()
    expect(page.locator('dl dd')).to_have_text(['Carol 👑'])
    captains = seed.query('select user from tournament_participants where is_team_captain = 1')
    assert [r['user'] for r in captains] == [carol.id]

    # unchecking everyone removes all teams
    page.get_by_label('Carol').uncheck()
    page.get_by_role('button', name='Set captains').click()
    expect(page.get_by_text('None so far.')).to_be_visible()
    expect(page.get_by_role('button', name='Start picking teams')).to_have_count(0)


def test_other_users_cannot_edit_event(page: Page, alice, bob, alices_event):
    login(page, bob)

    page.goto(f'/event/{alices_event}')

    expect(page.get_by_role('heading', name=f'Worms - Tourney by Alice (Event #{alices_event})')).to_be_visible()
    expect(page.get_by_role('heading', name='Edit event details')).to_have_count(0)
    expect(page.get_by_role('heading', name='Choose team captains')).to_have_count(0)
    expect(page.get_by_role('button', name='Delete event')).to_have_count(0)


def test_other_users_cannot_delete_event(page: Page, seed, bob, alices_event):
    login(page, bob)

    page.goto(f'/event/delete/{alices_event}')

    expect_flash(page, 'no.')
    assert len(seed.query('select * from events')) == 1


def test_admin_can_edit_other_users_event(page: Page, admin, alices_event):
    login(page, admin)

    page.goto(f'/event/{alices_event}')

    expect(page.get_by_text("You're editing an event created by Alice as administrator.")).to_be_visible()
    expect(page.get_by_role('heading', name='Edit event details')).to_be_visible()


def test_creator_deletes_event_after_confirmation(page: Page, seed, alice, alices_event):
    login(page, alice)
    page.goto(f'/event/{alices_event}')
    dialogs = []
    page.on('dialog', lambda dialog: (dialogs.append(dialog.message), dialog.accept()))

    # first click only warns
    page.get_by_role('button', name='Delete event').click()
    expect(page.get_by_role('heading', name='Danger Zone')).to_be_visible()
    assert len(dialogs) == 1 and 'Are you sure you want to delete' in dialogs[0]
    assert len(seed.query('select * from events')) == 1

    # second click deletes and returns to the game page
    page.get_by_role('button', name='Delete event').click()
    expect_flash(page, f'Deleted event {alices_event}.')
    expect(page.get_by_role('heading', name='Worms')).to_be_visible()
    expect(page.get_by_text('No Tournament scheduled for Worms')).to_be_visible()
    assert seed.query('select * from events') == []


def test_admin_removes_event_from_game_page(page: Page, seed, admin, alices_event):
    login(page, admin)
    page.goto('/game/worms')

    page.get_by_role('link', name='Remove').click()

    expect_flash(page, f'Deleted event {alices_event}.')
    assert seed.query('select * from events') == []


def test_deleting_game_removes_its_events(page: Page, seed, admin, alices_event):
    login(page, admin)

    page.get_by_role('link', name='Remove').click()

    expect_flash(page, 'Game Worms deleted.')
    assert seed.query('select * from events') == []
