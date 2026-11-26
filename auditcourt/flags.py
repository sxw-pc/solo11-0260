"""Manage temporary synthetic incident flags for isolated supervisor desks."""
from .store import act, one


def current(db, desk, flag):
    row = one(db, 'SELECT value FROM desk_flags WHERE desk=? AND flag=?', (desk, flag))
    return row['value'] if row else None


def update(db, desk, flag, value):
    db.execute('INSERT INTO desk_flags VALUES(?,?,?) ON CONFLICT(desk,flag) DO UPDATE SET value=excluded.value', (desk, flag, value))


def handle(db, command):
    if command['op'] != 'set':
        return {'decision': 'unknown_operation'}
    if type(command['value']) is not int or command['value'] not in (0,1):
        return {'decision': 'flag_invalid_value'}
    update(db, command['desk'], command['flag'], command['value'])
    return {'decision': 'flag_set', 'value': command['value']}


def run(db, command):
    return act(db, 'flags', command, handle)
