import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from auditcourt import routing, triage
from auditcourt.store import connect, many, replay


class RoutingTest(unittest.TestCase):
    def test_reordering_rules_changes_actual_duty_queue(self):
        fixture = Path(__file__).resolve().parents[1] / 'fixtures' / 'routing_precedence.json'
        commands = json.loads(fixture.read_text(encoding='utf-8'))
        modules = {'routing': routing, 'triage': triage}
        with TemporaryDirectory() as root:
            file = Path(root) / 'routing.sqlite'
            db = connect(file)
            try:
                results = [modules[x['subsystem']].run(db, x) for x in commands]
                self.assertEqual(results[0]['decision'], 'triage_unconfigured')
                self.assertEqual(results[2]['destination'], 'pager')
                self.assertEqual(results[4]['destination'], 'manual')
                self.assertEqual(results[5]['destination'], 'pager')
                self.assertEqual([ticket['version'] for ticket in many(db, 'SELECT * FROM routing_tickets ORDER BY rowid')], [1,2,2])
            finally:
                db.close()
            self.assertEqual(replay(file), {'events': 6, 'verified': True, 'differences': []})
