"""Offline evidence-copy storage, watch duties, read tests and withdrawal tickets."""
from .store import act, many, one


def _chain(db, chain_id):
    return one(db, 'SELECT * FROM evidence_chains WHERE id=?', (chain_id,))


def _stored_copy(db, copy_id):
    return one(db, 'SELECT * FROM custody_copies WHERE id=? AND state=\'stored\'', (copy_id,))


def _valid_read_test(db, copy_id, at):
    """A read test is valid only when it is not earlier than the copy's deposit."""
    return one(
        db,
        "SELECT t.* FROM read_tests t JOIN custody_copies c ON c.id=t.copy "
        "WHERE t.copy=? AND t.state='valid' AND t.at<=? AND t.at>=c.deposited "
        "ORDER BY t.at DESC LIMIT 1",
        (copy_id, at),
    )


def _covering_watches(db, chain_id, starts, ends):
    """Watch duties whose responsibility window covers the whole withdrawal window."""
    return many(
        db,
        'SELECT * FROM custody_watches WHERE state=\'active\' AND chain=? AND starts<=? AND expires>=? ORDER BY id',
        (chain_id, starts, ends),
    )


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
        chain = _chain(db, command['chain'])
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
    if operation == 'watch':
        chain = _chain(db, command['chain'])
        kind = command.get('kind')
        starts, expires = command['starts'], command['expires']
        if not chain or chain['object_uid'] != command['object_uid']:
            return {'decision': 'watch_denied'}
        if kind not in ('forensic', 'cold') or not command.get('actor') or expires <= starts or starts < at:
            return {'decision': 'watch_denied'}
        # Cold custody contracts need an explicit custodian-lead approval.
        if kind == 'cold' and not command.get('approver'):
            return {'decision': 'watch_approval_required'}
        if one(db, 'SELECT id FROM custody_watches WHERE id=?', (identity,)):
            return {'decision': 'watch_identity_conflict'}
        db.execute('INSERT INTO custody_watches VALUES(?,?,?,?,?,?,?,?,?)',
                   (identity, chain['object_uid'], chain['id'], kind, command['actor'], starts, expires, 'active',
                    command.get('approver')))
        return {'decision': 'watch_active', 'kind': kind, 'chain': chain['id'], 'starts': starts, 'expires': expires}
    if operation == 'read_test':
        copy = one(db, 'SELECT * FROM custody_copies WHERE id=?', (identity,))
        if not copy or copy['state'] != 'stored':
            return {'decision': 'read_test_denied'}
        # Read-test time cannot predate the deposit (ingress receipt) of the copy.
        if at < copy['deposited']:
            return {'decision': 'read_test_before_deposit'}
        if one(db, 'SELECT id FROM read_tests WHERE id=?', (identity,)):
            return {'decision': 'read_test_identity_conflict'}
        db.execute('INSERT INTO read_tests VALUES(?,?,?,?,?)', (identity, copy['id'], copy['chain'], at, 'valid'))
        return {'decision': 'read_test_valid', 'copy': copy['id'], 'at': at}
    if operation == 'withdraw':
        target = one(
            db,
            'SELECT c.*, v.zone, e.object_uid FROM custody_copies c '
            'JOIN custody_vaults v ON v.id=c.vault JOIN evidence_chains e ON e.id=c.chain WHERE c.id=?',
            (identity,),
        )
        starts, ends = at, command['ends']
        if not target or target['state'] != 'stored' or at < target['deposited'] or ends <= starts:
            return {'decision': 'withdraw_denied'}
        if one(db, "SELECT id FROM withdrawal_tickets WHERE copy=? AND state='issued'", (identity,)):
            return {'decision': 'withdraw_conflict'}
        backup_id = command.get('backup')
        backup = _stored_copy(db, backup_id) if backup_id else None
        # Independence: same sealed chain version, another vault. Child versions,
        # copies of another object and a same-vault slot never count as backup.
        if not backup or backup['chain'] != target['chain'] or backup['vault'] == target['vault']:
            return {'decision': 'backup_not_independent'}
        # In-flight forensic duty needs an effective read test before withdrawal.
        if not _valid_read_test(db, backup_id, at):
            return {'decision': 'backup_not_read_tested'}
        active = many(db, "SELECT * FROM custody_watches WHERE state='active' AND chain=?", (target['chain'],))
        # Watch duties that reach into the window but do not cover all of it leave
        # an uncovered stretch: pending/late tickets cannot offset capacity.
        if any(w['starts'] <= ends and w['expires'] >= starts
               and not (w['starts'] <= starts and w['expires'] >= ends) for w in active):
            return {'decision': 'coverage_gap'}
        covering = _covering_watches(db, target['chain'], starts, ends)
        if not covering:
            return {'decision': 'no_custody_contract'}
        kinds = {w['kind'] for w in covering}
        if 'forensic' in kinds:
            # Dual failure-domain continuous readback. After this copy leaves, the
            # remaining independent, read-tested copies must span two failure
            # domains over the whole window. A copy in the same domain or one that
            # has not ingested and read-tested yet cannot establish the relay.
            domains = set()
            for survivor in many(
                db,
                "SELECT c.*, v.zone FROM custody_copies c JOIN custody_vaults v ON v.id=c.vault "
                "WHERE c.chain=? AND c.state='stored' AND c.id<>? ORDER BY c.id",
                (target['chain'], identity),
            ):
                if survivor['vault'] != target['vault'] and _valid_read_test(db, survivor['id'], at):
                    domains.add(survivor['zone'])
            if len(domains) < 2:
                return {'decision': 'relay_not_established'}
            contract = next(w['id'] for w in covering if w['kind'] == 'forensic')
        else:
            cold = next((w for w in covering if w['kind'] == 'cold'), None)
            if not cold:
                return {'decision': 'no_custody_contract'}
            contract = cold['id']
        # Every surviving independent copy carrying watch duty over the window is
        # claimed: its read test is locked until this withdrawal completes.
        claimed = [
            row['id']
            for row in many(
                db,
                "SELECT c.id FROM custody_copies c JOIN custody_vaults v ON v.id=c.vault "
                "WHERE c.chain=? AND c.state='stored' AND c.id<>? AND c.vault<>? ORDER BY c.id",
                (target['chain'], identity, target['vault']),
            )
            if _valid_read_test(db, row['id'], at)
        ]
        db.execute('INSERT INTO withdrawal_tickets VALUES(?,?,?,?,?,?,?,?,?,?)',
                   (command['ticket'], identity, target['chain'], target['vault'], starts, ends, contract,
                    'issued', at, None))
        db.executemany('INSERT INTO read_test_claims VALUES(?,?)', [(command['ticket'], cid) for cid in claimed])
        return {'decision': 'withdrawal_issued', 'ticket': command['ticket'], 'contract': contract,
                'zone': target['zone'], 'window': [starts, ends], 'claimed': claimed}
    if operation == 'withdraw_complete':
        ticket = one(db, 'SELECT * FROM withdrawal_tickets WHERE id=?', (identity,))
        if not ticket or ticket['state'] != 'issued' or at < ticket['starts']:
            return {'decision': 'withdraw_complete_denied'}
        copy = one(db, 'SELECT * FROM custody_copies WHERE id=?', (ticket['copy'],))
        if not copy or copy['state'] != 'stored':
            return {'decision': 'withdraw_complete_denied'}
        db.execute("UPDATE custody_copies SET state='released', released=? WHERE id=?", (at, copy['id']))
        db.execute("UPDATE withdrawal_tickets SET state='completed', completed_at=? WHERE id=?", (at, identity))
        return {'decision': 'withdrawal_completed', 'ticket': identity, 'copy': copy['id'],
                'vault': ticket['vault'], 'released_at': at}
    if operation == 'release':
        copy = one(db, 'SELECT * FROM custody_copies c JOIN evidence_chains e ON c.chain=e.id WHERE c.id=?', (identity,))
        if not copy or copy['state'] != 'stored' or at < copy['deposited']:
            return {'decision': 'copy_release_denied'}
        claimed = one(
            db,
            "SELECT 1 FROM read_test_claims r JOIN withdrawal_tickets t ON t.id=r.ticket "
            "WHERE r.copy=? AND t.state='issued'",
            (identity,),
        )
        if claimed:
            return {'decision': 'copy_claim_locked'}
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
