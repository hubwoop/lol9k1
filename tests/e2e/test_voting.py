"""Voting on games and sorting / filtering the game list."""
from playwright.sync_api import Page, expect

from conftest import expect_flash, login


def game_row(page: Page, name: str):
    return page.locator('.gameTableRow').filter(has=page.get_by_role('link', name=name, exact=True))


def score_of(page: Page, name: str):
    return game_row(page, name).locator('.scoreRow')


def test_upvote_downvote_and_change_vote(page: Page, seed, alice, bob):
    seed.game('Starcraft', added_by=alice)
    login(page, bob)
    row = game_row(page, 'Starcraft')
    expect(score_of(page, 'Starcraft')).to_have_text('Points: 1')

    row.get_by_role('button', name='👍').click()
    expect_flash(page, 'Thanks for voting :)')
    expect(score_of(page, 'Starcraft')).to_have_text('Points: 2')
    expect(row.get_by_role('button', name='👍')).to_be_disabled()
    expect(row.get_by_role('button', name='👎')).to_be_enabled()

    row.get_by_role('button', name='👎').click()
    expect_flash(page, 'Your vote has been changed :)!')
    expect(score_of(page, 'Starcraft')).to_have_text('Points: 0')
    expect(row.get_by_role('button', name='👎')).to_be_disabled()
    expect(row.get_by_role('button', name='👍')).to_be_enabled()


def test_voting_twice_the_same_way_is_rejected(page: Page, seed, alice, bob):
    game_id = seed.game('Starcraft', added_by=alice, votes={bob: -1})
    login(page, bob)

    response = page.request.post(f'/api/vote/{game_id}/-1')

    assert 'You already voted for that!' in response.text()
    assert seed.query('select sum(vote) as score from votes where game = ?', [game_id])[0]['score'] == 0


def test_invalid_vote_is_refused(page: Page, seed, alice):
    game_id = seed.game('Starcraft', added_by=alice)
    login(page, alice)

    response = page.request.post(f'/api/vote/{game_id}/5')

    assert 'no.' in response.text()
    assert seed.query('select sum(vote) as score from votes where game = ?', [game_id])[0]['score'] == 1


def test_votes_from_other_users_are_visible(page: Page, new_user_page, seed, alice, bob):
    seed.game('Diablo II', added_by=alice)
    bobs_page = new_user_page(bob)
    game_row(bobs_page, 'Diablo II').get_by_role('button', name='👍').click()
    expect_flash(bobs_page, 'Thanks for voting')

    login(page, alice)

    expect(score_of(page, 'Diablo II')).to_have_text('Points: 2')


def test_order_games_by_score(page: Page, seed, admin, alice, bob):
    seed.game('A Low Rated Game', added_by=alice, votes={bob: -1, admin: -1})
    seed.game('B Top Rated Game', added_by=alice, votes={bob: 1, admin: 1})
    seed.game('C Average Game', added_by=alice)
    login(page, bob)
    names = page.locator('.gameTableRow a.gameLink')

    expect(names).to_have_text(['A Low Rated Game', 'B Top Rated Game', 'C Average Game'])

    page.get_by_role('link', name='Points ↓').click()
    expect(names).to_have_text(['B Top Rated Game', 'C Average Game', 'A Low Rated Game'])

    page.get_by_role('link', name='Points ❌').click()
    expect(names).to_have_text(['A Low Rated Game', 'B Top Rated Game', 'C Average Game'])


def test_filter_games_without_own_vote(page: Page, seed, alice, bob):
    seed.game('Already Voted', added_by=alice, votes={bob: 1})
    seed.game('Not Voted Yet', added_by=alice)
    seed.game('Suggested By Bob', added_by=bob)
    login(page, bob)
    names = page.locator('.gameTableRow a.gameLink')

    page.get_by_role('link', name='Without vote').click()
    expect(names).to_have_text(['Not Voted Yet'])

    page.get_by_role('link', name='All').click()
    expect(names).to_have_count(3)
