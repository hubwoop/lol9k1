import functools
import sqlite3
from typing import Optional, Union

from flask import (Blueprint, flash, g, redirect, render_template, request, session, url_for, abort, Response)
from werkzeug.security import check_password_hash

import lol9k1.database as database
from lol9k1 import utilities
from lol9k1.auth.forms import RegistrationForm
from lol9k1.auth.types import User
from lol9k1.utilities import STYLE

bp = Blueprint('auth', __name__, url_prefix='/auth', template_folder='templates')


def login_required(view):
    @functools.wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.user is None:
            session["redirect_target_after_login"] = request.url
            return redirect(url_for('landing.landing'))
        return view(*args, **kwargs)
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
def login() -> Union[Response, str]:
    if request.method == 'POST':
        user = get_user_by_name(request.form['username'])
        if user and check_password_hash(user.password, request.form['password']):
            initialize_session_for(user)
            flash("You've logged in successfully. Congratulations!", STYLE.message)
            if "redirect_target_after_login" in session and session["redirect_target_after_login"]:
                redirect_to = session["redirect_target_after_login"]
                session.pop("redirect_target_after_login", None)
                return redirect(redirect_to)
            return redirect(url_for('landing.landing'))
        else:
            flash('Invalid username and/or password.', STYLE.error)
    return render_template('auth/login.html')


def get_user_by_name(name) -> Optional[User]:
    try:
        cursor = database.get_db().execute('select * from users where name = (?)', [name])
    except sqlite3.Error:
        flash(utilities.DFAULT_REFUSAL_MESSAGE, STYLE.warning)
        return None
    result = cursor.fetchone()
    if result is None:
        return None
    return User(*result)


def initialize_session_for(user):
    session['user_id'] = int(user.id)
    session['username'] = user.name
    session['logged_in'] = True
    if user.is_admin == 1:
        session['is_admin'] = True


@bp.route('/logout')
def logout() -> Response:
    session.pop('logged_in', None)
    session.pop('user_id', None)
    session.pop('is_admin', None)
    session.pop('username', None)
    session.pop('redirect_target_after_login', None)
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
def register_with_token(token) -> Response:
    return redirect(url_for('.register', token=token))


@bp.route('/register', methods=['GET', 'POST'])
def register() -> Union[Response, str]:
    form = RegistrationForm()
    if form.validate_on_submit():
        try:
            database.add_user(name=form.name.data, password=form.password.data, email=form.email.data,
                              gender=form.gender.data, token=form.token.data.token, is_admin=form.token.data.admin)
            flash("Your registration was successful, you may now login.", STYLE.message)
            return redirect(url_for('landing.landing'))
        except sqlite3.IntegrityError:
            flash("Registration failed.", STYLE.error)
    return render_template('auth/register.html',
                           form=form,
                           token=request.args['token'] if 'token' in request.args else None)
