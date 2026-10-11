import json
import random
from collections import namedtuple
from datetime import datetime
from typing import List, Optional, NamedTuple, Tuple
from urllib.parse import urlparse

import dateutil.parser
from flask import session, Blueprint, request, redirect, url_for, flash, render_template, Response, abort, current_app

import lol9k1.utilities as utilities
from lol9k1.auth import auth
from lol9k1.database import get_db, get_party_start_date, get_party_end_date
from lol9k1.utilities import STYLE

Team = namedtuple('team', ['name', 'captain', 'players', 'team_id'])
Participant = namedtuple('participant', ['user', 'team_name', 'team_id', 'captain'])
Details = namedtuple('details',
                     ['creator', 'creator_id', 'game_id', 'game', 'game_slug', 'tournament_mode', 'state',
                      'description', 'external_url'])
Captain = namedtuple('captain', ['name', 'id', 'team', 'team_id'])
PickDetails = namedtuple('PickDetails', ['pick_order', 'currently_picking'])


class Event(NamedTuple):
    id: int
    game: int
    start_datetime: datetime
    end_datetime: datetime
    created_by: int
    mode: str
    state: Optional[str]
    description: Optional[str]
    external_url: Optional[str]
    pick_order: Optional[str]
    currently_picking: Optional[int]
    skips: int = 0


class EventCreationResult(NamedTuple):
    response: Tuple[str, str]
    event: Optional[Event]


MAX_TEAM_NAME_LENGTH = 50

bp = Blueprint('event', __name__, url_prefix='/event')


@bp.route('/<int:event_id>', methods=['GET', 'POST'])
@auth.login_required
def event(event_id):
    event_details = get_details(event_id)  # type: Details
    if not event_details:
        # user tries to call nonexistent event
        flash("The selected event does not exist (anymore).", STYLE.error)
        return redirect(url_for('landing.landing'))
    page_title = f"{event_details.game} Event #{event_id} -  by {event_details.creator}"
    if event_details.state:
        return render_template('pick.html',
                               page_title=page_title,
                               event_id=event_id,
                               event=event_details,
                               user_id=session.get('user_id'))
    if request.method == 'POST':
        if not user_may_manage(event_details.creator_id):
            flash(utilities.DFAULT_REFUSAL_MESSAGE, STYLE.warning)
            return redirect(url_for('.event', event_id=event_id))
        handle_url_post(event_id)
        handle_description_post(event_id)
        handle_captains_post(event_id)
        event_details = get_details(event_id)
        if not event_details:
            flash("The selected event does not exist (anymore).", STYLE.error)
            return redirect(url_for('landing.landing'))
    participants_rows = get_all_participants_for(event_id)
    teams = build_teams(participants_rows)
    if request.method == 'POST' and 'initiate-picking' in request.form:
        if not teams:
            flash('Picking teams does only make sense when teams exist :> '
                  'You need to assign team captains for that.', STYLE.message)
            return redirect(url_for('.event', event_id=event_id))
        initialize_pick_phase(event_id)
        return render_template('pick.html',
                               page_title=page_title,
                               event_id=event_id,
                               event=event_details)
    db = get_db()
    users = db.execute('''select id, name, gender from users order by name asc''').fetchall()
    captain_rows = db.execute(
        '''select user from tournament_participants where is_team_captain = 1 and tournament = ?''',
        [event_id]).fetchall()
    captains = [row[0] for row in captain_rows]
    has_participants = False
    if teams:
        for team in teams.values():
            if len(team.players) > 1:
                has_participants = True
                break
    return render_template('event.html',
                           page_title=page_title,
                           event_id=event_id,
                           event=event_details,
                           teams=teams,
                           users=users,
                           captains=captains,
                           hasParticipants=has_participants,
                           enable_brackets=current_app.config['ENABLE_BRACKETS'])


def handle_url_post(event_id):
    try:
        url = request.form['external_url']
    except KeyError:
        url = None
    url = url.strip() if url else None
    if not url:
        return
    if not is_http_url(url):
        flash('The bracket URL must start with http:// or https://.', STYLE.warning)
        return
    update_url(event_id, url)


def is_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in ('http', 'https') and bool(parsed.netloc)


