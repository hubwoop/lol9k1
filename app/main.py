#######################################################################################
#
#            IMPORTS
#
#######################################################################################
import json
import os
import random
import sqlite3
import uuid
import dateutil.parser
import utilities
import platform
import events
import register as register_module

from flask import Flask, request, session, g, redirect, url_for, abort, render_template, flash, Markup
from flaskext.markdown import Markdown
from werkzeug.security import generate_password_hash, check_password_hash
from slugify import slugify
from add_game import GameAdder
from constants import select_start_page
from utilities import STYLE


#            CONFIG
#######################################################################################

app = Flask(__name__)
app.config.from_object(__name__)

# Load default config and override config from an environment variable
app.config.update(dict(
    DATABASE=os.path.join(app.root_path, 'lol9k1.db'),
    SECRET_KEY=os.urandom(24),
    USERNAME='admin',
    PASSWORD='swordfish',
    IGDB_API_KEY=os.environ.get('IGDB_API_KEY'),
    MAX_INVITE_TOKENS=3
))

if os.environ.get('DEBUGGING', default="False").capitalize() == 'True':
    app.config['SECRET_KEY'] = 'wat'

app.config.from_envvar('LOL9K1_SETTINGS', silent=True)
Markdown(app)
utilities.g = g
utilities.app = app


@app.route('/')
def landing():
    if session.get('logged_in'):
        db = utilities.get_db()
        if request.args.get('not_voted', default='False') == 'True':
            cursor = db.execute(select_start_page(without_users_vote=True), [session.get('user_id')])
        elif request.args.get('order_by_score', default='False') == 'True':
            cursor = db.execute(select_start_page(order_by_score=True), [session.get('user_id')])
        else:
            cursor = db.execute(select_start_page(), [session.get('user_id')])
        game_rows = cursor.fetchall()
        return render_template('start.html', game_rows=game_rows, page_title="Start")
    else:
        this_dir = os.path.dirname(os.path.realpath(__file__))
        video_dir = os.path.join(this_dir, 'static', 'vid')
        random_video = random.choice(os.listdir(video_dir))
        return render_template('login.html', page_title="Start",
                               video_uri=url_for('static', filename=f'vid/{random_video}'))


@app.route('/add', methods=['POST'])
def add_game():
    if not utilities.user_logged_in(session):
        abort(401)
    db = utilities.get_db()
    title = request.form['title']
    cursor = db.execute('select id from games where slug = ?', [slugify(request.form['title'])])
    games_row = cursor.fetchone()
    if games_row:
        game_id = games_row[0]
        flash(
            Markup(f'Game <a href="#gameRow-{game_id}">{title}</a> has already been added!'),
            STYLE.error
        )
    else:
        game_id = GameAdder(request, session).add_game_to_db()
        flash(Markup(f'You added game (<a href="#gameRow-{game_id}">{title}</a>).'), STYLE.success)
    return redirect(url_for('landing'))


@app.route('/api/vote/<game>/<vote>', methods=['POST'])
def game_vote(game, vote):
    if not utilities.user_logged_in(session):
        abort(401)
    vote = int(vote)
    game = int(game)
    db = utilities.get_db()
    if abs(vote) != 1 or not db.execute('select id from games where id = ?', [game]).fetchone():
        flash(utilities.NAVY_SEAL, STYLE.warning)
        return redirect(url_for('landing'))
    user = session.get('user_id')
    cursor = db.execute('select vote from votes where user = ? and game = ?', [user, game])
    result = cursor.fetchone()
    if result:
        if result[0] == vote:
            flash("You already voted for that!", STYLE.error)
            return redirect(url_for('landing'))
        else:
            db.execute('update votes set vote = ? where user = ? and game = ?', [vote, user, game])
            db.commit()
            flash("Your vote has been changed :)!", STYLE.success)
            return redirect(url_for('landing', _anchor=f"gameRow-{game}"))
    else:
        db.execute('insert into votes (user, game, vote) values (?, ?, ?)', [user, game, vote])
        db.commit()
        flash("Thanks for voting :)", STYLE.success)
        return redirect(url_for('landing', _anchor=f"gameRow-{game}"))


