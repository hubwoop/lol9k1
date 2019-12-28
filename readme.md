# LOL9k1 (Lan party organizer LOL > 9000)
[![BCH compliance](https://bettercodehub.com/edge/badge/hubwoop/lol9k1?branch=master)](https://bettercodehub.com/)

Organize your lan party!

## Recommended Setup
### On macOS and Linux: 
- `python3 -m venv lol9k1env`
- `source lol9k1env/bin/activate`
- `pip install -r lol9k1/requirements.txt`
- `export FLASK_APP=lol9k1`
- `flask init-db`
- Generate an admin token for registration: `flask create-admin`
- Start lol9k1: `flask run`
### On Windows: 
- `py -m venv lol9k1env`
- `.\lol9k1env\Scripts\activate`
- `pip install -r lol9k1\requirements.txt`
- `set FLASK_APP=lol9k1`
- `flask init-db`
- Generate an admin token for registration: `flask create-admin`
- Start lol9k1: `flask run`

## When deploying
You might want to use the same secret every time you start lol9k1. 
This allows user to stay authenticated. To do this pass a good secret
via env var `SECRET_KEY`. If not set, a random string will be used as secret.

## Built With

* [Flask](http://flask.pocoo.org) - A microframework for Python based on Werkzeug, Jinja 2 and good intentions
* [Bootstrap](https://getbootstrap.com/) - An open source toolkit for developing with HTML, CSS, and JS.
* [PyCharm](https://www.jetbrains.com/pycharm/) - The Python IDE for Professional Developers

## Authors

* **Jonas Mai** - *Initial work* - [hubwoop](https://github.com/hubwoop)

## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details

## Acknowledgments

* Thank you [Markus](https://github.com/markusschuettler)
