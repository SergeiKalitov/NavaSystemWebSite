import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
import re
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, session
from werkzeug.security import check_password_hash

app = Flask(__name__, template_folder=str(Path(__file__).parent / 'templates'))
app.config.update(
    SECRET_KEY=os.environ['SESSION_SECRET'],
    SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE', 'true') == 'true',
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    MAX_CONTENT_LENGTH=5_000_000,
)
LOGIN = os.environ.get('FORMA_LOGIN', 'forma')
PASSWORD_HASH = os.environ['FORMA_PASSWORD_HASH']
HEALTH_TOKEN = os.environ.get('FORMA_HEALTH_TOKEN', '')
DB = Path(os.environ.get('FORMA_DB', '/var/data/forma.sqlite3'))
DB.parent.mkdir(parents=True, exist_ok=True)
with sqlite3.connect(DB) as db:
    db.execute('CREATE TABLE IF NOT EXISTS diary (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL, version INTEGER NOT NULL)')
    db.execute('INSERT OR IGNORE INTO diary VALUES (1, ?, 0)', (json.dumps({'demo': False, 'records': []}),))

attempts = []
attempt_lock = threading.Lock()

def auth_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get('signed_in'):
            if request.path.startswith('/api/'):
                return jsonify(error='Sign in again.'), 401
            return redirect('/login')
        return fn(*args, **kwargs)
    return wrapped

@app.after_request
def headers(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    if app.config['SESSION_COOKIE_SECURE']:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000'
    return response

@app.before_request
def csrf_check():
    if request.method == 'POST':
        # Device imports authenticate with their own bearer token below.
        if request.path == '/api/health/import':
            return None
        token = request.headers.get('X-CSRF-Token') if request.path.startswith('/api/') else request.form.get('csrf')
        expected = session.get('csrf')
        if not expected or not token or not hmac.compare_digest(expected, token):
            return jsonify(error='Please reload and try again.'), 403

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('signed_in'):
        return redirect('/')
    session.setdefault('csrf', secrets.token_urlsafe(32))
    error = ''
    if request.method == 'POST':
        now = time.monotonic()
        with attempt_lock:
            attempts[:] = [t for t in attempts if now - t < 300]
            blocked = len(attempts) >= 10
            if not blocked:
                attempts.append(now)
        if blocked:
            return render_template('login.html', error='Too many attempts. Try in 5 minutes.'), 429
        correct_password = check_password_hash(PASSWORD_HASH, request.form.get('password', ''))
        if hmac.compare_digest(request.form.get('login', ''), LOGIN) and correct_password:
            session.clear()
            session.update(signed_in=True, csrf=secrets.token_urlsafe(32))
            return redirect('/')
        error = 'Check your login and password.'
    return render_template('login.html', error=error)

@app.get('/')
@app.get('/forma/')
@auth_required
def diary():
    return render_template('diary.html')

@app.post('/logout')
@auth_required
def logout():
    session.clear()
    return redirect('/login')

@app.get('/api/diary')
@auth_required
def read_diary():
    with sqlite3.connect(DB) as db:
        data, version = db.execute('SELECT data, version FROM diary WHERE id=1').fetchone()
    return jsonify(state=json.loads(data), version=version)


@app.post('/api/health/import')
def import_health():
    """Merge one day's Apple Health values into the diary.

    This endpoint is intended for an iPhone Shortcut. It uses a separate
    bearer token so the Shortcut never needs the interactive Forma password.
    """
    if not HEALTH_TOKEN:
        return jsonify(error='Health import is not configured.'), 503
    supplied = request.headers.get('Authorization', '')
    if not supplied.startswith('Bearer ') or not hmac.compare_digest(supplied[7:], HEALTH_TOKEN):
        return jsonify(error='Unauthorized.'), 401
    payload = request.get_json(silent=True) or {}
    date_value = payload.get('date')
    try:
        from datetime import date
        if date(date.fromisoformat(date_value).year, date.fromisoformat(date_value).month, date.fromisoformat(date_value).day).isoformat() != date_value:
            raise ValueError
    except (AttributeError, TypeError, ValueError):
        return jsonify(error='date must be YYYY-MM-DD.'), 400
    allowed = ('weight', 'height', 'steps', 'sleep', 'pulse', 'wellbeing', 'protein')
    values = {}
    for key in allowed:
        if key in payload and payload[key] is not None:
            raw_value = payload[key]
            if isinstance(raw_value, dict) and 'value' in raw_value:
                raw_value = raw_value['value']
            if isinstance(raw_value, str):
                match = re.search(r'-?\d+(?:\.\d+)?', raw_value.replace(',', '.'))
                raw_value = float(match.group()) if match else None
            if type(raw_value) not in (int, float) or not 0 <= raw_value <= 200000:
                return jsonify(error=f'Invalid {key}.'), 400
            values[key] = raw_value
    if not values:
        return jsonify(error='No health values supplied.'), 400
    with sqlite3.connect(DB, timeout=15) as db:
        data, version = db.execute('SELECT data, version FROM diary WHERE id=1').fetchone()
        state = json.loads(data)
        records = [r for r in state['records'] if not (r.get('kind') == 'health' and r.get('date') == date_value and r.get('source') == 'apple-health')]
        records.append({'id': f'apple-health-{date_value}', 'kind': 'health', 'date': date_value, 'source': 'apple-health', 'note': 'Imported from Apple Health', **values})
        next_state = {'demo': False, 'records': records}
        result = db.execute('UPDATE diary SET data=?, version=version+1 WHERE id=1 AND version=?', (json.dumps(next_state, allow_nan=False), version))
        if result.rowcount != 1:
            return jsonify(error='Diary changed while importing. Try again.'), 409
    return jsonify(ok=True, date=date_value, values=values)


def valid_state(state):
    if not isinstance(state, dict) or type(state.get('demo')) is not bool or not isinstance(state.get('records'), list) or len(state['records']) > 10000:
        return False
    from datetime import date
    ids = set()
    for r in state['records']:
        if not isinstance(r, dict) or r.get('kind') not in ('training', 'activity', 'health') or not isinstance(r.get('id'), str) or r['id'] in ids:
            return False
        ids.add(r['id'])
        try:
            if date.fromisoformat(r['date']).isoformat() != r['date']:
                return False
        except (KeyError, TypeError, ValueError):
            return False
        if not isinstance(r.get('note', ''), str) or len(r.get('note', '')) > 1500 or not isinstance(r.get('title', ''), str) or len(r.get('title', '')) > 100:
            return False
        if 'muscles' in r and (not isinstance(r['muscles'], list) or any(g not in ('Arms', 'Shoulders', 'Legs', 'Core') for g in r['muscles'])):
            return False
        for key in ('duration', 'distance', 'weight', 'height', 'steps', 'sleep', 'pulse', 'wellbeing', 'protein'):
            if key in r and (type(r[key]) not in (int, float) or not 0 <= r[key] <= 200000):
                return False
    return True

@app.post('/api/diary')
@auth_required
def write_diary():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or type(payload.get('version')) is not int or not valid_state(payload.get('state')):
        return jsonify(error='Invalid diary data.'), 400
    data = json.dumps(payload['state'], allow_nan=False)
    with sqlite3.connect(DB, timeout=15) as db:
        result = db.execute('UPDATE diary SET data=?, version=version+1 WHERE id=1 AND version=?', (data, payload['version']))
        if result.rowcount != 1:
            return jsonify(error='Your diary changed on another device. Reload before saving.'), 409
        version = payload['version'] + 1
    return jsonify(version=version)

@app.get('/healthz')
def health():
    return {'status': 'ok'}
