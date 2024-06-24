#!/usr/bin/env python
import sys
import os
import requests
import atexit
import json
from authlib.integrations.requests_client import OAuth2Auth
from . import config
from .db import database, Task
from simple_revert import (
    download_changesets, revert_changes,
    RevertError, API_ENDPOINT, changeset_xml, changes_to_osc)

LOCK_FILENAME = os.path.join(os.path.dirname(__file__), 'lock')


def free_lock():
    if os.path.exists(LOCK_FILENAME):
        os.remove(LOCK_FILENAME)


def lock():
    if os.path.exists(LOCK_FILENAME):
        return False
    with open(LOCK_FILENAME, 'w') as f:
        f.write('Remove this if {0} is not running'.format(sys.argv[0]))
    atexit.register(free_lock)
    return True


def update_status_exit_on_error(task, status, error=None):
    if task.status == status and error is None:
        return
    task.status = status
    if error is not None:
        task.error = error
    task.save()
    if error is not None:
        sys.exit(1)


def process(task):
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

    if len(diffs) > config.MAX_DIFFS:
        update_status_exit_on_error(task, 'too big', 'Would not revert {0} changes'.format(len(diffs)))

    try:
        changes = revert_changes(diffs, print_status)
    except RevertError as e:
        update_status_exit_on_error(task, 'revert error', e.message)

    if not changes:
        update_status_exit_on_error(task, 'already reverted')
        sys.exit(0)

    oauth = OAuth2Auth(json.loads(task.token))

    comment = (task.comment or '').encode('utf-8')
    tags = {
        'created_by': config.CREATED_BY,
        'comment': comment or 'Reverting {0}'.format(
            ', '.join(['{0} by {1}'.format(str(x), ch_users[x]) for x in changesets]))
    }

    resp = requests.put(API_ENDPOINT + '/api/0.6/changeset/create', data=changeset_xml(tags), auth=oauth)
    if resp.status_code == 200:
        changeset_id = resp.text
    else:
        update_status_exit_on_error(
            task, 'error', 'Failed to create changeset: {0} {1}.'.format(resp.status_code, resp.reason))

    try:
        osc = changes_to_osc(changes, changeset_id)
        resp = requests.post('{0}/api/0.6/changeset/{1}/upload'.format(API_ENDPOINT, changeset_id), osc, auth=oauth)
        if resp.status_code == 200:
            task.status = 'done'
            task.error = str(changeset_id)
        else:
            # We don't want to exit before closing the changeset
            task.status = 'error'
            task.error = 'Server rejected the changeset with code {0}: {1}'.format(resp.code, resp.text)
        task.save()
    finally:
        resp = requests.put('{0}/api/0.6/changeset/{1}/close'.format(API_ENDPOINT, changeset_id), auth=oauth)


def main():
    if not lock():
        sys.exit(0)

    database.connect()
    database.create_tables([Task], safe=True)
    try:
        task = Task.get(Task.pending)
    except Task.DoesNotExist:
        # Yay, no jobs for us.
        sys.exit(0)

    try:
        process(task)
    except Exception as e:
        update_status_exit_on_error(task, 'system error', str(e))


if __name__ == '__main__':
    main()
