"""Sign a desk disposition after reading a real local prerequisite flag."""
from . import flags
from .store import act, one


def handle(db, command):
    if command['op'] != 'inspect':
        return {'decision': 'unknown_operation'}
    desk, key = command['desk'], command['id']
    observed = flags.current(db, desk, command['prerequisite'])
    if observed is None or observed != command['expected']:
        return {'decision': 'signoff_denied', 'observed': observed}
    if flags.current(db, desk, command['disposition']) is None:
        return {'decision': 'signoff_undefined_disposition'}
    if one(db, 'SELECT id FROM desk_signoffs WHERE id=?', (key,)):
        return {'decision': 'signoff_exists'}
    flags.update(db, desk, command['disposition'], 1)
    db.execute('INSERT INTO desk_signoffs VALUES(?,?,?,?,?)', (
        key, desk, command['prerequisite'], observed, command['disposition'],
    ))
    return {'decision': 'signoff_recorded', 'observed': observed, 'disposition': command['disposition']}


def run(db, command):
    return act(db, 'signoff', command, handle)
