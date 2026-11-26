import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from auditcourt import placard, reader
from auditcourt.store import connect, many, replay


class PlacardReadbackTests(unittest.TestCase):
    def test_actual_receipts_depend_on_active_wired_label(self):
        commands = json.loads(Path('fixtures/placard_readback.json').read_text(encoding='utf-8'))
        handlers = {'placard': placard.run, 'reader': reader.run}
        with TemporaryDirectory() as directory:
            path = str(Path(directory) / 'local.sqlite')
            db = connect(path)
            results = [handlers[command['subsystem']](db, command) for command in commands]
            self.assertEqual([results[i]['decision'] for i in (0, 2, 7, 9)],
                ['instruction_unknown', 'instruction_released', 'instruction_unknown', 'instruction_unknown'])
            self.assertEqual([results[i]['action'] for i in (2, 5, 6)],
                ['close-test-feed', 'stop-test-intake', 'isolate-test-bank'])
            self.assertEqual(len(many(db, 'SELECT id FROM instruction_receipts')), 3)
            db.close()
            self.assertEqual(replay(path), {'events': 10, 'verified': True, 'differences': []})
