import json
from pathlib import Path
from contextlib import closing
import tempfile
import unittest

from auditcourt import capture, feed, followup
from auditcourt.store import connect, replay


class FollowupFeedTest(unittest.TestCase):
    def test_receive_changes_feed_and_review_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'audit.sqlite'
            with closing(connect(path)) as db:
                handlers = {'capture': capture.run, 'feed': feed.run, 'followup': followup.run}
                cmds = json.loads(Path('fixtures/followup_feed.json').read_text(encoding='utf-8'))
                results = [handlers[c['subsystem']](db,c) for c in cmds]
            self.assertEqual(results[2], {'decision':'feed_empty'})
            self.assertEqual(results[4]['events'], ['e1'])
            self.assertEqual(results[7], {'decision':'followup_closed','response':'e2'})
            self.assertEqual(results[8]['decision'], 'feed_ack_pending')
            self.assertEqual(results[10]['events'], ['e2'])
            self.assertTrue(replay(path)['verified'])
