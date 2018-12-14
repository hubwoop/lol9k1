import functools
import sqlite3
from typing import NamedTuple, Optional

from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for, abort)
from werkzeug.security import check_password_hash, generate_password_hash

import lol9k1.database as database
from lol9k1 import utilities
from lol9k1.utilities import STYLE


class TokenInfo(NamedTuple):
    token: str
    added_by: int


class User(NamedTuple):
    id: int
    name: str
    email: str
    password: str
    gender: str
    is_admin: int
    token_used: str


bp = Blueprint('auth', __name__, url_prefix='/auth')


def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('auth.login'))
        return view(**kwargs)

    return wrapped_view


def admin_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if current_user_is_not_admin():
            return abort(403)
        return view(**kwargs)

    return wrapped_view


@bp.route('/login', methods=('GET', 'POST'))
def login() -> None:
    if request.method == 'POST':
        user = get_user_by_name(request.form['username'])
        if not user:
            return render_template('landing/start.html', page_title="Start")
        if check_password_hash(user.password, request.form['password']):
            session['logged_in'] = True
            session['user_id'] = int(user.id)
            session['username'] = request.form['username']
            if user.is_admin == 1:
                session['is_admin'] = True
            flash("You've logged in successfully. Congratulations!", STYLE.message)
            return redirect(url_for('landing.landing'))
        else:
            flash('Invalid username and/or password.', STYLE.error)
    return render_template('authentication/login.html', page_title="Start")


def get_user_by_name(name) -> Optional[User]:
    db = database.get_db()
    try:
        cursor = db.execute('select id, name, password, is_admin from users where name = (?)', [name])
    except sqlite3.Error:
        flash(utilities.NAVY_SEAL, STYLE.warning)
        return None
    return User(*cursor.fetchone())


@login_required
@bp.route('/logout')
def logout() -> None:
    session.pop('logged_in', None)
    session.pop('user_id', None)
    session.pop('is_admin', None)
    session.pop('username', None)
    flash("You've logged out.", STYLE.message)
    return redirect(url_for('landing.landing'))


@bp.before_app_request
def load_logged_in_user() -> None:
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        g.user = database.get_db().execute('select * from users where id = ?', (user_id,)).fetchone()


def username_already_registered(name) -> bool:
    db = database.get_db()
    cursor = db.execute('select id from users where name = ?', [name])
    return cursor.fetchone() is True


def email_already_registered(email) -> bool:
    db = database.get_db()
    cursor = db.execute('select email from users where email = ?', [email])
    return cursor.fetchone() is True


def add_user() -> None:
    token = database.get_invite_token(request.form['token'])
    if not token:
        raise RegistrationError("Your invite key is invalid or has already been used.")

    if username_already_registered(request.form['name']):
        raise RegistrationError("Name not available.")

    email = request.form['email']
    if email and email_already_registered(email):
        raise RegistrationError("Email already assigned to different user.")

    is_admin = is_admin_token(token)
    db = database.get_db()
    try:
        # add user
        db.execute('insert into users (name, password, email, gender, is_admin, token_used) '
                   'values (?, ?, ?, ?, ?, ?)',
                   [request.form['name'], generate_password_hash(request.form['password']),
                    request.form['email'], request.form['gender'], is_admin, request.form['token']])
    except sqlite3.IntegrityError:
        raise RegistrationError("Name not available.")

    db.execute('update invites set used = 1 where token = ?', [request.form['token']])
    db.commit()


class RegistrationError(Exception):
    pass


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template('authentication/register.html', page_title="Login")
    try:
        add_user()
    except RegistrationError as registration_error:
        flash(str(registration_error), STYLE.error)
        return render_template('authentication/register.html', page_title="Anmelden")

    flash("Your registration was successful, you may now login.", STYLE.message)
    return redirect(url_for('landing.landing'))


def is_admin_token(token):
    # checks if the user was invited via the create_admin_command
    is_admin = 1 if token.added_by == 0 else 0
    return is_admin


@bp.route('/register/<token>')
def register_with_token(token):
    return render_template('authentication/register.html', page_title="Login", token=token)


def current_user_is_not_admin():
    return g.user is None \
           or not session \
           or 'is_admin' not in session \
           or not session['is_admin'] \
           and not session.modified


def current_user_is_admin():
    return not current_user_is_not_admin()
