import dateutil
from flask import (Blueprint, render_template, request, flash)
from markupsafe import Markup

from lol9k1.auth import auth
import lol9k1.database as database
from lol9k1.utilities import STYLE

bp = Blueprint('admin', __name__, url_prefix='/admin')
INVALID_DATES = '<a href="https://www.youtube.com/watch?v=HGpr4r9X8DE">Ehh... No</a>. Choose a valid time span.'


@auth.admin_required
@bp.route('/admin', methods=['GET', 'POST'])
def administration():
    handle_form_posts()
    config_rows = database.get_db().execute('select * from config').fetchall()
    start_date = database.get_party_start_date()
    end_date = database.get_party_end_date()
    return render_template('admin.html', config_rows=config_rows,
                           event_start_date=start_date, event_end_date=end_date)


def handle_form_posts() -> None:
    if request.method == 'POST' and hasattr(request, 'form') and valid_date_received():
        store_form()
        flash("Settings updated.", STYLE.message)


def store_form() -> None:
    db = database.get_db()
    for key, value in request.form.items():
        db.execute('delete from config where key = ?', [key])
        db.execute(f'insert into config (key, value) values (?, ?) ', [key, value])
    db.commit()


def valid_date_received():
    start_date = dateutil.parser.parse(request.form['date_start'])
    end_date = dateutil.parser.parse(request.form['date_end'])
    if start_date >= end_date:
        flash(Markup(INVALID_DATES), STYLE.error)
        return False
    return True
