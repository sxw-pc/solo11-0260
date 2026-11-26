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
CREATE TABLE IF NOT EXISTS alarm_episodes (
    id TEXT PRIMARY KEY, batch TEXT NOT NULL, role TEXT NOT NULL, profile TEXT NOT NULL,
    trace TEXT NOT NULL, hazard_at INTEGER, evidence TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS alarm_gate_receipts (id TEXT PRIMARY KEY, batch TEXT NOT NULL, decision TEXT NOT NULL,
    summary TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,subsystem TEXT,event_id TEXT UNIQUE,payload TEXT,result TEXT);
'''
TABLES=['event_sources','audit_events','sequence_gaps','conflict_cases','evidence_chains','chain_members','sealing_receipts','relation_edges','retention_policies','legal_holds','disclosure_cases','cleanup_cases','alarm_episodes','alarm_gate_receipts']
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
    from . import capture,seal,hold,trialtrace,alarmgate
    a=connect(path);b=connect(':memory:');handlers={'capture':capture.run,'seal':seal.run,'hold':hold.run,'trialtrace':trialtrace.run,'alarmgate':alarmgate.run};bad=[];events=many(a,'SELECT * FROM events ORDER BY seq')
    for i,e in enumerate(events,1):
        got=handlers[e['subsystem']](b,json.loads(e['payload']))
        if got!=json.loads(e['result']):bad.append({'event':i})
    for table in TABLES:
        if [tuple(r) for r in a.execute('SELECT * FROM '+table+' ORDER BY rowid')]!=[tuple(r) for r in b.execute('SELECT * FROM '+table+' ORDER BY rowid')]:bad.append({'table':table})
    a.close();b.close();return {'events':len(events),'verified':not bad,'differences':bad}
