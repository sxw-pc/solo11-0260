"""Approve individual local maintenance actions against received observations."""
from .store import act, one


def handle(db, x):
    op, key = x['op'], x['id']
    if op == 'approve':
        evidence = one(db, 'SELECT * FROM audit_events WHERE id=?', (x['evidence'],))
        control = one(db, 'SELECT * FROM control_objects WHERE id=?', (x['object'],))
        if not control or not evidence or evidence['object_uid'] != x['object'] or evidence['received_at'] > x['at']:
            return {'decision': 'maintenance_evidence_denied'}
        if not x['operator'] or x['at'] >= x['until'] or one(db, 'SELECT 1 FROM maintenance_approvals WHERE id=?', (key,)):
            return {'decision': 'maintenance_approval_denied'}
        db.execute('INSERT INTO maintenance_approvals VALUES(?,?,?,?,?,?,NULL)', (key, x['object'], x['operator'], evidence['id'], x['at'], x['until']))
        return {'decision': 'maintenance_approved', 'evidence': evidence['id']}
    if op == 'outcome':
        change = one(db, 'SELECT * FROM control_changes WHERE id=?', (x['change'],))
        if not change or change['at'] > x['at'] or x['value'] != change['after_value'] or not x['inspector'] or change['operator'] == x['inspector']:
            return {'decision': 'maintenance_outcome_denied'}
        if one(db, 'SELECT 1 FROM maintenance_outcomes WHERE id=? OR change_id=?', (key, x['change'])):
            return {'decision': 'maintenance_outcome_exists'}
        db.execute('INSERT INTO maintenance_outcomes VALUES(?,?,?,?)', (key, x['change'], x['inspector'], x['at']))
        return {'decision': 'maintenance_verified', 'value': x['value']}
    return {'decision': 'unknown_operation'}


def run(db, command):
    return act(db, 'maintenance', command, handle)
