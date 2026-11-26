"""Resolve an exact label at its wired reader and journal the actual instruction."""
from . import placard
from .store import act


def handle(db, command):
    if command['op'] != 'read':
        return {'decision': 'unknown_operation'}
    area, code = command['area'], command['code']
    match = next((label for label in placard.active(db, area) if label['code'] == code), None)
    if match is None:
        return {'decision': 'instruction_unknown'}
    inserted = db.execute('INSERT OR IGNORE INTO instruction_receipts VALUES(?,?,?)',
                          (command['id'], match['id'], match['action'])).rowcount
    if not inserted:
        return {'decision': 'instruction_conflict'}
    return {'decision': 'instruction_released', 'placard': match['id'], 'action': match['action']}


def run(db, command):
    return act(db, 'reader', command, handle)
