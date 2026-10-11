"""The party schedule and creating tournaments (events)."""
import re

import pytest
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


def post_event(page: Page, game_id: int, start: str, end: str, mode: str = '1'):
    return page.request.post('/event/create', form={'game': str(game_id), 'start': start, 'end': end, 'mode': mode})


def test_create_event_without_party_dates_is_rejected(page: Page, seed, alice):
    game_id = seed.game('Worms', added_by=alice)
    login(page, alice)

    response = post_event(page, game_id, '2030-01-01T10:00', '2030-01-01T12:00')

    assert response.ok
    assert 'The administrators have yet to set a date for this LAN.' in response.text()
    assert seed.query('select * from events') == []


def test_event_with_same_start_and_end_is_rejected(page: Page, seed, party, alice):
    game_id = seed.game('Worms', added_by=alice)
    login(page, alice)

    at = party.at(0, 14).strftime(DATETIME_FORMAT)
    response = post_event(page, game_id, at, at)

    assert response.ok
    assert 'Event not in party boundaries' in response.text()
    assert seed.query('select * from events') == []


@pytest.mark.parametrize('suffix', ["'", ' of', '+02:00'])
def test_malformed_event_datetime_is_rejected(page: Page, seed, party, alice, suffix):
    game_id = seed.game('Worms', added_by=alice)
    login(page, alice)

    response = post_event(page, game_id, party.at(0, 10).strftime(DATETIME_FORMAT) + suffix,
                          party.at(0, 12).strftime(DATETIME_FORMAT))

    assert response.ok
    assert response.url.endswith('/schedule/')
    assert seed.query('select * from events') == []


def test_event_with_unknown_mode_is_rejected(page: Page, seed, party, alice):
    game_id = seed.game('Worms', added_by=alice)
    login(page, alice)

    response = post_event(page, game_id, party.at(0, 10).strftime(DATETIME_FORMAT),
                          party.at(0, 12).strftime(DATETIME_FORMAT), mode='99')

    assert response.ok
    assert 'Unknown tournament mode' in response.text()
    assert seed.query('select * from events') == []


def test_event_datetimes_are_stored_normalised(page: Page, seed, party, alice):
    game_id = seed.game('Worms', added_by=alice)
    login(page, alice)

    response = post_event(page, game_id, party.at(0, 10, 30).strftime('%Y-%m-%dT%H:%M:%S'),
                          party.at(0, 12).strftime('%Y-%m-%d %H:%M:%S.%f'))

    assert response.ok
    rows = seed.query('select start_datetime, end_datetime from events')
    assert [tuple(r) for r in rows] == [(party.at(0, 10, 30).strftime(DATETIME_FORMAT),
                                         party.at(0, 12).strftime(DATETIME_FORMAT))]


def test_schedule_tolerates_events_with_unknown_mode(page: Page, seed, party, alice):
    game_id = seed.game('Worms', added_by=alice)
    seed.event(game_id, creator=alice, start=party.at(0, 10), end=party.at(0, 12), mode=99)
    login(page, alice)

    page.goto('/schedule/')

    expect(page.locator('#calendar').get_by_text('Worms Tournament')).to_be_visible()


def test_schedule_escapes_event_data(page: Page, seed, party, alice):
    evil_name = "Evil'</script><script>window.__xss=1</script>"
    evil_game = seed.game(evil_name, added_by=alice)
    seed.event(evil_game, creator=alice, start=party.at(0, 10), end=party.at(0, 12))
    quoted_game = seed.game('Quake', added_by=alice)
    with seed._connect() as db:
        db.execute('insert into events (game, start_datetime, end_datetime, created_by, mode) values (?, ?, ?, ?, ?)',
                   [quoted_game, party.at(0, 14).strftime(DATETIME_FORMAT) + "'",
                    party.at(0, 16).strftime(DATETIME_FORMAT), alice.id, '1'])
    login(page, alice)

    page.goto('/schedule/')

    calendar = page.locator('#calendar')
    expect(calendar.get_by_text('Best LAN Ever').first).to_be_visible()
    # the calendar strips tags from titles, but the script must not be broken out of
    expect(calendar.get_by_text(re.compile(r"^Evil'.* Tournament$"))).to_be_visible()
    expect(calendar.get_by_text('Quake Tournament')).to_be_visible()
    assert page.evaluate('window.__xss') is None
