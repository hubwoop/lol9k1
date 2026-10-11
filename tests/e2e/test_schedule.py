"""The party schedule and creating tournaments (events)."""
from playwright.sync_api import Page, expect

from conftest import DATETIME_FORMAT, expect_flash, login


def test_schedule_without_party_dates(page: Page, alice):
    login(page, alice)

    page.get_by_role('link', name='Schedule').click()

    expect(page.get_by_text('The administrators have yet to set a date for this LAN.')).to_be_visible()


def test_schedule_shows_calendar_with_party_and_events(page: Page, seed, party, alice, bob, base_url):
    game_id = seed.game('Rocket League', added_by=alice)
    event_id = seed.event(game_id, creator=bob, start=party.at(0, 10), end=party.at(0, 12))
    login(page, alice)

    page.get_by_role('link', name='Schedule').click()

    expect(page.get_by_role('heading', name='Schedule')).to_be_visible()
    calendar = page.locator('#calendar')
    expect(calendar.get_by_text('Best LAN Ever').first).to_be_visible()
    event = calendar.get_by_text('Rocket League Tournament')
    expect(event).to_be_visible()

    # clicking an event in the calendar opens its page
    # (the calendar ignores clicks where the mouse button is released instantly, like a script would)
    event.click(delay=100)
    expect(page).to_have_url(f'{base_url}/event/{event_id}')
    expect(page.get_by_role('heading', name=f'Rocket League - Tourney by Bob (Event #{event_id})')).to_be_visible()


def test_event_creation_form_requires_games(page: Page, party, alice):
    login(page, alice)

    page.goto('/schedule/')

    expect(page.locator('#calendar')).to_be_visible()
    expect(page.get_by_role('heading', name='Event Creation')).to_have_count(0)


def test_create_event_from_schedule(page: Page, seed, party, alice):
    seed.game('Rocket League', added_by=alice)
    game_id = seed.game('Worms', added_by=alice)
    login(page, alice)
    page.goto('/schedule/')

    page.get_by_label('Game').select_option(label='Worms')
    page.get_by_label('Start').fill(party.at(0, 14).strftime(DATETIME_FORMAT))
    page.get_by_label('End').fill(party.at(0, 16).strftime(DATETIME_FORMAT))
    page.get_by_label('Mode').select_option(label='Double Elimination')
    page.get_by_role('button', name='Create!').click()

    expect_flash(page, 'Tournament erstellt!')
    expect(page.get_by_role('heading', name='Worms - Tourney by Alice (Event #1)')).to_be_visible()
    rows = seed.query('select game, start_datetime, end_datetime, created_by, mode from events')
    assert [tuple(r) for r in rows] == [(game_id, party.at(0, 14).strftime(DATETIME_FORMAT),
                                         party.at(0, 16).strftime(DATETIME_FORMAT), alice.id, '2')]

    # the new event shows up in the schedule
    page.goto('/schedule/')
    expect(page.locator('#calendar').get_by_text('Worms Tournament')).to_be_visible()


def test_create_tournament_from_game_page_preselects_game(page: Page, seed, party, alice):
    seed.game('Rocket League', added_by=alice)
    seed.game('Worms', added_by=alice)
    login(page, alice)

    page.get_by_role('link', name='Worms').click()
    page.get_by_role('link', name='Create a tournament!').click()

    expect(page.get_by_role('heading', name='Event Creation')).to_be_visible()
    expect(page.get_by_label('Game').locator('option:checked')).to_have_text('Worms')


def test_event_must_end_after_it_starts(page: Page, seed, party, alice):
    seed.game('Worms', added_by=alice)
    login(page, alice)
    page.goto('/schedule/')

    page.get_by_label('Start').fill(party.at(0, 16).strftime(DATETIME_FORMAT))
    page.get_by_label('End').fill(party.at(0, 14).strftime(DATETIME_FORMAT))
    page.get_by_role('button', name='Create!').click()

    expect_flash(page, 'Event not in party boundaries')
    expect(page.get_by_role('heading', name='Event Creation')).to_be_visible()
    assert seed.query('select * from events') == []


def test_event_outside_of_party_is_rejected(page: Page, seed, party, alice):
    game_id = seed.game('Worms', added_by=alice)
    login(page, alice)
    page.goto('/schedule/')

    # the browser's min/max validation prevents this in the form, so post directly
    response = page.request.post('/event/create', form={
        'game': str(game_id),
        'start': party.at(-2, 10).strftime(DATETIME_FORMAT),
        'end': party.at(-2, 12).strftime(DATETIME_FORMAT),
        'mode': '1',
    })

    assert response.ok
    assert 'Event not in party boundaries' in response.text()
    assert seed.query('select * from events') == []
