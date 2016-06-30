from www import app
from flask import render_template, session, url_for, redirect, request, flash, jsonify, escape, Response, abort
from flask_oauthlib.client import OAuth, get_etree
from db import database, Task
import urllib2
import json
import random
import string
from datetime import datetime

API_ENDPOINT = 'https://api.openstreetmap.org/api/0.6/'

oauth = OAuth()
openstreetmap = oauth.remote_app('OpenStreetMap',
                                 base_url=API_ENDPOINT,
                                 request_token_url='https://www.openstreetmap.org/oauth/request_token',
                                 access_token_url='https://www.openstreetmap.org/oauth/access_token',
                                 authorize_url='https://www.openstreetmap.org/oauth/authorize',
                                 consumer_key=app.config['OAUTH_KEY'],
                                 consumer_secret=app.config['OAUTH_SECRET']
                                 )


@app.route('/')
def front():
    """No logic, just display the front page.
    All interaction there is done via javascript."""
    if 'osm_token' not in session:
        return render_template('login.html')
    csrf_token = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(20))
    session['csrf_token'] = csrf_token
    return render_template('index.html', csrf_token=csrf_token,
                           max_changesets=app.config['MAX_CHANGESETS'],
                           max_edits=app.config['MAX_DIFFS'])


@app.route('/login')
def login():
    return openstreetmap.authorize(callback=url_for('oauth'))


@app.route('/oauth')
@openstreetmap.authorized_handler
def oauth(resp):
    if resp is None:
        return 'Denied. <a href="' + url_for('front') + '">Try again</a>.'
    session['osm_token'] = (
            resp['oauth_token'],
            resp['oauth_token_secret']
    )
    user_details = openstreetmap.get('user/details').data
    session['osm_username'] = user_details[0].get('display_name')
    return redirect(url_for('front'))


@openstreetmap.tokengetter
def get_token(token='user'):
    if token == 'user' and 'osm_token' in session:
        return session['osm_token']
    return None


@app.route('/logout')
def logout():
    if 'osm_token' in session:
        del session['osm_token']
    if 'osm_username' in session:
        del session['osm_username']
    return redirect(url_for('front'))


def get_changesets(query):
    """Downloads a changeset and returns a dict with its info."""
    try:
        resp = urllib2.urlopen('{0}{1}'.format(API_ENDPOINT, query))
        root = get_etree().parse(resp).getroot()
        changesets = []
        for changeset in root.findall('changeset'):
            res = {
                'id': changeset.get('id'),
                'user': changeset.get('user'),
                'created': datetime.strptime(changeset.get('created_at'), '%Y-%m-%dT%H:%M:%SZ'),
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
    changesets = get_changesets('changesets?changesets=' + changeset_ids)
    if changesets is None or len(changesets) == 0:
        return '<div class="changeset">Changesets {0}</div>'.format(changeset_ids)
    # Reorder changesets in the query order
    d = {}
    for ch in changesets:
        d[ch['id']] = ch
    return ''.join([render_template('changeset.html', changeset=d[x]) for x in changeset_ids.split(',')])


@app.route('/by_user/<user>')
def by_user(user):
    changesets = get_changesets('changesets?closed=true&display_name={0}'.format(escape(user)))
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
    task.token = session['osm_token'][0]
    task.secret = session['osm_token'][1]
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
    changesets = task.changesets.split()
    return render_template('job.html', job=task, can_cancel=can_cancel, changesets=changesets)


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
