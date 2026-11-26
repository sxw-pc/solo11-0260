"""Independent local review tickets for accepted synthetic operations."""
from .store import act, many, one


def handle(db, request):
    operation = request['op']
    identity, at = request['id'], request['at']
    if operation == 'open':
        evidence = one(db, 'SELECT * FROM audit_events WHERE id=?', (request['evidence'],))
        if not evidence or evidence['received_at'] > at or not request['reviewer']:
            return {'decision': 'followup_open_denied'}
        if one(db, 'SELECT 1 FROM followup_tickets WHERE id=?', (identity,)):
            return {'decision': 'followup_exists'}
        db.execute('INSERT INTO followup_tickets VALUES(?,?,?,?,?,NULL,NULL)',
                   (identity, evidence['id'], request['reviewer'], at, 'open'))
        return {'decision': 'followup_opened', 'object': evidence['object_uid']}
    if operation == 'respond':
        ticket = one(db, 'SELECT * FROM followup_tickets WHERE id=?', (identity,))
        response = one(db, 'SELECT * FROM audit_events WHERE id=?', (request['response'],))
        if not ticket or not response or ticket['state'] != 'open' or ticket['reviewer'] != request['reviewer']:
            return {'decision': 'followup_response_denied'}
        evidence = one(db, 'SELECT * FROM audit_events WHERE id=?', (ticket['evidence'],))
        if response['id'] == evidence['id'] or response['object_uid'] != evidence['object_uid']:
            return {'decision': 'followup_response_denied'}
        if not ticket['opened'] <= response['at'] <= response['received_at'] <= at:
            return {'decision': 'followup_response_denied'}
        db.execute("UPDATE followup_tickets SET state='closed', response=?, closed=? WHERE id=?",
                   (response['id'], at, identity))
        return {'decision': 'followup_closed', 'response': response['id']}
    if operation == 'queue':
        tickets = many(db, "SELECT id,evidence,opened FROM followup_tickets WHERE reviewer=? AND state='open' AND opened<=? ORDER BY opened,id", (identity, at))
        return {'decision': 'followup_queue', 'tickets': tickets}
    return {'decision': 'unknown_operation'}


def run(db, request):
    return act(db, 'followup', request, handle)
