#!/usr/bin/env python
import sys
import os
import config
import requests
from requests_oauthlib import OAuth1
from db import database, Task
from simple_revert.simple_revert import download_changesets, revert_changes
from simple_revert.common import RevertError, API_ENDPOINT, changeset_xml, changes_to_osc


def lock():
    filename = os.path.join(os.path.dirname(__file__), 'lock')
    if os.path.exists(filename):
        return False
    with open(filename, 'w') as f:
        f.write('Remove this if {0} is not running'.format(sys.argv[0]))
    return True


def free_lock():
    filename = os.path.join(os.path.dirname(__file__), 'lock')
    if os.path.exists(filename):
        os.remove(filename)


def lexit(code):
    free_lock()
    sys.exit(code)


def update_status_exit_on_error(task, status, error=None):
    if task.status == status and error is None:
        return
    task.status = status
    if error is not None:
        task.error = error
    task.save()
    if error is not None:
        lexit(1)

if __name__ == '__main__':
    if not lock():
        sys.exit(0)

    database.connect()
    database.create_tables([Task], safe=True)
    try:
        task = Task.get(Task.pending)
    except Task.DoesNotExist:
        # Yay, no jobs for us.
        lexit(0)

    task.pending = False
    task.status = 'start'
    task.save()

    def print_status(changeset_id, obj_type=None, obj_id=None, count=None, total=None):
        if changeset_id == 'flush':
            pass
        elif changeset_id is not None:
            update_status_exit_on_error(task, 'downloading')
        else:
            update_status_exit_on_error(task, 'reverting')

    changesets = task.changesets.split()
    if len(changesets) > config.MAX_CHANGESETS:
        update_status_exit_on_error(task, 'too big', 'Can revert at most {0} changesets.'.format(config.MAX_CHANGESETS))

    try:
        diffs, ch_users = download_changesets(changesets, print_status)
    except RevertError as e:
        update_status_exit_on_error(task, 'download error', e.message)

    if not diffs:
        update_status_exit_on_error(task, 'already reverted')
        lexit(0)
    elif len(diffs) > config.MAX_DIFFS:
        update_status_exit_on_error(task, 'too big', 'Would not revert {0} changes'.format(len(diffs)))

    try:
        changes = revert_changes(diffs, print_status)
    except RevertError as e:
        update_status_exit_on_error(task, 'revert error', e.message)

    oauth = OAuth1(task.token, task.secret, config.OAUTH_KEY, config.OAUTH_SECRET)

    tags = {
        'created_by': config.CREATED_BY,
        'comment': task.comment or 'Reverting {0}'.format(
            ', '.join(['{0} by {1}'.format(str(x), ch_users[x]) for x in changesets]))
    }

    resp = requests.put(API_ENDPOINT + '/api/0.6/changeset/create', data=changeset_xml(tags), auth=oauth)
    if resp.status == 200:
        changeset_id = resp.text
    else:
        update_status_exit_on_error(
            task, 'error', 'Failed to create changeset: {0} {1}.'.format(resp.status, resp.reason))

    osc = changes_to_osc(changes, changeset_id)
    resp = requests.post('{0}/api/0.6/changeset/{1}/upload'.format(API_ENDPOINT, changeset_id), osc, auth=oauth)
    if resp.status == 200:
        update_status_exit_on_error(task, 'done')
    else:
        # We don't want to exit before closing the changeset
        task.status = 'error'
        task.error = 'Server rejected the changeset with code {0}: {1}'.format(resp.code, resp.text)
        task.save()

    resp = requests.put('{0}/api/0.6/changeset/{1}/close'.format(API_ENDPOINT, changeset_id), auth=oauth)
    free_lock()
