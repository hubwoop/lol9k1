from flask import Blueprint, render_template

from lol9k1 import events, game
from lol9k1.auth import auth
from lol9k1.database import get_party_end_date, get_party_start_date

bp = Blueprint('schedule', __name__, url_prefix='/schedule', template_folder='templates')


@bp.route('/')
@auth.login_required
def schedule() -> str:
    start, end = events.get_party_start_and_end()
    if not start or not end:
        return "The administrators have yet to set a date for this LAN."
    return render_template('schedule/schedule.html',
                           tournaments=events.format_events(events.get_all()),
                           party_start=get_party_start_date(),
                           party_end=get_party_end_date(),
                           games=game.get_all())
