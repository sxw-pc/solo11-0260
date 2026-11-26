"""Offline evidence-copy storage and custody handoff."""
from .store import act, many, one


def handle(db, command):
    operation = command['op']
    identity = command['id']
    at = command['at']
    if operation == 'vault':
        zone, capacity = command['zone'], command['capacity']
        if not zone or type(capacity) is not int or capacity < 1 or one(db, 'SELECT id FROM custody_vaults WHERE id=?', (identity,)):
            return {'decision': 'vault_denied'}
        db.execute('INSERT INTO custody_vaults VALUES(?,?,?)', (identity, zone, capacity))
        return {'decision': 'vault_opened'}
    if operation == 'deposit':
        chain = one(db, 'SELECT * FROM evidence_chains WHERE id=?', (command['chain'],))
        vault = one(db, 'SELECT * FROM custody_vaults WHERE id=?', (command['vault'],))
        if not chain or not vault or chain['sealed_at'] > at or chain['digest'] != command['digest']:
            return {'decision': 'deposit_denied'}
        if one(db, 'SELECT id FROM custody_copies WHERE id=?', (identity,)):
            return {'decision': 'deposit_denied'}
        used = one(db, "SELECT count(*) used FROM custody_copies WHERE vault=? AND state='stored'", (vault['id'],))['used']
        if used >= vault['capacity']:
            return {'decision': 'vault_full'}
        db.execute('INSERT INTO custody_copies VALUES(?,?,?,?,?,NULL)', (identity, chain['id'], vault['id'], 'stored', at))
        return {'decision': 'copy_deposited', 'zone': vault['zone']}
    if operation == 'release':
        copy = one(db, 'SELECT c.*, e.object_uid FROM custody_copies c JOIN evidence_chains e ON c.chain=e.id WHERE c.id=?', (identity,))
        if not copy or copy['state'] != 'stored' or at < copy['deposited']:
            return {'decision': 'copy_release_denied'}
        if one(db, "SELECT id FROM legal_holds WHERE object_uid=? AND state='active' AND expires>?", (copy['object_uid'], at)):
            return {'decision': 'copy_under_hold'}
        db.execute("UPDATE custody_copies SET state='released', released=? WHERE id=?", (at, identity))
        return {'decision': 'copy_released'}
    if operation == 'inventory':
        copies = many(db, "SELECT c.id, c.vault, v.zone FROM custody_copies c JOIN custody_vaults v ON c.vault=v.id WHERE c.chain=? AND c.state='stored' ORDER BY c.id", (identity,))
        return {'decision': 'custody_inventory', 'copies': copies}
    return {'decision': 'unknown_operation'}


def run(db, command):
    return act(db, 'custody', command, handle)
