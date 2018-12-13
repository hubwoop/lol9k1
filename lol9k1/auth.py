import functools
import sqlite3
from typing import NamedTuple

from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for, abort)
from werkzeug.security import check_password_hash, generate_password_hash

from lol9k1 import utilities
import lol9k1.database as database
from lol9k1.utilities import STYLE


class TokenInfo(NamedTuple):
    token: str
    added_by: int


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
def login():
    if request.method == 'POST':
        db = database.get_db()
        try:
            cursor = db.execute('select id, name, password, is_admin from users where name = (?)',
                                [request.form['username']])
        except sqlite3.Error:
            flash(utilities.NAVY_SEAL, STYLE.warning)
            return render_template('landing/start.html', page_title="Start")
        row = cursor.fetchone()
        if row and check_password_hash(row[2], request.form['password']):
            session['logged_in'] = True
            session['user_id'] = int(row[0])
            session['username'] = request.form['username']
            if row[3] == 1:
                session['is_admin'] = True
            flash("You've logged in successfully. Congratulations!", STYLE.message)
            return redirect(url_for('landing.landing'))
        else:
            flash('Invalid username and/or password.', STYLE.error)
    return render_template('authentication/login.html', page_title="Start")


@login_required
@bp.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('user_id', None)
    session.pop('is_admin', None)
    session.pop('username', None)
    flash("You've logged out.", STYLE.message)
    return redirect(url_for('landing.landing'))


@bp.before_app_request
def load_logged_in_user():
    user_id = session.get('user_id')

    if user_id is None:
        g.user = None
    else:
        g.user = database.get_db().execute('select * from users where id = ?', (user_id,)).fetchone()


def username_already_registered():
    db = database.get_db()
    cursor = db.execute('select id from users where name = ?', [request.form['name']])
    return cursor.fetchone()


def email_already_registered():
    db = get_db()
    if request.form['email']:
        cursor = db.execute('select email from users where email = ?', [request.form['email']])
        if cursor.fetchone():
            return True
    return False


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        db = database.get_db()
        token = database.get_invite_token(request.form['token'])
        if not token:
            flash("Your invite key is invalid or has already been used.", STYLE.error)
            return render_template('authentication/register.html', page_title="Anmelden")

        if username_already_registered():
            flash("Name not available.", STYLE.error)
            return render_template('authentication/register.html', page_title="Anmelden")

        if email_already_registered():
            flash("Email already assigned to different user.", STYLE.error)
            return render_template('authentication/register.html', page_title="Anmelden")

        try:
            # checks if the user was invited via the create_admin_command
            is_admin = is_admin_token(token)
            # add user
            db.execute('insert into users (name, password, email, gender, is_admin, token_used) '
                       'values (?, ?, ?, ?, ?, ?)',
                       [request.form['name'], generate_password_hash(request.form['password']),
                        request.form['email'], request.form['gender'], is_admin, request.form['token']])
            db.execute('update invites set used = 1 where token = ?', [request.form['token']])
            db.commit()
        except sqlite3.IntegrityError:
            flash("Name not available.", STYLE.error)
            return render_template('authentication/register.html', page_title="Anmelden")

        flash("Your registration was successful, you may now login.", STYLE.message)
        return redirect(url_for('landing.landing'))
    return render_template('authentication/register.html', page_title="Login")


def is_admin_token(token):
    is_admin = 1 if token.added_by == 0 else is_admin = 0
    return is_admin


@bp.route('/register/<token>')
def register_with_token(token):
    return render_template('authentication/register.html', page_title="Login", token=token)


def current_user_is_not_admin():
    return g.user is None or not session or 'is_admin' not in session or not session[
        'is_admin'] and not session.modified


def current_user_is_admin():
    return not current_user_is_not_admin()