def user_may_manage(creator_id) -> bool:
    return auth.current_user_is_admin() or session.get('user_id') == creator_id


def handle_description_post(event_id):
    try:
        description = request.form['description']
    except KeyError:
        description = None
    if description:
        update_description(event_id, description)


def handle_captains_post(event_id):
    try:
        captains = request.form.getlist('checked-captains')
    except (KeyError, ValueError):
        captains = None
    if captains or type(captains) == list and 'check-captains' in request.form:
        update_captains(event_id, captains)


@bp.route('/<int:event_id>/stop-pick-phase', methods=['GET'])
@auth.login_required
def stop_pick_phase(event_id):
    creator = get_creator_or_404(event_id)
    if get_state(event_id) == 'pickphase' and user_may_manage(creator):
        end_pick_state_in_db(event_id)
    return redirect(url_for('.event', event_id=event_id))


@bp.route('/<int:event_id>/captain-of', methods=['POST'])
@auth.login_required
def get_teams_user_is_captain_of(event_id):
    captains = get_captains_from_db(event_id)
    leading = []
    for captain in captains:
        if captain.id == session.get('user_id'):
            leading.append(captain.team_id)
    return json.dumps(leading)


@bp.route('/<int:event_id>/state')
@auth.login_required
def get_state_api(event_id):
    get_creator_or_404(event_id)
    teams = get_teams_for_json(event_id)
    pick_details = get_pick_details(event_id)
    state = get_state(event_id)
    return json.dumps({'teams': teams, 'pick_details': pick_details._asdict(), 'state': state})


@bp.route('/<int:event_id>/possible-teammates')
@auth.login_required
def get_possible_teammates_api(event_id):
    possible_teammates = get_possible_teammates_for(event_id)
    teammates = []
    for teammate in possible_teammates:
        teammates.append({'id': teammate[0],
                          'name': teammate[1],
                          'gender': utilities.GENDER_INT_TO_STRING[int(teammate[2])]})
    return json.dumps(teammates)


@bp.route('/<int:event_id>/team/<int:team_id>/add-mate', methods=['POST'])
@auth.login_required
def add_teammate_api(event_id, team_id):
    get_creator_or_404(event_id)
    if get_captain(team_id) is None:
        abort(404)
    body = request.get_json(silent=True)
    try:
        if isinstance(body, bool):
            raise TypeError
        requested_user = int(body)
    except (TypeError, ValueError):
        abort(400)
    db = get_db()
    currently_picking_team = get_currently_picking(event_id)
    event_state = get_state(event_id)
    possible_users = get_possible_teammates_for(event_id)
    possible_users = [user[0] for user in possible_users]
    if session.get('user_id') != get_captain(currently_picking_team) \
            or team_id != currently_picking_team \
            or event_state != 'pickphase' \
            or requested_user not in possible_users:
        return json.dumps(utilities.DFAULT_REFUSAL_MESSAGE)
    # add requested user to requesting team
    db.execute('''insert into tournament_participants (user, tournament, team) values (?, ? ,?)''',
               (requested_user, event_id, team_id))
    db.commit()
    skips = get_skips(event_id)
    if skips > 0:
        reset_skips_for(event_id)
    advance_currently_picking(event_id, currently_picking_team)
    return json.dumps("yaaaay!")


def advance_currently_picking(event_id, currently_picking_team):
    db = get_db()
    pick_order = get_pick_order(event_id)
    next_up_team = pick_order[(pick_order.index(currently_picking_team) + 1) % len(pick_order)]
    db.execute('''update events set currently_picking = ? where id = ?''', (next_up_team, event_id))
    db.commit()


@bp.route('/<int:event_id>/team/<int:team_id>/skip', methods=['POST'])
@auth.login_required
def skip_picking_teammate_api(event_id, team_id):
    get_creator_or_404(event_id)
    if get_captain(team_id) is None:
        abort(404)
    currently_picking_team = get_currently_picking(event_id)
    event_state = get_state(event_id)
    if not user_allowed_to_skip(event_id, currently_picking_team, team_id, event_state):
        return json.dumps(utilities.DFAULT_REFUSAL_MESSAGE)
    pick_order = get_pick_order(event_id)
    skips = increase_skips_for(event_id)
    if skips >= len(pick_order):
        end_pick_state_in_db(event_id)
    else:
        advance_currently_picking(event_id, currently_picking_team)
    return json.dumps("wohooo!")


