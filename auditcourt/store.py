import json,sqlite3
from contextlib import contextmanager
SCHEMA='''
CREATE TABLE IF NOT EXISTS event_sources(id TEXT PRIMARY KEY,generation INTEGER,collector TEXT,state TEXT,max_seq INTEGER);
CREATE TABLE IF NOT EXISTS audit_events(id TEXT PRIMARY KEY,source TEXT,source_generation INTEGER,seq INTEGER,object_uid TEXT,request_id TEXT,parent_request TEXT,actor TEXT,at INTEGER,received_at INTEGER,digest TEXT,state TEXT,UNIQUE(source,source_generation,seq));
CREATE TABLE IF NOT EXISTS sequence_gaps(source TEXT,source_generation INTEGER,seq INTEGER,opened_at INTEGER,filled_at INTEGER,state TEXT,PRIMARY KEY(source,source_generation,seq));
CREATE TABLE IF NOT EXISTS conflict_cases(id TEXT PRIMARY KEY,source TEXT,source_generation INTEGER,seq INTEGER,old_digest TEXT,new_digest TEXT,opened_at INTEGER,resolved_at INTEGER,state TEXT,chosen_digest TEXT,arbitrator TEXT);
CREATE TABLE IF NOT EXISTS evidence_chains(id TEXT PRIMARY KEY,object_uid TEXT,version INTEGER,prior_id TEXT,digest TEXT,rating TEXT,sealed_at INTEGER);
CREATE TABLE IF NOT EXISTS chain_members(chain_id TEXT,event_id TEXT,PRIMARY KEY(chain_id,event_id));
CREATE TABLE IF NOT EXISTS sealing_receipts(id TEXT PRIMARY KEY,chain_id TEXT,member_count INTEGER,missing_count INTEGER,digest TEXT);
CREATE TABLE IF NOT EXISTS relation_edges(id TEXT PRIMARY KEY,child_event TEXT,parent_event TEXT,verified_at INTEGER,state TEXT);
CREATE TABLE IF NOT EXISTS retention_policies(id TEXT PRIMARY KEY,object_uid TEXT UNIQUE,expires INTEGER,generation INTEGER,state TEXT);
CREATE TABLE IF NOT EXISTS legal_holds(id TEXT PRIMARY KEY,object_uid TEXT,chain_id TEXT,actor TEXT,expires INTEGER,state TEXT);
CREATE TABLE IF NOT EXISTS disclosure_cases(id TEXT PRIMARY KEY,object_uid TEXT,chain_id TEXT,requester TEXT,scope TEXT,decision TEXT,at INTEGER);
CREATE TABLE IF NOT EXISTS cleanup_cases(id TEXT PRIMARY KEY,object_uid TEXT,decision TEXT,at INTEGER,reason TEXT);
CREATE TABLE IF NOT EXISTS custody_vaults(id TEXT PRIMARY KEY, zone TEXT NOT NULL, capacity INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS custody_copies(id TEXT PRIMARY KEY, chain TEXT NOT NULL, vault TEXT NOT NULL, state TEXT NOT NULL, deposited INTEGER NOT NULL, released INTEGER);
CREATE TABLE IF NOT EXISTS coverage_attestations(id TEXT PRIMARY KEY, source TEXT NOT NULL, generation INTEGER NOT NULL, collector TEXT NOT NULL, first INTEGER NOT NULL, last INTEGER NOT NULL, issued INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS followup_tickets(id TEXT PRIMARY KEY, evidence TEXT NOT NULL, reviewer TEXT NOT NULL, opened INTEGER NOT NULL, state TEXT NOT NULL, response TEXT, closed INTEGER);
CREATE TABLE IF NOT EXISTS evidence_feeds(id TEXT PRIMARY KEY, object_uid TEXT NOT NULL, cursor INTEGER NOT NULL, pending TEXT);
CREATE TABLE IF NOT EXISTS evidence_feed_batches(id TEXT PRIMARY KEY, feed TEXT NOT NULL, last_row INTEGER NOT NULL, acknowledged TEXT);
CREATE TABLE IF NOT EXISTS control_objects(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, value INTEGER NOT NULL, limit_value INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS maintenance_approvals(id TEXT PRIMARY KEY, object TEXT NOT NULL, operator TEXT NOT NULL, evidence TEXT NOT NULL, at INTEGER NOT NULL, until_at INTEGER NOT NULL, used TEXT);
CREATE TABLE IF NOT EXISTS control_changes(id TEXT PRIMARY KEY, object TEXT NOT NULL, operator TEXT NOT NULL, permit TEXT NOT NULL, at INTEGER NOT NULL, revision INTEGER NOT NULL, before_value INTEGER NOT NULL, after_value INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS maintenance_outcomes(id TEXT PRIMARY KEY, change_id TEXT NOT NULL UNIQUE, inspector TEXT NOT NULL, at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS routing_versions(scope TEXT NOT NULL, version INTEGER NOT NULL, rules TEXT NOT NULL, PRIMARY KEY(scope,version));
CREATE TABLE IF NOT EXISTS routing_tickets(id TEXT PRIMARY KEY, scope TEXT NOT NULL, version INTEGER NOT NULL, site TEXT NOT NULL, severity TEXT NOT NULL, signal TEXT NOT NULL, destination TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,subsystem TEXT,event_id TEXT UNIQUE,payload TEXT,result TEXT);
'''
TABLES=['event_sources','audit_events','sequence_gaps','conflict_cases','evidence_chains','chain_members','sealing_receipts','relation_edges','retention_policies','legal_holds','disclosure_cases','cleanup_cases','custody_vaults','custody_copies','coverage_attestations','followup_tickets','evidence_feeds','evidence_feed_batches','control_objects','maintenance_approvals','control_changes','maintenance_outcomes','routing_versions','routing_tickets']
def connect(path):
    db=sqlite3.connect(path,isolation_level=None);db.row_factory=sqlite3.Row;db.execute('PRAGMA busy_timeout=5000');db.executescript(SCHEMA);return db
