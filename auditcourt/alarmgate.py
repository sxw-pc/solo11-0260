"""Decide whether candidate alarm timing clears the observed trial gate."""
import json

from .store import act, many, one


def handle(db, event):
    if event['op'] == 'receipt':
        receipt = one(db, 'SELECT * FROM alarm_gate_receipts WHERE id=?', (event['id'],))
        if not receipt:
            return {'decision': 'receipt_missing'}
        return {'decision': receipt['decision'], 'summary': json.loads(receipt['summary'])}
    if event['op'] != 'evaluate':
        return {'decision': 'unknown_operation'}
    lead = event['required_lead']
    if type(lead) is not int or lead < 0:
        return {'decision': 'invalid_lead'}
    trials = many(db, "SELECT * FROM alarm_episodes WHERE batch=? AND role='observed' ORDER BY id", (event['batch'],))
    summary = {'covered': [], 'misses': [], 'quiet': []}
    for trial in trials:
        ident = trial['id']
        hazard = trial['hazard_at']
        if hazard is None:
            summary['quiet'].append(ident)
            continue
        samples = json.loads(trial['trace'])['samples']
        bucket = 'covered' if any(row['candidate'] and row['tick'] <= hazard - lead for row in samples) else 'misses'
        summary[bucket].append(ident)
    decision = 'trial_passed' if trials and summary['covered'] and not summary['misses'] else 'trial_pending'
    db.execute('INSERT INTO alarm_gate_receipts VALUES(?,?,?,?)', (
        event['event_id'], event['batch'], decision, json.dumps(summary, sort_keys=True)))
    return {'decision': decision, 'summary': summary}


def run(db, event):
    return act(db, 'alarmgate', event, handle)
