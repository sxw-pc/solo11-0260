import json
import tempfile
import unittest
from pathlib import Path

from auditcourt import capture, alarmgate, trialtrace
from auditcourt.store import connect, replay


class AlarmTrial(unittest.TestCase):
    def test_local_business_decision_and_replay(self):
        event_path = Path(__file__).resolve().parents[1] / 'fixtures/alarmtrial_local.json'
        events = json.loads(event_path.read_text(encoding='utf-8'))
        modules = {module.__name__.rsplit('.', 1)[1]: module for module in
                   (capture, alarmgate, trialtrace)}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'case.sqlite'
            db = connect(path)
            try:
                got = [modules[event['subsystem']].run(db, event) for event in events]
            finally:
                db.close()
            for index, decision in {3: 'trial_pending', 5: 'trial_recorded', 6: 'trial_passed', 8: 'trial_recorded', 10: 'trial_recorded', 11: 'trial_passed', 12: 'trial_pending'}.items():
                self.assertEqual(got[index]['decision'], decision, got[index])
            self.assertEqual(replay(path), {'events': len(events), 'verified': True, 'differences': []})
