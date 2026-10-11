"""Creating, sharing and deleting invite tokens."""
import re

from playwright.sync_api import Page, expect

from conftest import DEFAULT_PASSWORD, expect_flash, login

TOKEN = re.compile(r'Key (\w+) created\.')


def create_token(page: Page) -> str:
    page.get_by_role('button', name='Create token!').click()
    flash = page.get_by_role('alert').filter(has_text='created.')
    expect(flash).to_be_visible()
    return TOKEN.search(flash.inner_text()).group(1)


def test_user_creates_invite_token(page: Page, seed, alice):
    login(page, alice)
    page.get_by_role('link', name='Invite').click()
    expect(page.get_by_text('You can create 3 more tokens.')).to_be_visible()

    token = create_token(page)

    expect(page.get_by_role('link', name=token)).to_have_attribute('href', f'/auth/register/{token}')
    expect(page.get_by_text('You can create 2 more tokens.')).to_be_visible()
    rows = seed.query('select added_by, used, admin from invites where token = ?', [token])
    assert [tuple(row) for row in rows] == [(alice.id, 0, 0)]


def test_regular_user_is_limited_to_three_unused_tokens(page: Page, alice):
    login(page, alice)
    page.goto('/invite/invite')

    for _ in range(3):
        create_token(page)

    expect(page.get_by_role('button', name='Create token!')).to_have_count(0)
    response = page.goto('/invite/invite/generate')
    assert response.status == 403


def test_admin_can_create_unlimited_tokens(page: Page, admin):
    login(page, admin)
    page.goto('/invite/invite')
    expect(page.get_by_text('You can create ∞ more tokens.')).to_be_visible()

    for _ in range(4):
        create_token(page)

    expect(page.get_by_role('button', name='Create token!')).to_be_visible()


def test_delete_unused_token(page: Page, seed, alice):
    login(page, alice)
    page.goto('/invite/invite')
    token = create_token(page)

    page.get_by_role('listitem').filter(has_text=token).get_by_role('button', name='❌').click()

    expect_flash(page, f'Key {token} deleted.')
    expect(page.get_by_role('link', name=token)).to_have_count(0)
    assert seed.query('select * from invites where token = ?', [token]) == []


def test_used_token_is_marked_and_frees_a_slot(page: Page, new_context, alice):
    login(page, alice)
    page.goto('/invite/invite')
    token = create_token(page)
    expect(page.get_by_text('You can create 2 more tokens.')).to_be_visible()

    # somebody registers with the invite link
    guest = new_context().new_page()
    guest.goto(f'/auth/register/{token}')
    guest.get_by_label('Username').fill('Invited Guest')
    guest.get_by_label('New Password').fill(DEFAULT_PASSWORD)
    guest.get_by_label('Repeat Password').fill(DEFAULT_PASSWORD)
    guest.get_by_role('button', name='Hit me!').click()
    expect_flash(guest, 'Your registration was successful')

    page.reload()
    expect(page.locator('li.inviteUsed')).to_have_text(token)
    expect(page.get_by_role('link', name=token)).to_have_count(0)
    expect(page.get_by_text('You can create 3 more tokens.')).to_be_visible()


def test_token_in_delete_message_is_escaped(page: Page, alice):
    login(page, alice)

    page.goto('/invite/invite/delete/<em>sneaky<em>')

    expect_flash(page, 'Key <em>sneaky<em> deleted.')
    expect(page.get_by_role('alert').locator('em')).to_have_count(0)
