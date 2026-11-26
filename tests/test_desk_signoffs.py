import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from auditcourt import flags, signoff
from auditcourt.store import connect, many, replay


class DeskSignoffTest(unittest.TestCase):
    def test_shared_flags_change_the_second_actual_signoff(self):
        path = Path(__file__).resolve().parents[1] / 'fixtures' / 'desk_signoffs.json'
        entries = json.loads(path.read_text(encoding='utf-8'))
        modules = {'flags':flags, 'signoff':signoff}
        with TemporaryDirectory() as folder:
            db_path = Path(folder) / 'signoffs.db'
            db = connect(db_path)
            try:
                outcomes = [modules[c['subsystem']].run(db,c) for c in entries]
                self.assertEqual([x['decision'] for x in outcomes[6:]], ['signoff_recorded'] * 3 + ['signoff_denied'])
                self.assertEqual(outcomes[9]['observed'], 1)
                self.assertEqual([r['id'] for r in many(db,'SELECT id FROM desk_signoffs ORDER BY rowid')], ['east-review','west-review','comparison-first'])
            finally:
                db.close()
            self.assertEqual(replay(db_path), {'events':10,'verified':True,'differences':[]})
