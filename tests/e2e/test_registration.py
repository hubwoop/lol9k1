"""Registering a new account with an invite token."""
from playwright.sync_api import Page, expect

from conftest import DEFAULT_PASSWORD, expect_flash, login, User


def fill_registration(page: Page, name: str, password: str = DEFAULT_PASSWORD, confirm: str = None,
                      email: str = '', token: str = None, gender: str = "Doesn't matter"):
    if token is not None:
        page.get_by_label('Token').fill(token)
    page.get_by_label('Username').fill(name)
    page.get_by_label('New Password').fill(password)
    page.get_by_label('Repeat Password').fill(confirm if confirm is not None else password)
    page.get_by_label('E-Mail').fill(email)
    page.get_by_label('Gender').select_option(label=gender)
    page.get_by_role('button', name='Hit me!').click()


def test_register_with_invite_link_and_login(page: Page, seed, alice, base_url):
    token = seed.token(added_by=alice.id)

    page.goto(f'/auth/register/{token}')

    # the invite link pre-fills the token
    expect(page).to_have_url(f'{base_url}/auth/register?token={token}')
    expect(page.get_by_label('Token')).to_have_value(token)
    fill_registration(page, 'Newbie', email='newbie@example.com', gender='Female')

    expect_flash(page, 'Your registration was successful, you may now login.')
    login(page, User(id=0, name='Newbie', password=DEFAULT_PASSWORD, is_admin=False, token=token))
    expect(page.get_by_text('Hi Newbie!')).to_be_visible()
    rows = seed.query('select email, gender, is_admin, token_used from users where name = ?', ['Newbie'])
    assert [tuple(row) for row in rows] == [('newbie@example.com', '2', 0, token)]


def test_register_via_login_page_link(page: Page, seed):
    token = seed.token()

    page.goto('/')
    page.get_by_role('link', name='Register').click()
    fill_registration(page, 'Linkfollower', token=token)

    expect_flash(page, 'Your registration was successful')


def test_admin_invite_token_registers_an_admin(page: Page, seed):
    token = seed.token(admin=True)

    page.goto(f'/auth/register?token={token}')
    fill_registration(page, 'Second Admin')
    login(page, User(id=0, name='Second Admin', password=DEFAULT_PASSWORD, is_admin=True, token=token))

    expect(page.get_by_role('link', name='Administration')).to_be_visible()


def test_invalid_token_is_rejected(page: Page):
    page.goto('/auth/register')
    fill_registration(page, 'Intruder', token='not-a-token')

    expect(page.get_by_text('Invalid or used invite token')).to_be_visible()
    expect(page.get_by_role('alert')).to_have_count(0)


def test_used_token_cannot_be_reused(page: Page, alice):
    page.goto('/auth/register')
    fill_registration(page, 'Copycat', token=alice.token)

    expect(page.get_by_text('Invalid or used invite token')).to_be_visible()


def test_password_confirmation_must_match(page: Page, seed):
    token = seed.token()

    page.goto(f'/auth/register?token={token}')
    fill_registration(page, 'Typo', password='password-one', confirm='password-two')

    expect(page.get_by_text('Passwords must match')).to_be_visible()
    assert seed.query('select * from users where name = ?', ['Typo']) == []


def test_username_must_be_unique(page: Page, seed, alice):
    token = seed.token()

    page.goto(f'/auth/register?token={token}')
    fill_registration(page, alice.name)

    expect(page.get_by_text('Username already registered.')).to_be_visible()


def test_email_must_be_unique(page: Page, seed):
    first, second = seed.token(), seed.token()
    page.goto(f'/auth/register?token={first}')
    fill_registration(page, 'First', email='same@example.com')
    expect_flash(page, 'Your registration was successful')

    page.goto(f'/auth/register?token={second}')
    fill_registration(page, 'Second', email='same@example.com')

    expect(page.get_by_text('E-Mail already registered.')).to_be_visible()


def test_logged_in_user_is_told_they_are_registered(page: Page, alice):
    login(page, alice)

    page.goto('/auth/register')

    expect(page.get_by_text("You're already registered")).to_be_visible()
