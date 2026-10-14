"""
End-to-end test harness for lol9k1.

A real ``flask run`` server is started once per test session against a
temporary SQLite database. Every test starts with an empty database
(all tables are truncated before each test) and drives the app through a
real Chromium browser via Playwright.
"""
import os
import socket
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.error import URLError
from urllib.request import urlopen

import pytest
from playwright.sync_api import Page, expect
from werkzeug.security import generate_password_hash

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PASSWORD = 'correct horse battery staple'
DATETIME_FORMAT = '%Y-%m-%dT%H:%M'  # format used by <input type="datetime-local">
TABLES = ('matches', 'tournament_participants', 'teams', 'events', 'votes', 'games', 'users', 'invites', 'config')


SERVER_START_ATTEMPTS = 3
SERVER_START_TIMEOUT = 30  # seconds per attempt
SERVER_STOP_TIMEOUT = 10  # seconds before SIGTERM escalates to SIGKILL
SERVER_PAGE_MARKER = b'<title>LOL 9001'  # proves that a lol9k1 server answered


class _PortTaken(Exception):
    """The server could not bind its port because another process grabbed it first."""


def _free_port() -> int:
    # The port is released again before flask binds it, so another process may
    # take it in between. _start_server detects that and retries on a new port.
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _stop_server(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=SERVER_STOP_TIMEOUT)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _wait_until_ready(process: subprocess.Popen, url: str, log_path: Path) -> None:
    """
    Waits until *this* server answers on ``url``. A response alone isn't enough:
    if our bind failed, some other process may be listening on the port. So the
    server must have logged that it is running on the port (werkzeug logs that
    only after a successful bind), must still be alive, and must serve a lol9k1 page.
    """
    deadline = time.monotonic() + SERVER_START_TIMEOUT
    while time.monotonic() < deadline:
        log = log_path.read_text(errors='replace')
        if process.poll() is not None:
            if 'Address already in use' in log or 'is in use by another program' in log:
                raise _PortTaken(log)
            raise RuntimeError(f'lol9k1 server exited early (exit code {process.returncode}):\n{log}')
        if f'Running on {url}' in log:
            try:
                with urlopen(f'{url}/', timeout=2) as response:
                    body = response.read()
                if SERVER_PAGE_MARKER in body and process.poll() is None:
                    return
            except (URLError, OSError):
                pass
        time.sleep(0.1)
    raise RuntimeError(f'lol9k1 server did not come up within {SERVER_START_TIMEOUT}s:\n'
                       f'{log_path.read_text(errors="replace")}')


def _start_server(db_path: Path, log_dir: Path) -> tuple[subprocess.Popen, str, Path]:
    for attempt in range(1, SERVER_START_ATTEMPTS + 1):
        port = _free_port()
        url = f'http://127.0.0.1:{port}'
        log_path = log_dir / f'server-{attempt}.log'
        # The child gets its own copy of the file descriptor, so the parent can close it right away.
        with open(log_path, 'w') as log:
            process = subprocess.Popen(
                [sys.executable, '-m', 'flask', 'run', '--host', '127.0.0.1', '--port', str(port)],
                cwd=REPO_ROOT, env=_server_env(db_path), stdout=log, stderr=subprocess.STDOUT,
            )
        try:
            _wait_until_ready(process, url, log_path)
            return process, url, log_path
        except _PortTaken:
            _stop_server(process)
        except BaseException:  # includes KeyboardInterrupt
            _stop_server(process)
            raise
    raise RuntimeError(f'lol9k1 server could not bind a free port in {SERVER_START_ATTEMPTS} attempts, '
                       f'see logs in {log_dir}')


def _server_env(db_path: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k != 'FLASK_DEBUG'}
    env.update(
        FLASK_APP='lol9k1',
        LOL9K1_DB_PATH=str(db_path),
        LOL9K1_SECRET_KEY='e2e-test-secret',
        # Playwright's request API doesn't send Secure cookies over http
        LOL9K1_SECURE_COOKIE='false',
        LOL9K1_ENABLE_BRACKETS='true',
        PYTHONUNBUFFERED='1',
    )
    return env


