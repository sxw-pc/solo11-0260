"""Synthetic case O: withdrawal tickets, read tests, watch duties and slot return."""
import json
import tempfile
import unittest
from pathlib import Path

from auditcourt import custody, hold
from auditcourt.store import connect, many, one, replay

ROOT = Path(__file__).resolve().parents[1]

B1_DIGEST = '17e2d93442613f26343fe717b1ae604ea541d802ee10fe440c525984a41a2969'
B2_DIGEST = 'b77f079c2edb1e9637e6f684738830939f9d3fb988bcd4fd6d51a3fc85672d45'
C1_DIGEST = 'd608f82e0d6ac1f4f224005110b191187b24df16d193c7ba3354a83b83ea8bbe'


def build_case(kind, watch_starts=12, watch_expires=17, deposit_bw=False,
               window_end=16, request_at=12, second_request=False, north_capacity=3):
    """Both signed records begin from the same case and the same inventory."""
    commands = [
        # --- case O: B1 sealed incomplete, late backfill, B2 sealed complete ---
        {'subsystem': 'capture', 'op': 'source', 'event_id': 'src1', 'id': 's1', 'generation': 1, 'collector': 'col1'},
        {'subsystem': 'capture', 'op': 'receive', 'event_id': 'e1', 'id': 'e1', 'source': 's1', 'generation': 1, 'seq': 1, 'object_uid': 'O', 'request_id': 'q1', 'actor': 'ops', 'at': 1, 'digest': 'd1'},
        {'subsystem': 'capture', 'op': 'receive', 'event_id': 'e2', 'id': 'e2', 'source': 's1', 'generation': 1, 'seq': 2, 'object_uid': 'O', 'request_id': 'q2', 'actor': 'ops', 'at': 2, 'digest': 'd2'},
        {'subsystem': 'capture', 'op': 'receive', 'event_id': 'e4', 'id': 'e4', 'source': 's1', 'generation': 1, 'seq': 4, 'object_uid': 'O', 'request_id': 'q4', 'actor': 'ops', 'at': 4, 'digest': 'd4'},
        {'subsystem': 'seal', 'op': 'seal', 'event_id': 'b1', 'id': 'B1', 'object_uid': 'O', 'version': 1, 'prior': None, 'receipt': 'rb1', 'at': 5},
        {'subsystem': 'capture', 'op': 'receive', 'event_id': 'e3', 'id': 'e3', 'source': 's1', 'generation': 1, 'seq': 3, 'object_uid': 'O', 'request_id': 'q3', 'actor': 'ops', 'at': 3, 'received_at': 6, 'digest': 'd3'},
        {'subsystem': 'seal', 'op': 'seal', 'event_id': 'b2', 'id': 'B2', 'object_uid': 'O', 'version': 2, 'prior': 'B1', 'receipt': 'rb2', 'at': 7},
        # --- another object O2, used to prove cross-object copies do not back up O ---
        {'subsystem': 'capture', 'op': 'source', 'event_id': 'src2', 'id': 's2', 'generation': 1, 'collector': 'col2'},
        {'subsystem': 'capture', 'op': 'receive', 'event_id': 'g1', 'id': 'g1', 'source': 's2', 'generation': 1, 'seq': 1, 'object_uid': 'O2', 'request_id': 'z1', 'actor': 'ops', 'at': 2, 'digest': 'x1'},
        {'subsystem': 'seal', 'op': 'seal', 'event_id': 'c1', 'id': 'C1', 'object_uid': 'O2', 'version': 1, 'prior': None, 'receipt': 'rc1', 'at': 7},
        # --- synthetic legal hold on the actual chain version B2 ---
        {'subsystem': 'hold', 'op': 'hold', 'event_id': 'hold-b2', 'id': 'hold-b2', 'object_uid': 'O', 'chain': 'B2', 'actor': 'investigator', 'expires': 40, 'at': 8},
        # --- vaults: north, east and west; separate zones are separate failure domains ---
        {'op': 'vault', 'event_id': 'vn', 'id': 'vn', 'zone': 'north', 'capacity': north_capacity, 'at': 8},
        {'op': 'vault', 'event_id': 've', 'id': 've', 'zone': 'east', 'capacity': 3, 'at': 8},
        {'op': 'vault', 'event_id': 'vw', 'id': 'vw', 'zone': 'west', 'capacity': 3, 'at': 8},
        # --- inventory: Bn and Be of B2 stored; old B1 kept as-is in Bo; same-vault slot N2; other object Xo ---
        {'op': 'deposit', 'event_id': 'dep-bn', 'id': 'Bn', 'chain': 'B2', 'vault': 'vn', 'digest': B2_DIGEST, 'at': 9},
        {'op': 'deposit', 'event_id': 'dep-be', 'id': 'Be', 'chain': 'B2', 'vault': 've', 'digest': B2_DIGEST, 'at': 9},
        {'op': 'deposit', 'event_id': 'dep-bo', 'id': 'Bo', 'chain': 'B1', 'vault': 'vw', 'digest': B1_DIGEST, 'at': 9},
        {'op': 'deposit', 'event_id': 'dep-n2', 'id': 'N2', 'chain': 'B2', 'vault': 'vn', 'digest': B2_DIGEST, 'at': 10},
        {'op': 'deposit', 'event_id': 'dep-xo', 'id': 'Xo', 'chain': 'C1', 'vault': 'vw', 'digest': C1_DIGEST, 'at': 10},
    ]
    if kind == 'forensic':
        commands += [
            {'op': 'watch', 'event_id': 'watch-f', 'id': 'wF', 'object_uid': 'O', 'chain': 'B2', 'kind': 'forensic', 'actor': 'forensic-watcher', 'starts': watch_starts, 'expires': watch_expires, 'at': 11},
        ]
    else:
        commands += [
            # cold custody needs custodian-lead approval
            {'op': 'watch', 'event_id': 'watch-c', 'id': 'wC', 'object_uid': 'O', 'chain': 'B2', 'kind': 'cold', 'actor': 'custodian', 'approver': 'custody-lead', 'starts': watch_starts, 'expires': watch_expires, 'at': 11},
        ]
    commands += [
        # read test earlier than the deposit must be refused
        {'op': 'read_test', 'event_id': 'rt-bn-early', 'id': 'Bn', 'copy': 'Bn', 'at': 8},
        # Be read-tested at 11 (after its deposit at 9)
        {'op': 'read_test', 'event_id': 'rt-be', 'id': 'Be', 'copy': 'Be', 'at': 11},
        # north vault is full: a planned ticket cannot offset current capacity
        {'op': 'deposit', 'event_id': 'dep-north-extra', 'id': 'N3', 'chain': 'B2', 'vault': 'vn', 'digest': B2_DIGEST, 'at': 11},
    ]
    if kind == 'cold':
        # independence checks: child/old version, another object, same-vault slot, missing backup
        commands += [
            {'op': 'withdraw', 'event_id': 'w-old-version', 'id': 'Bn', 'ticket': 't-old', 'backup': 'Bo', 'ends': window_end, 'at': 12},
            {'op': 'withdraw', 'event_id': 'w-other-object', 'id': 'Bn', 'ticket': 't-obj', 'backup': 'Xo', 'ends': window_end, 'at': 12},
            {'op': 'withdraw', 'event_id': 'w-same-vault', 'id': 'Bn', 'ticket': 't-same', 'backup': 'N2', 'ends': window_end, 'at': 12},
            {'op': 'withdraw', 'event_id': 'w-no-backup', 'id': 'Bn', 'ticket': 't-none', 'ends': window_end, 'at': 12},
        ]
    if deposit_bw:
        commands += [
            # Bw only promises to arrive at 14 and must ingest before it can help
            {'op': 'deposit', 'event_id': 'dep-bw', 'id': 'Bw', 'chain': 'B2', 'vault': 'vw', 'digest': B2_DIGEST, 'at': 14},
            {'op': 'read_test', 'event_id': 'rt-bw', 'id': 'Bw', 'copy': 'Bw', 'at': 14},
        ]
    commands += [
        {'op': 'withdraw', 'event_id': 'withdraw-bn', 'id': 'Bn', 'ticket': 'ticket-bn',
         'backup': 'Bw' if deposit_bw else 'Be', 'ends': window_end, 'at': request_at},
    ]
    if second_request:
        commands += [
            {'op': 'withdraw', 'event_id': 'withdraw-bn-again', 'id': 'Bn', 'ticket': 'ticket-bn-2', 'backup': 'Bw' if deposit_bw else 'Be', 'ends': window_end, 'at': request_at + 1},
        ]
    if kind == 'cold' and not second_request:
        # the approved cold path completes the withdrawal at 12 and restores north
        commands += [
            {'op': 'withdraw_complete', 'event_id': 'complete-bn', 'id': 'ticket-bn', 'at': 12},
            {'op': 'deposit', 'event_id': 'dep-restore', 'id': 'Bc', 'chain': 'B2', 'vault': 'vn', 'digest': B2_DIGEST, 'at': 13},
        ]
    return commands


