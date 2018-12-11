import json
import random
import dateutil.parser
from flask import session, Blueprint, request, redirect, url_for, flash, render_template

import lol9k1.utilities as utilities
from lol9k1 import auth
from lol9k1.database import get_db, get_party_start_date, get_party_end_date
from collections import namedtuple
from datetime import datetime
from typing import List
from lol9k1.utilities import STYLE
Schedule = namedtuple('prepared_schedule',
                      ['fetch_date', 'formatted_events', 'next_day', 'previous_day', 'event_creators'])
Team = namedtuple('team', ['name', 'captain', 'players', 'team_id'])
Participants = namedtuple('participants', ['user', 'team_name', 'team_id', 'captain'])
Details = namedtuple('details',
                     ['creator', 'creator_id', 'game_id', 'game', 'game_slug', 'tournament_mode', 'state',
                      'description', 'external_url'])
Captain = namedtuple('captain', ['name', 'id', 'team', 'team_id'])
PickDetails = namedtuple('PickDetails', ['pick_order', 'currently_picking'])

bp = Blueprint('event', __name__, url_prefix='/event')


@auth.login_required
@bp.route('/<int:event_id>', methods=['GET', 'POST'])
def event(event_id):
    event_details = get_details(event_id)  # type: Details
    if not event_details:
        # user tries to call nonexistent event
        flash("The selected event does not exist (anymore).", STYLE.error)
        return redirect(url_for('landing'))
    page_title = f"{event_details.game} Event #{event_id} -  by {event_details.creator}"
    if event_details.state:
        return render_template('pick.html',
                               page_title=page_title,
                               event_id=event_id,
                               event=event_details,
                               user_id=session.get('user_id'))
    if request.method == 'POST':
        handle_url_post(event_id)
        handle_description_post(event_id)
        handle_captains_post(event_id)
        event_details = get_details(event_id)
    participants_rows = get_all_participants_for(event_id)
    teams = build_teams(participants_rows)
    if request.method == 'POST' and 'initiate-picking' in request.form:
        if not teams:
            flash('Picking teams does only make sense when teams exist :> '
                  'You need to assign team captains for that.', STYLE.message)
            return redirect(url_for('event', event_id=event_id))
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
                           hasParticipants=has_participants)


def handle_url_post(event_id):
    try:
        url = request.form['external_url']
    except KeyError:
        url = None
    if url:
        update_url(event_id, url)


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


@auth.login_required
@bp.route('/<int:event_id>/stop-pick-phase', methods=['GET'])
def stop_pick_phase(event_id):
    if get_state(event_id) == 'pickphase' and session.get('user_id') == get_creator_of(event_id):
        end_pick_state_in_db(event_id)
    return redirect(url_for('event', event_id=event_id))


@auth.login_required
@bp.route('/<int:event_id>/captain-of', methods=['POST'])
def get_teams_user_is_captain_of(event_id):
    captains = get_captains_from_db(event_id)
    leading = []
    for captain in captains:
        if captain.id == session.get('user_id'):
            leading.append(captain.team_id)
    return json.dumps(leading)


@auth.login_required
@bp.route('/<int:event_id>/state')
def get_state_api(event_id):
    teams = get_teams_for_json(event_id)
    pick_details = get_pick_details(event_id)
    state = get_state(event_id)
    return json.dumps({'teams': teams, 'pick_details': pick_details._asdict(), 'state': state})


@auth.login_required
@bp.route('/<int:event_id>/possible-teammates')
def get_possible_teammates_api(event_id):
    possible_teammates = get_possible_teammates_for(event_id)
    teammates = []
    for teammate in possible_teammates:
        teammates.append({'id': teammate[0],
                          'name': teammate[1],
                          'gender': utilities.GENDER_INT_TO_STRING[int(teammate[2])]})
    return json.dumps(teammates)


@auth.login_required
@bp.route('/<int:event_id>/team/<int:team_id>/add-mate', methods=['POST'])
def add_teammate_api(event_id, team_id):
    db = get_db()
    currently_picking_team = get_currently_picking(event_id)
    event_state = get_state(event_id)
    requested_user = int(request.json)
    possible_users = get_possible_teammates_for(event_id)
    possible_users = [user[0] for user in possible_users]
    if session.get('user_id') != get_captain(currently_picking_team) \
            or team_id != currently_picking_team \
            or event_state != 'pickphase' \
            or requested_user not in possible_users:
        return json.dumps(utilities.NAVY_SEAL)
    # add requested user to requesting team
    db.execute('''insert into tournament_participants (user, tournament, team) values (?, ? ,?)''',
               (int(request.json), event_id, team_id))
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


