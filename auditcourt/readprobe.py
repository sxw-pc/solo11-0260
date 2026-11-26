"""Ingest observations from the local publication-read simulator."""
import hashlib
import json

from .store import act, one


def handle(db, event):
    if event['op'] != 'record':
        return {'decision': 'unknown_operation'}
    payload = event['payload']
    versions = payload['versions']
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    model_digest = hashlib.sha256(encoded.encode()).hexdigest()
    evidence = one(db, "SELECT * FROM audit_events WHERE id=? AND state='accepted'", (event['evidence'],))
    if not evidence or (evidence['digest'], evidence['object_uid']) != (model_digest, event['id']):
        return {'decision': 'read_evidence_missing'}
    if (type(payload['tick']) is not int or payload['tick'] < 0 or not versions
            or not all(isinstance(v, str) and v for v in versions.values())
            or evidence['at'] < payload['tick']):
        return {'decision': 'invalid_read'}
    if one(db, 'SELECT 1 FROM published_reads WHERE id=?', (event['id'],)):
        return {'decision': 'read_already_recorded'}
    db.execute('INSERT INTO published_reads VALUES(?,?,?,?,?,?,?)', (
        event['id'], payload['rehearsal'], payload['client'], payload['tick'], payload['display'],
        json.dumps(versions, sort_keys=True), event['evidence']))
    return {'decision': 'read_recorded', 'client': payload['client'], 'tick': payload['tick']}


def run(db, event):
    return act(db, 'readprobe', event, handle)
