"""Store captured alarm and intervention traces from a local sandbox trial."""
import hashlib
import json

from .store import act, one


def valid_trace(trace):
    samples = trace['samples']
    if not samples or any(type(row['tick']) is not int or row['tick'] < 0 for row in samples):
        return False
    ticks = [row['tick'] for row in samples]
    if ticks != sorted(set(ticks)):
        return False
    if any(type(row['candidate']) is not bool or type(row['incumbent']) is not bool for row in samples):
        return False
    return all(action['tick'] in ticks and action['actuator'] for action in trace['actions'])


def handle(db, event):
    if event['op'] != 'ingest':
        return {'decision': 'unknown_operation'}
    trace = event['trace']
    encoded = json.dumps(trace, sort_keys=True, separators=(',', ':'))
    model_digest = hashlib.sha256(encoded.encode()).hexdigest()
    evidence = one(db, "SELECT * FROM audit_events WHERE id=? AND state='accepted'", (event['evidence'],))
    if not evidence or (evidence['digest'], evidence['object_uid']) != (model_digest, event['id']):
        return {'decision': 'trial_evidence_missing'}
    if (trace['role'] not in {'observed', 'control'} or not valid_trace(trace)
            or trace['samples'][-1]['tick'] > evidence['at']):
        return {'decision': 'invalid_trial_trace'}
    hazard = trace['hazard_at']
    if hazard is not None and hazard not in {sample['tick'] for sample in trace['samples']}:
        return {'decision': 'invalid_hazard_tick'}
    if one(db, 'SELECT 1 FROM alarm_episodes WHERE id=?', (event['id'],)):
        return {'decision': 'trial_already_recorded'}
    db.execute('INSERT INTO alarm_episodes VALUES(?,?,?,?,?,?,?)', (
        event['id'], trace['batch'], trace['role'], trace['profile'], encoded, hazard, event['evidence']))
    return {'decision': 'trial_recorded', 'role': trace['role'], 'hazard_at': hazard}


def run(db, event):
    return act(db, 'trialtrace', event, handle)
