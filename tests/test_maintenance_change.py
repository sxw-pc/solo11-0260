from contextlib import closing
import json
from pathlib import Path
import tempfile
import unittest

from auditcourt import capture, controls, maintenance
from auditcourt.store import connect, replay


class MaintenanceTest(unittest.TestCase):
    def test_audited_approval_controls_execution_and_receipt(self):
        commands = json.loads(Path('fixtures/maintenance_change.json').read_text())
        handlers = {'capture': capture.run, 'controls': controls.run, 'maintenance': maintenance.run}
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / 'change.sqlite'
            with closing(connect(database)) as db:
                outcomes = [handlers[x['subsystem']](db,x) for x in commands]
            self.assertEqual([outcomes[i]['decision'] for i in (1,4,5,6,7,8)], [
                'control_not_authorized','maintenance_approved','maintenance_outcome_denied',
                'control_changed','maintenance_verified','control_not_authorized'])
            self.assertEqual(outcomes[7]['value'], 4)
            self.assertTrue(replay(database)['verified'])