def user_allowed_to_skip(event_id, currently_picking_team, team_id, event_state) -> bool:
    return ((session.get('user_id') == get_captain(currently_picking_team)
             or auth.current_user_is_admin()
             or session.get('user_id') == get_creator_of(event_id))
            and event_state == "pickphase"
            and team_id == currently_picking_team)


@bp.route('/team/<int:team_id>/name', methods=['POST'])
@auth.login_required
def set_team_name_api(team_id):
    captain = get_captain(team_id)
    if captain is None:
        abort(404)
    if not auth.current_user_is_admin() and int(session.get('user_id')) != int(captain):
        return json.dumps(utilities.DFAULT_REFUSAL_MESSAGE)
    new_name = request.get_json(silent=True)
    if not isinstance(new_name, str):
        abort(400)
    new_name = new_name.strip()
    if not new_name or len(new_name) > MAX_TEAM_NAME_LENGTH:
        return json.dumps(utilities.DFAULT_REFUSAL_MESSAGE)
    set_team_name(team_id, new_name)
    return json.dumps("yep :)!")


@bp.route('/delete/<int:event_id>')
@auth.login_required
def delete_event(event_id) -> Response:
    if user_may_manage(get_creator_or_404(event_id)):
        game = delete_with_all_dependencies_in_database(event_id)
        flash(f"Deleted event {event_id}.", STYLE.message)
        return redirect(url_for('game.game_detail', game=game))
    else:
        flash(utilities.DFAULT_REFUSAL_MESSAGE, STYLE.warning)
        return redirect(url_for('landing.landing'))


@bp.route('/create', methods=['POST'])
@auth.login_required
def create_event() -> Response:
    game_id = None
    try:
        game_id = int(request.form['game'])
    except (KeyError, ValueError, AttributeError):
        pass
    if not game_id:
        flash(utilities.DFAULT_REFUSAL_MESSAGE, STYLE.warning)
        return redirect(url_for('landing.landing'))
    db = get_db()
    games_row = db.execute('select * from games where id = ?', [game_id]).fetchone()
    if not games_row:
        abort(404)
    result = handle_event_post(games_row[0])
    if result.response:
        flash(*result.response)
    if not result.event:
        return redirect(url_for('schedule.schedule'))
    return redirect(url_for('event.event', event_id=result.event.id))


EVENT_DATETIME_FORMAT = '%Y-%m-%dT%H:%M'


def parse_event_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        raise ValueError('time zone offsets are not supported')
    return parsed.replace(second=0, microsecond=0)