def one(db,sql,args=()):
    row=db.execute(sql,args).fetchone();return dict(row) if row else None
def many(db,sql,args=()):return [dict(row) for row in db.execute(sql,args)]
@contextmanager
def tx(db):
    db.execute('BEGIN IMMEDIATE')
    try:yield;db.execute('COMMIT')
    except Exception:db.execute('ROLLBACK');raise
def act(db,sub,x,handler):
    body=json.dumps(x,sort_keys=True,ensure_ascii=False)
    with tx(db):
        old=one(db,'SELECT * FROM events WHERE event_id=?',(x['event_id'],))
        if old:return json.loads(old['result']) if old['payload']==body else {'decision':'event_identity_conflict'}
        result=handler(db,x)
        db.execute('INSERT INTO events(subsystem,event_id,payload,result) VALUES(?,?,?,?)',(sub,x['event_id'],body,json.dumps(result,sort_keys=True,ensure_ascii=False)))
        return result
def replay(path):
    from . import capture,seal,hold,custody,coverage,feed,followup,controls,maintenance,routing,triage
    a=connect(path);b=connect(':memory:');handlers={'capture':capture.run,'seal':seal.run,'hold':hold.run,'custody':custody.run,'coverage':coverage.run,'feed':feed.run,'followup':followup.run,'controls':controls.run,'maintenance':maintenance.run,'routing':routing.run,'triage':triage.run};bad=[];events=many(a,'SELECT * FROM events ORDER BY seq')
    for i,e in enumerate(events,1):
        got=handlers[e['subsystem']](b,json.loads(e['payload']))
        if got!=json.loads(e['result']):bad.append({'event':i})
    for table in TABLES:
        if [tuple(r) for r in a.execute('SELECT * FROM '+table+' ORDER BY rowid')]!=[tuple(r) for r in b.execute('SELECT * FROM '+table+' ORDER BY rowid')]:bad.append({'table':table})
    a.close();b.close();return {'events':len(events),'verified':not bad,'differences':bad}
