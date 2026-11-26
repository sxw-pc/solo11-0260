import hashlib,json
from .store import act,one,many
def chain_digest(events,prior):
    body=[(e['id'],e['digest'],e['source'],e['source_generation'],e['seq']) for e in events]
    return hashlib.sha256(json.dumps([prior,body],sort_keys=True).encode()).hexdigest()
def handle(db,x):
    op=x['op']
    if op=='link':
        child=one(db,'SELECT * FROM audit_events WHERE id=?',(x['child'],))
        parent=one(db,'SELECT * FROM audit_events WHERE id=?',(x['parent'],))
        if not child or not parent or child['parent_request']!=parent['request_id'] or child['at']<parent['at'] or x['at']<max(child['received_at'],parent['received_at']):
            return {'decision':'unproven_relation'}
        db.execute('INSERT INTO relation_edges VALUES(?,?,?,?,?)',(x['id'],child['id'],parent['id'],x['at'],'verified'))
        return {'decision':'relation_verified'}
    if op=='seal':
        events=many(db,"SELECT * FROM audit_events WHERE object_uid=? AND state='accepted' AND received_at<=? ORDER BY at,source,source_generation,seq",(x['object_uid'],x['at']))
        if not events:return {'decision':'no_evidence'}
        last=one(db,'SELECT * FROM evidence_chains WHERE object_uid=? ORDER BY version DESC LIMIT 1',(x['object_uid'],))
        if x['version']!=(last['version']+1 if last else 1) or x.get('prior')!=(last['id'] if last else None) or (last and x['at']<=last['sealed_at']):
            return {'decision':'wrong_chain_parent'}
        missing_set=set();conflict_set=set();unlinked=0
        for e in events:
            for gap in many(db,"SELECT seq FROM sequence_gaps WHERE source=? AND source_generation=? AND seq<=? AND opened_at<=? AND (filled_at IS NULL OR filled_at>?)",(e['source'],e['source_generation'],e['seq'],x['at'],x['at'])):
                missing_set.add((e['source'],e['source_generation'],gap['seq']))
            for conflict in many(db,"SELECT id FROM conflict_cases WHERE source=? AND source_generation=? AND seq=? AND opened_at<=? AND (resolved_at IS NULL OR resolved_at>?)",(e['source'],e['source_generation'],e['seq'],x['at'],x['at'])):
                conflict_set.add(conflict['id'])
            if e['parent_request'] and not one(db,"SELECT 1 FROM relation_edges WHERE child_event=? AND state='verified' AND verified_at<=?",(e['id'],x['at'])):
                unlinked+=1
        missing=len(missing_set)
        rating='conflicted' if conflict_set else 'incomplete' if missing or unlinked else 'complete'
        digest=chain_digest(events,last['digest'] if last else None)
        if last and rating==last['rating']:
            prior_members=many(db,'SELECT event_id FROM chain_members WHERE chain_id=?',(last['id'],))
            if {m['event_id'] for m in prior_members}=={e['id'] for e in events}:
                return {'decision':'no_new_evidence'}
        db.execute('INSERT INTO evidence_chains VALUES(?,?,?,?,?,?,?)',(x['id'],x['object_uid'],x['version'],x.get('prior'),digest,rating,x['at']))
        db.executemany('INSERT INTO chain_members VALUES(?,?)',[(x['id'],e['id']) for e in events])
        db.execute('INSERT INTO sealing_receipts VALUES(?,?,?,?,?)',(x['receipt'],x['id'],len(events),missing+unlinked,digest))
        return {'decision':'sealed','rating':rating,'members':len(events),'missing':missing+unlinked}
    if op=='verify':
        chain=one(db,'SELECT * FROM evidence_chains WHERE id=?',(x['id'],))
        receipt=one(db,'SELECT * FROM sealing_receipts WHERE chain_id=?',(x['id'],))
        if not chain or not receipt:return {'decision':'unsealed'}
        members=many(db,'SELECT e.* FROM chain_members m JOIN audit_events e ON e.id=m.event_id WHERE m.chain_id=? ORDER BY e.at,e.source,e.source_generation,e.seq',(x['id'],))
        prior=one(db,'SELECT * FROM evidence_chains WHERE id=?',(chain['prior_id'],)) if chain['prior_id'] else None
        digest=chain_digest(members,prior['digest'] if prior else None)
        return {'decision':'verified' if digest==chain['digest']==receipt['digest'] and len(members)==receipt['member_count'] else 'tampered'}
    return {'decision':'unknown_operation'}
def run(db,x):return act(db,'seal',x,handle)