def handle_event_post(game_id) -> EventCreationResult:
    try:
        start = parse_event_datetime(request.form['start'])
        end = parse_event_datetime(request.form['end'])
        mode = int(request.form['mode'])
    except (KeyError, ValueError, OverflowError):
        return EventCreationResult((utilities.DFAULT_REFUSAL_MESSAGE, STYLE.warning), None)
    if mode not in utilities.MODE_INT_TO_STRING:
        return EventCreationResult(('Unknown tournament mode', STYLE.warning), None)

    party_end, party_start = get_party_start_and_end()
    if not party_start or not party_end:
        return EventCreationResult(('The administrators have yet to set a date for this LAN.', STYLE.warning),
                                   None)
    if start < party_start or start >= party_end or end > party_end or end <= party_start or start >= end:
        return EventCreationResult(('Event not in party boundaries', STYLE.warning), None)
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        insert into events (game, start_datetime, end_datetime, created_by, mode)
        values (?, ?, ?, ?, ?)
      ''', (game_id, start.strftime(EVENT_DATETIME_FORMAT), end.strftime(EVENT_DATETIME_FORMAT),
            session.get('user_id'), mode))
    event_row = cursor.execute('''select * from events where id=?''', [cursor.lastrowid]).fetchone()
    db.commit()
    return EventCreationResult(("Tournament erstellt!", STYLE.success), Event(*event_row))


def get_party_start_and_end() -> (Optional[datetime], Optional[datetime]):
    start = get_party_start_date()
    end = get_party_end_date()
    if not start or not end:
        return None, None
    try:
        start = dateutil.parser.parse(start).replace(tzinfo=None)
        end = dateutil.parser.parse(end).replace(tzinfo=None)
    except (ValueError, OverflowError):
        return None, None
    return end, start


def mode_to_string(mode) -> str:
    try:
        return utilities.MODE_INT_TO_STRING.get(int(mode), 'Unknown')
    except (TypeError, ValueError):
        return 'Unknown'


def normalise_stored_datetime(value) -> Optional[str]:
    try:
        return dateutil.parser.parse(str(value)).replace(tzinfo=None).strftime(EVENT_DATETIME_FORMAT)
    except (ValueError, OverflowError):
        return None


def format_events(events) -> List[dict]:
    formatted_events = []
    for row in events:
        event_id = row[0]
        start, end = normalise_stored_datetime(row[2]), normalise_stored_datetime(row[3])
        if not start or not end:
            current_app.logger.warning('Skipping event %s with invalid dates in schedule', event_id)
            continue
        formatted_events.append({
            'id': event_id,
            'game': row[1],
            'start': start,
            'end': end,
            'created_by': row[4],
            'mode': mode_to_string(row[5]),
            'state': row[6],
        })
    return formatted_events


def get_all() -> List[tuple]:
    events = get_db().execute('''
      select t.id, games.name, t.start_datetime, t.end_datetime, users.name, t.mode, t.state 
      from events t 
        join games on t.game = games.id 
        join users on t.created_by = users.id
      ''').fetchall()
    return events


def get_all_by_game(game_id):
    tournaments = get_db().execute('''
      select t.id, games.name, t.start_datetime, t.end_datetime, users.name, t.mode, t.state 
      from events t 
        join games on t.game = games.id 
        join users on t.created_by = users.id
      where t.game = ?
      ''', (game_id,)).fetchall()
    return tournaments


def build_teams(participants_rows):
    teams = None
    if participants_rows:
        teams = {}
        for row in participants_rows:
            player = Participant(row[0], row[1], row[2], row[3])
            if player.team_id in teams:
                # add to existing team
                teams[player.team_id].players.append(player.user)
            else:
                # add a new team
                teams[player.team_id] = Team(player.team_name, player.captain, [player.user], player.team_id)
    return teams


def get_teams_for_json(event_id: int) -> List[dict]:
    teams = get_participants(event_id) or {}
    teams_for_json = []
    for value in teams.values():
        teams_for_json.append(value._asdict())
    return teams_for_json


def get_pick_details(event_id: int):
    db = get_db()
    pick_details = db.execute('''select pick_order, currently_picking from events where id = ?''',
                              [event_id]).fetchone()
    pick_order = json.loads(pick_details[0]) if pick_details[0] else []
    return PickDetails(pick_order=pick_order, currently_picking=pick_details[1])


def initialize_pick_phase(event_id: int):
    teams = get_teams_for_json(event_id)
    pick_order = [team['team_id'] for team in teams]
    random.shuffle(pick_order)
    db = get_db()
    db.execute('''update events set state = ?, pick_order = ?, currently_picking = ? where id = ?''',
               ("pickphase", json.dumps(pick_order), pick_order[0], event_id))
    db.commit()
    return True


def get_all_participants_for(event_id):
    participants_rows = get_db().execute('''
      select u.name, t.name, t.id, (select u.name where u.id = tp.user and tp.is_team_captain = 1) 
      from tournament_participants tp
        join users u on tp.user = u.id
        join teams t on tp.team = t.id
      where tp.tournament = ?
    ''', [event_id]).fetchall()
    return participants_rows


def get_details(event_id) -> Optional[Details]:
    row = get_db().execute('''
      select u.name, e.created_by, e.game, g.name, g.slug, e.mode, e.state, e.description, e.external_url from events e 
        join users u on e.created_by = u.id
        join games g on e.game = g.id
      where e.id = ?
    ''', [event_id]).fetchone()
    if row is None:
        return None
    event_details = Details(*row)
    return event_details


def delete_with_all_dependencies_in_database(event_id):
    db = get_db()
    game = db.execute('''
      select games.slug from events e join games on e.game = games.id where e.id = ?
    ''', [event_id]).fetchone()[0]
    delete_all_teams_associated_with(event_id)
    db.execute('''delete from tournament_participants where tournament = ?''', [event_id])
    db.execute('''delete from events where id = ?''', [event_id])
    db.commit()
    return game


def get_creator_of(event_id):
    db = get_db()
    row = db.execute('''select created_by from events where id = ?''', [event_id]).fetchone()
    return row[0] if row else None


def get_creator_or_404(event_id):
    creator = get_creator_of(event_id)
    if creator is None:
        abort(404)
    return creator


def get_captains_from_db(event_id: int):
    db = get_db()
    captain_rows = db.execute('''
          select u.name, t.user, teams.name, teams.id  from tournament_participants t
            join users u on t.user = u.id
            join teams on t.team = teams.id
          where tournament = ? and is_team_captain = 1
        ''', [event_id]).fetchall()
    captains = []
    for row in captain_rows:
        captains.append(Captain(*row))
    return captains


def get_participants(event_id):
    participants_rows = get_all_participants_for(event_id)
    teams = build_teams(participants_rows)
    return teams


def update_captains(event_id, captains):
    # reset captains and teams
    db = get_db()
    delete_all_teams_associated_with(event_id)
    db.execute('''delete from tournament_participants where tournament = ?''', [event_id])
    captains_teams = []
    for captain in captains:
        cur = db.execute('''insert into teams (captain) values (?)''', [int(captain)])
        captains_teams.append((captain, cur.lastrowid))
    # set captains
    for captain_team in captains_teams:
        db.execute('''
                  insert into tournament_participants (user, tournament, team, is_team_captain)
                  values (?, ?, ?, 1)
                ''', (captain_team[0], event_id, captain_team[1]))
    db.commit()


def delete_all_teams_associated_with(event_id):
    db = get_db()
    db.execute('''delete from teams where id in (select team from tournament_participants where tournament = ?)
              ''', [event_id])
    db.commit()


def update_description(event_id, description):
    db = get_db()
    db.execute('''update events set description = ? where id = ?''', (description, event_id))
    db.commit()


def update_url(event_id, url):
    db = get_db()
    db.execute('''update events set external_url = ? where id = ?''', (url, event_id))
    db.commit()


def get_state(event_id):
    db = get_db()
    return db.execute('''select state from events where id = ?''', [event_id]).fetchone()[0]


def get_currently_picking(event_id):
    db = get_db()
    return db.execute('''select currently_picking from events where id = ?''', [event_id]).fetchone()[0]


def get_captain(team_id):
    db = get_db()
    row = db.execute('select captain from teams where id = ?', [team_id]).fetchone()
    return row[0] if row else None


def get_possible_teammates_for(event_id):
    db = get_db()
    possible_teammates = db.execute('''
      select id, name, gender from users where id not in 
      (select user from tournament_participants where tournament = ?)''', [event_id]).fetchall()
    return possible_teammates


def set_team_name(team_id, new_name):
    db = get_db()
    db.execute('''update teams set name = ? where id = ?''', (new_name, team_id))
    db.commit()


def get_pick_order(event_id: int) -> List[int]:
    db = get_db()
    pick_order_json = db.execute('''select pick_order from events where id = ?''', [event_id]).fetchone()[0]
    return json.loads(pick_order_json)


def increase_skips_for(event_id: int) -> int:
    db = get_db()
    db.execute('''update events set skips = skips + 1 where id = ?''', [event_id])
    db.commit()
    return db.execute('select skips from events where id = ?', [event_id]).fetchone()[0]


def reset_skips_for(event_id: int):
    db = get_db()
    db.execute('''update events set skips = 0 where id = ?''', [event_id])
    db.commit()


def end_pick_state_in_db(event_id):
    db = get_db()
    db.execute('''update events set state = ? where id = ?''', (None, event_id))
    db.commit()
    reset_skips_for(event_id)


def get_skips(event_id: int) -> int:
    db = get_db()
    return db.execute('''select skips from events where id = ?''', [event_id]).fetchone()[0]
