"""Run and record a supported probe on a specific specimen."""
from . import specimen
from .store import act, one


def handle(db, command):
    if command['op'] != 'probe':
        return {'decision': 'unknown_operation'}
    sample, probe = command['sample'], command['probe']
    outputs, spent = specimen.load(db, sample)
    if outputs is None or spent or probe not in outputs:
        return {'decision': 'trial_blocked'}
    if one(db, 'SELECT id FROM trials WHERE id=? OR (sample=? AND probe=?)', (command['id'], sample, probe)):
        return {'decision': 'trial_exists'}
    if probe == 'Z' and not one(db, "SELECT id FROM trials WHERE sample=? AND probe='Y' AND output=1", (sample,)):
        return {'decision': 'trial_door_closed'}
    value = outputs[probe]
    db.execute('INSERT INTO trials VALUES(?,?,?,?)', (command['id'], sample, probe, value))
    if probe == 'X':
        db.execute('UPDATE specimens SET spent=1 WHERE id=?', (sample,))
    return {'decision': 'trial_observed', 'probe': probe, 'output': value}


def run(db, command):
    return act(db, 'trial', command, handle)
