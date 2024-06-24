from . import app
from flask import (
    render_template, session, url_for, redirect, request,
    flash, jsonify, Response, abort)
from authlib.integrations.flask_client import OAuth
from authlib.common.errors import AuthlibBaseError
from ..db import database, Task
import json
import random
import string
import requests
from datetime import datetime
from xml.etree import ElementTree as etree

API_ENDPOINT = 'https://api.openstreetmap.org/api/0.6/'

oauth = OAuth(app)
oauth.register(
    'openstreetmap',
    api_base_url=API_ENDPOINT,
    access_token_url='https://www.openstreetmap.org/oauth2/token',
    authorize_url='https://www.openstreetmap.org/oauth2/authorize',
    client_id=app.config['OAUTH_KEY'],
    client_secret=app.config['OAUTH_SECRET'],
    client_kwargs={'scope': 'read_prefs write_api'},
)


@app.route('/')
def front():
    """No logic, just display the front page.
    All interaction there is done via javascript."""
    if 'osm_token2' not in session:
        return render_template('login.html')
    csrf_token = ''.join(
        random.choice(string.ascii_letters + string.digits)
        for _ in range(20))
    session['csrf_token'] = csrf_token
    return render_template('index.html', csrf_token=csrf_token,
                           max_changesets=app.config['MAX_CHANGESETS'],
                           max_edits=app.config['MAX_DIFFS'])


@app.route('/login')
def login():
    return oauth.openstreetmap.authorize_redirect(
        url_for('authorize', _external=True))


@app.route('/oauth')
def authorize():
    client = oauth.openstreetmap
    try:
        token = client.authorize_access_token()
    except AuthlibBaseError:
        return f'Authorization denied. <a href="{url_for("front")}">Try again</a>.'

    response = client.get('user/details')
    user_details = etree.fromstring(response.content)
    name = user_details[0].get('display_name')

    session['osm_token2'] = json.dumps(token)
    session['osm_username'] = name
    session.permanent = True
    return redirect(url_for('front'))


@app.route('/logout')
def logout():
    if 'osm_token2' in session:
        del session['osm_token2']
    if 'osm_username' in session:
        del session['osm_username']
    return redirect(url_for('front'))


def get_changesets(params):
    """Downloads a changeset and returns a dict with its info."""
    try:
        resp = requests.get(f'{API_ENDPOINT}changesets', params)
        if resp.status_code != 200:
            return None
        root = etree.fromstring(resp.content)
        changesets = []
        for changeset in root.findall('changeset'):
            res = {
                'id': changeset.get('id'),
                'user': changeset.get('user'),
                'created': datetime.strptime(changeset.get('created_at'),
                                             '%Y-%m-%dT%H:%M:%SZ'),
                'tags': {}
            }
            for tag in changeset.findall('tag'):
                res['tags'][tag.get('k')] = tag.get('v')
            changesets.append(res)
        return changesets
    except:
        return None


@app.route('/changeset/<changeset_ids>')
def changeset(changeset_ids):
    import re
    if not re.match(r'^\d+(,\d+)*$', changeset_ids):
        abort(401)
    changesets = get_changesets({'changesets': changeset_ids})
    if changesets is None or len(changesets) == 0:
        return '<div class="changeset">Changesets {0}</div>'.format(changeset_ids)
    # Reorder changesets in the query order
    d = {}
    for ch in changesets:
        d[ch['id']] = ch
    return ''.join([render_template('changeset.html', changeset=d[x])
                    for x in changeset_ids.split(',')])


@app.route('/by_user/<user>')
def by_user(user):
    changesets = get_changesets({'closed': 'true', 'display_name': user})
    if changesets is None or len(changesets) == 0:
        return jsonify(status='Error')
    return Response(json.dumps(changesets), mimetype='application/json')


@app.route('/revert', methods=['POST'])
def revert():
    """Adds changesets to the job database and redirects
    user to the relevant job page."""
    # Check the CSRF token.
    if 'csrf_token' not in session or session['csrf_token'] != request.form['csrf']:
        flash('Invalid CSRF token.')
        return redirect(url_for('front'))
    del session['csrf_token']

    # Check the changeset list and convert changeset urls to ids.
    changesets = request.form['changesets'].split()
    if len(changesets) == 0:
        flash('Please enter changeset ids')
        return redirect(url_for('front'))
    comment = request.form['comment'].strip()
    for i in range(len(changesets)):
        pre = '.org/changeset/'
        pos = changesets[i].find(pre)
        if pos > 0:
            changesets[i] = changesets[i][pos+len(pre):]
        if not changesets[i].isdigit():
            flash('Invalid changeset id: ' + changesets[i])
            return redirect(url_for('front'))

    # Finally, add the task to the pool.
    database.connect()
    database.create_tables([Task], safe=True)
    task = Task()
    task.username = session['osm_username']
    task.token = session['osm_token2']
    task.secret = ''
    task.changesets = ' '.join(changesets)
    task.comment = comment
    task.save()
    return redirect(url_for('show', revid=task.id))


@app.route('/<int:revid>')
def show(revid):
    database.connect()
    try:
        task = Task.get(Task.id == revid)
    except Task.DoesNotExist:
        flash('There is not job with id={0}'.format(revid))
        return redirect(url_for('queue'))
    can_cancel = task.pending and task.username == session['osm_username']
    return render_template('job.html', job=task, can_cancel=can_cancel)


@app.route('/<int:revid>/cancel')
def cancel_task(revid):
    database.connect()
    try:
        task = Task.get(Task.id == revid)
        if task.username != session['osm_username']:
            flash('A task can be cancelled only by its owner.')
        elif task.pending:
            task.delete_instance()
        else:
            flash('The task is not pending, cannot cancel it.')
    except Task.DoesNotExist:
        flash('There is not job with id={0}'.format(revid))
    return redirect(url_for('queue'))


@app.route('/queue')
def queue():
    database.connect()
    pending = Task.select().where(Task.pending)
    done = Task.select().where(~Task.pending).order_by(-Task.id).limit(app.config['MAX_HISTORY'])
    return render_template('queue.html', pending=pending, done=done)
