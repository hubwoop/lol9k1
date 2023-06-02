from flask import (
    Blueprint, render_template
)

import lol9k1.game as game
import lol9k1.database
from lol9k1 import events
from lol9k1.auth import auth


bp = Blueprint('schedule', __name__, url_prefix='/schedule', template_folder='templates')


@bp.route('/', methods=['GET', 'POST'])
@auth.login_required
def schedule() -> str:
    prepared_schedule = events.prepare_schedule()
    game_rows = game.get_all()
    if not prepared_schedule:
        return "The administrators have yet to set a date for this LAN."
    return render_template('schedule/schedule.html',
                           creators=prepared_schedule.event_creators,
                           tournaments=prepared_schedule.formatted_events,
                           party_start=lol9k1.database.get_party_start_date(),
                           party_end=lol9k1.database.get_party_end_date(),
                           fetched_date=prepared_schedule.fetch_date,
                           games=game_rows)

