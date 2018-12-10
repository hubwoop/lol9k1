import functools
import sqlite3
import uuid

from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for, current_app,
    abort)
from markupsafe import Markup
from werkzeug.security import check_password_hash, generate_password_hash

from lol9k1 import utilities
from lol9k1.database import get_db
from lol9k1.utilities import STYLE

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
        if g.user is None or not session or 'is_admin' not in session or not session['is_admin'] and not session.modified:
            return abort(403)

        return view(**kwargs)

    return wrapped_view


#            LOGIN/LOGOUT
#######################################################################################
@bp.route('/login', methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        db = get_db()
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
    return redirect(url_for('landing'))


def get_invite_token_from_db(provided_token):
    db = get_db()
    cursor = db.execute('select token, added_by from invites where token = ? and used = 0', [provided_token])
    return cursor.fetchone()


def username_already_registered():
    db = get_db()
    cursor = db.execute('select id from users where name = ?', [request.form['name']])
    return cursor.fetchone()


def email_already_registered():
    db = get_db()
    if request.form['email']:
        cursor = db.execute('select email from users where email = ?', [request.form['email']])
        if cursor.fetchone():
            return True
    return False

#            INVITE & REGISTER
#######################################################################################


@login_required
@bp.route('/invite')
def invite():
    db = get_db()
    cursor = db.execute('select count(token) from invites where added_by = ? and used = 0', [session.get('user_id')])
    if utilities.current_user_is_admin(session):
        tokens_left = "∞"
    else:
        tokens_left = current_app.config.get('MAX_INVITE_TOKENS') - int(cursor.fetchall()[0][0])
        if tokens_left < 1:
            tokens_left = None
    cursor = db.execute('select token, used from invites where added_by = ?', [session.get('user_id')])
    invites = cursor.fetchall()
    return render_template('invite.html', page_title="Manage invites", invites=invites, tokens_left=tokens_left)


@login_required
@bp.route('/invite/generate')
def generate_invite():
    db = get_db()
    cursor = db.execute('select count(token) from invites where added_by = ? and used = 0', [session.get('user_id')])
    tokens = cursor.fetchall()[0][0]
    if tokens < 3 or utilities.current_user_is_admin(session):
        token = uuid.uuid4().hex[:12]
        db.execute('insert into invites (token, used, added_by) values (?, ?, ?)',
                   [token, 0, int(session.get('user_id'))])
        db.commit()
    else:
        return abort(403)
    flash(Markup(f'Key <code style="user-select: all;">{token}</code> created.'), STYLE.message)
    return redirect(url_for('invite'))


@login_required
@bp.route('/invite/delete/<token>')
def delete_invite(token):
    db = get_db()
    db.execute('delete from invites where token = ? and added_by = ?', [token, session.get('user_id')])
    db.commit()
    flash(Markup(f'Key <code>{token}</code> deleted.'), STYLE.message)
    return redirect(url_for('invite'))


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        db = get_db()
        token_and_added_by = get_invite_token_from_db(request.form['token'])
        if not token_and_added_by:
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
            if token_and_added_by[1] == 0:
                is_admin = 1
            else:
                is_admin = 0
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


@bp.route('/register/<token>')
def register_with_token(token):
    return render_template('authentication/register.html', page_title="Login", token=token)