@auth.login_required
@bp.route('/<int:event_id>/team/<int:team_id>/skip', methods=['POST'])
def skip_picking_teammate_api(event_id, team_id):
    currently_picking_team = get_currently_picking(event_id)
    event_state = get_state(event_id)
    if not user_allowed_to_skip(event_id, currently_picking_team, team_id, event_state):
        return json.dumps(utilities.NAVY_SEAL)
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


@auth.login_required
@bp.route('/team/<int:team_id>/name', methods=['POST'])
def set_team_name_api(team_id):
    try:
        captain = get_captain(team_id)
    except KeyError:
        return json.dumps(utilities.NAVY_SEAL)
    if not auth.current_user_is_admin():
        if int(session.get('user_id')) != int(captain):
            return json.dumps(utilities.NAVY_SEAL)
    new_name = request.json
    if not type(new_name) == str:
        return json.dumps(utilities.NAVY_SEAL)
    set_team_name(team_id, new_name)
    return json.dumps("yep :)!")


@auth.login_required
@bp.route('/<int:event_id>/possible-captains')
def get_possible_captains_api(event_id):
    db = get_db()
    eligible_users = db.execute('''
      select id, name, gender from users where id not in
      (select user from tournament_participants where is_team_captain = 1 and tournament = ?)
      ''', [event_id]).fetchall()
    possible_captains = []
    for row in eligible_users:
        possible_captains.append(row[1])
    return json.dumps(possible_captains)


@auth.login_required
@bp.route('/<int:event_id>/captains', methods=['GET', 'DELETE', 'UPDATE', 'POST'])
def event_captains_api(event_id):
    if request.method == 'GET':
        captains = get_captains_from_db(event_id)
        return json.dumps([captain._asdict() for captain in captains])
    elif request.method == 'POST':
        return add_captains(request.json())
    elif request.method == 'DELETE':
        return delete_captains(request.json(), event_id)
    else:
        return utilities.NAVY_SEAL


@auth.login_required
@bp.route('/<int:event_id>/participants', methods=['GET', 'UPDATE'])
def event_participants_api(event_id):
    if request.method == 'GET':
        participants = get_participants(event_id)
        return json.dumps(participants)
    elif request.method == 'UPDATE':
        participants = update_participants(request.json())
        return json.dumps(participants)
    else:
        return utilities.NAVY_SEAL


@auth.login_required
@bp.route('/delete/<int:event_id>')
def delete_event(event_id):
    if auth.current_user_is_admin() or get_creator_of(event_id) == session.get('user_id'):
        game = delete_with_all_dependencies_in_database(event_id)
        flash(f"Deleted event {event_id}.", STYLE.message)
        return redirect(url_for('game_detail', game=game))
    else:
        flash(utilities.NAVY_SEAL, STYLE.warning)
        return redirect(url_for('landing'))


def prepare_schedule(fetch_date=None) -> Schedule:
    end, start = get_party_start_and_end()
    if not fetch_date:
        fetch_date = decide_which_date_to_fetch(end, start)
    events = get_all_by_date(fetch_date)
    event_creators = distinct_creators_as_string(events)
    formatted_events = format_events(fetch_date, events)
    next_day, previous_day = get_surrounding_dates_if_possible(end, fetch_date, start)
    return Schedule(fetch_date, formatted_events, next_day, previous_day, event_creators)


def handle_event_post(game_id):
    if request.args.get('fetch_date', None):
        return
    try:
        start = dateutil.parser.parse(request.form['start'])
        end = dateutil.parser.parse(request.form['end'])
        mode = int(request.form['mode'])
    except (KeyError, ValueError, OverflowError):
        return utilities.NAVY_SEAL, STYLE.warning

    party_end = dateutil.parser.parse(get_party_end_date())
    party_start = dateutil.parser.parse(get_party_start_date())
    if start < party_start or start >= party_end or end > party_end or end <= party_start or start >= end:
        return utilities.NAVY_SEAL, STYLE.warning
    db = get_db()
    db.execute('''
        insert into events (game, start_datetime, end_datetime, created_by, mode)
        values (?, ?, ?, ?, ?)
      ''', (game_id, request.form['start'], request.form['end'], session.get('user_id'), mode))
    db.commit()
    return "Tournament erstellt!", STYLE.success


def get_party_start_and_end():
    start = dateutil.parser.parse(get_party_start_date())
    end = dateutil.parser.parse(get_party_end_date())
    return end, start