def run_commands(db, commands):
    decisions = {}
    for item in commands:
        sub = item.get('subsystem', 'custody')
        module = {'custody': custody, 'hold': hold}[sub] if sub in ('custody', 'hold') else None
        if module is None:
            from auditcourt import capture, seal
            module = {'capture': capture, 'seal': seal}[sub]
        decisions[item['event_id']] = module.run(db, item)
    return decisions


class WithdrawalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'withdraw.sqlite'
        self.db = connect(self.path)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_forensic_record_holds_bn_until_new_domain_ingests_and_read_tests(self):
        decisions = run_commands(self.db, build_case('forensic'))
        # at 12 there is no pre-confirmed readback relay: Bn stays, no receipt
        self.assertEqual(decisions['withdraw-bn']['decision'], 'relay_not_established')
        self.assertEqual(one(self.db, "SELECT state FROM custody_copies WHERE id='Bn'")['state'], 'stored')
        self.assertIsNone(one(self.db, "SELECT * FROM withdrawal_tickets WHERE copy='Bn'"))
        # Be's read test is valid, but one domain alone cannot establish dual-domain relay
        self.assertEqual(decisions['rt-be']['decision'], 'read_test_valid')
        self.assertTrue(replay(self.path)['verified'])

    def test_forensic_relay_after_bw_ingest_locks_claims_and_returns_north_slot(self):
        decisions = run_commands(self.db, build_case('forensic', deposit_bw=True, request_at=14))
        issued = decisions['withdraw-bn']
        self.assertEqual(issued['decision'], 'withdrawal_issued')
        self.assertEqual(issued['zone'], 'north')
        self.assertEqual(issued['window'], [14, 16])
        self.assertEqual(set(issued['claimed']), {'Be', 'Bw'})
        # claimed copies cannot be released while the ticket is open
        self.assertEqual(custody.run(self.db, {'op': 'release', 'event_id': 'rel-be', 'id': 'Be', 'at': 14})['decision'],
                         'copy_claim_locked')
        # conflicting request on the same copy is refused
        self.assertEqual(custody.run(self.db, {'op': 'withdraw', 'event_id': 'w-conflict', 'id': 'Bn', 'ticket': 't2',
                                               'backup': 'Bw', 'ends': 16, 'at': 15})['decision'], 'withdraw_conflict')
        # complete the withdrawal: Bn leaves and the north slot is returned
        completed = custody.run(self.db, {'op': 'withdraw_complete', 'event_id': 'complete-bn', 'id': 'ticket-bn', 'at': 16})
        self.assertEqual(completed['decision'], 'withdrawal_completed')
        self.assertEqual(one(self.db, "SELECT state FROM custody_copies WHERE id='Bn'")['state'], 'released')
        self.assertEqual(one(self.db, "SELECT state FROM withdrawal_tickets WHERE id='ticket-bn'")['state'], 'completed')
        # north vault can re-ingest into the freed slot (only N2 remains stored)
        redeposit = custody.run(self.db, {'op': 'deposit', 'event_id': 'dep-bn2', 'id': 'Bn2', 'chain': 'B2',
                                          'vault': 'vn', 'digest': B2_DIGEST, 'at': 16})
        self.assertEqual(redeposit['decision'], 'copy_deposited')
        # after completion claims are gone, but the hold still blocks ordinary release
        self.assertEqual(custody.run(self.db, {'op': 'release', 'event_id': 'rel-be2', 'id': 'Be', 'at': 16})['decision'],
                         'copy_under_hold')
        inventory = custody.run(self.db, {'op': 'inventory', 'event_id': 'inv', 'id': 'B2', 'at': 17})['copies']
        self.assertEqual([c['id'] for c in inventory], ['Be', 'Bn2', 'Bw', 'N2', 'N3'])
        self.assertTrue(replay(self.path)['verified'])

    def test_cold_contract_withdraws_bn_at_12_and_restores_with_approved_cold_copy(self):
        decisions = run_commands(self.db, build_case('cold'))
        self.assertEqual(decisions['w-old-version']['decision'], 'backup_not_independent')
        self.assertEqual(decisions['w-other-object']['decision'], 'backup_not_independent')
        self.assertEqual(decisions['w-same-vault']['decision'], 'backup_not_independent')
        self.assertEqual(decisions['w-no-backup']['decision'], 'backup_not_independent')
        self.assertEqual(decisions['rt-bn-early']['decision'], 'read_test_before_deposit')
        # north has spare capacity here; the full-vault check lives in the dedicated test
        self.assertEqual(decisions['dep-north-extra']['decision'], 'copy_deposited')
        issued = decisions['withdraw-bn']
        self.assertEqual(issued['decision'], 'withdrawal_issued')
        self.assertEqual(issued['claimed'], ['Be'])
        # the record itself completes the ticket at 12 and restores the slot with Bc
        self.assertEqual(decisions['complete-bn']['decision'], 'withdrawal_completed')
        self.assertEqual(decisions['dep-restore']['decision'], 'copy_deposited')
        # after completion the claim is gone; the active hold still blocks ordinary release
        self.assertEqual(custody.run(self.db, {'op': 'release', 'event_id': 'rel-be-cold', 'id': 'Be', 'at': 12})['decision'],
                         'copy_under_hold')
        self.assertEqual(one(self.db, "SELECT state FROM custody_copies WHERE id='Bn'")['state'], 'released')
        self.assertEqual(one(self.db, "SELECT vault FROM custody_copies WHERE id='Bc'")['vault'], 'vn')
        self.assertTrue(replay(self.path)['verified'])

    def test_cold_contract_requires_approver(self):
        commands = build_case('cold')
        for item in commands:
            if item.get('id') == 'wC':
                item.pop('approver')
        decisions = run_commands(self.db, commands)
        self.assertEqual(decisions['watch-c']['decision'], 'watch_approval_required')

    def test_be_expiring_at_15_leaves_uncovered_window(self):
        decisions = run_commands(self.db, build_case('cold', watch_expires=15))
        self.assertEqual(decisions['withdraw-bn']['decision'], 'coverage_gap')
        self.assertEqual(one(self.db, "SELECT state FROM custody_copies WHERE id='Bn'")['state'], 'stored')

    def test_watch_pulled_to_13_does_not_cover_full_window(self):
        decisions = run_commands(self.db, build_case('cold', watch_expires=13))
        # cold request at 12: the watch reaches into the window but ends early -> gap
        self.assertEqual(decisions['withdraw-bn']['decision'], 'coverage_gap')
        with tempfile.TemporaryDirectory() as tmp:
            fdb = connect(Path(tmp) / 'forensic.sqlite')
            at12 = build_case('forensic', watch_expires=13, deposit_bw=True, request_at=12)
            # use the already read-tested Be so the decision reaches the window check
            for item in at12:
                if item.get('event_id') == 'withdraw-bn':
                    item['backup'] = 'Be'
            forensic = run_commands(fdb, at12)
            self.assertEqual(forensic['withdraw-bn']['decision'], 'coverage_gap')
            # requesting at 14, after the watch ended, leaves no applicable duty at all
            late = run_commands(connect(Path(tmp) / 'late.sqlite'),
                                build_case('forensic', watch_expires=13, deposit_bw=True, request_at=14))
            self.assertEqual(late['withdraw-bn']['decision'], 'no_custody_contract')
            self.assertTrue(replay(Path(tmp) / 'forensic.sqlite')['verified'])
            fdb.close()

    def test_unread_tested_backup_is_refused_even_under_hold(self):
        commands = build_case('forensic', deposit_bw=True, request_at=14)
        # remove Bw's read test: ingested but never verified
        commands = [c for c in commands if c.get('event_id') != 'rt-bw']
        decisions = run_commands(self.db, commands)
        self.assertEqual(decisions['withdraw-bn']['decision'], 'backup_not_read_tested')

    def test_no_watch_means_no_applicable_responsibility(self):
        commands = build_case('cold')
        commands = [c for c in commands if c.get('op') != 'watch']
        decisions = run_commands(self.db, commands)
        self.assertEqual(decisions['withdraw-bn']['decision'], 'no_custody_contract')

    def test_pending_ticket_cannot_offset_current_capacity(self):
        decisions = run_commands(self.db, build_case('cold', north_capacity=2))
        # north holds Bn and N2: the planned withdrawal ticket has not completed,
        # so its future slot is not available to a new deposit
        self.assertEqual(decisions['dep-north-extra']['decision'], 'vault_full')
        # once Bn actually leaves (the record completes the ticket), the slot returns
        self.assertEqual(decisions['withdraw-bn']['decision'], 'withdrawal_issued')
        self.assertEqual(decisions['complete-bn']['decision'], 'withdrawal_completed')
        # north now holds N2 plus the restoring cold copy Bc: exactly capacity 2 again
        stored = many(self.db, "SELECT id FROM custody_copies WHERE vault='vn' AND state='stored' ORDER BY id")
        self.assertEqual([row['id'] for row in stored], ['Bc', 'N2'])

    def test_fixture_files_match_builder_and_replay_on_empty_db(self):
        for name in ('withdraw_forensic.json', 'withdraw_cold.json'):
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'db.sqlite'
                db = connect(path)
                decisions = run_commands(db, json.loads((ROOT / 'fixtures' / name).read_text(encoding='utf8')))
                self.assertTrue(all(d['decision'] != 'unknown_operation' for d in decisions.values()))
                self.assertTrue(replay(path)['verified'])
                db.close()
