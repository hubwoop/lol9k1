# LOL9k1 (Lan party organizer LOL > 9000)

Organize your lan party!

## Minigolf ⛳
Bored while waiting for the next match? Hit *Minigolf* in the navigation: a 9 hole top down minigolf
game (windmill included) for 1-4 players taking turns on one computer. Your rounds land in the
shared Hall of Fame, so you can compete with everyone else at the party.

Or play across the network: *Host a network game*, and up to three other registered players join it
from their own computers. Everybody sees every putt roll, and every player's round goes into the
Hall of Fame. A player who hasn't putted for 90 seconds can be skipped by the others.

Balls knock each other around, but only your own putt can hole your ball: a ball knocked into the
cup goes back to where it lay, and so does a ball knocked into the water, for one penalty stroke.

Pick a map pack before you tee off or host a game, every pack has a Hall of Fame of its own:
- *Classic*: nine holes, everybody tees off from the same spot.
- *Bumper Brawl*: nine holes made for getting in each other's way. Everybody tees off from a
  different side and goes for the same cup, across narrow planks over the water, through a gate
  just wide enough for one ball, around pinball bumpers that kick balls away, on a pool table with
  pockets. Knock the others into the water, or clear their ball out of your way.
  Every tee of a hole is as good as the others: they are mirror images of each other, and with more
  players than tees, players share them.

### Map editor 🛠
Building holes? Open the *Map editor* below the game (`/minigolf/editor`). Load a pack or start a new
one, place walls, sand, water, boosts, bumpers, sliders and windmills, drag them around and resize
them by their handles, and hit *Test* to putt the hole with the real game (nothing gets saved). Checks
point out tees and cups off the fairway and tees that aren't as good as the others, the mirror
buttons make the copies that fix that. Your work stays in your browser, with undo. *Copy pack* gives
you the code to paste into `lol9k1/static/js/minigolf.js` and `lol9k1/minigolf.py`, *Import* reads
holes back in.

### Shared map packs 🗺
Hit *Publish* in the editor and everybody at the party can play your pack. It's in the map pack picker
under *Shared by players*, for hot seat and network games, with a Hall of Fame of its own.
*Map packs* (`/minigolf/packs`) lists them all, most played or newest first, with a picture of every hole:
*Play* one, or *Test* it in the editor, where a click on a hole opens it to putt. There it can be changed
and published as a pack of your own, which says what it was made from.

- Every hole has to be holed in a test run before the pack can be published, so nobody shares a hole
  that can't be played. (Like rounds, that's taken on trust.)
- Publishing it again is an update: a new version with a fresh Hall of Fame, as the holes aren't the same
  anymore. Rounds and running games keep the version they're played on. Versions nobody played are thrown
  away a while after they're replaced.
- *Withdraw* takes a pack off offer, for its author and the admins. Games on it can still be finished.
- Limits, to keep packs playable on any laptop and the database small: every player shares up to 10 packs,
  a pack has up to 18 holes and 64 KB, a hole up to 8 tees, 40 blocks, 30 each of sand, water, boosts and
  bumpers, 12 sliders, 4 windmills and 200 wall corners. Tees and cup are on the fairway. The server
  checks it all and keeps nothing it doesn't know (see `lol9k1/minigolf_packs.py`).

## Recommended Setup
### On macOS and Linux 
- `python3 -m venv lol9k1env`
- `source lol9k1env/bin/activate`
- `pip install -r lol9k1/requirements.txt`
- `export FLASK_APP=lol9k1`
- `flask db upgrade`
- Generate an admin token for registration: `flask create-admin-token`
- Start lol9k1: `flask run`

### On Windows (pwsh)
- `py -m venv lol9k1env`
- `.\lol9k1env\Scripts\activate`
- `pip install -r lol9k1\requirements.txt`
- `$env:FLASK_APP="lol9k1"`
- `flask db upgrade`
- Generate an admin token for registration: `flask create-admin-token`
- Start lol9k1: `flask run`

## When deploying
You might want to use the same 
[`SECRET_KEY`](https://flask.palletsprojects.com/en/stable/config/#SECRET_KEY) 
every time you start lol9k1. 
This is useful because it allows users to stay authenticated even when the 
server is restarted within a session. 
To do this pass a good secret via env var `LOL9K1_SECRET_KEY`. If not set, 
a random string will be used.

### With Docker
The image runs lol9k1 with [gunicorn](https://gunicorn.org/) on port `9001` as an unprivileged user
and keeps the SQLite database at `/data/lol9k1.db`, so mount a volume there (see `docker-compose.yml`).

- `docker compose up -d`
  (the container creates or migrates the database on every start)
- Generate an admin token for registration: `docker compose exec web flask create-admin-token`

### Configuration via Environment Variables

#### Required
- `FLASK_APP` - Set this to `lol9k1`

#### Optional
- `LOL9K1_SECRET_KEY` - A secret key for the session. If not set, a random string will be used.
- `LOL9K1_DB_PATH` - The path to the [SQLite database file](https://www.sqlite.org/fileformat.html).
- `LOL9K1_SECURE_COOKIE` - Set this to `False` if lol9k1 is served over plain http (not in debug mode), else browsers don't send the session cookie. Defaults to `True`.
- [Flask configuration](https://flask.palletsprojects.com/en/stable/config/#configuring-from-environment-variables)
- Experimental: `LOL9K1_ENABLE_BRACKETS` - Set this to `True` (or `1`/`yes`) to enable brackets. Defaults to `False`.
  When enabled, the creator of a single elimination event can draw a bracket from its teams on the event page.
  Team captains enter the results of their matches, the creator and admins can enter or correct any result,
  and the bracket updates itself for everyone watching it.

## CLI commands
- `flask db upgrade` - Creates the database or migrates it to the latest version.
- `flask db status` - Shows the database version and pending migrations.
- `flask init-db` - Alias for `flask db upgrade`.
- `flask create-admin-token` - Creates an admin user invite token.
- `flask create-dummy-users` - Creates dummy users.

## Database migrations
Schema changes are versioned migrations in `lol9k1/migrations/`, see [docs/migrations.md](docs/migrations.md).

## Testing
End-to-end tests drive the app through a real browser with [Playwright](https://playwright.dev/python/).
Each test run starts its own `flask run` server on a free port against a temporary database.

- `pip install -r requirements-test.txt -c constraints-test.txt`
- `python -m playwright install --with-deps chromium`
- `pytest` (add `--headed` to watch the browser)

The migration tests don't need Playwright: with only `lol9k1/requirements.txt` and `pytest` installed,
run `pytest tests/test_migrations.py`.

The tests run on every pull request via the `e2e` GitHub Actions workflow, which installs the exact
versions from `constraints-test.txt`. Regenerate that file when the requirements change (see its header).
To use an already installed Chromium instead, point `PLAYWRIGHT_CHROMIUM_EXECUTABLE` at its binary.

## Built With

* [Flask](http://flask.pocoo.org) - A microframework for Python based on Werkzeug, Jinja 2 and good intentions
* [Bootstrap](https://getbootstrap.com/) - An open source toolkit for developing with HTML, CSS, and JS.
* [PyCharm](https://www.jetbrains.com/pycharm/) - The Python IDE for Professional Developers

## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details

## Acknowledgments

* Thank you, [Markus](https://github.com/markusschuettler)
