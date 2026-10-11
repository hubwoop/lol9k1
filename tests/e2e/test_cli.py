"""Bootstrapping a party with the ``flask`` CLI commands documented in the readme."""
import re

from playwright.sync_api import Page, expect

from conftest import DEFAULT_PASSWORD, User, expect_flash, login, run_flask_cli


def test_create_admin_token_bootstraps_first_admin(page: Page, db_path, seed):
    output = run_flask_cli(db_path, 'create-admin-token')
    token = re.search(r'Your invite token is:\n(\w+)', output).group(1)

    page.goto(f'/auth/register/{token}')
    page.get_by_label('Username').fill('Party Host')
    page.get_by_label('New Password').fill(DEFAULT_PASSWORD)
    page.get_by_label('Repeat Password').fill(DEFAULT_PASSWORD)
    page.get_by_role('button', name='Hit me!').click()
    expect_flash(page, 'Your registration was successful')

    login(page, User(id=0, name='Party Host', password=DEFAULT_PASSWORD, is_admin=True, token=token))
    page.get_by_role('link', name='Administration').click()
    expect(page.get_by_role('heading', name='Content of the config table:')).to_be_visible()


def test_create_dummy_users(page: Page, db_path, seed):
    output = run_flask_cli(db_path, 'create-dummy-users', '--number', '2', '--password', 'dummy-password')

    names = re.findall(r"Created '(.+)' with token", output)
    assert len(names) == 2
    login(page, User(id=0, name=names[0], password='dummy-password', is_admin=False, token=''))
    expect(page.get_by_text(f'Hi {names[0]}!')).to_be_visible()