def decide_which_date_to_fetch(end, start) -> datetime:
    current_date = datetime.now()
    fetch_date = request.args.get('fetch_date', None)
    if request.args.get('fetch_date', None):
        fetch_date = dateutil.parser.parse(fetch_date)
    elif start <= current_date <= end:
        fetch_date = current_date
    else:
        fetch_date = dateutil.parser.parse(get_party_start_date())
    return fetch_date


def get_surrounding_dates_if_possible(end, fetch_date, start):
    next_day = None
    previous_day = None
    if fetch_date.day + 1 <= end.day:
        next_day = datetime(fetch_date.year, fetch_date.month, fetch_date.day + 1).isoformat()
    if fetch_date.day - 1 >= start.day:
        previous_day = datetime(fetch_date.year, fetch_date.month, fetch_date.day - 1).isoformat()
    return next_day, previous_day


def format_events(fetch_date, events):
    formatted_events = []
    for row in events:
        start = define_start(fetch_date, row)
        end = define_end(fetch_date, row)
        formatted_events.append({
            'id': row[0],
            'game': row[1],
            'start': start,
            'end': end,
            'created_by': row[4],
            'mode': utilities.MODE_INT_TO_STRING[int(row[5])],
            'state': row[6]
        })
    return formatted_events


def define_end(fetch_date, row):
    if dateutil.parser.parse(row[3]).day != fetch_date.day:
        end = datetime(fetch_date.year, fetch_date.month, fetch_date.day, 23, 00).isoformat()
    else:
        end = row[3]
    return end


def define_start(fetch_date, row):
    if dateutil.parser.parse(row[2]).day != fetch_date.day:
        start = datetime(fetch_date.year, fetch_date.month, fetch_date.day, 0, 0).isoformat()
    else:
        start = row[2]
    return start


def get_all_by_date(fetch_date: datetime) -> List[tuple]:
    tournaments = get_db().execute('''
      select t.id, games.name, t.start_datetime, t.end_datetime, users.name, t.mode, t.state 
      from events t 
        join games on t.game = games.id 
        join users on t.created_by = users.id
      where date(start_datetime) = date(?) 
        or date(end_datetime) = date(?) 
        or (date(start_datetime) < date(?) and date(end_datetime) > date(?))
      ''', (fetch_date, fetch_date, fetch_date, fetch_date)).fetchall()
    return tournaments


def distinct_creators_as_string(events: List[tuple]) -> str:
    tournament_creators = set()
    for row in events:
        tournament_creators.add(f"'{row[4]}'")
    tournament_creators = ', '.join(tournament_creators)
    return tournament_creators


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
            player = Participants(row[0], row[1], row[2], row[3])
            if player.team_id in teams:
                # add to existing team
                teams[player.team_id].players.append(player.user)
            else:
                # add a new team
                teams[player.team_id] = Team(player.team_name, player.captain, [player.user], player.team_id)
    return teams


def get_teams_for_json(event_id: int) -> List[dict]:
    teams = get_participants(event_id)
    teams_for_json = []
    for value in teams.values():
        teams_for_json.append(value._asdict())
    return teams_for_json


def get_pick_details(event_id: int):
    db = get_db()
    pick_details = db.execute('''select pick_order, currently_picking from events where id = ?''',
                              [event_id]).fetchone()
    return PickDetails(pick_order=json.loads(pick_details[0]), currently_picking=pick_details[1])


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


def get_details(event_id) -> Details:
    row = get_db().execute('''
      select u.name, e.created_by, e.game, g.name, g.slug, e.mode, e.state, e.description, e.external_url from events e 
        join users u on e.created_by = u.id
        join games g on e.game = g.id
      where e.id = ?
    ''', [event_id]).fetchone()
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
    creator = db.execute('''select created_by from events where id = ?''', [event_id]).fetchone()[0]
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


def add_captains(captains: str):
    return None


def delete_captains(captains: str, tournament: int):
    if valid_captains_json(captains):
        captains = json.loads(captains)
        for captain in captains:
            db = get_db()
            db.execute('''
              delete from tournament_participants where tournament = ? and user = ? and is_team_captain = 1
            ''', (tournament, captain))
    else:
        return utilities.NAVY_SEAL


def valid_captains_json(captains: str) -> bool:
    try:
        captains = json.loads(captains)
    except json.JSONDecodeError:
        return False
    if type(captains) is not List:
        return False
    return True


def get_participants(event_id):
    participants_rows = get_all_participants_for(event_id)
    teams = build_teams(participants_rows)
    return teams


def update_participants(param):
    return None


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
    return db.execute('select captain from teams where id = ?', [team_id]).fetchone()[0]


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
