from .store import act,one
def handle(db,x):
    op=x['op']
    if op=='source':
        old=one(db,'SELECT * FROM event_sources WHERE id=?',(x['id'],))
        if old and x['generation']<=old['generation']:return {'decision':'stale_source'}
        if not x.get('collector'):return {'decision':'invalid_collector'}
        db.execute('INSERT INTO event_sources VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET generation=excluded.generation,collector=excluded.collector,state=excluded.state,max_seq=excluded.max_seq',(x['id'],x['generation'],x['collector'],'active',0))
        return {'decision':'source_active'}
    if op=='receive':
        received=x.get('received_at',x['at'])
        if received<x['at']:return {'decision':'received_before_event'}
        s=one(db,'SELECT * FROM event_sources WHERE id=?',(x['source'],))
        if not s or s['state']!='active' or s['generation']!=x['generation'] or x['seq']<1 or not x['digest'] or not x['object_uid']:
            return {'decision':'source_unavailable'}
        prior=one(db,'SELECT * FROM audit_events WHERE source=? AND source_generation=? AND seq=?',(x['source'],x['generation'],x['seq']))
        if prior:
            if prior['digest']==x['digest'] and prior['object_uid']==x['object_uid']:
                return {'decision':'event_reused'}
            db.execute('INSERT INTO conflict_cases VALUES(?,?,?,?,?,?,?,?,?,?,?)',(x['id'],x['source'],x['generation'],x['seq'],prior['digest'],x['digest'],received,None,'open',None,None))
            return {'decision':'event_conflict'}
        gap=one(db,'SELECT * FROM sequence_gaps WHERE source=? AND source_generation=? AND seq=?',(x['source'],x['generation'],x['seq']))
        if x['seq']<=s['max_seq'] and not gap:return {'decision':'stale_sequence'}
        if x['seq']>s['max_seq']+1:
            db.executemany('INSERT INTO sequence_gaps VALUES(?,?,?,?,?,?)',[(s['id'],s['generation'],n,received,None,'open') for n in range(s['max_seq']+1,x['seq'])])
        if gap:db.execute("UPDATE sequence_gaps SET state='filled',filled_at=? WHERE source=? AND source_generation=? AND seq=?",(received,s['id'],s['generation'],x['seq']))
        db.execute('INSERT INTO audit_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(x['id'],s['id'],s['generation'],x['seq'],x['object_uid'],x['request_id'],x.get('parent_request'),x['actor'],x['at'],received,x['digest'],'accepted'))
        db.execute('UPDATE event_sources SET max_seq=MAX(max_seq,?) WHERE id=?',(x['seq'],s['id']))
        return {'decision':'gap_filled' if gap else 'accepted','open_gaps':one(db,"SELECT COUNT(*) n FROM sequence_gaps WHERE source=? AND source_generation=? AND state='open'",(s['id'],s['generation']))['n']}
    if op=='revoke':
        s=one(db,'SELECT * FROM event_sources WHERE id=?',(x['id'],))
        if not s or x['generation']<=s['generation']:return {'decision':'stale_revoke'}
        db.execute("UPDATE event_sources SET generation=?,state='revoked' WHERE id=?",(x['generation'],x['id']))
        return {'decision':'source_revoked'}
    if op=='resolve_conflict':
        case=one(db,'SELECT * FROM conflict_cases WHERE id=?',(x['id'],))
        if not case or case['state']!='open' or x.get('chosen_digest') not in (case['old_digest'],case['new_digest']) or not x.get('arbitrator'):
            return {'decision':'resolution_denied'}
        if x['chosen_digest']!=case['old_digest']:
            return {'decision':'replacement_not_materialized'}
        if x['at']<case['opened_at']:return {'decision':'resolution_before_conflict'}
        db.execute("UPDATE conflict_cases SET state='resolved',chosen_digest=?,arbitrator=?,resolved_at=? WHERE id=?",(x['chosen_digest'],x['arbitrator'],x['at'],x['id']))
        return {'decision':'conflict_resolved','chosen_digest':x['chosen_digest']}
    return {'decision':'unknown_operation'}
def run(db,x):return act(db,'capture',x,handle)
