"""Suggesting games, the game list and game detail pages."""
from playwright.sync_api import Page, expect

from conftest import expect_flash, login


def game_row(page: Page, name: str):
    return page.locator('.gameTableRow').filter(has=page.get_by_role('link', name=name, exact=True))


def test_empty_game_list(page: Page, alice):
    login(page, alice)

    expect(page.get_by_text('No games added yet.')).to_be_visible()


def test_add_game_with_all_details(page: Page, seed, alice):
    login(page, alice)
    page.get_by_role('link', name='Add Game').click()

    page.locator('#gameTitle').fill('Unreal Tournament 2004')
    page.locator('#max_players').fill('16')
    page.locator('#description').fill('Fast paced arena shooter.')
    # the checkboxes themselves are hidden, users toggle them by clicking the icon labels
    for bonus in ('DRM-Free! No copyright protection.', 'A game that everybody has anyways.',
                  'Runs on weak machines.'):
        page.locator('.plusPointForm label').filter(has_text=bonus).click()
        expect(page.get_by_label(bonus)).to_be_checked()
    page.get_by_role('button', name='Add!').click()

    expect_flash(page, 'You added game (Unreal Tournament 2004).')
    row = game_row(page, 'Unreal Tournament 2004')
    expect(row).to_contain_text('Addded by: Alice')
    expect(row).to_contain_text('16')
    expect(row).to_contain_text('Fast paced arena shooter.')
    for title in ('DRM-Free! No copyright protection.', 'A game that everybody has anyways.',
                  'Runs on weak machines.'):
        expect(row.locator(f'img.bonusIcon[title="{title}"]')).to_be_visible()
    # the person suggesting a game automatically upvotes it
    expect(row.locator('.scoreRow')).to_contain_text('1')
    expect(row.get_by_role('button', name='👍')).to_be_disabled()
    rows = seed.query('select slug, max_players, no_drm, available, low_spec, added_by from games')
    assert [tuple(r) for r in rows] == [('unreal-tournament-2004', 16, 1, 1, 1, alice.id)]


def test_add_game_with_title_only(page: Page, alice):
    login(page, alice)

    page.locator('#gameTitle').fill('Worms Armageddon')
    page.get_by_role('button', name='Add!').click()

    expect_flash(page, 'You added game (Worms Armageddon).')
    row = game_row(page, 'Worms Armageddon')
    expect(row).to_be_visible()
    expect(row.locator('img.bonusIcon')).to_have_count(0)


def test_adding_a_game_twice_is_rejected(page: Page, seed, alice, bob):
    seed.game('Age of Empires II', added_by=bob)
    login(page, alice)

    # the duplicate check is based on the slug, so different spelling is caught too
    page.locator('#gameTitle').fill('age of empires ii')
    page.get_by_role('button', name='Add!').click()

    expect_flash(page, 'Game age of empires ii has already been added!')
    assert len(seed.query('select * from games')) == 1


def test_game_detail_page(page: Page, seed, alice):
    seed.game('Trackmania Nations Forever', added_by=alice, description='Racing for everyone.')
    login(page, alice)

    page.get_by_role('link', name='Trackmania Nations Forever').click()

    expect(page).to_have_title('LOL 9001 - Trackmania Nations Forever')
    expect(page.get_by_role('heading', name='Trackmania Nations Forever')).to_be_visible()
    expect(page.get_by_text('Description: Racing for everyone.')).to_be_visible()
    expect(page.get_by_text('No Tournament scheduled for Trackmania Nations Forever')).to_be_visible()
    expect(page.get_by_role('link', name='Create a tournament!')).to_be_visible()


def test_admin_removes_game(page: Page, seed, admin, alice):
    seed.game('Counter-Strike 1.6', added_by=alice, votes={admin: 1})
    seed.game('Quake III Arena', added_by=alice)
    login(page, admin)

    game_row(page, 'Counter-Strike 1.6').get_by_role('link', name='Remove').click()

    expect_flash(page, 'Game Counter-Strike 1.6 deleted.')
    expect(game_row(page, 'Counter-Strike 1.6')).to_have_count(0)
    expect(game_row(page, 'Quake III Arena')).to_be_visible()
    assert [r['name'] for r in seed.query('select name from games')] == ['Quake III Arena']


def test_regular_user_cannot_see_remove_link(page: Page, seed, alice):
    seed.game('Counter-Strike 1.6', added_by=alice)
    login(page, alice)

    expect(game_row(page, 'Counter-Strike 1.6')).to_be_visible()
    expect(page.get_by_role('link', name='Remove')).to_have_count(0)
