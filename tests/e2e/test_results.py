"""Recording match results and the leaderboard built from them."""
import sqlite3

import pytest
from playwright.sync_api import Page, expect

from conftest import expect_flash, login
from test_event_permissions import make_captains
from test_pick_phase import pick_phase, other  # noqa: F401


def results_of(seed, event_id: int) -> dict:
    rows = seed.query('select team, placement from event_results where event = ?', [event_id])
    return {row['team']: row['placement'] for row in rows}


def team_ids(seed, event_id: int) -> dict:
    rows = seed.query('select u.name, tp.team from tournament_participants tp join users u on tp.user = u.id '
                      'where tp.tournament = ? and tp.is_team_captain = 1', [event_id])
    return {row['name']: row['team'] for row in rows}


def test_last_pick_wins_and_tops_the_leaderboard(pick_phase):
    page = pick_phase.creator_page
    first = pick_phase.picking_captain()
    second = other(first)
    users = pick_phase.users
    base = f'/event/{pick_phase.event_id}'
    for captain, player in ((first, 'Dave'), (second, 'Erin'), (first, 'Alice')):
        response = pick_phase.pages[captain].request.post(
            f'{base}/team/{pick_phase.team_of(captain)}/add-mate', data=users[player].id)
        assert response.json() == 'yaaaay!'
    page.goto(f'{base}/stop-pick-phase')

    page.get_by_label(f'Team #{pick_phase.team_of(first)}').select_option('1')
    page.get_by_label(f'Team #{pick_phase.team_of(second)}').select_option('2')
    page.get_by_role('button', name='Save results').click()

    expect_flash(page, 'Results saved.')
    expect(page.locator('dl dt').filter(has_text='🥇 1st')).to_contain_text(f'Team #{pick_phase.team_of(first)}')
    expect(page.locator('dl dt').filter(has_text='🥈 2nd')).to_contain_text(f'Team #{pick_phase.team_of(second)}')

    page.get_by_role('link', name='Leaderboard', exact=True).click()
    rows = page.locator('table.leaderboard tbody tr')
    expect(rows).to_have_count(5)
    winners = sorted([first, 'Dave', 'Alice'])
    for row, name in zip(range(3), winners):
        expect(rows.nth(row).locator('td').nth(0)).to_have_text('1')
        expect(rows.nth(row).locator('td').nth(1)).to_have_text(name)
        expect(rows.nth(row).locator('td').nth(2)).to_have_text('1')
    expect(rows.nth(3).locator('td').nth(0)).to_have_text('4')
    expect(rows.filter(has_text='Alice').locator('.badgeIcon[title^="Picked last but won"]')).to_have_count(1)
    achievements = page.locator('dl.achievements')
    expect(achievements).to_contain_text('🐢 Picked last but won')
    expect(achievements).to_contain_text('🗳️ Most games voted for')


def test_night_owls_and_undefeated_players_get_badges(page: Page, seed, party, alice, bob):
    game_id = seed.game('Counter-Strike', added_by=alice)
    events = [seed.event(game_id, creator=alice, start=party.at(1, 2), end=party.at(1, 4)),
              seed.event(game_id, creator=alice, start=party.at(0, 14), end=party.at(0, 15))]
    for event_id in events:
        make_captains(seed, event_id, alice, bob)
    with sqlite3.connect(seed.path) as db:
        for event_id in events:
            for name, team in team_ids(seed, event_id).items():
                db.execute('insert into event_results (event, team, placement) values (?, ?, ?)',
                           [event_id, team, 1 if name == 'Alice' else 2])

    login(page, bob)
    page.goto('/leaderboard/')

    rows = page.locator('table.leaderboard tbody tr')
    expect(rows.nth(0)).to_contain_text('Alice')
    expect(rows.nth(0).locator('td').nth(2)).to_have_text('2')
    expect(rows.nth(0).locator('td').nth(3)).to_have_text('2')
    achievements = page.locator('dl.achievements')
    expect(achievements.locator('dt')).to_have_text(
        ['🗳️ Most games voted for', '🦉 Night owl', '🛡️ Undefeated in Counter-Strike'])
    expect(achievements.locator('dd').nth(1)).to_contain_text('Alice, Bob')
    expect(achievements.locator('dd').nth(2)).to_contain_text('Alice')
    expect(achievements.locator('dd').nth(2)).not_to_contain_text('Bob')


def test_leaderboard_without_results(page: Page, alice):
    login(page, alice)
    page.goto('/leaderboard/')
    expect(page.get_by_text('No results recorded yet.')).to_be_visible()


@pytest.fixture
def event_with_teams(seed, party, alice, bob) -> int:
    carol = seed.user('Carol')
    game_id = seed.game('Worms', added_by=alice)
    event_id = seed.event(game_id, creator=alice, start=party.at(0, 10), end=party.at(0, 12))
    make_captains(seed, event_id, bob, carol)
    return event_id


def test_non_owner_cannot_record_results(page: Page, seed, bob, event_with_teams):
    login(page, bob)
    team = team_ids(seed, event_with_teams)['Bob']

    page.request.post(f'/event/{event_with_teams}/results', form={f'placement-{team}': '1'})

    assert results_of(seed, event_with_teams) == {}


@pytest.mark.parametrize('placement', ['0', '3', 'first'])
def test_invalid_placements_are_refused(page: Page, seed, alice, event_with_teams, placement):
    login(page, alice)
    team = team_ids(seed, event_with_teams)['Bob']

    response = page.request.post(f'/event/{event_with_teams}/results', form={f'placement-{team}': placement})

    assert response.ok
    assert results_of(seed, event_with_teams) == {}


def test_results_of_other_events_teams_are_ignored(page: Page, seed, party, alice, event_with_teams):
    other_event = seed.event(seed.game('Quake', added_by=alice), creator=alice,
                             start=party.at(0, 13), end=party.at(0, 14))
    make_captains(seed, other_event, alice)
    foreign_team = team_ids(seed, other_event)['Alice']
    login(page, alice)

    page.request.post(f'/event/{event_with_teams}/results', form={f'placement-{foreign_team}': '1'})

    assert results_of(seed, event_with_teams) == {}
    assert results_of(seed, other_event) == {}


def test_changing_captains_clears_results(page: Page, seed, alice, event_with_teams):
    teams = team_ids(seed, event_with_teams)
    login(page, alice)
    page.request.post(f'/event/{event_with_teams}/results',
                      form={f'placement-{teams["Bob"]}': '2', f'placement-{teams["Carol"]}': '1'})
    assert results_of(seed, event_with_teams) == {teams['Bob']: 2, teams['Carol']: 1}

    page.goto(f'/event/{event_with_teams}')
    page.get_by_label('Alice').check()
    page.get_by_role('button', name='Set captains').click()

    expect(page.locator('dl dd')).to_have_count(3)
    assert results_of(seed, event_with_teams) == {}
