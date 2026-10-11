# LOL9k1 (Lan party organizer LOL > 9000)

Organize your lan party!

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
- [Flask configuration](https://flask.palletsprojects.com/en/stable/config/#configuring-from-environment-variables)
- Experimental: `LOL9K1_ENABLE_BRACKETS` - Set this to `True` (or `1`/`yes`) to enable brackets. Defaults to `False`.

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
Each test run starts its own `flask run` server against a temporary database.

- `pip install -r requirements-test.txt`
- `python -m playwright install --with-deps chromium`
- `pytest` (add `--headed` to watch the browser)

The tests run on every pull request via the `e2e` GitHub Actions workflow.
To use an already installed Chromium instead, point `PLAYWRIGHT_CHROMIUM_EXECUTABLE` at its binary.

## Built With

* [Flask](http://flask.pocoo.org) - A microframework for Python based on Werkzeug, Jinja 2 and good intentions
* [Bootstrap](https://getbootstrap.com/) - An open source toolkit for developing with HTML, CSS, and JS.
* [PyCharm](https://www.jetbrains.com/pycharm/) - The Python IDE for Professional Developers

## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details

## Acknowledgments

* Thank you, [Markus](https://github.com/markusschuettler)
