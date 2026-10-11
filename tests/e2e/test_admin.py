"""The administration page: configuring the party dates."""
from playwright.sync_api import Page, expect

from conftest import expect_flash, login


def test_regular_user_cannot_access_administration(page: Page, alice):
    login(page, alice)

    response = page.goto('/admin/admin')

    assert response.status == 403


def test_admin_sets_party_dates(page: Page, seed, admin):
    login(page, admin)
    page.get_by_role('link', name='Administration').click()
    expect(page.get_by_text('Nothing configured :(')).to_be_visible()

    page.get_by_label('Start Date').fill('2030-07-12T16:00')
    page.get_by_label('End Date').fill('2030-07-14T12:00')
    page.locator('input[type=submit]').click()

    expect_flash(page, 'Settings updated.')
    table = page.get_by_role('table')
    expect(table.get_by_role('row').filter(has_text='date_start')).to_contain_text('2030-07-12T16:00')
    expect(table.get_by_role('row').filter(has_text='date_end')).to_contain_text('2030-07-14T12:00')
    # the form shows the stored values
    expect(page.get_by_label('Start Date')).to_have_value('2030-07-12T16:00')
    expect(page.get_by_label('End Date')).to_have_value('2030-07-14T12:00')
    config = {row['key']: row['value'] for row in seed.query('select * from config')}
    assert config == {'date_start': '2030-07-12T16:00', 'date_end': '2030-07-14T12:00'}


def test_admin_cannot_set_end_before_start(page: Page, seed, admin):
    login(page, admin)
    page.goto('/admin/admin')

    page.get_by_label('Start Date').fill('2030-07-14T12:00')
    page.get_by_label('End Date').fill('2030-07-12T16:00')
    page.locator('input[type=submit]').click()

    expect(page.get_by_role('alert')).to_contain_text('Choose a valid time span.')
    expect(page.get_by_role('alert').filter(has_text='Settings updated.')).to_have_count(0)
    assert seed.query('select * from config') == []