def run_flask_cli(db_path: Path, *args: str) -> str:
    """Runs a ``flask`` CLI command against the test database and returns its stdout."""
    result = subprocess.run(
        [sys.executable, '-m', 'flask', *args],
        cwd=REPO_ROOT, env=_server_env(db_path), capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f'flask {" ".join(args)} failed:\n{result.stdout}\n{result.stderr}'
    return result.stdout


@pytest.fixture(scope='session')
def db_path(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp('db') / 'lol9k1-e2e.db'
    run_flask_cli(path, 'db', 'upgrade')
    return path


@pytest.fixture(scope='session')
def live_server(db_path, tmp_path_factory) -> str:
    process, url, log_path = _start_server(db_path, tmp_path_factory.mktemp('logs'))
    try:
        yield url
    finally:
        _stop_server(process)
        print(f'\nServer log: {log_path}')


@pytest.fixture(scope='session')
def base_url(live_server) -> str:
    # Overrides pytest-base-url's fixture so page.goto('/...') hits the live server.
    return live_server


@pytest.fixture(scope='session')
def browser_type_launch_args(browser_type_launch_args):
    # Allows using a pre-installed Chromium whose revision differs from the one
    # bundled with the installed Playwright version.
    executable = os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE')
    if executable:
        return {**browser_type_launch_args, 'executable_path': executable}
    return browser_type_launch_args


@pytest.fixture(autouse=True)
def _set_default_timeouts(page: Page):
    page.set_default_timeout(10_000)
    expect.set_options(timeout=10_000)


@dataclass(frozen=True)
class User:
    id: int
    name: str
    password: str
    is_admin: bool
    token: str


class Seed:
    """Direct database access to arrange test data without clicking through the UI."""

    def __init__(self, path: Path):
        self.path = path
        self._token_counter = 0

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def reset(self) -> None:
        with self._connect() as db:
            for table in TABLES:
                db.execute(f'delete from {table}')
            db.execute('delete from sqlite_sequence')

    def query(self, sql: str, params=()) -> list:
        with self._connect() as db:
            return db.execute(sql, params).fetchall()

    def token(self, added_by: int = 0, admin: bool = False, used: bool = False) -> str:
        self._token_counter += 1
        token = f'e2etoken{self._token_counter:04d}'
        with self._connect() as db:
            db.execute('insert into invites (token, used, added_by, admin) values (?, ?, ?, ?)',
                       [token, int(used), added_by, int(admin)])
        return token

    def user(self, name: str, admin: bool = False, password: str = DEFAULT_PASSWORD, gender: int = 0) -> User:
        token = self.token(admin=admin, used=True)
        with self._connect() as db:
            cursor = db.execute(
                'insert into users (name, password, email, gender, is_admin, token_used) values (?, ?, ?, ?, ?, ?)',
                [name, generate_password_hash(password), None, str(gender), int(admin), token])
            user_id = cursor.lastrowid
        return User(id=user_id, name=name, password=password, is_admin=admin, token=token)

    def game(self, name: str, added_by: User, max_players: Optional[int] = None,
             description: Optional[str] = None, votes: Optional[dict] = None) -> int:
        """Adds a game. Like the UI, the creator automatically upvotes it. ``votes`` maps users to +1/-1."""
        from slugify import slugify
        with self._connect() as db:
            cursor = db.execute(
                'insert into games (name, slug, max_players, description, added_by) values (?, ?, ?, ?, ?)',
                [name, slugify(name), max_players, description, added_by.id])
            game_id = cursor.lastrowid
            db.execute('insert into votes (user, game, vote) values (?, ?, 1)', [added_by.id, game_id])
            for user, vote in (votes or {}).items():
                db.execute('insert into votes (user, game, vote) values (?, ?, ?)', [user.id, game_id, vote])
        return game_id

    def party(self, start: datetime, end: datetime) -> None:
        with self._connect() as db:
            for key, value in (('date_start', start), ('date_end', end)):
                db.execute('insert or replace into config (key, value) values (?, ?)',
                           [key, value.strftime(DATETIME_FORMAT)])

    def event(self, game_id: int, creator: User, start: datetime, end: datetime, mode: int = 1) -> int:
        with self._connect() as db:
            cursor = db.execute(
                'insert into events (game, start_datetime, end_datetime, created_by, mode) values (?, ?, ?, ?, ?)',
                [game_id, start.strftime(DATETIME_FORMAT), end.strftime(DATETIME_FORMAT), creator.id, str(mode)])
            return cursor.lastrowid


@pytest.fixture(scope='session')
def _seed(db_path) -> Seed:
    return Seed(db_path)


@pytest.fixture
def seed(_seed, live_server) -> Seed:
    _seed.reset()
    return _seed


@pytest.fixture(autouse=True)
def _clean_database(seed):
    """Every test starts with an empty database."""


@pytest.fixture
def admin(seed) -> User:
    return seed.user('Ada Admin', admin=True)


@pytest.fixture
def alice(seed) -> User:
    return seed.user('Alice')


@pytest.fixture
def bob(seed) -> User:
    return seed.user('Bob')


@dataclass(frozen=True)
class PartyWindow:
    start: datetime
    end: datetime

    def at(self, day_offset: int, hour: int, minute: int = 0) -> datetime:
        """A point in time relative to today (the party is always running around 'now')."""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return today + timedelta(days=day_offset, hours=hour, minutes=minute)


@pytest.fixture
def party(seed) -> PartyWindow:
    """
    Configures a party that spans the current day, so its events are visible
    in the schedule's default (current week) calendar view.
    """
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    window = PartyWindow(start=today, end=today + timedelta(days=1, hours=23, minutes=59))
    seed.party(window.start, window.end)
    return window


def login(page: Page, user: User) -> None:
    page.goto('/')
    page.locator('input[name=username]').fill(user.name)
    page.locator('input[name=password]').fill(user.password)
    page.get_by_role('button', name='Login').click()
    expect(page.get_by_role('alert')).to_contain_text("You've logged in successfully")


def expect_flash(page: Page, text: str) -> None:
    expect(page.get_by_role('alert').filter(has_text=text)).to_be_visible()


@pytest.fixture
def new_user_page(new_context):
    """Factory for additional, independently logged-in browser sessions."""

    def _open(user: User) -> Page:
        page = new_context().new_page()
        page.set_default_timeout(10_000)
        login(page, user)
        return page

    return _open
