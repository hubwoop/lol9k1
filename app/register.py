from utilities import get_db


def get_invite_token_from_db(provided_token):
    db = get_db()
    cursor = db.execute('select token, added_by from invites where token = ? and used = 0', [provided_token])
    return cursor.fetchone()


def username_already_registered(request):
    db = get_db()
    cursor = db.execute('select id from users where name = ?', [request.form['name']])
    return cursor.fetchone()


def email_already_registered(request):
    db = get_db()
    if request.form['email']:
        cursor = db.execute('select email from users where email = ?', [request.form['email']])
        if cursor.fetchone():
            return True
    return False
