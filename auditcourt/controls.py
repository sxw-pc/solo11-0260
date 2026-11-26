"""Execute bounded synthetic configuration changes with optimistic revisions."""
from .store import act, one


def handle(db, x):
    op, key = x['op'], x['id']
    item = one(db, 'SELECT * FROM control_objects WHERE id=?', (x['object'],))
    if op == 'register':
        if item or type(x['value']) is not int or not 0 <= x['value'] <= x['limit']:
            return {'decision': 'control_register_denied'}
        db.execute('INSERT INTO control_objects VALUES(?,?,?,?)', (x['object'], 1, x['value'], x['limit']))
        return {'decision': 'control_registered', 'revision': 1}
    if op != 'apply':
        return {'decision': 'unknown_operation'}
    privilege = one(db, 'SELECT * FROM maintenance_approvals WHERE id=?', (x['permit'],))
    if not item or not privilege or privilege['object'] != x['object'] or privilege['operator'] != x['operator'] or privilege['used'] is not None:
        return {'decision': 'control_not_authorized'}
    if not privilege['at'] <= x['at'] < privilege['until_at'] or x['revision'] != item['revision'] or type(x['delta']) is not int or not 0 <= item['value'] + x['delta'] <= item['limit_value']:
        return {'decision': 'control_change_denied'}
    if one(db, 'SELECT 1 FROM control_changes WHERE id=?', (key,)):
        return {'decision': 'control_change_denied'}
    after = item['value'] + x['delta']
    db.execute('UPDATE control_objects SET revision=revision+1, value=? WHERE id=?', (after, x['object']))
    db.execute('UPDATE maintenance_approvals SET used=? WHERE id=?', (key, x['permit']))
    db.execute('INSERT INTO control_changes VALUES(?,?,?,?,?,?,?,?)', (key, x['object'], x['operator'], x['permit'], x['at'], item['revision'], item['value'], after))
    return {'decision': 'control_changed', 'revision': item['revision']+1, 'value': after}


def run(db, command):
    return act(db, 'controls', command, handle)
