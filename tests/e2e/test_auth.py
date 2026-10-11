"""Logging in and out, and protecting pages from anonymous visitors."""
from playwright.sync_api import Page, expect

from conftest import expect_flash, login


def test_anonymous_visitor_sees_login_form(page: Page):
    page.goto('/')

    expect(page.locator('input[name=username]')).to_be_visible()
    expect(page.locator('input[name=password]')).to_be_visible()
    expect(page.get_by_role('link', name='Register')).to_be_visible()
    expect(page.get_by_role('link', name='Log Out')).to_have_count(0)


def test_login_with_valid_credentials(page: Page, alice):
    login(page, alice)

    expect(page.get_by_text(f'Hi {alice.name}!')).to_be_visible()
    nav = page.locator('.mainNavigation')
    for link in ('Home', 'Schedule', 'Add Game', 'Invite', 'Log Out'):
        expect(nav.get_by_role('link', name=link)).to_be_visible()
    expect(nav.get_by_role('link', name='Administration')).to_have_count(0)


def test_login_with_wrong_password_is_rejected(page: Page, alice):
    page.goto('/')
    page.locator('input[name=username]').fill(alice.name)
    page.locator('input[name=password]').fill('not the password')
    page.get_by_role('button', name='Login').click()

    expect_flash(page, 'Invalid username and/or password.')
    expect(page.get_by_role('link', name='Log Out')).to_have_count(0)


def test_login_with_unknown_user_is_rejected(page: Page):
    page.goto('/')
    page.locator('input[name=username]').fill('Nobody')
    page.locator('input[name=password]').fill('whatever123')
    page.get_by_role('button', name='Login').click()

    expect_flash(page, 'Invalid username and/or password.')


def test_logout(page: Page, alice):
    login(page, alice)

    page.get_by_role('link', name='Log Out').click()

    expect_flash(page, "You've logged out.")
    expect(page.locator('input[name=username]')).to_be_visible()
    page.goto('/invite/invite')
    expect(page.locator('input[name=username]')).to_be_visible()


def test_protected_pages_redirect_anonymous_visitors_to_login(page: Page, base_url):
    for path in ('/invite/invite', '/schedule/', '/admin/admin', '/game/some-game', '/event/1'):
        page.goto(path)
        expect(page).to_have_url(f'{base_url}/')
        expect(page.locator('input[name=username]')).to_be_visible()


def test_login_returns_to_originally_requested_page(page: Page, alice, base_url):
    page.goto('/invite/invite')
    expect(page.locator('input[name=username]')).to_be_visible()

    page.locator('input[name=username]').fill(alice.name)
    page.locator('input[name=password]').fill(alice.password)
    page.get_by_role('button', name='Login').click()

    expect(page).to_have_url(f'{base_url}/invite/invite')
    expect(page.get_by_role('heading', name='Your invites')).to_be_visible()


def test_admin_sees_administration_link(page: Page, admin):
    login(page, admin)

    expect(page.locator('.mainNavigation').get_by_role('link', name='Administration')).to_be_visible()
