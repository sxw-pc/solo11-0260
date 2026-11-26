"""Issue immutable audit labels for local equipment isolation drills."""
from .store import act, many


def active(db, area):
    return many(db, "SELECT id,code,action FROM placards WHERE area=? AND state='active' ORDER BY id", (area,))


def handle(db, command):
    op, key = command['op'], command['id']
    if op == 'print':
        area, code, action = (command[name] for name in ('area', 'code', 'action'))
        if not area or not action or not isinstance(code, str) or len(code) != 3 or set(code) - set('01'):
            return {'decision': 'placard_invalid'}
        if any(row['code'] == code for row in active(db, area)):
            return {'decision': 'placard_code_busy'}
        inserted = db.execute('INSERT OR IGNORE INTO placards VALUES(?,?,?,?,?)', (key, area, code, action, 'active')).rowcount
        return {'decision': 'placard_printed' if inserted else 'placard_exists'}
    if op == 'retire':
        changed = db.execute("UPDATE placards SET state='retired' WHERE id=? AND state='active'", (key,)).rowcount
        return {'decision': 'placard_retired' if changed else 'placard_unavailable'}
    return {'decision': 'unknown_operation'}


def run(db, command):
    return act(db, 'placard', command, handle)
