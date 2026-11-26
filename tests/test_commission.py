import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from auditcourt import capture, commission, controls, maintenance
from auditcourt.store import connect, one, replay


class CommissionTest(unittest.TestCase):
    def test_condition_tracks_actual_upstream_revision_and_commits_output(self):
        fixture = Path(__file__).resolve().parents[1] / 'fixtures' / 'commission_timeline.json'
        commands = json.loads(fixture.read_text(encoding='utf-8'))
        modules = {'capture': capture, 'commission': commission, 'controls': controls, 'maintenance': maintenance}
        with TemporaryDirectory() as root:
            path = Path(root) / 'commission.sqlite'
            db = connect(path)
            try:
                actual = [modules[x['subsystem']].run(db, x) for x in commands]
                self.assertEqual((actual[8]['branch'], actual[8]['value']), ('low', 3))
                self.assertEqual((actual[10]['branch'], actual[10]['value']), ('high', 6))
                self.assertEqual(actual[11], {'decision': 'maintenance_verified', 'value': 6})
                self.assertEqual(one(db, "SELECT input_revision FROM commission_runs WHERE id='late'")['input_revision'], 2)
                self.assertEqual(one(db, "SELECT value FROM control_objects WHERE id='y'")['value'], 6)
            finally:
                db.close()
            self.assertEqual(replay(path), {'events': 12, 'verified': True, 'differences': []})
