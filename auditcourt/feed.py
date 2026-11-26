"""Ordered, bounded consumption of received evidence for a synthetic tenant."""
from .store import act, many, one


def handle(db, request):
    operation = request['op']
    identity = request['id']
    if operation == 'subscribe':
        if not request['object_uid'] or one(db, 'SELECT 1 FROM evidence_feeds WHERE id=?', (identity,)):
            return {'decision': 'subscription_denied'}
        db.execute('INSERT INTO evidence_feeds VALUES(?,?,0,NULL)', (identity, request['object_uid']))
        return {'decision': 'feed_subscribed'}
    feed = one(db, 'SELECT * FROM evidence_feeds WHERE id=?', (identity,))
    if not feed:
        return {'decision': 'subscription_unknown'}
    if operation == 'read':
        if feed['pending'] is not None:
            return {'decision': 'feed_ack_pending', 'batch': feed['pending']}
        limit = request['limit']
        if type(limit) is not int or not 1 <= limit <= 50:
            return {'decision': 'feed_limit_denied'}
        batch = request['event_id']
        observations = many(db, 'SELECT rowid,id,at,received_at FROM audit_events WHERE object_uid=? AND rowid>? ORDER BY rowid LIMIT ?', (feed['object_uid'], feed['cursor'], limit))
        if not observations:
            return {'decision': 'feed_empty'}
        db.execute('INSERT INTO evidence_feed_batches VALUES(?,?,?,NULL)', (batch, identity, observations[-1]['rowid']))
        db.execute('UPDATE evidence_feeds SET pending=? WHERE id=?', (batch, identity))
        return {'decision': 'feed_batch_open', 'batch': batch, 'events': [row['id'] for row in observations]}
    if operation == 'ack':
        batch = one(db, 'SELECT * FROM evidence_feed_batches WHERE id=? AND feed=?', (request['batch'], identity))
        if not batch or feed['pending'] != batch['id']:
            return {'decision': 'feed_ack_denied'}
        db.execute('UPDATE evidence_feed_batches SET acknowledged=? WHERE id=?', (request['event_id'], batch['id']))
        db.execute('UPDATE evidence_feeds SET cursor=?,pending=NULL WHERE id=?', (batch['last_row'], identity))
        return {'decision': 'feed_batch_acknowledged'}
    return {'decision': 'unknown_operation'}


def run(db, request):
    return act(db, 'feed', request, handle)
