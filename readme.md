# LOL9k1 (Lan party organizer LOL > 9000)

Organize your lan party!

## Recommended Setup
### On macOS and Linux 
- `python3 -m venv lol9k1env`
- `source lol9k1env/bin/activate`
- `pip install -r lol9k1/requirements.txt`
- `export FLASK_APP=lol9k1`
- `flask init-db`
- Generate an admin token for registration: `flask create-admin`
- Start lol9k1: `flask run`

### On Windows (pwsh)
- `py -m venv lol9k1env`
- `.\lol9k1env\Scripts\activate`
- `pip install -r lol9k1\requirements.txt`
- `$env:FLASK_APP="lol9k1"`
- `flask init-db`
- Generate an admin token for registration: `flask create-admin`
- Start lol9k1: `flask run`

## When deploying
You might want to use the same 
[`SECRET_KEY`](https://flask.palletsprojects.com/en/2.3.x/config/#SECRET_KEY) 
every time you start lol9k1. 
This is useful because it allows users to stay authenticated even when the 
server is restarted within a session. 
To do this pass a good secret via env var `LOL9K1_SECRET_KEY`. If not set, 
a random string will be used.

### Configuration via Environment Variables

#### Required
- `FLASK_APP` - Set this to `lol9k1`

#### Optional
- `LOL9K1_SECRET_KEY` - A secret key for the session. If not set, a random string will be used.
- `LOL9K1_DB_PATH` - The path to the [SQLite database file](https://www.sqlite.org/fileformat.html).
- [Flask configuration](https://flask.palletsprojects.com/en/2.3.x/config/#configuring-from-environment-variables)

## CLI commands
- `flask init-db` - Initializes the database.
- `flask create-admin` - Creates an admin user invite token.

## Built With

* [Flask](http://flask.pocoo.org) - A microframework for Python based on Werkzeug, Jinja 2 and good intentions
* [Bootstrap](https://getbootstrap.com/) - An open source toolkit for developing with HTML, CSS, and JS.
* [PyCharm](https://www.jetbrains.com/pycharm/) - The Python IDE for Professional Developers

## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details

## Acknowledgments

* Thank you, [Markus](https://github.com/markusschuettler)
