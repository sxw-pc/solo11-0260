import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from auditcourt import specimen, trial
from auditcourt.store import connect, replay


class SpecimenTrialTests(unittest.TestCase):
    def test_real_observation_and_probe_prerequisites(self):
        commands = json.loads(Path('fixtures/specimen_trial.json').read_text(encoding='utf-8'))
        handlers = {'specimen': specimen.run, 'trial': trial.run}
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'drill.sqlite'
            db = connect(path)
            results = [handlers[x['subsystem']](db, x) for x in commands]
            db.close()
            self.assertEqual([result['decision'] for result in results], [
                'trial_blocked', 'specimen_installed', 'trial_door_closed', 'trial_observed',
                'trial_observed', 'specimen_installed', 'trial_observed', 'trial_blocked',
            ])
            self.assertEqual([results[i]['output'] for i in (3,4,6)], [1,1,1])
            self.assertEqual(replay(path), {'events':8,'verified':True,'differences':[]})
