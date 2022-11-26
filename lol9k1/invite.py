import uuid

from flask import session, current_app, render_template, abort, flash, redirect, url_for, Blueprint, Response
from markupsafe import Markup

import lol9k1.auth.auth as authentication
from lol9k1.database import get_db
from lol9k1.utilities import STYLE

bp = Blueprint('invite', __name__, url_prefix='/invite')


@bp.route('/invite')
@authentication.login_required
def invite() -> str:
    db = get_db()
    cursor = db.execute('select count(token) from invites where added_by = ? and used = 0', [session.get('user_id')])
    if authentication.current_user_is_admin():
        tokens_left = "∞"
    else:
        tokens_left = current_app.config.get('MAX_INVITE_TOKENS') - int(cursor.fetchall()[0][0])
        if tokens_left < 1:
            tokens_left = None
    cursor = db.execute('select token, used from invites where added_by = ?', [session.get('user_id')])
    invites = cursor.fetchall()
    return render_template('invite.html', invites=invites, tokens_left=tokens_left)


@bp.route('/invite/generate')
@authentication.login_required
def generate_invite() -> Response:
    db = get_db()
    cursor = db.execute('select count(token) from invites where added_by = ? and used = 0', [session.get('user_id')])
    tokens = cursor.fetchall()[0][0]
    if tokens < 3 or authentication.current_user_is_admin():
        token = uuid.uuid4().hex[:12]
        db.execute('insert into invites (token, used, added_by) values (?, ?, ?)',
                   [token, 0, int(session.get('user_id'))])
        db.commit()
    else:
        return abort(403)
    flash(Markup(f'Key <code style="user-select: all;">{token}</code> created.'), STYLE.message)
    return redirect(url_for('invite.invite'))


@bp.route('/invite/delete/<token>')
@authentication.login_required
def delete_invite(token) -> Response:
    db = get_db()
    db.execute('delete from invites where token = ? and added_by = ?', [token, session.get('user_id')])
    db.commit()
    flash(Markup(f'Key <code>{token}</code> deleted.'), STYLE.message)
    return redirect(url_for('invite.invite'))
