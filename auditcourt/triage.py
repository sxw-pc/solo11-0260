"""Open an actual follow-up ticket in the selected duty queue."""
from . import routing
from .store import act, one


def handle(db, command):
    if command['op'] != 'open':
        return {'decision': 'unknown_operation'}
    key, scope = command['id'], command['scope']
    current = routing.active(db, scope)
    if not current:
        return {'decision': 'triage_unconfigured'}
    if any(not isinstance(command[k], str) or not command[k] or command[k] == '*' for k in routing.FIELDS):
        return {'decision': 'triage_bad_dimensions'}
    if one(db, 'SELECT id FROM routing_tickets WHERE id=?', (key,)):
        return {'decision': 'triage_ticket_exists'}
    destination = routing.select(current['rules'], command)
    db.execute('INSERT INTO routing_tickets VALUES(?,?,?,?,?,?,?)', (
        key, scope, current['version'], *(command[k] for k in routing.FIELDS), destination,
    ))
    return {'decision': 'triage_opened', 'destination': destination, 'version': current['version']}


def run(db, command):
    return act(db, 'triage', command, handle)
