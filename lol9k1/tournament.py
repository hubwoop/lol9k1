import dateutil
from flask import Blueprint, abort, request, flash, render_template

from lol9k1 import auth, events
from lol9k1.database import get_db, get_party_start_date, get_party_end_date
from lol9k1.utilities import STYLE

bp = Blueprint('tournament', __name__, url_prefix='/tournament')


@auth.login_required
@bp.route('/create/<game>', methods=['GET', 'POST'])
def create_tournament(game: str):
    db = get_db()
    games_row = db.execute('select * from games where slug = ?', [game]).fetchone()
    if not games_row:
        abort(404)
    fetch_date = None
    if request.method == 'POST':
        response = events.handle_event_post(games_row[0])
        if response:
            flash(*response)
            if response[1] == STYLE.success:
                fetch_date = dateutil.parser.parse(request.form['start'])
    prepared_schedule = events.prepare_schedule(fetch_date)
    flash("ALPHA: Use only in chrome and with activated JS!", STYLE.error)
    return render_template('tournament_creation.html',
                           page_title="Tournament erstellen",
                           game_row=games_row,
                           creators=prepared_schedule.event_creators,
                           tournaments=prepared_schedule.formatted_events,
                           party_start=get_party_start_date(),
                           party_end=get_party_end_date(),
                           fetched_date=prepared_schedule.fetch_date,
                           next_day=prepared_schedule.next_day,
                           previous_day=prepared_schedule.previous_day)
