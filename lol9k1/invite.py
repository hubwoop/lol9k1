from flask import session, current_app, render_template, abort, flash, redirect, url_for, Blueprint, Response
from markupsafe import Markup

import lol9k1.auth.auth as authentication
from lol9k1.database import get_db, add_token
from lol9k1.utilities import STYLE, generate_token

bp = Blueprint('invite', __name__, url_prefix='/invite')


@bp.route('/invite')
@authentication.login_required
def invite() -> str:
    if authentication.current_user_is_admin():
        tokens_left = "∞"
    else:
        tokens_left = max(current_app.config['MAX_INVITE_TOKENS'] - count_unused_invites(), 0)
    invites = get_db().execute('select token, used from invites where added_by = ?',
                               [session.get('user_id')]).fetchall()
    return render_template('invite.html', invites=invites, tokens_left=tokens_left)


def count_unused_invites() -> int:
    return get_db().execute('select count(token) from invites where added_by = ? and used = 0',
                            [session.get('user_id')]).fetchone()[0]


@bp.route('/invite/generate')
@authentication.login_required
def generate_invite() -> Response:
    if not authentication.current_user_is_admin() \
            and count_unused_invites() >= current_app.config['MAX_INVITE_TOKENS']:
        abort(403)
    token = create_token(added_by=int(session.get('user_id')))
    flash(Markup('Key <code style="user-select: all;">{}</code> created.').format(token), STYLE.message)
    return redirect(url_for('invite.invite'))


def create_token(added_by: int, admin=False) -> str:
    token = generate_token()
    add_token(token=token, added_by=added_by, admin=admin)
    return token


@bp.route('/invite/delete/<token>')
@authentication.login_required
def delete_invite(token) -> Response:
    db = get_db()
    db.execute('delete from invites where token = ? and added_by = ?', [token, session.get('user_id')])
    db.commit()
    # the token comes from the url, so it must be escaped
    flash(Markup('Key <code>{}</code> deleted.').format(token), STYLE.message)
    return redirect(url_for('invite.invite'))