@app.route('/delete/game/<int:game_id>')
def delete_game(game_id: int):
    if not utilities.current_user_is_admin(session):
        abort(403)
    db = utilities.get_db()
    game = db.execute('select name from games where id = ?', [game_id]).fetchone()[0]
    try:
        db.execute('delete from votes where game = ?', [game_id])
        db.execute('delete from events where game = ?', [game_id])
        db.execute('delete from games where id = ?', [game_id])
        db.commit()
    except sqlite3.Error as e:
        flash(f'Something went wrong during deletion of game "{game}": {e}', STYLE.error)
    flash(f"Game {game} deleted.", STYLE.message)
    return redirect(url_for('landing'))


@app.route('/game/<game>')
def game_detail(game):
    if not utilities.user_logged_in(session):
        abort(401)
    db = utilities.get_db()
    game_row = db.execute('select * from games where slug = ?', [game]).fetchone()
    games_events = events.get_all_by_game(game_row[0])
    return render_template('game.html', game_row=game_row, page_title=game_row[1], events=games_events)


@app.route('/schedule', methods=['GET', 'POST'])
def schedule():
    prepared_schedule = events.prepare_schedule(request)
    return render_template('schedule.html',
                           page_title="Schedule",
                           creators=prepared_schedule.event_creators,
                           tournaments=prepared_schedule.formatted_events,
                           party_start=utilities.get_party_start_date(),
                           party_end=utilities.get_party_end_date(),
                           fetched_date=prepared_schedule.fetch_date,
                           next_day=prepared_schedule.next_day,
                           previous_day=prepared_schedule.previous_day)


@app.route('/tournament/create/<game>', methods=['GET', 'POST'])
def create_tournament(game: str):
    if not utilities.user_logged_in(session):
        abort(401)
    db = utilities.get_db()
    games_row = db.execute('select * from games where slug = ?', [game]).fetchone()
    if not games_row:
        abort(404)
    fetch_date = None
    if request.method == 'POST':
        response = events.handle_event_post(request, session, games_row[0])
        if response:
            flash(*response)
            if response[1] == STYLE.success:
                fetch_date = dateutil.parser.parse(request.form['start'])
    prepared_schedule = events.prepare_schedule(request, fetch_date)
    flash("ALPHA: Use only in chrome and with activated JS!", STYLE.error)
    return render_template('tournament_creation.html',
                           page_title="Tournament erstellen",
                           game_row=games_row,
                           creators=prepared_schedule.event_creators,
                           tournaments=prepared_schedule.formatted_events,
                           party_start=utilities.get_party_start_date(),
                           party_end=utilities.get_party_end_date(),
                           fetched_date=prepared_schedule.fetch_date,
                           next_day=prepared_schedule.next_day,
                           previous_day=prepared_schedule.previous_day)


@app.route('/event/<int:event_id>', methods=['GET', 'POST'])
def event(event_id):
    if not utilities.user_logged_in(session):
        if request.method == 'GET':
            return redirect(url_for(landing))
        return json.dumps("Please log in to proceed.")
    event_details = events.get_details(event_id)  # type: events.Details
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
        event_details = events.get_details(event_id)
    participants_rows = events.get_all_participants_for(event_id)
    teams = events.build_teams(participants_rows)
    if request.method == 'POST' and 'initiate-picking' in request.form:
        if not teams:
            flash('Picking teams does only make sense when teams exist :> '
                  'You need to assign team captains for that.', STYLE.message)
            return redirect(url_for('event', event_id=event_id))
        events.initialize_pick_phase(event_id)
        return render_template('pick.html',
                               page_title=page_title,
                               event_id=event_id,
                               event=event_details)
    db = utilities.get_db()
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
        events.update_url(event_id, url)


def handle_description_post(event_id):
    try:
        description = request.form['description']
    except KeyError:
        description = None
    if description:
        events.update_description(event_id, description)


def handle_captains_post(event_id):
    try:
        captains = request.form.getlist('checked-captains')
    except (KeyError, ValueError):
        captains = None
    if captains or type(captains) == list and 'check-captains' in request.form:
        events.update_captains(event_id, captains)


