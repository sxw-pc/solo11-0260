import json,tempfile,unittest
from pathlib import Path
import auditcourt
from auditcourt import capture,seal,hold
from auditcourt.store import connect,one,replay
ROOT=Path(__file__).resolve().parents[1]
MODULES={'capture':capture,'seal':seal,'hold':hold}
def fixture(db,name,module):return [MODULES[x.get('subsystem',module)].run(db,x) for x in json.loads((ROOT/'fixtures'/name).read_text(encoding='utf8'))]
class AuditBusiness(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'db.sqlite';self.db=connect(self.path)
    def tearDown(self):self.db.close();self.tmp.cleanup()
    def captured(self):fixture(self.db,'capture_normal.json','capture')
    def sealed(self):self.captured();fixture(self.db,'seal_normal.json','seal')
    def base(self):self.sealed();fixture(self.db,'hold_normal.json','hold')
    def test_all_six_fixtures_and_replay(self):
        self.base()
        self.assertEqual(fixture(self.db,'capture_failure.json','capture')[0]['decision'],'gap_filled')
        self.assertEqual(fixture(self.db,'seal_failure.json','seal')[0]['rating'],'conflicted')
        end=fixture(self.db,'hold_failure.json','hold')
        self.assertEqual(end[1]['reason'],'source_conflict')
        self.assertEqual(end[3]['decision'],'cleanup_approved')
        self.assertTrue(replay(self.path)['verified'])
    def test_gap_backfill_creates_new_complete_version_without_rewriting_old(self):
        self.sealed()
        self.assertEqual(one(self.db,"SELECT rating FROM evidence_chains WHERE id='chain-1'")['rating'],'incomplete')
        capture.run(self.db,json.loads((ROOT/'fixtures'/'capture_failure.json').read_text(encoding='utf8'))[0])
        result=seal.run(self.db,{'op':'seal','event_id':'new-seal','id':'chain-2','object_uid':'object-a','version':2,'prior':'chain-1','receipt':'r2','at':30})
        self.assertEqual(result['rating'],'complete')
        self.assertEqual(one(self.db,"SELECT rating FROM evidence_chains WHERE id='chain-1'")['rating'],'incomplete')
        self.assertEqual(seal.run(self.db,{'op':'verify','event_id':'verify-old','id':'chain-1'})['decision'],'verified')
    def test_future_event_cannot_enter_earlier_seal_and_time_is_monotonic(self):
        self.captured()
        capture.run(self.db,{'op':'receive','event_id':'future','id':'future','source':'source-a','generation':1,'seq':5,'object_uid':'object-a','request_id':'future','actor':'operator','at':30,'digest':'future-digest'})
        self.assertEqual(seal.run(self.db,{'op':'seal','event_id':'early','id':'early','object_uid':'object-a','version':1,'prior':None,'receipt':'early-r','at':20})['members'],2)
        self.assertIsNone(one(self.db,"SELECT * FROM chain_members WHERE chain_id='early' AND event_id='future'"))
        self.assertEqual(seal.run(self.db,{'op':'seal','event_id':'backdated','id':'backdated','object_uid':'object-a','version':2,'prior':'early','receipt':'backdated-r','at':19})['decision'],'wrong_chain_parent')
        self.assertEqual(seal.run(self.db,{'op':'seal','event_id':'later','id':'later','object_uid':'object-a','version':2,'prior':'early','receipt':'later-r','at':31})['members'],3)
    def test_late_backfill_does_not_retroactively_enter_earlier_seal(self):
        self.captured()
        late=json.loads((ROOT/'fixtures'/'capture_failure.json').read_text(encoding='utf8'))[0]
        capture.run(self.db,late)
        first=seal.run(self.db,{'op':'seal','event_id':'first','id':'first','object_uid':'object-a','version':1,'prior':None,'receipt':'r1','at':20})
        self.assertEqual((first['members'],first['rating'],first['missing']),(2,'incomplete',1))
        second=seal.run(self.db,{'op':'seal','event_id':'second','id':'second','object_uid':'object-a','version':2,'prior':'first','receipt':'r2','at':30})
        self.assertEqual((second['members'],second['rating']),(3,'complete'))
    def test_one_source_gap_counted_once_across_members(self):
        self.captured()
        capture.run(self.db,{'op':'receive','event_id':'event-5','id':'event-5','source':'source-a','generation':1,'seq':5,'object_uid':'object-a','request_id':'request-5','actor':'operator','at':14,'digest':'digest-5'})
        result=seal.run(self.db,{'op':'seal','event_id':'s','id':'chain','object_uid':'object-a','version':1,'prior':None,'receipt':'r','at':20})
        self.assertEqual(result['missing'],1)
    def test_same_source_sequence_conflict_preserves_original(self):
        self.captured()
        same={'op':'receive','event_id':'same','id':'same','source':'source-a','generation':1,'seq':3,'object_uid':'object-a','request_id':'request-3','actor':'operator','at':12,'digest':'digest-3'}
        self.assertEqual(capture.run(self.db,same)['decision'],'event_reused')
        self.assertEqual(capture.run(self.db,dict(same,event_id='different',id='different',digest='forged'))['decision'],'event_conflict')
        self.assertEqual(one(self.db,"SELECT digest FROM audit_events WHERE id='event-3'")['digest'],'digest-3')
    def test_conflict_resolution_requires_existing_digest_and_arbitrator(self):
        self.captured()
        cmd={'op':'receive','event_id':'conflict','id':'conflict','source':'source-a','generation':1,'seq':3,'object_uid':'object-a','request_id':'request-3','actor':'operator','at':12,'digest':'forged'}
        capture.run(self.db,cmd)
        self.assertEqual(capture.run(self.db,{'op':'resolve_conflict','event_id':'bad','id':'conflict','chosen_digest':'invented','arbitrator':'auditor','at':20})['decision'],'resolution_denied')
        self.assertEqual(capture.run(self.db,{'op':'resolve_conflict','event_id':'new','id':'conflict','chosen_digest':'forged','arbitrator':'auditor','at':20})['decision'],'replacement_not_materialized')
        self.assertEqual(one(self.db,"SELECT state FROM conflict_cases WHERE id='conflict'")['state'],'open')
        self.assertEqual(capture.run(self.db,{'op':'resolve_conflict','event_id':'good','id':'conflict','chosen_digest':'digest-3','arbitrator':'auditor','at':20})['decision'],'conflict_resolved')
    def test_unmaterialized_replacement_cannot_be_sealed_or_disclosed_as_complete(self):
        self.captured()
        capture.run(self.db,{'op':'receive','event_id':'conflict','id':'conflict','source':'source-a','generation':1,'seq':3,'object_uid':'object-a','request_id':'request-3','actor':'operator','at':12,'received_at':19,'digest':'new-digest'})
        self.assertEqual(capture.run(self.db,{'op':'resolve_conflict','event_id':'new-choice','id':'conflict','chosen_digest':'new-digest','arbitrator':'auditor','at':20})['decision'],'replacement_not_materialized')
        result=seal.run(self.db,{'op':'seal','event_id':'seal-conflict','id':'chain','object_uid':'object-a','version':1,'prior':None,'receipt':'r','at':21})
        self.assertEqual(result['rating'],'conflicted')
        hold.run(self.db,{'op':'hold','event_id':'hold','id':'hold','object_uid':'object-a','chain':'chain','actor':'investigator','expires':50,'at':22})
        self.assertEqual(hold.run(self.db,{'op':'disclose','event_id':'full','id':'full','object_uid':'object-a','chain':'chain','requester':'investigator','scope':'full','at':23})['decision'],'chain_not_complete')
    def test_cross_object_relation_needs_actual_parent_request(self):
        self.captured()
        self.assertEqual(seal.run(self.db,{'op':'link','event_id':'bad-link','id':'bad-link','child':'event-4','parent':'event-1','at':14})['decision'],'unproven_relation')
        self.assertEqual(seal.run(self.db,{'op':'link','event_id':'good-link','id':'good-link','child':'event-4','parent':'event-3','at':14})['decision'],'relation_verified')
    def test_hold_prevents_cleanup_after_retention_expires(self):
        self.base()
        self.assertEqual(one(self.db,"SELECT reason FROM cleanup_cases WHERE id='clean-55'")['reason'],'legal_hold')
    def test_disclosure_bound_to_exact_chain_and_incomplete_rating(self):
        self.base()
        self.assertEqual(one(self.db,"SELECT chain_id FROM disclosure_cases WHERE id='disclose-summary'")['chain_id'],'chain-1')
        self.assertIsNone(one(self.db,"SELECT * FROM disclosure_cases WHERE id='disclose-full'"))
        self.assertEqual(hold.run(self.db,{'op':'disclose','event_id':'other','id':'other','object_uid':'object-a','chain':'chain-1','requester':'other','scope':'summary','at':30})['decision'],'disclosure_denied')
    def test_release_requires_hold_actor(self):
        self.base()
        self.assertEqual(hold.run(self.db,{'op':'release','event_id':'wrong','id':'hold-1','actor':'other'})['decision'],'release_denied')
    def test_source_generation_prevents_late_old_collector(self):
        self.captured()
        capture.run(self.db,{'op':'source','event_id':'new-source','id':'source-a','generation':2,'collector':'new-collector'})
        old={'op':'receive','event_id':'old','id':'old','source':'source-a','generation':1,'seq':5,'object_uid':'object-a','request_id':'r5','actor':'op','at':15,'digest':'d5'}
        self.assertEqual(capture.run(self.db,old)['decision'],'source_unavailable')
    def test_module_source(self):self.assertEqual(Path(auditcourt.__file__).resolve().parents[1],ROOT)
print('module_file',auditcourt.__file__)
