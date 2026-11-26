"""Collector attestations over enumerated sequence ranges in a synthetic log."""
from .store import act, many, one


def handle(db, command):
    if command['op'] != 'attest':
        return {'decision': 'unknown_operation'}
    first, last = command['first'], command['last']
    at = command['at']
    if type(first) is not int or type(last) is not int or not 1 <= first <= last:
        return {'decision': 'invalid_coverage_range'}
    source = one(db, 'SELECT * FROM event_sources WHERE id=?', (command['source'],))
    if not source or source['state'] != 'active' or source['generation'] != command['generation'] or source['collector'] != command['collector'] or last > source['max_seq']:
        return {'decision': 'coverage_source_denied'}
    if one(db, 'SELECT id FROM coverage_attestations WHERE id=?', (command['id'],)):
        return {'decision': 'coverage_identity_conflict'}
    args = (source['id'], source['generation'], first, last, at)
    known = many(db, 'SELECT seq FROM audit_events WHERE source=? AND source_generation=? AND seq BETWEEN ? AND ? AND received_at<=? ORDER BY seq', args)
    if len(known) != last - first + 1:
        return {'decision': 'coverage_missing', 'missing': last - first + 1 - len(known)}
    if one(db, 'SELECT id FROM conflict_cases WHERE source=? AND source_generation=? AND seq BETWEEN ? AND ? AND opened_at<=? AND (resolved_at IS NULL OR resolved_at>?)', (*args, at)):
        return {'decision': 'coverage_disputed'}
    db.execute('INSERT INTO coverage_attestations VALUES(?,?,?,?,?,?,?)', (command['id'], source['id'], source['generation'], source['collector'], first, last, at))
    return {'decision': 'coverage_attested', 'observations': len(known)}


def run(db, command):
    return act(db, 'coverage', command, handle)
