"""Issue a release-check receipt for observed presentation values."""
import json

from .store import act, many, one


def handle(db, event):
    if event['op'] == 'receipt':
        receipt = one(db, 'SELECT * FROM read_decisions WHERE id=?', (event['id'],))
        if not receipt:
            return {'decision': 'receipt_missing'}
        return {'decision': receipt['decision'], 'observations': json.loads(receipt['observations'])}
    if event['op'] != 'assess':
        return {'decision': 'unknown_operation'}
    rows = many(db, 'SELECT * FROM published_reads WHERE rehearsal=? ORDER BY tick,id', (event['rehearsal'],))
    matches = [row for row in rows if row['display'] == event['expected_display']]
    covered = {row['client'] for row in matches}
    missing = sorted(set(event['required_clients']) - covered)
    result = {'reads': [row['id'] for row in matches], 'missing_clients': missing}
    decision = 'read_check_passed' if event['required_clients'] and not missing else 'read_check_pending'
    db.execute('INSERT INTO read_decisions VALUES(?,?,?,?)', (
        event['event_id'], event['rehearsal'], decision, json.dumps(result, sort_keys=True)))
    return {'decision': decision, 'observations': result}


def run(db, event):
    return act(db, 'readcheck', event, handle)