@app.route('/event/<int:event_id>/stop-pick-phase', methods=['GET'])
def stop_pick_phase(event_id):
    if events.get_state(event_id) == 'pickphase' and session.get('user_id') == events.get_creator_of(event_id):
        events.end_pick_state_in_db(event_id)
    return redirect(url_for('event', event_id=event_id))


@app.route('/event/<int:event_id>/captain-of', methods=['POST'])
def get_teams_user_is_captain_of(event_id):
    if not session.get('logged_in'):
        return utilities.NAVY_SEAL
    captains = events.get_captains_from_db(event_id)
    leading = []
    for captain in captains:
        if captain.id == session.get('user_id'):
            leading.append(captain.team_id)
    return json.dumps(leading)


@app.route('/event/<int:event_id>/state')
def get_state_api(event_id):
    teams = events.get_teams_for_json(event_id)
    pick_details = events.get_pick_details(event_id)
    state = events.get_state(event_id)
    return json.dumps({'teams': teams, 'pick_details': pick_details._asdict(), 'state': state})


@app.route('/event/<int:event_id>/possible-teammates')
def get_possible_teammates_api(event_id):
    possible_teammates = events.get_possible_teammates_for(event_id)
    teammates = []
    for teammate in possible_teammates:
        teammates.append({'id': teammate[0],
                          'name': teammate[1],
                          'gender': utilities.GENDER_INT_TO_STRING[int(teammate[2])]})
    return json.dumps(teammates)


@app.route('/event/<int:event_id>/team/<int:team_id>/add-mate', methods=['POST'])
def add_teammate_api(event_id, team_id):
    db = utilities.get_db()
    currently_picking_team = events.get_currently_picking(event_id)
    event_state = events.get_state(event_id)
    requested_user = int(request.json)
    possible_users = events.get_possible_teammates_for(event_id)
    possible_users = [user[0] for user in possible_users]
    if session.get('user_id') != events.get_captain(currently_picking_team) \
            or team_id != currently_picking_team \
            or event_state != 'pickphase' \
            or requested_user not in possible_users:
        return json.dumps(utilities.NAVY_SEAL)
    # add requested user to requesting team
    db.execute('''insert into tournament_participants (user, tournament, team) values (?, ? ,?)''',
               (int(request.json), event_id, team_id))
    db.commit()
    skips = events.get_skips(event_id)
    if skips > 0:
        events.reset_skips_for(event_id)
    advance_currently_picking(event_id, currently_picking_team)
    return json.dumps("yaaaay!")


def advance_currently_picking(event_id, currently_picking_team):
    db = utilities.get_db()
    pick_order = events.get_pick_order(event_id)
    next_up_team = pick_order[(pick_order.index(currently_picking_team) + 1) % len(pick_order)]
    db.execute('''update events set currently_picking = ? where id = ?''', (next_up_team, event_id))
    db.commit()


@app.route('/event/<int:event_id>/team/<int:team_id>/skip', methods=['POST'])
def skip_picking_teammate_api(event_id, team_id):
    currently_picking_team = events.get_currently_picking(event_id)
    event_state = events.get_state(event_id)
    if not user_allowed_to_skip(event_id, currently_picking_team, team_id, event_state):
        return json.dumps(utilities.NAVY_SEAL)
    pick_order = events.get_pick_order(event_id)
    skips = events.increase_skips_for(event_id)
    if skips >= len(pick_order):
        events.end_pick_state_in_db(event_id)
    else:
        advance_currently_picking(event_id, currently_picking_team)
    return json.dumps("wohooo!")


def user_allowed_to_skip(event_id, currently_picking_team, team_id, event_state) -> bool:
    return ((session.get('user_id') == events.get_captain(currently_picking_team)
            or utilities.current_user_is_admin(session)
            or session.get('user_id') == events.get_creator_of(event_id))
            and event_state == "pickphase"
            and team_id == currently_picking_team)


@app.route('/team/<int:team_id>/name', methods=['POST'])
def set_team_name_api(team_id):
    if not utilities.user_logged_in(session):
        return json.dumps("Please log-in to proceed.")
    try:
        captain = events.get_captain(team_id)
    except KeyError:
        return json.dumps(utilities.NAVY_SEAL)
    if not utilities.current_user_is_admin(session):
        if int(session.get('user_id')) != int(captain):
            return json.dumps(utilities.NAVY_SEAL)
    new_name = request.json
    if not type(new_name) == str:
        return json.dumps(utilities.NAVY_SEAL)
    events.set_team_name(team_id, new_name)
    return json.dumps("yep :)!")


