import json
from pathlib import Path
import tempfile
import unittest

from auditcourt import capture, coverage, custody, seal
from auditcourt.store import connect, one, replay


class CustodyCoverageTest(unittest.TestCase):
    def test_gap_arrival_changes_testimony_and_sealed_rating(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'audit.sqlite'
            db = connect(path)
            modules = {module.__name__.split('.')[-1]: module for module in (capture, coverage, custody, seal)}
            commands = json.loads(Path('fixtures/custody_coverage.json').read_text(encoding='utf-8'))
            decisions = [modules[item['subsystem']].run(db, item) for item in commands]
            self.assertEqual(decisions[2], {'decision': 'coverage_missing', 'missing': 1})
            self.assertEqual(decisions[3]['rating'], 'incomplete')
            self.assertEqual(decisions[5], {'decision': 'coverage_attested', 'observations': 2})
            self.assertEqual(decisions[6]['rating'], 'complete')
            chain = one(db, "SELECT digest FROM evidence_chains WHERE id='s2'")
            request = {'op': 'deposit', 'id': 'copy', 'event_id': 'copy', 'at': 6, 'digest': chain['digest'], 'chain': 's2', 'vault': 'v1'}
            self.assertEqual(custody.run(db, request)['decision'], 'copy_deposited')
            self.assertEqual(custody.run(db, {**request, 'id': 'extra', 'event_id': 'extra'})['decision'], 'vault_full')
            self.assertEqual(custody.run(db, {'op': 'inventory', 'id': 's2', 'event_id': 'inventory', 'at': 6})['copies'],
                             [{'id': 'copy', 'vault': 'v1', 'zone': 'north'}])
            db.close()
            self.assertTrue(replay(path)['verified'])
