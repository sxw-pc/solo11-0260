"""Install disposable binary-response specimens for a local audit drill."""
import json

from .store import act, one


def load(db, specimen):
    row = one(db, 'SELECT responses,spent FROM specimens WHERE id=?', (specimen,))
    return (json.loads(row['responses']), bool(row['spent'])) if row else (None, False)


def handle(db, command):
    if command['op'] != 'install':
        return {'decision': 'unknown_operation'}
    outputs = command['outputs']
    if set(outputs) != {'X', 'Y', 'Z'} or any(type(value) is not int or value not in (0, 1) for value in outputs.values()):
        return {'decision': 'invalid_specimen'}
    inserted = db.execute('INSERT OR IGNORE INTO specimens VALUES(?,?,0)',
                          (command['id'], json.dumps(outputs, sort_keys=True))).rowcount
    return {'decision': 'specimen_installed' if inserted else 'specimen_exists'}


def run(db, command):
    return act(db, 'specimen', command, handle)