@app.route('/event/<int:event_id>/possible-captains')
def get_possible_captains_api(event_id):
    db = utilities.get_db()
    eligible_users = db.execute('''
      select id, name, gender from users where id not in
      (select user from tournament_participants where is_team_captain = 1 and tournament = ?)
      ''', [event_id]).fetchall()
    possible_captains = []
    for row in eligible_users:
        possible_captains.append(row[1])
    return json.dumps(possible_captains)


@app.route('/event/<int:event_id>/captains', methods=['GET', 'DELETE', 'UPDATE', 'POST'])
def event_captains_api(event_id):
    if request.method == 'GET':
        captains = events.get_captains_from_db(event_id)
        return json.dumps([captain._asdict() for captain in captains])
    elif request.method == 'POST':
        return events.add_captains(request.json())
    elif request.method == 'DELETE':
        return events.delete_captains(request.json(), event_id)
    else:
        return utilities.NAVY_SEAL


@app.route('/event/<int:event_id>/participants', methods=['GET', 'UPDATE'])
def event_participants_api(event_id):
    if request.method == 'GET':
        participants = events.get_participants(event_id)
        return json.dumps(participants)
    elif request.method == 'UPDATE':
        participants = events.update_participants(request.json())
        return json.dumps(participants)
    else:
        return utilities.NAVY_SEAL


@app.route('/event/delete/<int:event_id>')
def delete_event(event_id):
    if utilities.current_user_is_admin(session) or events.get_creator_of(event_id) == session.get('user_id'):
        game = events.delete_with_all_dependencies_in_database(event_id)
        flash(f"Deleted event {event_id}.", STYLE.message)
        return redirect(url_for('game_detail', game=game))
    else:
        flash(utilities.NAVY_SEAL, STYLE.warning)
        return redirect(url_for('landing'))


#            ADMINISTRATION
#######################################################################################
@app.route('/administration', methods=['GET', 'POST'])
def administration():
    if not utilities.current_user_is_admin(session):
        abort(403)
    db = utilities.get_db()
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
    event_start_date = utilities.get_party_start_date()
    event_end_date = utilities.get_party_end_date()
    return render_template('admin.html', page_title="Administration", config_rows=config_rows,
                           event_start_date=event_start_date, event_end_date=event_end_date)


#            INVITE & REGISTER
#######################################################################################
@app.route('/invite')
def invite():
    if not utilities.user_logged_in(session):
        abort(401)
    db = utilities.get_db()
    cursor = db.execute('select count(token) from invites where added_by = ? and used = 0', [session.get('user_id')])
    if utilities.current_user_is_admin(session):
        tokens_left = "∞"
    else:
        tokens_left = app.config.get('MAX_INVITE_TOKENS') - int(cursor.fetchall()[0][0])
        if tokens_left < 1:
            tokens_left = None
    cursor = db.execute('select token, used from invites where added_by = ?', [session.get('user_id')])
    invites = cursor.fetchall()
    return render_template('invite.html', page_title="Manage invites", invites=invites, tokens_left=tokens_left)


@app.route('/invite/generate')
def generate_invite():
    if not utilities.user_logged_in(session):
        abort(401)
    db = utilities.get_db()
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


