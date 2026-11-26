import json
import tempfile
import unittest
from pathlib import Path

from auditcourt import capture, readcheck, readprobe
from auditcourt.store import connect, replay


class ReadCheck(unittest.TestCase):
    def test_local_business_decision_and_replay(self):
        event_path = Path(__file__).resolve().parents[1] / 'fixtures/readcheck_local.json'
        events = json.loads(event_path.read_text(encoding='utf-8'))
        modules = {module.__name__.rsplit('.', 1)[1]: module for module in
                   (capture, readcheck, readprobe)}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'case.sqlite'
            db = connect(path)
            try:
                got = [modules[event['subsystem']].run(db, event) for event in events]
            finally:
                db.close()
            for index, decision in {3: 'read_check_pending', 4: 'read_evidence_missing', 6: 'read_recorded', 7: 'read_check_passed', 8: 'read_check_pending', 9: 'read_check_passed'}.items():
                self.assertEqual(got[index]['decision'], decision, got[index])
            self.assertEqual(replay(path), {'events': len(events), 'verified': True, 'differences': []})
