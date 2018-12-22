import functools
import sqlite3
from typing import Optional

from flask import (Blueprint, flash, g, redirect, render_template, request, session, url_for, abort)
from werkzeug.security import check_password_hash, generate_password_hash

import lol9k1.database as database
from lol9k1 import utilities
from lol9k1.auth.forms import RegistrationForm
from lol9k1.auth.types import User, RegistrationError
from lol9k1.utilities import STYLE

bp = Blueprint('auth', __name__, url_prefix='/auth', template_folder='/pages')


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
        if not current_user_is_admin():
            return abort(403)
        return view(**kwargs)

    return wrapped_view


def current_user_is_admin() -> bool:
    return g.user and session and not session.modified and 'is_admin' in session and session['is_admin']


@bp.route('/login', methods=('GET', 'POST'))
def login() -> None:
    if request.method == 'POST':
        user = get_user_by_name(request.form['username'])
        if user and check_password_hash(user.password, request.form['password']):
            initialize_session_for(user)
            flash("You've logged in successfully. Congratulations!", STYLE.message)
            return redirect(url_for('landing.landing'))
        else:
            flash('Invalid username and/or password.', STYLE.error)
    return render_template('login.html')


def get_user_by_name(name) -> Optional[User]:
    try:
        cursor = database.get_db().execute('select * from users where name = (?)', [name])
    except sqlite3.Error:
        flash(utilities.NAVY_SEAL, STYLE.warning)
        return None
    return User(*cursor.fetchone())


def initialize_session_for(user):
    session['user_id'] = int(user.id)
    session['username'] = user.name
    session['logged_in'] = True
    if user.is_admin == 1:
        session['is_admin'] = True


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


@bp.route('/register/<string:token>')
def register_with_token(token) -> None:
    return redirect(url_for('.register', token=token))


@bp.route('/register', methods=['GET', 'POST'])
def register() -> None:
    form = RegistrationForm()
    if form.validate_on_submit():
        try:
            add_user(form)
            flash("Your registration was successful, you may now login.", STYLE.message)
            return redirect(url_for('landing.landing'))
        except RegistrationError as registration_error:
            flash(str(registration_error), STYLE.error)
    return render_template('register.html',
                           form=form,
                           token=request.args['token'] if 'token' in request.args else None)


def add_user(form: RegistrationForm) -> None:
    is_admin = is_admin_token(form.token.data)
    db = database.get_db()
    try:
        # add user
        db.execute('insert into users (name, password, email, gender, is_admin, token_used) '
                   'values (?, ?, ?, ?, ?, ?)',
                   [request.form['name'], generate_password_hash(request.form['password']),
                    request.form['email'], request.form['gender'], is_admin, request.form['token']])
    except sqlite3.IntegrityError:
        raise RegistrationError("Registration failed.")

    db.execute('update invites set used = 1 where token = ?', [request.form['token']])
    db.commit()


def is_admin_token(token):
    # checks if the user was invited via the create_admin_command
    is_admin = 1 if token.added_by == 0 else 0
    return is_admin