@app.route('/invite/delete/<token>')
def delete_invite(token):
    if not utilities.user_logged_in(session):
        abort(401)
    db = utilities.get_db()
    db.execute('delete from invites where token = ? and added_by = ?', [token, session.get('user_id')])
    db.commit()
    flash(Markup(f'Key <code>{token}</code> deleted.'), STYLE.message)
    return redirect(url_for('invite'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        db = utilities.get_db()
        token_and_added_by = register_module.get_invite_token_from_db(request.form['token'])
        if not token_and_added_by:
            flash("Your invite key is invalid or has already been used.", STYLE.error)
            return render_template('register.html', page_title="Anmelden")

        if register_module.username_already_registered(request):
            flash("Name not available.", STYLE.error)
            return render_template('register.html', page_title="Anmelden")

        if register_module.email_already_registered(request):
            flash("Email already assigned to different user.", STYLE.error)
            return render_template('register.html', page_title="Anmelden")

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
            return render_template('register.html', page_title="Anmelden")

        flash("Your registration was successful, you may now login.", STYLE.message)
        return redirect(url_for('landing'))
    return render_template('register.html', page_title="Login")


@app.route('/register/<token>')
def register_with_token(token):
    return render_template('register.html', page_title="Login", token=token)


#            LOGIN/LOGOUT
#######################################################################################
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        db = utilities.get_db()
        try:
            cursor = db.execute('select id, name, password, is_admin from users where name = (?)',
                                [request.form['username']])
        except sqlite3.Error:
            flash(utilities.NAVY_SEAL, STYLE.warning)
            return render_template('start.html', page_title="Start")
        row = cursor.fetchone()
        if row and check_password_hash(row[2], request.form['password']):
            session['logged_in'] = True
            session['user_id'] = int(row[0])
            session['username'] = request.form['username']
            if row[3] == 1:
                session['is_admin'] = True
            flash("You've logged in successfully. Congratulations!", STYLE.message)
            return redirect(url_for('landing'))
        else:
            flash('Invalid username and/or password.', STYLE.error)
    return render_template('login.html', page_title="Start")


@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('user_id', None)
    session.pop('is_admin', None)
    session.pop('username', None)
    flash("You've logged out.", STYLE.message)
    return redirect(url_for('landing'))


#            API
#######################################################################################
@app.route('/api')
def api():
    if not utilities.user_logged_in(session):
        abort(418)
    return "hi!"


#            UTILITIES with urls...
#######################################################################################
@app.route('/utils/add-missing-slugs')
def add_slugs_if_missing():
    if not utilities.current_user_is_admin(session):
        abort(403)
    db = utilities.get_db()
    cursor = db.execute('select id, name, slug from games')
    game_names = cursor.fetchall()
    for game_name in game_names:
        if not game_name[2]:
            db.execute('update games set slug = ? where id = ?', [slugify(game_name[1]), game_name[0]])
    db.commit()
    return "done :)"


@app.route('/utils/add-missing-igdb-ids')
def add_igdb_ids_if_missing():
    if not utilities.current_user_is_admin(session):
        abort(403)
    igdb_connection = utilities.get_igdb()
    db = utilities.get_db()
    cursor = db.execute('select id, name, igdb_id from games')
    game_names = cursor.fetchall()
    for game_name in game_names:
        if not game_name[2]:
            result = igdb_connection.games({
                'search': game_name[1],
                'fields': 'name'
            })
            print(json.dumps(result.json(), indent=2, sort_keys=True))
            igdb_id = input(f"ID of game: {game_name[1]}?")
            if igdb_id:
                db.execute('update games set igdb_id = ? where id = ?', [int(igdb_id), game_name[0]])
    db.commit()
    return "done :)"


#            CUSTOM FILTERS
#######################################################################################
@app.template_filter('strftime')
def _jinja2_filter_datetime(date, fmt=None):
    date = dateutil.parser.parse(date)
    native = date.replace(tzinfo=None)
    the_format = '%d.%m.%y <strong>%H:%M</strong>'
    return native.strftime(the_format)


@app.template_filter('gender')
def _jinja2_filter_datetime(gender_id, fmt=None):
    gender = utilities.GENDER_INT_TO_STRING[int(gender_id)]
    return gender


#            GENERIC
#######################################################################################
@app.teardown_appcontext
def close_db(error):
    if hasattr(g, 'sqlite_db'):
        g.sqlite_db.close()


@app.cli.command('initdb')
def initdb_command():
    utilities.init_db()
    print('Initialized the database.')


@app.cli.command('create-admin')
def create_admin_command():
    db = utilities.get_db()
    token = uuid.uuid4().hex[:12]
    db.execute('insert into invites (token, added_by) values (?, ?)', [token, 0])
    db.commit()
    print(f'Your invite token is:\n{token}')


if __name__ == "__main__":
    # Only for debugging while developing
    if platform.system() == 'Darwin':
        app.run(debug=True, port=8080)
    else:
        app.run(debug=True, port=80)
