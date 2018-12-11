import dateutil
from flask import (Blueprint, render_template, request, flash)
from markupsafe import Markup

import lol9k1.database
from lol9k1 import auth
from lol9k1.database import get_db
from lol9k1.utilities import STYLE

bp = Blueprint('admin', __name__, url_prefix='/admin')


@auth.admin_required
@bp.route('/admin', methods=['GET', 'POST'])
def administration():
    db = get_db()
    if request.method == 'POST':
        if dateutil.parser.parse(request.form['date_start']) >= dateutil.parser.parse(request.form['date_end']):
            flash(Markup(
                '<a href="https://www.youtube.com/watch?v=HGpr4r9X8DE">Ehh... No</a>. Choose a valid time span.'
            ), STYLE.error)
        else:
            for key, value in request.form.items():
                db.execute('delete from config where key = ?', [key])
                db.execute(f'insert into config (key, value) values (?, ?) ', [key, value])
            db.commit()
            flash("Settings updated.", STYLE.message)

    config_rows = db.execute('select * from config').fetchall()
    event_start_date = lol9k1.database.get_party_start_date()
    event_end_date = lol9k1.database.get_party_end_date()
    return render_template('admin.html', page_title="Administration", config_rows=config_rows,
                           event_start_date=event_start_date, event_end_date=event_end_date)
